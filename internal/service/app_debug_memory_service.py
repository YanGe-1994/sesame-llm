#!/usr/bin/env python
# -*- coding: utf-8 -*-
import fcntl
import json
import os
import tempfile
import uuid
from datetime import datetime

from flask import current_app
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate


class AppDebugMemoryService:
    def load(self, appid: uuid.UUID) -> dict:
        return self._read_state(self._memory_file_path(appid), str(appid))

    def build_prompt_messages(self, state: dict, query: str) -> list[tuple[str, str]]:
        messages: list[tuple[str, str]] = [
            (
                "system",
                "你是一个幽默的ai工具，请用幽默的方式回答用户的问题。",
            )
        ]
        summary = state.get("summary", "").strip()
        if summary:
            messages.append(
                (
                    "system",
                    f"以下是此前对话的摘要，请作为上下文参考，并优先遵循最近几轮对话：\n{summary}",
                )
            )
        for turn in self._normalize_recent_turns(state.get("recent_turns", [])):
            role = "human" if turn["role"] == "user" else "ai"
            messages.append((role, turn["content"]))
        messages.append(("human", query))
        return messages

    def append_and_compact(self, appid: uuid.UUID, query: str, answer: str, llm) -> None:
        appid_str = str(appid)
        path = self._memory_file_path(appid)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        lock_path = f"{path}.lock"

        with open(lock_path, "a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            state = self._read_state(path, appid_str)
            now = datetime.utcnow().isoformat()
            recent_turns = self._normalize_recent_turns(state.get("recent_turns", []))
            recent_turns.append(self._build_turn("user", query, now))
            recent_turns.append(self._build_turn("assistant", answer, now))
            state["recent_turns"] = recent_turns
            compacted_state = self._compact_state(state, llm)
            compacted_state["appid"] = appid_str
            compacted_state["updated_at"] = now
            compacted_state["version"] = 1
            self._write_state(path, compacted_state)

    def _compact_state(self, state: dict, llm) -> dict:
        max_rounds = current_app.config["DEBUG_MEMORY_MAX_ROUNDS"]
        recent_turns = self._normalize_recent_turns(state.get("recent_turns", []))
        max_messages = max_rounds * 2
        if len(recent_turns) <= max_messages:
            state["recent_turns"] = recent_turns
            state["summary"] = state.get("summary", "").strip()
            return state

        older_turns = recent_turns[:-max_messages]
        state["summary"] = self._summarize_turns(state.get("summary", ""), older_turns, llm)
        state["recent_turns"] = recent_turns[-max_messages:]
        return state

    def _summarize_turns(self, existing_summary: str, turns: list[dict], llm) -> str:
        conversation = self._format_turns(turns)
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你负责压缩多轮对话上下文。保留用户目标、已确认事实、关键偏好和未解决问题，忽略无关寒暄。输出简洁中文摘要，不要分点，控制在300字以内。",
                ),
                (
                    "human",
                    "已有摘要：\n{summary}\n\n需要压缩的新增对话：\n{conversation}\n\n请生成新的整合摘要。",
                ),
            ]
        )
        chain = prompt | llm | StrOutputParser()
        return chain.invoke(
            {
                "summary": existing_summary.strip() or "无",
                "conversation": conversation,
            }
        ).strip()

    def _format_turns(self, turns: list[dict]) -> str:
        lines: list[str] = []
        for turn in turns:
            speaker = "用户" if turn["role"] == "user" else "助手"
            lines.append(f"{speaker}: {turn['content']}")
        return "\n".join(lines)

    def _normalize_recent_turns(self, turns) -> list[dict]:
        if not isinstance(turns, list):
            return []

        normalized_turns: list[dict] = []
        pending_user = None
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            role = turn.get("role")
            content = turn.get("content")
            ts = turn.get("ts")
            if role not in {"user", "assistant"} or not isinstance(content, str):
                continue
            normalized_turn = {
                "role": role,
                "content": content,
                "ts": ts if isinstance(ts, str) else "",
            }
            if role == "user":
                pending_user = normalized_turn
                continue
            if pending_user is None:
                continue
            normalized_turns.append(pending_user)
            normalized_turns.append(normalized_turn)
            pending_user = None
        return normalized_turns

    def _read_state(self, path: str, appid: str) -> dict:
        if not os.path.exists(path):
            return self._empty_state(appid)
        try:
            with open(path, "r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return self._empty_state(appid)
        return self._coerce_state(payload, appid)

    def _write_state(self, path: str, state: dict) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(state, file, ensure_ascii=False, indent=2)
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def _coerce_state(self, payload, appid: str) -> dict:
        if not isinstance(payload, dict):
            return self._empty_state(appid)
        summary = payload.get("summary", "")
        updated_at = payload.get("updated_at", "")
        return {
            "appid": appid,
            "summary": summary.strip() if isinstance(summary, str) else "",
            "recent_turns": self._normalize_recent_turns(payload.get("recent_turns", [])),
            "updated_at": updated_at if isinstance(updated_at, str) else "",
            "version": 1,
        }

    def _memory_file_path(self, appid: uuid.UUID) -> str:
        return os.path.join(current_app.config["DEBUG_MEMORY_DIR"], f"{appid}.json")

    def _empty_state(self, appid: str) -> dict:
        return {
            "appid": appid,
            "summary": "",
            "recent_turns": [],
            "updated_at": "",
            "version": 1,
        }

    def _build_turn(self, role: str, content: str, ts: str) -> dict:
        return {
            "role": role,
            "content": content,
            "ts": ts,
        }