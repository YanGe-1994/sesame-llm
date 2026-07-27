#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/5/12 14:09
@Author : yange19940310@gmail.com
@File   : config.py
"""
import os
from typing import Any

from .default_config import DEFAULT_CONFIG


def _get_env(key: str) -> Any:
    """从环境变量中获取配置项，如果找不到则返回默认值"""
    return os.getenv(key, DEFAULT_CONFIG.get(key))


def _get_bool_env(key: str) -> bool:
    """从环境变量中获取布尔值型的配置项，如果找不到则返回默认值"""
    value: str = _get_env(key)
    return value.lower() == "true" if value is not None else False


class Config:
    def __init__(self):
        # 关闭wtf的csrf保护
        self.WTF_CSRF_ENABLED = _get_bool_env("WTF_CSRF_ENABLED")

        # 配置数据库配置
        self.SQLALCHEMY_DATABASE_URI = _get_env("SQLALCHEMY_DATABASE_URI")
        self.SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_size": int(_get_env("SQLALCHEMY_POOL_SIZE")),
            "pool_recycle": int(_get_env("SQLALCHEMY_POOL_RECYCLE")),
             # 从连接池取连接前检测连接是否还活着
            "pool_pre_ping": True,
            # 连接池不足时允许额外创建的连接数
            "max_overflow": 10,
            # 获取连接最长等待时间
            "pool_timeout": 30,
            # 优先复用最近使用的连接
            "pool_use_lifo": True,
            "connect_args": {
                # 建立新连接的超时时间
                "connect_timeout": 10,
                # TCP Keepalive
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5,
                "application_name": "sesame-llm-web",
            },
        }
        self.SQLALCHEMY_ECHO = _get_bool_env("SQLALCHEMY_ECHO")

        # Redis配置
        self.REDIS_HOST = _get_env("REDIS_HOST")
        self.REDIS_PORT = _get_env("REDIS_PORT")
        self.REDIS_USERNAME = _get_env("REDIS_USERNAME")
        self.REDIS_PASSWORD = _get_env("REDIS_PASSWORD")
        self.REDIS_DB = _get_env("REDIS_DB")
        self.REDIS_USE_SSL = _get_bool_env("REDIS_USE_SSL")

        # Celery配置
        # 认证安全配置
        self.ACCESS_TOKEN_TTL_SECONDS = int(_get_env("ACCESS_TOKEN_TTL_SECONDS"))
        self.REFRESH_TOKEN_TTL_SECONDS = int(_get_env("REFRESH_TOKEN_TTL_SECONDS"))
        self.AUTH_COOKIE_SECURE = _get_bool_env("AUTH_COOKIE_SECURE")
        self.AUTH_COOKIE_SAMESITE = _get_env("AUTH_COOKIE_SAMESITE")
        self.FRONTEND_ORIGIN = _get_env("FRONTEND_ORIGIN")
        self.MCP_REQUIRE_HTTPS = _get_bool_env("MCP_REQUIRE_HTTPS")
        self.MCP_ALLOW_PRIVATE_NETWORKS = _get_bool_env("MCP_ALLOW_PRIVATE_NETWORKS")
        self.MCP_OUTBOUND_ALLOWED_PORTS = _get_env("MCP_OUTBOUND_ALLOWED_PORTS")
        self.MCP_OUTBOUND_HOST_ALLOWLIST = _get_env("MCP_OUTBOUND_HOST_ALLOWLIST")
        self.MCP_MAX_RESPONSE_BYTES = int(_get_env("MCP_MAX_RESPONSE_BYTES"))
        self.MCP_RATE_LIMIT_WINDOW_SECONDS = int(_get_env("MCP_RATE_LIMIT_WINDOW_SECONDS"))
        self.MCP_RATE_LIMIT_ACCOUNT = int(_get_env("MCP_RATE_LIMIT_ACCOUNT"))
        self.MCP_RATE_LIMIT_SERVER = int(_get_env("MCP_RATE_LIMIT_SERVER"))
        self.MCP_RATE_LIMIT_TOOL = int(_get_env("MCP_RATE_LIMIT_TOOL"))
        self.MCP_CIRCUIT_FAILURE_THRESHOLD = int(_get_env("MCP_CIRCUIT_FAILURE_THRESHOLD"))
        self.MCP_CIRCUIT_FAILURE_WINDOW_SECONDS = int(_get_env("MCP_CIRCUIT_FAILURE_WINDOW_SECONDS"))
        self.MCP_CIRCUIT_BASE_BACKOFF_SECONDS = int(_get_env("MCP_CIRCUIT_BASE_BACKOFF_SECONDS"))
        self.MCP_CIRCUIT_MAX_BACKOFF_SECONDS = int(_get_env("MCP_CIRCUIT_MAX_BACKOFF_SECONDS"))
        self.MCP_CIRCUIT_HALF_OPEN_TIMEOUT_SECONDS = int(_get_env("MCP_CIRCUIT_HALF_OPEN_TIMEOUT_SECONDS"))
        self.MCP_RESILIENCE_FAIL_OPEN = _get_bool_env("MCP_RESILIENCE_FAIL_OPEN")

        self.CELERY = {
            "broker_url": f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{int(_get_env('CELERY_BROKER_DB'))}",
            "result_backend": f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{int(_get_env('CELERY_RESULT_BACKEND_DB'))}",
            "task_ignore_result": _get_bool_env("CELERY_TASK_IGNORE_RESULT"),
            "result_expires": int(_get_env("CELERY_RESULT_EXPIRES")),
            "broker_connection_retry_on_startup": _get_bool_env(
                "CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP"),
            # Redis broker连接配置
            "broker_transport_options": {
                # socket建立连接超时
                "socket_connect_timeout": 10,

                # socket读取超时
                "socket_timeout": 30,

                # Redis超时时自动重试
                "retry_on_timeout": True,

                # 定期检查Redis连接健康状态
                "health_check_interval": 30,

                # 防止任务丢失
                "visibility_timeout": 3600,
            },

            # Redis result backend连接配置
            "result_backend_transport_options": {
                "socket_connect_timeout": 10,
                "socket_timeout": 30,
                "retry_on_timeout": True,
            },
        }