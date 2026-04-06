import json
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import AuthResponse
from app.api.schemas import ChatCreateRequest
from app.api.schemas import ChatMessageResponse
from app.api.schemas import ChatRequest, ChatResponse, ChatThreadResponse
from app.api.schemas import HealthResponse
from app.api.schemas import LoginRequest
from app.api.schemas import RegisterRequest
from app.api.schemas import UserResponse
from app.core.auth import generate_token, hash_password, token_expiry, token_hash, verify_password
from app.core.agent import agent
from app.db.database import get_db
from app.db.models import AuthToken, ChatMessage, ChatThread, User

router = APIRouter(prefix="/api", tags=["api"])


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")

    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization scheme")
    return parts[1].strip()


def _current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    token = _extract_bearer_token(authorization)
    hashed = token_hash(token)
    token_row = db.scalar(select(AuthToken).where(AuthToken.token_hash == hashed))
    if not token_row or token_row.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid")

    user = db.get(User, token_row.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name, role=user.role)


def _to_thread_response(thread: ChatThread) -> ChatThreadResponse:
    return ChatThreadResponse(
        id=thread.id,
        role=thread.role,
        title=thread.title,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


def _thread_history(thread_messages: list[ChatMessage]) -> list[dict]:
    history = []
    for message in thread_messages:
        if message.sender in {"user", "assistant"}:
            history.append({"role": message.sender, "content": message.content})
    return history


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok")


@router.post("/auth/register", response_model=AuthResponse)
async def register(req: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.scalar(select(User).where(User.email == req.email.lower()))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=req.email.lower(),
        full_name=req.full_name.strip(),
        role="patient",
        password_hash=hash_password(req.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    raw_token = generate_token()
    db.add(AuthToken(user_id=user.id, token_hash=token_hash(raw_token), expires_at=token_expiry()))
    db.commit()
    return AuthResponse(token=raw_token, user=_to_user_response(user))


@router.post("/auth/login", response_model=AuthResponse)
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == req.email.lower()))
    if not user or user.role != req.role or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    raw_token = generate_token()
    db.add(AuthToken(user_id=user.id, token_hash=token_hash(raw_token), expires_at=token_expiry()))
    db.commit()
    return AuthResponse(token=raw_token, user=_to_user_response(user))


@router.post("/auth/logout")
async def logout(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    raw = _extract_bearer_token(authorization)
    hashed = token_hash(raw)
    token_row = db.scalar(select(AuthToken).where(AuthToken.token_hash == hashed))
    if token_row:
        db.delete(token_row)
        db.commit()
    return {"status": "ok"}


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(_current_user)):
    return _to_user_response(user)


@router.get("/chats", response_model=list[ChatThreadResponse])
async def list_chats(user: User = Depends(_current_user), db: Session = Depends(get_db)):
    threads = db.scalars(
        select(ChatThread).where(ChatThread.user_id == user.id).order_by(ChatThread.updated_at.desc())
    ).all()
    return [_to_thread_response(thread) for thread in threads]


@router.post("/chats", response_model=ChatThreadResponse)
async def create_chat(req: ChatCreateRequest, user: User = Depends(_current_user), db: Session = Depends(get_db)):
    default_title = "Doctor Chat" if user.role == "doctor" else "Patient Chat"
    thread = ChatThread(user_id=user.id, role=user.role, title=(req.title or default_title).strip()[:200])
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return _to_thread_response(thread)


@router.get("/chats/{chat_id}/messages", response_model=list[ChatMessageResponse])
async def get_chat_messages(chat_id: str, user: User = Depends(_current_user), db: Session = Depends(get_db)):
    thread = db.scalar(select(ChatThread).where(ChatThread.id == chat_id, ChatThread.user_id == user.id))
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

    messages = db.scalars(select(ChatMessage).where(ChatMessage.thread_id == thread.id).order_by(ChatMessage.created_at)).all()
    output = []
    for message in messages:
        trace = json.loads(message.tool_trace_json) if message.tool_trace_json else None
        output.append(
            ChatMessageResponse(
                id=message.id,
                sender=message.sender,
                content=message.content,
                tool_trace=trace,
                created_at=message.created_at,
            )
        )
    return output


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, user: User = Depends(_current_user), db: Session = Depends(get_db)):
    thread = None
    if req.chat_id:
        thread = db.scalar(select(ChatThread).where(ChatThread.id == req.chat_id, ChatThread.user_id == user.id))
        if not thread:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    else:
        default_title = "Doctor Chat" if user.role == "doctor" else "Patient Chat"
        thread = ChatThread(user_id=user.id, role=user.role, title=default_title)
        db.add(thread)
        db.commit()
        db.refresh(thread)

    thread_messages = db.scalars(
        select(ChatMessage).where(ChatMessage.thread_id == thread.id).order_by(ChatMessage.created_at)
    ).all()
    history = _thread_history(thread_messages)

    db.add(ChatMessage(thread_id=thread.id, sender="user", content=req.message))
    db.commit()

    result = await agent.run(
        role=user.role,
        user_message=req.message,
        session_id=thread.id,
        history=history,
    )

    db.add(
        ChatMessage(
            thread_id=thread.id,
            sender="assistant",
            content=result["answer"],
            tool_trace_json=json.dumps(result["tool_trace"]),
        )
    )
    if thread.title in {"Patient Chat", "Doctor Chat", "New Chat"}:
        short_message = req.message.strip()[:60]
        thread.title = short_message or thread.title
    thread.updated_at = datetime.utcnow()
    db.commit()

    return ChatResponse(chat_id=thread.id, response=result["answer"], tool_trace=result["tool_trace"])
