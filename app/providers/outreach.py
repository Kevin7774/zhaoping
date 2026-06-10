from __future__ import annotations

import json
import os
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from uuid import uuid4
from urllib.parse import quote


def _require_env(env_name: str) -> str:
    value = os.environ.get(env_name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {env_name}")
    return value


class HunterEmailFinderProvider:
    def __init__(
        self,
        endpoint: str = "https://api.hunter.io/v2/email-finder",
        api_key_env: str = "HUNTER_API_KEY",
        timeout_seconds: int = 20,
    ) -> None:
        self.endpoint = endpoint
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds

    def find(
        self,
        *,
        full_name: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        domain: str | None = None,
        company: str | None = None,
        linkedin_handle: str | None = None,
    ) -> dict[str, Any]:
        api_key = _require_env(self.api_key_env)
        params = {"api_key": api_key}
        if domain:
            params["domain"] = domain
        if company:
            params["company"] = company
        if linkedin_handle:
            params["linkedin_handle"] = linkedin_handle
        if full_name:
            params["full_name"] = full_name
        if first_name:
            params["first_name"] = first_name
        if last_name:
            params["last_name"] = last_name

        import requests

        response = requests.get(self.endpoint, params=params, timeout=self.timeout_seconds)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Hunter email finder failed: {response.status_code} {response.text[:300]}") from exc

        data = response.json().get("data") or {}
        score = data.get("score")
        return {
            "provider": "hunter_email_finder",
            "email": data.get("email"),
            "score": score,
            "quality": self._quality(score),
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "position": data.get("position"),
            "company": data.get("company"),
            "sources": data.get("sources") or [],
        }

    @staticmethod
    def _quality(score: Any) -> str:
        try:
            numeric_score = int(score)
        except (TypeError, ValueError):
            return "unknown"
        if numeric_score >= 90:
            return "high_confidence"
        if numeric_score >= 70:
            return "medium_confidence"
        return "low_confidence"


class ZeroBounceEmailValidationProvider:
    def __init__(
        self,
        endpoint: str = "https://api.zerobounce.net/v2/validate",
        api_key_env: str = "ZEROBOUNCE_API_KEY",
        timeout_seconds: int = 30,
    ) -> None:
        self.endpoint = endpoint
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds

    def verify(self, email: str, *, ip_address: str | None = None) -> dict[str, Any]:
        api_key = _require_env(self.api_key_env)
        params = {"api_key": api_key, "email": email, "timeout": self.timeout_seconds}
        if ip_address:
            params["ip_address"] = ip_address

        import requests

        response = requests.get(self.endpoint, params=params, timeout=self.timeout_seconds)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"ZeroBounce email validation failed: {response.status_code} {response.text[:300]}") from exc

        payload = response.json()
        status = str(payload.get("status") or "")
        return {
            "provider": "zerobounce_email_validation",
            "email": payload.get("address") or email,
            "status": status,
            "sub_status": payload.get("sub_status"),
            "deliverable": status == "valid",
            "mx_found": payload.get("mx_found"),
            "free_email": payload.get("free_email"),
            "did_you_mean": payload.get("did_you_mean"),
        }


class NeverBounceEmailValidationProvider:
    def __init__(
        self,
        endpoint: str = "https://api.neverbounce.com/v4.2/single/check",
        api_key_env: str = "NEVERBOUNCE_API_KEY",
        timeout_seconds: int = 30,
    ) -> None:
        self.endpoint = endpoint
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds

    def verify(self, email: str) -> dict[str, Any]:
        api_key = _require_env(self.api_key_env)

        import requests

        response = requests.get(
            self.endpoint,
            params={"key": api_key, "email": email, "timeout": self.timeout_seconds},
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"NeverBounce email validation failed: {response.status_code} {response.text[:300]}") from exc

        payload = response.json()
        result = str(payload.get("result") or "")
        return {
            "provider": "neverbounce_email_validation",
            "email": email,
            "status": payload.get("status"),
            "result": result,
            "deliverable": result == "valid",
            "flags": payload.get("flags") or [],
            "suggested_correction": payload.get("suggested_correction"),
        }


class CompliantEmailDeliveryProvider:
    def __init__(
        self,
        *,
        provider: str,
        endpoint: str,
        token_env: str,
        from_email_env: str,
        unsubscribe_base_url_env: str,
        suppression_list_path: str,
        audit_log_path: str,
        daily_send_limit: int = 50,
        manual_approval_required: bool = True,
        timeout_seconds: int = 20,
    ) -> None:
        self.provider = provider
        self.endpoint = endpoint
        self.token_env = token_env
        self.from_email_env = from_email_env
        self.unsubscribe_base_url_env = unsubscribe_base_url_env
        self.suppression_list_path = suppression_list_path
        self.audit_log_path = audit_log_path
        self.daily_send_limit = daily_send_limit
        self.manual_approval_required = manual_approval_required
        self.timeout_seconds = timeout_seconds

    def send(
        self,
        *,
        to: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
        sender_email: str | None = None,
        approved: bool = False,
    ) -> dict[str, Any]:
        if self.manual_approval_required and not approved:
            raise RuntimeError("Human approval is required before email delivery.")
        recipient = to.strip().lower()
        if not recipient or "@" not in recipient:
            raise RuntimeError("A valid recipient email is required.")
        if self._is_suppressed(recipient):
            raise RuntimeError(f"Recipient is suppressed: {recipient}")
        if self._sent_today_count() >= int(self.daily_send_limit):
            raise RuntimeError(f"Daily send limit reached: {self.daily_send_limit}")

        token = _require_env(self.token_env)
        sender = _normalize_sender_email(sender_email) or _require_env(self.from_email_env)
        unsubscribe_base_url = _require_env(self.unsubscribe_base_url_env)
        unsubscribe_url = f"{unsubscribe_base_url.rstrip('/')}?email={quote(recipient)}"
        text_with_unsubscribe = f"{text_body.rstrip()}\n\nUnsubscribe: {unsubscribe_url}"

        response_payload = self._send_request(
            token=token,
            sender=sender,
            to=recipient,
            subject=subject,
            text_body=text_with_unsubscribe,
            html_body=html_body,
            unsubscribe_url=unsubscribe_url,
        )
        message_id = (
            response_payload.get("MessageID")
            or response_payload.get("message_id")
            or response_payload.get("id")
        )
        self._append_audit(
            {
                "event": "sent",
                "provider": self.provider,
                "to": recipient,
                "subject": subject,
                "message_id": message_id,
            }
        )
        return {"status": "sent", "provider": self.provider, "message_id": message_id}

    def suppress(self, email: str, *, reason: str = "unsubscribe") -> dict[str, Any]:
        recipient = email.strip().lower()
        record = {
            "email": recipient,
            "reason": reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        path = Path(self.suppression_list_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        self._append_audit({"event": "suppressed", "provider": self.provider, "to": recipient, "reason": reason})
        return {"status": "suppressed", "email": recipient}

    def _send_request(
        self,
        *,
        token: str,
        sender: str,
        to: str,
        subject: str,
        text_body: str,
        html_body: str | None,
        unsubscribe_url: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def _is_suppressed(self, email: str) -> bool:
        path = Path(self.suppression_list_path)
        if not path.exists():
            return False
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(record.get("email") or "").strip().lower() == email:
                return True
        return False

    def _sent_today_count(self) -> int:
        path = Path(self.audit_log_path)
        if not path.exists():
            return 0
        today = datetime.now(timezone.utc).date().isoformat()
        count = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("event") == "sent" and str(record.get("created_at", "")).startswith(today):
                count += 1
        return count

    def _append_audit(self, record: dict[str, Any]) -> None:
        path = Path(self.audit_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {"created_at": datetime.now(timezone.utc).isoformat(), **record}
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(envelope, ensure_ascii=False, sort_keys=True) + "\n")


def _normalize_sender_email(value: str | None) -> str | None:
    sender = str(value or "").strip().lower()
    if not sender:
        return None
    if "@" not in sender or sender.startswith("@") or sender.endswith("@"):
        raise RuntimeError("A valid sender email is required.")
    return sender


class ResendCompliantEmailProvider(CompliantEmailDeliveryProvider):
    def _send_request(
        self,
        *,
        token: str,
        sender: str,
        to: str,
        subject: str,
        text_body: str,
        html_body: str | None,
        unsubscribe_url: str,
    ) -> dict[str, Any]:
        import requests

        response = requests.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "from": sender,
                "to": [to],
                "subject": subject,
                "text": text_body,
                **({"html": html_body} if html_body else {}),
                "headers": {"List-Unsubscribe": f"<{unsubscribe_url}>"},
            },
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Resend email send failed: {response.status_code} {response.text[:300]}") from exc
        return response.json()


class PostmarkCompliantEmailProvider(CompliantEmailDeliveryProvider):
    def _send_request(
        self,
        *,
        token: str,
        sender: str,
        to: str,
        subject: str,
        text_body: str,
        html_body: str | None,
        unsubscribe_url: str,
    ) -> dict[str, Any]:
        import requests

        response = requests.post(
            self.endpoint,
            headers={
                "Content-Type": "application/json",
                "X-Postmark-Server-Token": token,
            },
            json={
                "From": sender,
                "To": to,
                "Subject": subject,
                "TextBody": text_body,
                **({"HtmlBody": html_body} if html_body else {}),
                "Headers": [{"Name": "List-Unsubscribe", "Value": f"<{unsubscribe_url}>"}],
            },
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Postmark email send failed: {response.status_code} {response.text[:300]}") from exc
        return response.json()


class SendGridCompliantEmailProvider(CompliantEmailDeliveryProvider):
    def _send_request(
        self,
        *,
        token: str,
        sender: str,
        to: str,
        subject: str,
        text_body: str,
        html_body: str | None,
        unsubscribe_url: str,
    ) -> dict[str, Any]:
        import requests

        content = [{"type": "text/plain", "value": text_body}]
        if html_body:
            content.append({"type": "text/html", "value": html_body})
        response = requests.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "personalizations": [{"to": [{"email": to}]}],
                "from": {"email": sender},
                "subject": subject,
                "content": content,
                "headers": {"List-Unsubscribe": f"<{unsubscribe_url}>"},
            },
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"SendGrid email send failed: {response.status_code} {response.text[:300]}") from exc
        if response.text.strip():
            return response.json()
        return {"message_id": response.headers.get("X-Message-Id")}


class MailtrapSMTPEmailProvider(CompliantEmailDeliveryProvider):
    def __init__(
        self,
        *,
        provider: str,
        host_env: str,
        port_env: str,
        username_env: str,
        password_env: str,
        from_email_env: str,
        unsubscribe_base_url_env: str,
        suppression_list_path: str,
        audit_log_path: str,
        daily_send_limit: int = 50,
        manual_approval_required: bool = True,
        use_starttls: bool = True,
        timeout_seconds: int = 20,
    ) -> None:
        super().__init__(
            provider=provider,
            endpoint="smtp",
            token_env=password_env,
            from_email_env=from_email_env,
            unsubscribe_base_url_env=unsubscribe_base_url_env,
            suppression_list_path=suppression_list_path,
            audit_log_path=audit_log_path,
            daily_send_limit=daily_send_limit,
            manual_approval_required=manual_approval_required,
            timeout_seconds=timeout_seconds,
        )
        self.host_env = host_env
        self.port_env = port_env
        self.username_env = username_env
        self.password_env = password_env
        self.use_starttls = use_starttls

    def _send_request(
        self,
        *,
        token: str,
        sender: str,
        to: str,
        subject: str,
        text_body: str,
        html_body: str | None,
        unsubscribe_url: str,
    ) -> dict[str, Any]:
        host = _require_env(self.host_env)
        username = _require_env(self.username_env)
        password = token
        try:
            port = int(_require_env(self.port_env))
        except ValueError as exc:
            raise RuntimeError(f"Invalid Mailtrap SMTP port in {self.port_env}") from exc

        message = EmailMessage()
        message["From"] = sender
        message["To"] = to
        message["Subject"] = subject
        message["List-Unsubscribe"] = f"<{unsubscribe_url}>"
        message.set_content(text_body)
        if html_body:
            message.add_alternative(html_body, subtype="html")

        with smtplib.SMTP(host, port, timeout=self.timeout_seconds) as smtp:
            if self.use_starttls:
                smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(message)

        return {"message_id": f"mailtrap-{uuid4().hex[:16]}"}
