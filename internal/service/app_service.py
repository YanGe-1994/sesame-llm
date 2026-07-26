#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/5/13 10:23
@Author : yange19940310@gmail.com
@File   : app_service.py
"""
from dataclasses import dataclass
from uuid import UUID

from injector import inject
from sqlalchemy import desc

from internal.core.tools.builtin_tools.providers import BuiltinProviderManager

from internal.exception import FailException, NotFoundException
from internal.model import Account, App, AppConfigVersion, DraftAppConfig, Dataset, ApiTool, ApiToolProvider, McpServer, McpTool
from internal.schema.app_schema import CreateAppReq, GetAppsWithPageReq, UpdateAppReq, UpdateDraftAppConfigReq
from pkg.paginator import Paginator
from pkg.sqlalchemy import SQLAlchemy
from .base_service import BaseService


DEFAULT_MODEL_CONFIG = {
    "provider": "dashscope",
    "model": "qwen3.7-max-2026-06-08",
    "parameters": {"temperature": 0.7},
}
DEFAULT_RETRIEVAL_CONFIG = {"retrieval_strategy": "semantic", "k": 4, "score": 0.5}
DEFAULT_REVIEW_CONFIG = {
    "enable": False,
    "keywords": [],
    "inputs_config": {"enable": False, "preset_response": ""},
    "outputs_config": {"enable": False},
}


@inject
@dataclass
class AppService(BaseService):
    """应用服务逻辑"""
    db: SQLAlchemy
    builtin_provider_manager: BuiltinProviderManager

    def create_app(self, req: CreateAppReq, account: Account) -> App:
        account_id = account.id
        with self.db.auto_commit():
            app = App(
                account_id=account_id,
                name=req.name.data,
                icon=req.icon.data or "",
                description=req.description.data or "",
                status="draft",
            )
            self.db.session.add(app)
            self.db.session.flush()
            self.db.session.add(self._build_default_draft_app_config(app.id))
        return app

    def get_app(self, app_id: UUID, account: Account) -> App:
        app = self.db.session.query(App).filter(
            App.id == app_id,
            App.account_id == account.id,
        ).one_or_none()
        if app is None:
            raise NotFoundException("该应用不存在")
        app.draft_app_config = self._get_draft_app_config(app.id)
        return app

    def update_app(self, app_id: UUID, req: UpdateAppReq, account: Account) -> App:
        app = self.get_app(app_id, account)
        self.update(
            app,
            name=req.name.data,
            icon=req.icon.data or "",
            description=req.description.data or "",
        )
        return app

    def delete_app(self, app_id: UUID, account: Account) -> App:
        app = self.get_app(app_id, account)
        with self.db.auto_commit():
            self.db.session.query(DraftAppConfig).filter(DraftAppConfig.app_id == app_id).delete()
            self.db.session.query(AppConfigVersion).filter(AppConfigVersion.app_id == app_id).delete()
            self.db.session.delete(app)
        return app

    def get_apps_with_page(self, req: GetAppsWithPageReq, account: Account) -> tuple[list[App], Paginator]:
        paginator = Paginator(db=self.db, req=req)
        filters = [App.account_id == account.id]
        if req.search_word.data:
            filters.append(App.name.ilike(f"%{req.search_word.data}%"))
        apps = paginator.paginate(
            self.db.session.query(App).filter(*filters).order_by(desc("created_at"))
        )
        for app in apps:
            app.draft_app_config = self._get_draft_app_config(app.id)
        return apps, paginator

    def get_draft_app_config(self, app_id: UUID, account: Account) -> DraftAppConfig:
        self.get_app(app_id, account)
        draft_app_config = self._get_draft_app_config(app_id)
        if draft_app_config is None:
            draft_app_config = self.create_draft_app_config(app_id)
        draft_app_config = self._reconcile_draft_references(draft_app_config, account)
        return self._hydrate_draft_app_config(draft_app_config, account)

    def update_draft_app_config(
            self,
            app_id: UUID,
            req: UpdateDraftAppConfigReq,
            account: Account,
            submitted_fields: set[str] | None = None,
    ) -> DraftAppConfig:
        draft_app_config = self.get_draft_app_config(app_id, account)
        update_fields = {}
        field_map = {
            "model": "model_config",
            "dialog_round": "dialog_round",
            "preset_prompt": "preset_prompt",
            "tools": "tools",
            "mcp_servers": "mcp_servers",
            "workflows": "workflows",
            "datasets": "datasets",
            "retrieval_config": "retrieval_config",
            "long_term_memory": "long_term_memory",
            "opening_statement": "opening_statement",
            "opening_questions": "opening_questions",
            "speech_to_text": "speech_to_text",
            "text_to_speech": "text_to_speech",
            "suggested_after_answer": "suggested_after_answer",
            "review_config": "review_config",
        }
        for req_field, model_field in field_map.items():
            if submitted_fields is not None and req_field not in submitted_fields:
                continue
            field = getattr(req, req_field)
            if field.data is not None:
                if req_field == "tools":
                    update_fields[model_field] = self._normalize_tools(field.data, account)
                elif req_field == "datasets":
                    update_fields[model_field] = self._normalize_datasets(field.data, account)
                elif req_field == "mcp_servers":
                    update_fields[model_field] = self._normalize_mcp_servers(field.data, account)
                else:
                    update_fields[model_field] = field.data
        if update_fields:
            self.update(draft_app_config, **update_fields)
        draft_app_config = self._reconcile_draft_references(draft_app_config, account)
        return self._hydrate_draft_app_config(draft_app_config, account)

    def _normalize_datasets(self, datasets: list, account: Account) -> list[str]:
        """只保留属于当前账号的有效知识库引用。"""
        dataset_ids = []
        for item in datasets or []:
            raw_id = item.get("id") if isinstance(item, dict) else item
            try:
                dataset_id = UUID(str(raw_id))
            except (TypeError, ValueError):
                continue
            if dataset_id not in dataset_ids:
                dataset_ids.append(dataset_id)
        if not dataset_ids:
            return []
        owned_ids = {
            dataset.id
            for dataset in self.db.session.query(Dataset.id).filter(
                Dataset.id.in_(dataset_ids),
                Dataset.account_id == account.id,
            ).all()
        }
        return [str(dataset_id) for dataset_id in dataset_ids if dataset_id in owned_ids][:5]

    def _normalize_tools(self, tools: list, account: Account) -> list[dict]:
        """Only persist tools that are still available to the current account."""
        normalized_tools = []
        tool_keys = set()
        for item in tools or []:
            if not isinstance(item, dict):
                continue
            provider = item.get("provider") or {}
            tool = item.get("tool") or {}
            tool_type = item.get("type")
            provider_id = item.get("provider_id") or provider.get("id") or provider.get("name")
            tool_id = item.get("tool_id") or tool.get("name") or tool.get("id")
            if tool_type not in {"builtin_tool", "api_tool"} or not provider_id or not tool_id:
                continue
            if tool_type == "builtin_tool":
                builtin_provider = self.builtin_provider_manager.get_provider(str(provider_id))
                tool_entity = builtin_provider.get_tool_entity(str(tool_id)) if builtin_provider else None
                if tool_entity is None:
                    continue
                provider_id = builtin_provider.provider_entity.name
                tool_id = tool_entity.name
            else:
                try:
                    api_provider_id = UUID(str(provider_id))
                except (TypeError, ValueError):
                    continue
                api_tool = self.db.session.query(ApiTool).join(
                    ApiToolProvider,
                    ApiTool.provider_id == ApiToolProvider.id,
                ).filter(
                    ApiTool.provider_id == api_provider_id,
                    ApiTool.name == str(tool_id),
                    ApiTool.account_id == account.id,
                    ApiToolProvider.account_id == account.id,
                ).one_or_none()
                if api_tool is None:
                    continue
                provider_id = str(api_tool.provider_id)
                tool_id = api_tool.name
            tool_key = (tool_type, str(provider_id), str(tool_id))
            if tool_key in tool_keys:
                continue
            tool_keys.add(tool_key)
            params = item.get("params") or tool.get("params") or {}
            normalized_tools.append({
                "type": tool_type,
                "provider_id": str(provider_id),
                "tool_id": str(tool_id),
                "params": params if isinstance(params, dict) else {},
            })
        return normalized_tools[:5]

    def create_draft_app_config(self, app_id: UUID) -> DraftAppConfig:
        return self.create(DraftAppConfig, **self._default_draft_app_config_values(app_id))

    def _hydrate_draft_app_config(self, draft_app_config: DraftAppConfig, account: Account) -> DraftAppConfig:
        draft_app_config.hydrated_datasets = self._hydrate_datasets(draft_app_config.datasets or [], account)
        draft_app_config.hydrated_tools = self._hydrate_tools(draft_app_config.tools or [], account)
        draft_app_config.hydrated_mcp_servers = self._hydrate_mcp_servers(draft_app_config.mcp_servers or [], account)
        return draft_app_config

    def _reconcile_draft_references(self, draft_app_config: DraftAppConfig, account: Account) -> DraftAppConfig:
        """Remove deleted, inaccessible, or invalid tool and dataset references from a draft."""
        current_tools = draft_app_config.tools or []
        current_datasets = draft_app_config.datasets or []
        valid_tools = self._normalize_tools(current_tools, account)
        valid_datasets = self._normalize_datasets(current_datasets, account)
        update_fields = {}
        if valid_tools != current_tools:
            update_fields["tools"] = valid_tools
        if valid_datasets != current_datasets:
            update_fields["datasets"] = valid_datasets
        if update_fields:
            self.update(draft_app_config, **update_fields)
        return draft_app_config

    def _hydrate_datasets(self, draft_datasets: list, account: Account) -> list[dict]:
        dataset_ids = [item.get("id") if isinstance(item, dict) else item for item in draft_datasets]
        dataset_ids = [dataset_id for dataset_id in dataset_ids if dataset_id]
        if len(dataset_ids) == 0:
            return []
        datasets = self.db.session.query(Dataset).filter(
            Dataset.id.in_(dataset_ids),
            Dataset.account_id == account.id,
        ).all()
        dataset_map = {str(dataset.id): dataset for dataset in datasets}
        return [
            {
                "id": str(dataset.id),
                "name": dataset.name,
                "icon": dataset.icon,
                "description": dataset.description,
            }
            for dataset_id in dataset_ids
            if (dataset := dataset_map.get(str(dataset_id))) is not None
        ]

    def _hydrate_tools(self, draft_tools: list[dict], account: Account) -> list[dict]:
        hydrated_tools = []
        for draft_tool in draft_tools:
            if not isinstance(draft_tool, dict):
                continue
            tool_type = draft_tool.get("type")
            provider_id = draft_tool.get("provider_id") or (draft_tool.get("provider") or {}).get("id")
            tool_name = draft_tool.get("tool_id") or (draft_tool.get("tool") or {}).get("name")
            params = draft_tool.get("params") or (draft_tool.get("tool") or {}).get("params") or {}
            if not provider_id or not tool_name:
                continue
            if tool_type == "builtin_tool":
                provider = self.builtin_provider_manager.get_provider(provider_id)
                if provider is None:
                    continue
                tool_entity = provider.get_tool_entity(tool_name)
                if tool_entity is None:
                    continue
                provider_entity = provider.provider_entity
                hydrated_tools.append({
                    "type": "builtin_tool",
                    "provider_id": provider_entity.name,
                    "tool_id": tool_entity.name,
                    "params": params,
                    "provider": {
                        "id": provider_entity.name,
                        "name": provider_entity.name,
                        "label": provider_entity.label,
                        "icon": provider_entity.icon,
                        "description": provider_entity.description,
                    },
                    "tool": {
                        "id": tool_entity.name,
                        "name": tool_entity.name,
                        "label": tool_entity.label,
                        "description": tool_entity.description,
                        "params": params,
                    },
                })
            elif tool_type == "api_tool":
                api_tool = self.db.session.query(ApiTool).join(
                    ApiToolProvider,
                    ApiTool.provider_id == ApiToolProvider.id,
                ).filter(
                    ApiTool.provider_id == provider_id,
                    ApiTool.name == tool_name,
                    ApiTool.account_id == account.id,
                    ApiToolProvider.account_id == account.id,
                ).one_or_none()
                if api_tool is None:
                    continue
                provider = api_tool.provider
                hydrated_tools.append({
                    "type": "api_tool",
                    "provider_id": str(provider.id),
                    "tool_id": api_tool.name,
                    "params": params,
                    "provider": {
                        "id": str(provider.id),
                        "name": provider.name,
                        "label": provider.name,
                        "icon": provider.icon,
                        "description": provider.description,
                    },
                    "tool": {
                        "id": str(api_tool.id),
                        "name": api_tool.name,
                        "label": api_tool.name,
                        "description": api_tool.description,
                        "params": params,
                    },
                })
        return hydrated_tools

    def _normalize_mcp_servers(self, bindings: list, account: Account) -> list[dict]:
        """只保存当前账号下状态正常、工具可用的 MCP 引用。"""
        normalized = []
        seen_server_ids = set()
        for binding in bindings or []:
            if not isinstance(binding, dict):
                continue
            try:
                server_id = UUID(str(binding.get("server_id")))
            except (TypeError, ValueError):
                continue
            if server_id in seen_server_ids or len(normalized) >= 5:
                continue
            server = self.db.session.query(McpServer).filter(
                McpServer.id == server_id,
                McpServer.account_id == account.id,
                McpServer.status == "active",
            ).one_or_none()
            if server is None:
                continue
            requested_names = []
            for name in binding.get("enabled_tools") or []:
                name = str(name).strip()
                if name and name not in requested_names:
                    requested_names.append(name)
            if not requested_names:
                continue
            tools = self.db.session.query(McpTool).filter(
                McpTool.server_id == server.id,
                McpTool.tool_name.in_(requested_names),
                McpTool.enabled.is_(True),
                McpTool.is_available.is_(True),
            ).all()
            tool_map = {tool.tool_name: tool for tool in tools}
            valid_names = [name for name in requested_names if name in tool_map][:20]
            if not valid_names:
                continue
            approval_policy = binding.get("approval_policy")
            if approval_policy not in {"auto", "always_ask"}:
                approval_policy = "auto"
            normalized.append({
                "server_id": str(server.id),
                "enabled_tools": valid_names,
                "tool_versions": {name: tool_map[name].schema_hash for name in valid_names},
                "tool_overrides": binding.get("tool_overrides") if isinstance(binding.get("tool_overrides"), dict) else {},
                "approval_policy": approval_policy,
            })
            seen_server_ids.add(server_id)
        return normalized

    def _hydrate_mcp_servers(self, bindings: list[dict], account: Account) -> list[dict]:
        """回填 MCP 服务与工具名称，并保留失效引用以便前端提示。"""
        hydrated = []
        for binding in bindings or []:
            if not isinstance(binding, dict):
                continue
            server_id = str(binding.get("server_id") or "")
            tool_names = [str(name) for name in binding.get("enabled_tools") or [] if name]
            try:
                server_uuid = UUID(server_id)
            except (TypeError, ValueError):
                server_uuid = None
            server = self.db.session.query(McpServer).filter(
                McpServer.id == server_uuid,
                McpServer.account_id == account.id,
            ).one_or_none() if server_uuid else None
            if server is None:
                hydrated.append({
                    **binding,
                    "server": {"id": server_id, "name": "已删除的 MCP 服务", "status": "missing", "is_available": False},
                    "tools": [
                        {"name": name, "display_name": name, "is_available": False, "schema_changed": False}
                        for name in tool_names
                    ],
                    "is_available": False,
                })
                continue
            tools = self.db.session.query(McpTool).filter(
                McpTool.server_id == server.id,
                McpTool.tool_name.in_(tool_names),
            ).all() if tool_names else []
            tool_map = {tool.tool_name: tool for tool in tools}
            versions = binding.get("tool_versions") or {}
            hydrated_tools = []
            for name in tool_names:
                tool = tool_map.get(name)
                hydrated_tools.append({
                    "id": str(tool.id) if tool else "",
                    "name": name,
                    "display_name": (tool.display_name or tool.tool_name) if tool else name,
                    "description": tool.description if tool else "",
                    "is_available": bool(tool and tool.enabled and tool.is_available and server.status == "active"),
                    "schema_changed": bool(tool and versions.get(name) and versions.get(name) != tool.schema_hash),
                    "schema_hash": tool.schema_hash if tool else "",
                })
            hydrated.append({
                **binding,
                "server": {
                    "id": str(server.id),
                    "name": server.name,
                    "description": server.description,
                    "icon": server.icon,
                    "status": server.status,
                    "is_available": server.status == "active",
                },
                "tools": hydrated_tools,
                "is_available": server.status == "active" and all(tool["is_available"] for tool in hydrated_tools),
            })
        return hydrated
    def publish_app(self, app_id: UUID, account: Account) -> AppConfigVersion:
        app = self.get_app(app_id, account)
        draft = self._get_draft_app_config(app_id)
        if draft is None:
            raise NotFoundException("应用草稿配置不存在")
        issues = self.validate_mcp_snapshot(draft.mcp_servers or [], account)
        if issues:
            raise FailException("MCP 发布校验失败：" + "；".join(issues))
        config = self._snapshot_draft_config(draft)
        config["mcp_servers"] = self._build_mcp_publish_snapshot(
            draft.mcp_servers or [], account,
        )
        latest_version = self.db.session.query(AppConfigVersion.version).filter(
            AppConfigVersion.app_id == app_id,
        ).order_by(desc(AppConfigVersion.version)).first()
        version = int(latest_version[0]) + 1 if latest_version else 1
        with self.db.auto_commit():
            published = AppConfigVersion(
                app_id=app_id,
                version=version,
                config=config,
                mcp_servers=config.get("mcp_servers") or [],
            )
            self.db.session.add(published)
            app.status = "published"
        return published

    def cancel_publish(self, app_id: UUID, account: Account) -> App:
        app = self.get_app(app_id, account)
        return self.update(app, status="draft")

    def get_publish_histories(self, app_id: UUID, account: Account, req):
        self.get_app(app_id, account)
        paginator = Paginator(self.db, req)
        versions = paginator.paginate(
            self.db.session.query(AppConfigVersion).filter(
                AppConfigVersion.app_id == app_id,
            ).order_by(desc(AppConfigVersion.version))
        )
        return versions, paginator

    def fallback_version_to_draft(
            self, app_id: UUID, version_id: UUID, account: Account,
    ) -> DraftAppConfig:
        self.get_app(app_id, account)
        version = self.db.session.query(AppConfigVersion).filter(
            AppConfigVersion.id == version_id,
            AppConfigVersion.app_id == app_id,
        ).one_or_none()
        if version is None:
            raise NotFoundException("发布版本不存在")
        draft = self._get_draft_app_config(app_id)
        if draft is None:
            draft = self.create_draft_app_config(app_id)
        config = version.config or {}
        with self.db.auto_commit():
            for field in self._snapshot_fields():
                if field in config:
                    setattr(draft, field, config[field])
        return self._hydrate_draft_app_config(draft, account)

    def get_published_config(self, app_id: UUID, account: Account) -> dict:
        app = self.get_app(app_id, account)
        if app.status != "published":
            raise NotFoundException("应用尚未发布或已取消发布")
        version = self.db.session.query(AppConfigVersion).filter(
            AppConfigVersion.app_id == app_id,
        ).order_by(desc(AppConfigVersion.version)).first()
        if version is None:
            raise NotFoundException("应用发布版本不存在")
        issues = self.validate_mcp_snapshot(version.mcp_servers or [], account)
        return {
            "id": str(version.id),
            "app_id": str(version.app_id),
            "version": version.version,
            "config": version.config or {},
            "mcp_servers": version.mcp_servers or [],
            "runtime_ready": len(issues) == 0,
            "runtime_issues": issues,
            "created_at": int(version.created_at.timestamp()),
        }

    def _build_mcp_publish_snapshot(self, bindings: list[dict], account: Account) -> list[dict]:
        snapshots = []
        for binding in bindings or []:
            server_id = str(binding.get("server_id") or "")
            try:
                server_uuid = UUID(server_id)
            except (TypeError, ValueError):
                continue
            server = self.db.session.query(McpServer).filter(
                McpServer.id == server_uuid,
                McpServer.account_id == account.id,
            ).one_or_none()
            if server is None:
                continue
            tool_names = [str(name) for name in binding.get("enabled_tools") or [] if name]
            tools = self.db.session.query(McpTool).filter(
                McpTool.server_id == server.id,
                McpTool.tool_name.in_(tool_names),
            ).all() if tool_names else []
            tool_map = {tool.tool_name: tool for tool in tools}
            snapshots.append({
                **binding,
                "server_name": server.name,
                "server_transport": server.transport,
                "auth_type": server.auth_type,
                "tool_snapshots": [
                    {
                        "name": name,
                        "display_name": tool_map[name].display_name or name,
                        "schema_hash": tool_map[name].schema_hash,
                        "risk_level": tool_map[name].risk_level,
                        "approval_mode": tool_map[name].approval_mode,
                    }
                    for name in tool_names if name in tool_map
                ],
            })
        return snapshots
    def validate_mcp_snapshot(self, bindings: list[dict], account: Account) -> list[str]:
        issues = []
        for binding in bindings or []:
            server_id = str(binding.get("server_id") or "")
            try:
                server_uuid = UUID(server_id)
            except (TypeError, ValueError):
                issues.append("MCP 服务引用无效")
                continue
            server = self.db.session.query(McpServer).filter(
                McpServer.id == server_uuid,
                McpServer.account_id == account.id,
            ).one_or_none()
            if server is None:
                issues.append(f"MCP 服务 {server_id} 已删除")
                continue
            if server.status != "active":
                issues.append(f"MCP 服务 {server.name} 当前不可用")
                continue
            if server.auth_type == "oauth2" and not server.encrypted_access_token:
                issues.append(f"MCP 服务 {server.name} 尚未完成 OAuth 授权")
            enabled_names = [str(name) for name in binding.get("enabled_tools") or [] if name]
            versions = binding.get("tool_versions") or {}
            tools = self.db.session.query(McpTool).filter(
                McpTool.server_id == server.id,
                McpTool.tool_name.in_(enabled_names),
            ).all() if enabled_names else []
            tool_map = {tool.tool_name: tool for tool in tools}
            for tool_name in enabled_names:
                tool = tool_map.get(tool_name)
                if tool is None or not tool.enabled or not tool.is_available:
                    issues.append(f"MCP 工具 {server.name}/{tool_name} 不可用")
                elif versions.get(tool_name) != tool.schema_hash:
                    issues.append(f"MCP 工具 {server.name}/{tool_name} Schema 已变化，请重新绑定并发布")
        return issues

    @staticmethod
    def _snapshot_fields() -> tuple[str, ...]:
        return (
            "model_config", "dialog_round", "preset_prompt", "tools", "mcp_servers",
            "workflows", "datasets", "retrieval_config", "long_term_memory",
            "opening_statement", "opening_questions", "speech_to_text", "text_to_speech",
            "suggested_after_answer", "review_config",
        )

    @classmethod
    def _snapshot_draft_config(cls, draft: DraftAppConfig) -> dict:
        return {field: getattr(draft, field) for field in cls._snapshot_fields()}
    def _get_draft_app_config(self, app_id: UUID) -> DraftAppConfig | None:
        return self.db.session.query(DraftAppConfig).filter(DraftAppConfig.app_id == app_id).one_or_none()

    def _build_default_draft_app_config(self, app_id: UUID) -> DraftAppConfig:
        return DraftAppConfig(**self._default_draft_app_config_values(app_id))

    def _default_draft_app_config_values(self, app_id: UUID) -> dict:
        return {
            "app_id": app_id,
            "model_config": DEFAULT_MODEL_CONFIG,
            "dialog_round": 3,
            "preset_prompt": "",
            "tools": [],
            "mcp_servers": [],
            "workflows": [],
            "datasets": [],
            "retrieval_config": DEFAULT_RETRIEVAL_CONFIG,
            "long_term_memory": {"enable": True},
            "opening_statement": "",
            "opening_questions": [],
            "speech_to_text": {"enable": False},
            "text_to_speech": {"enable": False, "voice": "", "auto_play": False},
            "suggested_after_answer": {"enable": True},
            "review_config": DEFAULT_REVIEW_CONFIG,
        }
