#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/6/21 20:50
@Author : yange19940310@gmail.com
@File   : conftest.py
"""

import pytest
from sqlalchemy.orm import sessionmaker, scoped_session

from app.http.app import app as _app
from internal.extension.database_extension import db as _db


@pytest.fixture
def app():
    """获取Flask应用并返回"""
    _app.config["TESTING"] = True
    return _app


@pytest.fixture
def client(app):
    """获取Flask应用的测试应用，并返回"""
    with app.test_client() as client:
        yield client