import json
from uuid import uuid4

import pytest

from internal.core.mcp.mcp_approval import (
    McpApprovalError,
    McpApprovalRejectedError,
    McpApprovalService,
)


class FakeRedis:
    def __init__(self):
        self.values = {}

    def setex(self, key, ttl, value):
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)


def create_pending(service):
    return service.create_request(
        account_id=uuid4(),
        task_id=uuid4(),
        server_id=str(uuid4()),
        tool_name="delete_record",
        display_name="Delete record",
        arguments={"id": "1"},
        risk_level="high",
    )


def test_approve_once_unblocks_pending_request():
    service = McpApprovalService(FakeRedis())
    approval = create_pending(service)
    service.decide(
        approval.approval_id,
        approval.account_id,
        approval.task_id,
        "approve_once",
    )
    assert service.wait_for_decision(approval.approval_id) == "approve_once"


def test_session_approval_creates_task_scoped_grant():
    service = McpApprovalService(FakeRedis())
    approval = create_pending(service)
    service.decide(
        approval.approval_id,
        approval.account_id,
        approval.task_id,
        "approve_session",
    )
    assert service.has_session_grant(
        approval.task_id,
        approval.server_id,
        approval.tool_name,
    )


def test_rejection_prevents_execution():
    service = McpApprovalService(FakeRedis())
    approval = create_pending(service)
    service.decide(
        approval.approval_id,
        approval.account_id,
        approval.task_id,
        "reject",
    )
    with pytest.raises(McpApprovalRejectedError):
        service.wait_for_decision(approval.approval_id)


def test_other_account_cannot_decide_request():
    service = McpApprovalService(FakeRedis())
    approval = create_pending(service)
    with pytest.raises(McpApprovalError, match="无权"):
        service.decide(
            approval.approval_id,
            uuid4(),
            approval.task_id,
            "approve_once",
        )


def test_decision_is_single_use():
    redis = FakeRedis()
    service = McpApprovalService(redis)
    approval = create_pending(service)
    service.decide(
        approval.approval_id,
        approval.account_id,
        approval.task_id,
        "approve_once",
    )
    with pytest.raises(McpApprovalError, match="已处理"):
        service.decide(
            approval.approval_id,
            approval.account_id,
            approval.task_id,
            "reject",
        )
