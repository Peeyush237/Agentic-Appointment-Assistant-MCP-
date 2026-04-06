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
        <header>
          <h1>Agentic Appointment Assistant (MCP)</h1>
          <p>Sign in as patient or doctor to access your own chat history and appointments.</p>
        </header>

        <section className="authCard">
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
      <header>
        <h1>Agentic Appointment Assistant (MCP)</h1>
        <p>
          Logged in as {user.full_name} ({user.role})
        </p>
      </header>

      <div className="sessionBar">
        <button onClick={onLogout}>
          Logout
        </button>
      </div>

      <ChatPanel token={token} user={user} />
    </main>
  );
}
