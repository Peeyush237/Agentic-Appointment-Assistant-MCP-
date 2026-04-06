from datetime import datetime
import re

import httpx
from twilio.rest import Client

from app.core.config import settings


ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


async def _refresh_google_access_token() -> str:
    refresh_token = (settings.google_refresh_token or "").strip()
    client_id = (settings.google_client_id or "").strip()
    client_secret = (settings.google_client_secret or "").strip()
    token_url = (settings.google_token_url or "https://oauth2.googleapis.com/token").strip()

    if not refresh_token or not client_id or not client_secret:
        return ""

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(token_url, data=payload)
        if response.status_code >= 400:
            return ""
        data = response.json()
        return (data.get("access_token") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


async def _refresh_google_access_token_with_error() -> tuple[str, str]:
    refresh_token = (settings.google_refresh_token or "").strip()
    client_id = (settings.google_client_id or "").strip()
    client_secret = (settings.google_client_secret or "").strip()
    token_url = (settings.google_token_url or "https://oauth2.googleapis.com/token").strip()

    missing = []
    if not refresh_token:
        missing.append("GOOGLE_REFRESH_TOKEN")
    if not client_id:
        missing.append("GOOGLE_CLIENT_ID")
    if not client_secret:
        missing.append("GOOGLE_CLIENT_SECRET")
    if missing:
        return "", f"Missing refresh credentials: {', '.join(missing)}"

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(token_url, data=payload)
        if response.status_code >= 400:
            return "", f"Token refresh failed ({response.status_code}): {response.text}"
        data = response.json()
        access_token = (data.get("access_token") or "").strip()
        if not access_token:
            return "", "Token refresh succeeded but access_token was missing in response"
        return access_token, ""
    except Exception as exc:  # noqa: BLE001
        return "", f"Token refresh exception: {exc}"


async def create_google_calendar_event(summary: str, description: str, start_time: datetime, end_time: datetime) -> dict:
    access_token = (settings.google_access_token or "").strip()
    refresh_error = ""
    if settings.google_refresh_token:
        refreshed_token = await _refresh_google_access_token()
        if refreshed_token:
            access_token = refreshed_token
        else:
            _, refresh_error = await _refresh_google_access_token_with_error()

    if not access_token:
        return {
            "mode": "mock",
            "event_id": f"mock-{int(start_time.timestamp())}",
            "message": (
                "Google access credentials missing, created mock calendar event"
                + (f". {refresh_error}" if refresh_error else "")
            ),
        }

    payload = {
        "summary": summary,
        "description": description,
        "start": {
            "dateTime": start_time.isoformat(),
            "timeZone": settings.google_timezone,
        },
        "end": {
            "dateTime": end_time.isoformat(),
            "timeZone": settings.google_timezone,
        },
    }

    url = f"https://www.googleapis.com/calendar/v3/calendars/{settings.google_calendar_id}/events"
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code == 401 and settings.google_refresh_token:
            refreshed_token, retry_refresh_error = await _refresh_google_access_token_with_error()
            if refreshed_token:
                retry_headers = {"Authorization": f"Bearer {refreshed_token}"}
                response = await client.post(url, json=payload, headers=retry_headers)
            else:
                return {
                    "mode": "error",
                    "event_id": None,
                    "message": (
                        "Calendar API authentication failed and token refresh could not recover"
                        f": {retry_refresh_error}"
                    ),
                }

        if response.status_code >= 400:
            return {
                "mode": "error",
                "event_id": None,
                "message": f"Calendar API failed: {response.text}",
            }
        data = response.json()
        return {"mode": "live", "event_id": data.get("id"), "message": "Calendar event created"}


async def send_patient_email(to_email: str, subject: str, body: str) -> dict:
    provider = settings.email_provider.lower().strip()

    if provider != "sendgrid":
        return {
            "mode": "mock",
            "message": f"Unsupported email provider '{provider}'. Mock email sent to {to_email}",
            "subject": subject,
            "body": body,
        }

    if not settings.email_api_key:
        return {
            "mode": "mock",
            "message": f"SendGrid API key missing, mock email sent to {to_email}",
            "subject": subject,
            "body": body,
        }

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": settings.email_from},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }

    headers = {
        "Authorization": f"Bearer {settings.email_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post("https://api.sendgrid.com/v3/mail/send", json=payload, headers=headers)

    if response.status_code == 202:
        return {
            "mode": "live",
            "message": f"SendGrid accepted email for {to_email}",
            "subject": subject,
        }

    return {
        "mode": "error",
        "message": f"SendGrid email failed ({response.status_code}): {response.text}",
        "subject": subject,
    }


def _normalize_whatsapp_number(target: str) -> str:
    normalized = (target or "").strip()
    if not normalized:
        return ""

    if normalized.lower().startswith("whatsapp:"):
        normalized = normalized.split(":", 1)[1].strip()

    # Accept commonly typed separators and convert to canonical format.
    normalized = (
        normalized.replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )

    if normalized.startswith("00"):
        normalized = "+" + normalized[2:]

    if normalized.startswith("+"):
        return f"whatsapp:{normalized}"

    if normalized.isdigit():
        return f"whatsapp:+{normalized}"

    return f"whatsapp:{normalized}"


def _extract_e164(whatsapp_number: str) -> str:
    value = (whatsapp_number or "").strip()
    if value.startswith("whatsapp:"):
        return value[len("whatsapp:") :].strip()
    return value


def _is_valid_e164(phone: str) -> bool:
    return bool(E164_RE.fullmatch((phone or "").strip()))


def _clean_provider_error(text: str) -> str:
    cleaned = ANSI_ESCAPE_RE.sub("", text or "")
    return " ".join(cleaned.split())


def _friendly_twilio_error(error_code: int | None, error_message: str | None) -> str:
    if error_message:
        return error_message
    if error_code == 63015:
        return (
            "Target number has not joined the Twilio WhatsApp Sandbox. "
            "From the target phone, send the sandbox join code to the Twilio sandbox number first."
        )
    return ""


async def send_doctor_notification(message: str, doctor_whatsapp_to: str | None = None) -> dict:
    provider = settings.whatsapp_provider.lower().strip()
    if provider != "twilio":
        return {
            "mode": "mock",
            "message": "Unsupported WhatsApp provider configured. Falling back to mock delivery.",
            "payload": message,
        }

    target_number = _normalize_whatsapp_number(doctor_whatsapp_to or settings.doctor_whatsapp_to or "")
    e164_target = _extract_e164(target_number)

    if target_number and not _is_valid_e164(e164_target):
        return {
            "mode": "error",
            "message": (
                "Invalid doctor WhatsApp number format. Use E.164 format, for example: "
                "whatsapp:+919876543210"
            ),
            "to": target_number,
        }

    creds = {
        "TWILIO_ACCOUNT_SID": (settings.twilio_account_sid or "").strip(),
        "TWILIO_AUTH_TOKEN": (settings.twilio_auth_token or "").strip(),
        "TWILIO_WHATSAPP_FROM": (settings.twilio_whatsapp_from or "").strip(),
        "DOCTOR_WHATSAPP_TO": target_number,
    }
    missing_fields = [k for k, v in creds.items() if not v]
    if missing_fields:
        return {
            "mode": "mock",
            "message": (
                "Twilio WhatsApp credentials missing: "
                + ", ".join(missing_fields)
                + ". Mock doctor notification delivered."
            ),
            "payload": message,
        }

    try:
        client = Client(creds["TWILIO_ACCOUNT_SID"], creds["TWILIO_AUTH_TOKEN"])
        twilio_message = client.messages.create(
            from_=creds["TWILIO_WHATSAPP_FROM"],
            to=creds["DOCTOR_WHATSAPP_TO"],
            body=message,
        )

        delivery_status = str(twilio_message.status)
        delivery_error_code = twilio_message.error_code
        delivery_error_message = twilio_message.error_message

        # Fetch latest status once to surface immediate channel errors (e.g. sandbox join required).
        try:
            latest = client.messages(twilio_message.sid).fetch()
            delivery_status = str(latest.status)
            delivery_error_code = latest.error_code
            delivery_error_message = latest.error_message
        except Exception:  # noqa: BLE001
            pass

        if delivery_status in {"failed", "undelivered"}:
            friendly_error = _friendly_twilio_error(delivery_error_code, delivery_error_message)
            return {
                "mode": "error",
                "message": (
                    "Doctor WhatsApp notification failed"
                    + (f" (error_code={delivery_error_code})" if delivery_error_code else "")
                    + (f": {friendly_error}" if friendly_error else "")
                ),
                "sid": twilio_message.sid,
                "to": creds["DOCTOR_WHATSAPP_TO"],
                "status": delivery_status,
                "error_code": delivery_error_code,
                "error_message": friendly_error or delivery_error_message,
            }

        if delivery_status in {"queued", "accepted", "scheduled", "sending"}:
            return {
                "mode": "accepted",
                "message": "Doctor WhatsApp request accepted by Twilio; delivery is pending",
                "sid": twilio_message.sid,
                "to": creds["DOCTOR_WHATSAPP_TO"],
                "status": delivery_status,
                "error_code": delivery_error_code,
                "error_message": delivery_error_message,
            }

        return {
            "mode": "live",
            "message": "Doctor WhatsApp notification delivered",
            "sid": twilio_message.sid,
            "to": creds["DOCTOR_WHATSAPP_TO"],
            "status": delivery_status,
            "error_code": delivery_error_code,
            "error_message": delivery_error_message,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "mode": "error",
            "message": f"Twilio WhatsApp notification failed: {_clean_provider_error(str(exc))}",
            "to": creds["DOCTOR_WHATSAPP_TO"],
        }
