import React from "react";
import { useEffect, useState } from "react";
import ChatPanel from "./components/ChatPanel";
import { getMe, login, register } from "./api/client";

const STORAGE_KEY = "appointment_auth";

export default function App() {
  const [authRole, setAuthRole] = useState("patient");
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [user, setUser] = useState(null);
  const [busy, setBusy] = useState(false);
  const [authError, setAuthError] = useState("");

  useEffect(() => {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw);
      if (parsed?.token) {
        setToken(parsed.token);
        setUser(parsed.user || null);
      }
    } catch {
      localStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  useEffect(() => {
    if (!token) return;
    getMe(token)
      .then((me) => {
        setUser(me);
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ token, user: me }));
      })
      .catch(() => {
        setToken("");
        setUser(null);
        localStorage.removeItem(STORAGE_KEY);
      });
  }, [token]);

  function persistAuth(data) {
    setToken(data.token);
    setUser(data.user);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    setAuthError("");
    setEmail("");
    setFullName("");
    setPassword("");
  }

  async function onLogin() {
    setBusy(true);
    setAuthError("");
    try {
      const data = await login({ email, password, role: authRole });
      persistAuth(data);
    } catch (err) {
      setAuthError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function onRegister() {
    if (authRole !== "patient") {
      setAuthError("Doctor accounts are provisioned by the system. Use doctor login.");
      return;
    }

    setBusy(true);
    setAuthError("");
    try {
      const data = await register({ email, full_name: fullName, password });
      persistAuth(data);
    } catch (err) {
      setAuthError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function onLogout() {
    setToken("");
    setUser(null);
    localStorage.removeItem(STORAGE_KEY);
  }

  if (!token || !user) {
    return (
      <main className="container">
        <section className="heroBlock brutalCard">
          <div className="heroTopbar">
            <span className="pill">MCP</span>
            <span className="pill">Auth</span>
            <span className="pill">Calendar</span>
          </div>
          <h1>Agentic Appointment Assistant</h1>
          <p>Brutalist edition. Login as patient or doctor to unlock your own persistent chats and booking history.</p>
        </section>

        <section className="authCard brutalCard">
          <h2>{authRole === "patient" ? "Patient Access" : "Doctor Access"}</h2>

          <div className="roleToggle">
            <button className={authRole === "patient" ? "active" : ""} onClick={() => setAuthRole("patient")}>
              Patient Login
            </button>
            <button className={authRole === "doctor" ? "active" : ""} onClick={() => setAuthRole("doctor")}>
              Doctor Login
            </button>
          </div>

          <div className="authFields">
            {authRole === "patient" && (
              <input
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Full name (for register)"
                disabled={busy}
              />
            )}
            <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" disabled={busy} />
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              disabled={busy}
            />
          </div>

          <div className="authActions">
            <button onClick={onLogin} disabled={busy || !email || !password}>
              {busy ? "Please wait..." : "Login"}
            </button>
            {authRole === "patient" && (
              <button onClick={onRegister} disabled={busy || !email || !password || !fullName}>
                {busy ? "Please wait..." : "Register + Login"}
              </button>
            )}
          </div>

          {authError && <p className="authError">{authError}</p>}
        </section>
      </main>
    );
  }

  return (
    <main className="container">
      <header className="appHeader brutalCard">
        <div>
          <h1>Agentic Appointment Assistant</h1>
          <p>
            Logged in as <strong>{user.full_name}</strong> ({user.role})
          </p>
        </div>
        <div className="sessionBar">
          <button onClick={onLogout}>Logout</button>
        </div>
      </header>

      <div className="dashboardTags">
        <span className="pill">Role: {user.role}</span>
        <span className="pill">Stored Threads</span>
        <span className="pill">LLM + MCP Tools</span>
      </div>

      <ChatPanel token={token} user={user} />
    </main>
  );
}
