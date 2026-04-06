from datetime import datetime

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=6, max_length=128)
    role: str = Field(pattern="^(patient|doctor)$")


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


class ChatCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ChatRequest(BaseModel):
    message: str
    chat_id: str | None = None


class ChatResponse(BaseModel):
    chat_id: str
    response: str
    tool_trace: list[dict]


class ChatThreadResponse(BaseModel):
    id: str
    role: str
    title: str
    created_at: datetime
    updated_at: datetime


class ChatMessageResponse(BaseModel):
    id: int
    sender: str
    content: str
    tool_trace: list[dict] | None = None
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
