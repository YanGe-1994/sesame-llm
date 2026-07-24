#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/7/23
@Author : yange19940310@gmail.com
@File   : ai_handler.py
"""
import json
import uuid
from dataclasses import dataclass
from typing import Generator

from flask import request
from flask_login import current_user, login_required
from injector import inject

from internal.service import ConversationService
from pkg.response import compact_generate_response, success_json


@inject
@dataclass
class AIHandler:
    """AI辅助能力控制器"""
    conversation_service: ConversationService

    @login_required
    def generate_suggested_questions(self):
        message_id = (request.get_json(silent=True) or {}).get("message_id", "")
        if message_id == "":
            return success_json([])
        questions = self.conversation_service.generate_suggested_questions_by_message(message_id, current_user)
        return success_json(questions)

    @login_required
    def optimize_prompt(self):
        prompt = (request.get_json(silent=True) or {}).get("prompt", "")

        def stream_event_response() -> Generator:
            data = {
                "id": str(uuid.uuid4()),
                "optimize_prompt": prompt,
            }
            yield f"event: optimize_prompt\ndata: {json.dumps(data)}\n\n"

        return compact_generate_response(stream_event_response())
