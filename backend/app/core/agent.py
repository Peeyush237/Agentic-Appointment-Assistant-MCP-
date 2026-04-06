from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from openai import APIConnectionError, APIStatusError, AsyncOpenAI

from app.core.config import settings
from app.mcp.client import MCPClient


class AgentOrchestrator:
    def __init__(self):
        self.mcp = MCPClient(settings.mcp_server_url)
        self.client = (
            AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=(settings.openai_base_url or None),
            )
            if settings.openai_api_key
            else None
        )

    @staticmethod
    def _friendly_provider_error(exc: Exception) -> str:
        message = str(exc)
        lowered = message.lower()

        if "402" in lowered or "requires more credits" in lowered:
            return (
                "Your LLM provider rejected this request due to credit/token limits. "
                "Reduce token usage or add credits, then retry."
            )
        if "401" in lowered or "invalid api key" in lowered:
            return "Invalid API key. Please verify OPENAI_API_KEY in backend/.env."
        if "429" in lowered or "rate" in lowered:
            return "Rate limited by provider. Please wait a moment and try again."

        return f"LLM provider error: {message}"

    @staticmethod
    def _server_time_context() -> str:
        timezone_name = settings.google_timezone or "UTC"
        try:
            now = datetime.now(ZoneInfo(timezone_name))
        except Exception:  # noqa: BLE001
            timezone_name = "UTC"
            now = datetime.now(ZoneInfo("UTC"))

        return (
            "Current server datetime context (source of truth): "
            f"{now.isoformat()} | day={now.strftime('%A')} | timezone={timezone_name}."
        )

    async def run(
        self,
        role: str,
        user_message: str,
        session_id: str | None = None,
        history: list[dict] | None = None,
    ) -> dict:
        if not self.client:
            return {
                "session_id": session_id or str(uuid4()),
                "answer": "OPENAI_API_KEY is missing. Set it in backend .env to enable LLM orchestration.",
                "tool_trace": [],
            }

        session_id = session_id or str(uuid4())
        history = history or []

        tools = await self.mcp.list_tools()
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
                },
            }
            for tool in tools
        ]

        prompt_name = "doctor_agent_system" if role == "doctor" else "patient_agent_system"
        prompt_response = await self.mcp.get_prompt(prompt_name)
        system_prompt = prompt_response["messages"][0]["content"]["text"]

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": self._server_time_context()},
            *history,
            {"role": "user", "content": user_message},
        ]

        tool_trace = []

        for _ in range(6):
            try:
                completion = await self.client.chat.completions.create(
                    model=settings.openai_model,
                    messages=messages,
                    tools=openai_tools,
                    tool_choice="auto",
                    max_tokens=settings.openai_max_tokens,
                )
            except (APIStatusError, APIConnectionError) as exc:
                return {
                    "session_id": session_id,
                    "answer": self._friendly_provider_error(exc),
                    "tool_trace": tool_trace,
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "session_id": session_id,
                    "answer": self._friendly_provider_error(exc),
                    "tool_trace": tool_trace,
                }
            message = completion.choices[0].message

            if not message.tool_calls:
                answer = message.content or "No response generated"
                return {"session_id": session_id, "answer": answer, "tool_trace": tool_trace}

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in message.tool_calls
                    ],
                }
            )

            for tc in message.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                result = await self.mcp.call_tool(tc.function.name, args)
                text = result["content"][0]["text"]
                tool_trace.append({"tool": tc.function.name, "args": args, "result": json.loads(text)})

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": text,
                    }
                )

        return {
            "session_id": session_id,
            "answer": "Max tool-call iterations reached. Please refine your request.",
            "tool_trace": tool_trace,
        }


agent = AgentOrchestrator()
