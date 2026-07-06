#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/7/5 20:42
@Author : yange19940310@gmail.com
@File   : serializer.py
"""
import json
from langchain_core.documents import Document


def serialize_docs(docs):
    return json.dumps([
        {
            "page_content": d.page_content,
            "metadata": d.metadata
        }
        for d in docs
    ], ensure_ascii=False)


def deserialize_docs(data):
    items = json.loads(data)
    return [
        Document(page_content=i["page_content"], metadata=i["metadata"])
        for i in items
    ]