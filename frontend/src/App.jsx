import React from "react";
import { useEffect, useState } from "react";
import ChatPanel from "./components/ChatPanel";
import { getMe, login, register } from "./api/client";

const STORAGE_KEY = "appointment_auth";

const PUBLIC_LINKS = [
  {
    key: "github",
    label: "GitHub",
    href: "https://github.com/Peeyush237",
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M12 2a10 10 0 0 0-3.162 19.486c.5.093.682-.217.682-.482 0-.237-.008-.866-.013-1.699-2.775.603-3.36-1.338-3.36-1.338-.455-1.157-1.11-1.465-1.11-1.465-.908-.62.069-.608.069-.608 1.004.07 1.532 1.031 1.532 1.031.893 1.53 2.343 1.088 2.914.832.091-.647.35-1.088.636-1.338-2.216-.252-4.546-1.108-4.546-4.933 0-1.09.39-1.981 1.03-2.679-.104-.252-.447-1.268.098-2.644 0 0 .84-.27 2.75 1.024A9.58 9.58 0 0 1 12 6.844a9.57 9.57 0 0 1 2.504.337c1.909-1.294 2.748-1.024 2.748-1.024.547 1.376.204 2.392.1 2.644.64.698 1.028 1.589 1.028 2.679 0 3.835-2.334 4.678-4.557 4.925.36.31.681.921.681 1.857 0 1.34-.012 2.422-.012 2.751 0 .268.18.58.688.481A10 10 0 0 0 12 2Z"
          fill="currentColor"
        />
      </svg>
    ),
  },
  {
    key: "email",
    label: "Email",
    href: "mailto:peeyush.lyf237@gmail.com",
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M3 5.5A2.5 2.5 0 0 1 5.5 3h13A2.5 2.5 0 0 1 21 5.5v13a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 18.5v-13Zm2 .5v.216l7 4.667 7-4.667V6h-14Zm14 2.618-6.445 4.297a1 1 0 0 1-1.11 0L5 8.618V19h14V8.618Z"
          fill="currentColor"
        />
      </svg>
    ),
  },
  {
    key: "linkedin",
    label: "LinkedIn",
    href: "https://www.linkedin.com/in/peeyush-mishra-23187027b",
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M5.5 3A2.5 2.5 0 1 1 3 5.5 2.5 2.5 0 0 1 5.5 3ZM4 9h3v12H4V9Zm5 0h2.875v1.64h.041c.4-.758 1.379-1.557 2.838-1.557C17.79 9.083 20 11.07 20 14.72V21h-3v-5.569c0-1.328-.024-3.037-1.852-3.037-1.854 0-2.138 1.448-2.138 2.942V21H9V9Z"
          fill="currentColor"
        />
      </svg>
    ),
  },
  {
    key: "resume",
    label: "Resume",
    href: "https://drive.google.com/drive/folders/1KA0Kiv826hwjpqrdAfJx1sRWWsS0hBD6?usp=sharing",
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M6 2.5A2.5 2.5 0 0 0 3.5 5v14A2.5 2.5 0 0 0 6 21.5h12a2.5 2.5 0 0 0 2.5-2.5V9.414a2.5 2.5 0 0 0-.732-1.768l-3.414-3.414A2.5 2.5 0 0 0 14.586 3H6Zm8 1.5v4a2 2 0 0 0 2 2h4V19a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h8Zm-5 9a1 1 0 1 0 0 2h6a1 1 0 1 0 0-2H9Zm0 4a1 1 0 1 0 0 2h6a1 1 0 1 0 0-2H9Z"
          fill="currentColor"
        />
      </svg>
    ),
  },
];

function PublicLinks() {
  return (
    <div className="publicLinks" aria-label="Public profile links">
      {PUBLIC_LINKS.map((item) => (
        <a
          key={item.key}
          className="publicLink"
          href={item.href}
          target={item.href.startsWith("mailto:") ? undefined : "_blank"}
          rel={item.href.startsWith("mailto:") ? undefined : "noopener noreferrer"}
          title={item.label}
        >
          <span className="publicLinkIcon">{item.icon}</span>
          <span>{item.label}</span>
        </a>
      ))}
    </div>
  );
}

export default function App() {
  const [authRole, setAuthRole] = useState("patient");
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [doctorWhatsapp, setDoctorWhatsapp] = useState("");
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
        setDoctorWhatsapp(parsed.doctor_whatsapp_to || "");
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
    const doctorWhatsappToSave = data.user?.role === "doctor" ? doctorWhatsapp.trim() : "";
    const persisted = { ...data, doctor_whatsapp_to: doctorWhatsappToSave };

    setToken(data.token);
    setUser(data.user);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(persisted));
    setAuthError("");
    setEmail("");
    setFullName("");
    setPassword("");
  }

  async function onLogin() {
    setBusy(true);
    setAuthError("");
    try {
      const payload = { email, password, role: authRole };
      if (authRole === "doctor") {
        payload.doctor_whatsapp_to = doctorWhatsapp;
      }
      const data = await login(payload);
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
    setDoctorWhatsapp("");
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
                {authRole === "doctor" && (
                  <input
                    value={doctorWhatsapp}
                    onChange={(e) => setDoctorWhatsapp(e.target.value)}
                    placeholder="Doctor WhatsApp number (+91...)"
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
                <button
                  onClick={onLogin}
                  disabled={busy || !email || !password || (authRole === "doctor" && !doctorWhatsapp.trim())}
                >
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

            <section className="publicLinksCard surfaceCard">
              <h3>Developer Profiles</h3>
              <PublicLinks />
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

      <section className="topLinksBar surfaceCard">
        <PublicLinks />
      </section>

      <section className="workspaceSection">
        <ChatPanel token={token} user={user} doctorWhatsapp={doctorWhatsapp} />
      </section>
    </main>
  );
}
