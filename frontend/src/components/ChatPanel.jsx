import React from "react";
import { useEffect, useState } from "react";
import { createChat, getChatMessages, listChats, sendChat } from "../api/client";

export default function ChatPanel({ token, user }) {
  const [chatId, setChatId] = useState(null);
  const [chats, setChats] = useState([]);
  const [message, setMessage] = useState("");
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);
  const [loadingChats, setLoadingChats] = useState(true);

  useEffect(() => {
    async function load() {
      setLoadingChats(true);
      try {
        const threads = await listChats(token);
        setChats(threads);
        if (threads.length > 0) {
          setChatId(threads[0].id);
        }
      } finally {
        setLoadingChats(false);
      }
    }
    load();
  }, [token]);

  useEffect(() => {
    async function loadMessages() {
      if (!chatId) {
        setItems([]);
        return;
      }
      const history = await getChatMessages(token, chatId);
      setItems(
        history.map((msg) => ({
          from: msg.sender,
          text: msg.content,
          trace: msg.tool_trace,
        }))
      );
    }

    loadMessages();
  }, [chatId, token]);

  async function refreshChats(preferredChatId = null) {
    const threads = await listChats(token);
    setChats(threads);
    if (preferredChatId) {
      setChatId(preferredChatId);
      return;
    }
    if (!chatId && threads.length > 0) {
      setChatId(threads[0].id);
    }
  }

  async function startNewChat() {
    const thread = await createChat(token, "");
    setChatId(thread.id);
    setItems([]);
    await refreshChats(thread.id);
  }

  async function submitText(outgoing) {
    if (!outgoing.trim()) return;

    setItems((prev) => [...prev, { from: "user", text: outgoing }]);
    setBusy(true);

    try {
      const data = await sendChat(token, {
        message: outgoing,
        chat_id: chatId,
      });

      setChatId(data.chat_id);
      setItems((prev) => [
        ...prev,
        {
          from: "assistant",
          text: data.response,
          trace: data.tool_trace,
        },
      ]);
      await refreshChats(data.chat_id);
    } catch (err) {
      setItems((prev) => [...prev, { from: "assistant", text: `Error: ${err.message}` }]);
    } finally {
      setBusy(false);
    }
  }

  async function onSend() {
    const outgoing = message;
    setMessage("");
    await submitText(outgoing);
  }

  return (
    <div className="workspaceGrid">
      <aside className="chatSidebar surfaceCard">
        <div className="chatSidebarHeader">
          <h3>Your Chats</h3>
          <button onClick={startNewChat} disabled={busy}>
            + New
          </button>
        </div>

        {loadingChats ? (
          <p className="hint">Loading chats...</p>
        ) : (
          <div className="chatList">
            {chats.map((thread) => (
              <button
                key={thread.id}
                className={`chatListItem ${thread.id === chatId ? "active" : ""}`}
                onClick={() => setChatId(thread.id)}
              >
                <div className="chatListTitle">{thread.title}</div>
                <div className="chatListMeta">{new Date(thread.updated_at).toLocaleString()}</div>
              </button>
            ))}
            {chats.length === 0 && <p className="hint">No chats yet. Start a new one.</p>}
          </div>
        )}
      </aside>

      <section className="panel surfaceCard">
        <div className="panelTop">
          <h2>{user.role === "patient" ? "Patient Assistant" : "Doctor Report Assistant"}</h2>
          <span className="panelBadge">Live</span>
        </div>
        <p className="hint">
          {user.role === "patient"
            ? "Try: I want to book an appointment with Dr. Ahuja tomorrow morning"
            : "Try: How many patients visited yesterday?"}
        </p>

        <div className="chatWindow">
          {items.map((item, idx) => (
            <div key={idx} className={`bubble ${item.from}`}>
              <div className="bubbleMeta">{item.from === "user" ? "You" : "Assistant"}</div>
              <div>{item.text}</div>
              {item.trace && item.trace.length > 0 && (
                <details>
                  <summary>Tool Trace</summary>
                  <pre>{JSON.stringify(item.trace, null, 2)}</pre>
                </details>
              )}
            </div>
          ))}
        </div>

        <div className="composer">
          <input
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Type your request..."
            disabled={busy}
            onKeyDown={(e) => {
              if (e.key === "Enter") onSend();
            }}
          />
          <button onClick={onSend} disabled={busy}>
            {busy ? "Thinking..." : "Send"}
          </button>
        </div>

        {user.role === "doctor" && (
          <div className="quickActions">
            <button
              disabled={busy}
              onClick={() => submitText("How many appointments do I have today and tomorrow for Dr. Ahuja?")}
            >
              Trigger Daily Summary
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
