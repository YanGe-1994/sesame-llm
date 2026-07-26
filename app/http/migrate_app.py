#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""只初始化数据库扩展的 Flask-Migrate 入口。

完整 HTTP 应用会在导入路由时初始化 Weaviate 等外部服务，这会让数据库迁移
依赖所有运行时服务都处于在线状态。迁移入口仅加载数据库配置和迁移扩展。
"""

import dotenv
from flask import Flask

from config import Config
from internal.extension.database_extension import db
from internal.extension.migrate_extension import migrate


dotenv.load_dotenv()

app = Flask(__name__)
app.config.from_object(Config())

db.init_app(app)
migrate.init_app(app, db, directory="internal/migration")
