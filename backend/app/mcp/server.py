from __future__ import annotations

import json
from contextvars import ContextVar
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from dateutil import parser
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import and_, func, select

from app.core.integrations import create_google_calendar_event, send_doctor_notification, send_patient_email
from app.core.config import settings
from app.db.database import SessionLocal
from app.db.models import Appointment, Doctor

router = APIRouter()

SLOT_MINUTES = 30
MORNING_START_HOUR = 9
LUNCH_START_HOUR = 13
AFTERNOON_START_HOUR = 14
DAY_END_HOUR = 18

RUNTIME_DOCTOR_WHATSAPP_TO: ContextVar[str] = ContextVar("runtime_doctor_whatsapp_to", default="")


def set_runtime_doctor_whatsapp_to(number: str | None):
    return RUNTIME_DOCTOR_WHATSAPP_TO.set((number or "").strip())


def reset_runtime_doctor_whatsapp_to(token) -> None:
    RUNTIME_DOCTOR_WHATSAPP_TO.reset(token)


def _is_weekday(day: datetime) -> bool:
    return day.weekday() < 5


def _normalize_period(period: str) -> str:
    key = period.lower().strip()
    if key in {"morning", "afternoon", "full_day"}:
        return key
    if key == "evening":
        return "afternoon"
    return "full_day"


def _build_slots_for_period(day: datetime, period: str) -> list[datetime]:
    if not _is_weekday(day):
        return []

    windows: list[tuple[int, int]]
    period_key = _normalize_period(period)
    if period_key == "morning":
        windows = [(MORNING_START_HOUR, LUNCH_START_HOUR)]
    elif period_key == "afternoon":
        windows = [(AFTERNOON_START_HOUR, DAY_END_HOUR)]
    else:
        windows = [(MORNING_START_HOUR, LUNCH_START_HOUR), (AFTERNOON_START_HOUR, DAY_END_HOUR)]

    slots: list[datetime] = []
    for start_hour, end_hour in windows:
        cur = day.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        end = day.replace(hour=end_hour, minute=0, second=0, microsecond=0)
        while cur < end:
            slots.append(cur)
            cur += timedelta(minutes=SLOT_MINUTES)
    return slots


def _is_valid_appointment_slot(start_time: datetime) -> bool:
    if not _is_weekday(start_time):
        return False
    if start_time.second != 0 or start_time.microsecond != 0:
        return False
    if start_time.minute not in {0, 30}:
        return False

    hour = start_time.hour
    minute = start_time.minute
    in_morning = (hour > MORNING_START_HOUR or (hour == MORNING_START_HOUR and minute >= 0)) and hour < LUNCH_START_HOUR
    in_afternoon = (
        (hour > AFTERNOON_START_HOUR or (hour == AFTERNOON_START_HOUR and minute >= 0)) and hour < DAY_END_HOUR
    )
    return in_morning or in_afternoon


class MCPRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] = {}


def _mcp_result(req_id: int | str | None, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _mcp_error(req_id: int | str | None, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _get_doctor(db, doctor_name: str) -> Doctor | None:
    return db.scalar(select(Doctor).where(Doctor.name.ilike(doctor_name)))


def _parse_range(date: str, period: str) -> tuple[datetime, datetime]:
    base = parser.parse(date).replace(second=0, microsecond=0)
    period_key = _normalize_period(period)

    if period_key == "morning":
        return base.replace(hour=MORNING_START_HOUR, minute=0), base.replace(hour=LUNCH_START_HOUR, minute=0)
    if period_key == "afternoon":
        return base.replace(hour=AFTERNOON_START_HOUR, minute=0), base.replace(hour=DAY_END_HOUR, minute=0)

    return base.replace(hour=MORNING_START_HOUR, minute=0), base.replace(hour=DAY_END_HOUR, minute=0)


def _current_time_payload() -> dict[str, Any]:
    timezone_name = settings.google_timezone or "UTC"
    try:
        now = datetime.now(ZoneInfo(timezone_name))
    except Exception:  # noqa: BLE001
        timezone_name = "UTC"
        now = datetime.now(ZoneInfo("UTC"))

    return {
        "ok": True,
        "timezone": timezone_name,
        "now_iso": now.isoformat(),
        "day_of_week": now.strftime("%A"),
        "date": now.date().isoformat(),
        "time_24h": now.strftime("%H:%M:%S"),
        "message": "Current server date and time",
    }


async def _tool_check_doctor_availability(arguments: dict[str, Any]) -> dict[str, Any]:
    doctor_name = arguments.get("doctor_name", "")
    date = arguments.get("date", datetime.now().date().isoformat())
    period = _normalize_period(arguments.get("period", "morning"))

    with SessionLocal() as db:
        doctor = _get_doctor(db, doctor_name)
        if not doctor:
            return {"ok": False, "message": f"Doctor not found: {doctor_name}"}

        base_day = parser.parse(date).replace(second=0, microsecond=0)
        if not _is_weekday(base_day):
            return {
                "ok": True,
                "doctor_name": doctor.name,
                "date": base_day.date().isoformat(),
                "period": period,
                "available_slots": [],
                "message": "Doctor is available only Monday to Friday. No slots on weekends.",
            }

        day_start = base_day.replace(hour=0, minute=0)
        day_end = day_start + timedelta(days=1)

        rows = db.scalars(
            select(Appointment).where(
                and_(
                    Appointment.doctor_id == doctor.id,
                    Appointment.start_time >= day_start,
                    Appointment.start_time < day_end,
                    Appointment.status != "cancelled",
                )
            )
        ).all()

        occupied = {row.start_time.replace(second=0, microsecond=0) for row in rows}

        slots = []
        for cur in _build_slots_for_period(base_day, period):
            if cur not in occupied:
                slots.append(
                    {
                        "start_time": cur.isoformat(),
                        "end_time": (cur + timedelta(minutes=SLOT_MINUTES)).isoformat(),
                    }
                )

        return {
            "ok": True,
            "doctor_name": doctor.name,
            "date": base_day.date().isoformat(),
            "period": period,
            "available_slots": slots,
            "message": f"Found {len(slots)} available slots",
        }


async def _tool_book_appointment(arguments: dict[str, Any]) -> dict[str, Any]:
    doctor_name = arguments.get("doctor_name", "")
    patient_name = arguments.get("patient_name", "Patient")
    patient_email = arguments.get("patient_email", "patient@example.com")
    symptoms = arguments.get("symptoms", "general")
    start_time_raw = arguments.get("start_time")

    if not start_time_raw:
        return {"ok": False, "message": "start_time is required"}

    start_time = parser.parse(start_time_raw).replace(second=0, microsecond=0)
    end_time = start_time + timedelta(minutes=SLOT_MINUTES)

    if not _is_valid_appointment_slot(start_time):
        return {
            "ok": False,
            "message": (
                "Doctor is available Monday to Friday, 9:00 AM-1:00 PM and 2:00 PM-6:00 PM. "
                "Lunch break is 1:00 PM-2:00 PM. Please choose a valid 30-minute slot."
            ),
        }

    with SessionLocal() as db:
        doctor = _get_doctor(db, doctor_name)
        if not doctor:
            return {"ok": False, "message": f"Doctor not found: {doctor_name}"}

        collision = db.scalar(
            select(Appointment).where(
                and_(
                    Appointment.doctor_id == doctor.id,
                    Appointment.start_time == start_time,
                    Appointment.status != "cancelled",
                )
            )
        )
        if collision:
            return {
                "ok": False,
                "message": "Selected slot is no longer available. Please choose another slot.",
            }

        calendar = await create_google_calendar_event(
            summary=f"{doctor.name} with {patient_name}",
            description=f"Symptoms: {symptoms}",
            start_time=start_time,
            end_time=end_time,
        )

        appt = Appointment(
            doctor_id=doctor.id,
            patient_name=patient_name,
            patient_email=patient_email,
            symptoms=symptoms,
            status="booked",
            start_time=start_time,
            end_time=end_time,
            calendar_event_id=calendar.get("event_id"),
        )
        db.add(appt)
        db.commit()
        db.refresh(appt)

        booking_message = "Appointment booked"
        if calendar.get("mode") == "error":
            booking_message = "Appointment booked in clinic records, but Google Calendar sync failed"

        return {
            "ok": True,
            "appointment_id": appt.id,
            "doctor_name": doctor.name,
            "patient_name": patient_name,
            "patient_email": patient_email,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "calendar": calendar,
            "message": booking_message,
        }


async def _tool_send_patient_email(arguments: dict[str, Any]) -> dict[str, Any]:
    patient_email = arguments.get("patient_email")
    patient_name = arguments.get("patient_name", "Patient")
    doctor_name = arguments.get("doctor_name", "Doctor")
    start_time = arguments.get("start_time", "")

    if not patient_email:
        return {"ok": False, "message": "patient_email is required"}

    subject = f"Appointment Confirmation with {doctor_name}"
    body = (
        f"Hello {patient_name},\n\n"
        f"Your appointment with {doctor_name} is confirmed for {start_time}.\n"
        f"Please arrive 10 minutes early.\n\n"
        "Thanks,\nClinic"
    )
    sent = await send_patient_email(patient_email, subject, body)
    return {"ok": True, "delivery": sent, "message": "Patient email sent"}


async def _tool_get_doctor_report_stats(arguments: dict[str, Any]) -> dict[str, Any]:
    doctor_name = arguments.get("doctor_name", "Dr. Ahuja")
    timeframe = arguments.get("timeframe", "today")
    symptom = arguments.get("symptom")

    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if timeframe == "yesterday":
        start = today_start - timedelta(days=1)
        end = today_start
    elif timeframe == "tomorrow":
        start = today_start + timedelta(days=1)
        end = today_start + timedelta(days=2)
    elif timeframe == "today_and_tomorrow":
        start = today_start
        end = today_start + timedelta(days=2)
    else:
        start = today_start
        end = today_start + timedelta(days=1)

    with SessionLocal() as db:
        doctor = _get_doctor(db, doctor_name)
        if not doctor:
            return {"ok": False, "message": f"Doctor not found: {doctor_name}"}

        stmt = select(func.count(Appointment.id)).where(
            and_(
                Appointment.doctor_id == doctor.id,
                Appointment.start_time >= start,
                Appointment.start_time < end,
                Appointment.status != "cancelled",
            )
        )

        if symptom:
            stmt = stmt.where(Appointment.symptoms.ilike(f"%{symptom}%"))

        count = db.scalar(stmt) or 0

        return {
            "ok": True,
            "doctor_name": doctor.name,
            "timeframe": timeframe,
            "symptom": symptom,
            "count": int(count),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "message": f"{count} appointments found",
        }


async def _tool_send_doctor_notification(arguments: dict[str, Any]) -> dict[str, Any]:
    report_text = arguments.get("report_text", "No report text provided")
    doctor_whatsapp_to = arguments.get("doctor_whatsapp_to") or RUNTIME_DOCTOR_WHATSAPP_TO.get()
    sent = await send_doctor_notification(report_text, doctor_whatsapp_to=doctor_whatsapp_to)
    return {"ok": True, "delivery": sent, "message": "Doctor notification sent"}


async def _tool_get_current_datetime(arguments: dict[str, Any]) -> dict[str, Any]:
    return _current_time_payload()


TOOLS: dict[str, dict[str, Any]] = {
    "get_current_datetime": {
        "description": "Get current server date, time, day, and timezone",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "handler": _tool_get_current_datetime,
    },
    "check_doctor_availability": {
        "description": "Check doctor availability for a given date and period",
        "inputSchema": {
            "type": "object",
            "properties": {
                "doctor_name": {"type": "string"},
                "date": {"type": "string", "description": "ISO date like 2026-04-05"},
                "period": {"type": "string", "enum": ["morning", "afternoon", "evening", "full_day"]},
            },
            "required": ["doctor_name", "date", "period"],
        },
        "handler": _tool_check_doctor_availability,
    },
    "book_appointment": {
        "description": "Book appointment and create calendar event",
        "inputSchema": {
            "type": "object",
            "properties": {
                "doctor_name": {"type": "string"},
                "patient_name": {"type": "string"},
                "patient_email": {"type": "string"},
                "symptoms": {"type": "string"},
                "start_time": {"type": "string", "description": "ISO datetime"},
            },
            "required": ["doctor_name", "patient_name", "patient_email", "start_time"],
        },
        "handler": _tool_book_appointment,
    },
    "send_patient_email": {
        "description": "Send appointment confirmation email to patient",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_email": {"type": "string"},
                "patient_name": {"type": "string"},
                "doctor_name": {"type": "string"},
                "start_time": {"type": "string"},
            },
            "required": ["patient_email", "patient_name", "doctor_name", "start_time"],
        },
        "handler": _tool_send_patient_email,
    },
    "get_doctor_report_stats": {
        "description": "Get doctor appointment statistics with optional symptom filtering",
        "inputSchema": {
            "type": "object",
            "properties": {
                "doctor_name": {"type": "string"},
                "timeframe": {
                    "type": "string",
                    "enum": ["today", "tomorrow", "yesterday", "today_and_tomorrow"],
                },
                "symptom": {"type": "string"},
            },
            "required": ["doctor_name", "timeframe"],
        },
        "handler": _tool_get_doctor_report_stats,
    },
    "send_doctor_notification": {
        "description": "Send doctor report to Slack or alternate notifier",
        "inputSchema": {
            "type": "object",
            "properties": {
                "report_text": {"type": "string"},
                "doctor_whatsapp_to": {
                    "type": "string",
                    "description": "Target WhatsApp number like +919XXXXXXXXX or whatsapp:+919XXXXXXXXX",
                },
            },
            "required": ["report_text"],
        },
        "handler": _tool_send_doctor_notification,
    },
}

PROMPTS: dict[str, str] = {
    "patient_agent_system": (
        "You are a patient appointment assistant. Always use MCP tools for availability and booking. "
        "If user asks current day/date/time (for example: what day is today, what time is it now), "
        "you MUST call get_current_datetime and answer from that tool result. "
        "Never claim any slot is available unless check_doctor_availability was called for that date/period. "
        "Never claim appointment booked unless book_appointment returned ok=true. "
        "After successful booking, call send_patient_email and only then confirm email sent. "
        "Use conversation history to remember previously provided patient name/email/symptoms and ask only missing fields. "
        "Clinic hours are Monday-Friday, 9:00 AM-1:00 PM and 2:00 PM-6:00 PM, lunch 1:00 PM-2:00 PM. "
        "Keep responses short and clear. In every patient response, include a short reminder to check Spam/Junk folder for confirmation emails."
    ),
    "doctor_agent_system": (
        "You are a doctor reporting assistant. Use MCP tools to gather stats, summarize in plain English, "
        "and if user asks current day/date/time, call get_current_datetime before answering. "
        "and send a notification via send_doctor_notification whenever user asks for a report."
    ),
}


@router.post("")
async def mcp_handler(req: MCPRequest):
    if req.method == "initialize":
        return _mcp_result(req.id, {"name": "appointment-mcp-server", "version": "1.0.0"})

    if req.method == "tools/list":
        tools = []
        for name, conf in TOOLS.items():
            tools.append(
                {
                    "name": name,
                    "description": conf["description"],
                    "inputSchema": conf["inputSchema"],
                }
            )
        return _mcp_result(req.id, {"tools": tools})

    if req.method == "tools/call":
        name = req.params.get("name", "")
        arguments = req.params.get("arguments", {})
        if name not in TOOLS:
            return _mcp_error(req.id, -32601, f"Unknown tool: {name}")

        try:
            result = await TOOLS[name]["handler"](arguments)
            return _mcp_result(req.id, {"content": [{"type": "text", "text": json.dumps(result)}]})
        except Exception as exc:  # noqa: BLE001
            return _mcp_error(req.id, -32000, str(exc))

    if req.method == "resources/list":
        return _mcp_result(
            req.id,
            {
                "resources": [
                    {
                        "uri": "resource://doctors",
                        "name": "Doctors",
                        "description": "List of all doctors and specializations",
                        "mimeType": "application/json",
                    }
                ]
            },
        )

    if req.method == "resources/read":
        uri = req.params.get("uri")
        if uri != "resource://doctors":
            return _mcp_error(req.id, -32602, "Unknown resource URI")

        with SessionLocal() as db:
            doctors = db.scalars(select(Doctor)).all()
            payload = [{"name": d.name, "specialization": d.specialization} for d in doctors]

        return _mcp_result(
            req.id,
            {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps(payload),
                    }
                ]
            },
        )

    if req.method == "prompts/list":
        return _mcp_result(
            req.id,
            {
                "prompts": [{"name": name, "description": "Agent system prompt"} for name in PROMPTS],
            },
        )

    if req.method == "prompts/get":
        name = req.params.get("name")
        if name not in PROMPTS:
            return _mcp_error(req.id, -32602, f"Unknown prompt: {name}")
        return _mcp_result(
            req.id,
            {
                "description": "Prompt loaded",
                "messages": [
                    {
                        "role": "system",
                        "content": {
                            "type": "text",
                            "text": PROMPTS[name],
                        },
                    }
                ],
            },
        )

    return _mcp_error(req.id, -32601, f"Unknown method: {req.method}")
