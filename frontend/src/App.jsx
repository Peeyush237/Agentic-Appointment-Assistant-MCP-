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
      <main className="appShell authMode">
        <section className="landingShell">
          <div className="landingContent">
            <section className="heroBlock surfaceCard">
              <div className="heroTopbar">
                <span className="pill">MCP</span>
                <span className="pill">Persistent Threads</span>
                <span className="pill">Patient + Doctor</span>
              </div>
              <h1>Agentic Appointment Assistant</h1>
              <p>
                A cinematic, role-based assistant for appointment booking and doctor reporting with continuous chat
                history on every login.
              </p>
            </section>

            <section className="authCard surfaceCard">
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
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="appShell">
      <header className="appHeader surfaceCard">
        <div className="brandBlock">
          <h1>Agentic Appointment Assistant</h1>
          <p>
            Logged in as <strong>{user.full_name}</strong> ({user.role})
          </p>
        </div>
        <div className="sessionBar">
          <span className="pill">Role: {user.role}</span>
          <button onClick={onLogout}>Logout</button>
        </div>
      </header>

      <section className="workspaceSection">
        <ChatPanel token={token} user={user} />
      </section>
    </main>
  );
}
