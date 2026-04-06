from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import hash_password
from app.core.config import settings
from app.db.models import Doctor, Appointment
from app.db.models import User


def seed_data(db: Session) -> None:
    doctors = [
        ("Dr. Ahuja", "General Physician"),
        ("Dr. Rao", "Pediatrics"),
    ]

    for doctor_name, specialization in doctors:
        existing = db.scalar(select(Doctor).where(Doctor.name == doctor_name))
        if not existing:
            db.add(Doctor(name=doctor_name, specialization=specialization))

    doctor_user = db.scalar(select(User).where(User.email == settings.default_doctor_login_email))
    if not doctor_user:
        db.add(
            User(
                email=settings.default_doctor_login_email,
                full_name="Dr. Ahuja",
                role="doctor",
                password_hash=hash_password(settings.default_doctor_login_password),
            )
        )
    else:
        doctor_user.full_name = doctor_user.full_name or "Dr. Ahuja"
        doctor_user.role = "doctor"
        doctor_user.password_hash = hash_password(settings.default_doctor_login_password)

    db.commit()

    ahuja = db.scalar(select(Doctor).where(Doctor.name == "Dr. Ahuja"))
    if not ahuja:
        return

    yesterday_noon = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=1)
    existing_appt = db.scalar(
        select(Appointment).where(
            Appointment.doctor_id == ahuja.id,
            Appointment.start_time == yesterday_noon,
        )
    )
    if not existing_appt:
        db.add(
            Appointment(
                doctor_id=ahuja.id,
                patient_name="Seed Patient",
                patient_email="seed@example.com",
                symptoms="fever",
                status="completed",
                start_time=yesterday_noon,
                end_time=yesterday_noon + timedelta(minutes=30),
                notes="Follow-up in one week",
            )
        )
        db.commit()
