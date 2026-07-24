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

from internal.exception import NotFoundException
from internal.model import Account, App, DraftAppConfig, Dataset, ApiTool, ApiToolProvider
from internal.schema.app_schema import CreateAppReq, GetAppsWithPageReq, UpdateAppReq, UpdateDraftAppConfigReq
from pkg.paginator import Paginator
from pkg.sqlalchemy import SQLAlchemy
from .base_service import BaseService


DEFAULT_MODEL_CONFIG = {
    "provider": "dashscope",
    "model": "glm-5.2",
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
                    update_fields[model_field] = self._normalize_tools(field.data)
                elif req_field == "datasets":
                    update_fields[model_field] = self._normalize_datasets(field.data, account)
                else:
                    update_fields[model_field] = field.data
        if update_fields:
            self.update(draft_app_config, **update_fields)
        return draft_app_config

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

    @staticmethod
    def _normalize_tools(tools: list) -> list[dict]:
        """将前端展示结构统一转换为可持久化、可执行的工具引用。"""
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
            tool_key = (tool_type, str(provider_id), str(tool_id))
            if tool_key in tool_keys:
                continue
            tool_keys.add(tool_key)
            normalized_tools.append({
                "type": tool_type,
                "provider_id": str(provider_id),
                "tool_id": str(tool_id),
                "params": item.get("params") or tool.get("params") or {},
            })
        return normalized_tools[:5]

    def create_draft_app_config(self, app_id: UUID) -> DraftAppConfig:
        return self.create(DraftAppConfig, **self._default_draft_app_config_values(app_id))

    def _hydrate_draft_app_config(self, draft_app_config: DraftAppConfig, account: Account) -> DraftAppConfig:
        draft_app_config.hydrated_datasets = self._hydrate_datasets(draft_app_config.datasets or [], account)
        draft_app_config.hydrated_tools = self._hydrate_tools(draft_app_config.tools or [], account)
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
                hydrated_tools.append(draft_tool)
                continue
            if tool_type == "builtin_tool":
                provider = self.builtin_provider_manager.get_provider(provider_id)
                if provider is None:
                    hydrated_tools.append(draft_tool)
                    continue
                tool_entity = provider.get_tool_entity(tool_name)
                if tool_entity is None:
                    hydrated_tools.append(draft_tool)
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
                    hydrated_tools.append(draft_tool)
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
