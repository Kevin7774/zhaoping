from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.schemas.common import CamelModel

OutreachStrategyTag = Literal["场景叙事类", "硬核技术类"]


class OutreachDraftRequest(CamelModel):
    project_id: str
    job_id: str
    candidate_id: str
    segment_id: str | None = None
    strategy_tag: OutreachStrategyTag | None = None


class OutreachDraftPatchRequest(CamelModel):
    subject: str | None = None
    body: str | None = None
    strategy_tag: OutreachStrategyTag | None = None


class OutreachSendRequest(CamelModel):
    draft_id: str
    decision: Literal["approve", "edit", "reject"] = "approve"
    simulate: bool = True


class OutreachDraftResponse(CamelModel):
    draft_id: str
    project_id: str
    job_id: str
    candidate_id: str
    segment_id: str | None = None
    subject: str
    body: str
    status: str
    strategy_tag: OutreachStrategyTag | None = None
    created_by_user_id: str | None = None
    backend_generated: bool = True
    created_at: datetime
    updated_at: datetime


class OutreachHistoryRecord(CamelModel):
    history_id: str
    project_id: str
    job_id: str | None = None
    candidate_id: str | None = None
    draft_id: str | None = None
    segment_id: str | None = None
    email: str | None = None
    sender_email: str | None = None
    sent_by_user_id: str | None = None
    strategy_tag: OutreachStrategyTag | None = None
    subject: str
    body: str
    status: str
    delivery_mode: str
    provider_status: str | None = None
    created_at: datetime


class OutreachHistoryResponse(CamelModel):
    items: list[OutreachHistoryRecord]
