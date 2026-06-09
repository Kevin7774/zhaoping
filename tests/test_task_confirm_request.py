from __future__ import annotations

from app.api.main import ConfirmRequest


def test_confirm_request_accepts_action_data_payload() -> None:
    request = ConfirmRequest.model_validate(
        {
            "action": "approve",
            "data": {
                "draft": "Hi Alex, updated.",
            },
        }
    )

    assert request.decision == "approve"
    assert request.edits == "Hi Alex, updated."


def test_confirm_request_still_accepts_legacy_payload() -> None:
    request = ConfirmRequest.model_validate({"decision": "reject", "edits": "not a fit"})

    assert request.decision == "reject"
    assert request.edits == "not a fit"
