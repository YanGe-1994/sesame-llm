#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/7/5 20:41
@Author : yange19940310@gmail.com
@File   : rag_task.py
"""
from celery import shared_task, chain
from internal.lib.serializer.serializer import serialize_docs, deserialize_docs
from internal.model import Document

@shared_task
def process_single_document_task(document_id: str):

    chain(
        parsing_task.s(document_id),
        splitting_task.s(),
        indexing_task.s(),
        completed_task.s()
    ).apply_async()

@shared_task
def parsing_task(document_id: str):
    from app.http.module import injector
    from internal.service.indexing_service import IndexingService

    service = injector.get(IndexingService)
    # service = indexing_service()
    document = service.get(Document, document_id)

    service.update(document, status="PARSING")

    lc_documents = service.parsing(document)

    return {
        "document_id": document_id,
        "lc_documents": serialize_docs(lc_documents)
    }

@shared_task
def splitting_task(payload):
    from app.http.module import injector
    from internal.service.indexing_service import IndexingService

    service = injector.get(IndexingService)

    document = service.get(Document, payload["document_id"])
    lc_documents = deserialize_docs(payload["lc_documents"])

    lc_segments = service.splitting(document, lc_documents)

    return {
        "document_id": payload["document_id"],
        "lc_segments": serialize_docs(lc_segments)
    }

@shared_task
def indexing_task(payload):
    from app.http.module import injector
    from internal.service.indexing_service import IndexingService

    service = injector.get(IndexingService)

    document = service.get(Document, payload["document_id"])
    lc_segments = deserialize_docs(payload["lc_segments"])

    service.indexing(document, lc_segments)

    return payload

@shared_task
def completed_task(payload):
    from app.http.module import injector
    from internal.service.indexing_service import IndexingService

    service = injector.get(IndexingService)

    document = service.get(Document, payload["document_id"])
    lc_segments = deserialize_docs(payload["lc_segments"])

    service.completed(document, lc_segments)

    return "done"