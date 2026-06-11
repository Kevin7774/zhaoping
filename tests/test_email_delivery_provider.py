from __future__ import annotations

import json
from typing import Any

import pytest

from app.core.router import ServiceRouter
from app.providers.outreach import ResendCompliantEmailProvider


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.status_code = 200
        self.text = json.dumps(payload)

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def _provider(tmp_path) -> ResendCompliantEmailProvider:
    return ResendCompliantEmailProvider(
        provider="resend_email",
        endpoint="https://api.resend.com/emails",
        token_env="RESEND_API_KEY",
        from_email_env="OUTREACH_FROM_EMAIL",
        unsubscribe_base_url_env="UNSUBSCRIBE_BASE_URL",
        suppression_list_path=str(tmp_path / "suppression.jsonl"),
        audit_log_path=str(tmp_path / "audit.jsonl"),
        daily_send_limit=50,
        manual_approval_required=True,
    )


def test_resend_email_delivery_is_not_registered_without_required_project_keys() -> None:
    with pytest.raises(KeyError):
        ServiceRouter().email_delivery()


def test_resend_send_posts_payload_with_unsubscribe_and_audit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("OUTREACH_FROM_EMAIL", "recruiter@example.com")
    monkeypatch.setenv("UNSUBSCRIBE_BASE_URL", "https://example.com/unsubscribe")
    captured: dict[str, Any] = {}

    def fake_post(url: str, *, headers: dict, json: dict, timeout: int) -> FakeResponse:  # noqa: A002
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse({"id": "msg_123"})

    monkeypatch.setattr("requests.post", fake_post)
    provider = _provider(tmp_path)

    result = provider.send(
        to="candidate@example.com",
        subject="技术切磋",
        text_body="正文",
        approved=True,
    )

    assert result == {"status": "sent", "provider": "resend_email", "message_id": "msg_123"}
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["Authorization"] == "Bearer re_test_key"
    assert captured["json"]["from"] == "recruiter@example.com"
    assert captured["json"]["to"] == ["candidate@example.com"]
    assert "Unsubscribe: https://example.com/unsubscribe?email=candidate%40example.com" in captured["json"]["text"]
    audit_lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(audit_lines[-1])["event"] == "sent"


def test_resend_send_blocks_suppressed_recipient(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("OUTREACH_FROM_EMAIL", "recruiter@example.com")
    monkeypatch.setenv("UNSUBSCRIBE_BASE_URL", "https://example.com/unsubscribe")
    provider = _provider(tmp_path)
    provider.suppress("candidate@example.com", reason="unsubscribe")

    with pytest.raises(RuntimeError, match="suppressed"):
        provider.send(to="candidate@example.com", subject="s", text_body="b", approved=True)


def test_resend_send_requires_human_approval(tmp_path) -> None:
    provider = _provider(tmp_path)

    with pytest.raises(RuntimeError, match="approval"):
        provider.send(to="candidate@example.com", subject="s", text_body="b", approved=False)
