import { useState, useEffect } from "react";
import "./App.css";

type Message = {
  role: "user" | "assistant";
  question: string;
  sql?: string;
  insights?: { what_happened: string; why: string; next_steps: string };
  showSql?: boolean;
};

const SUGGESTIONS = [
  "Why did sales decrease this month?",
  "Show my top-performing products",
  "What caused the revenue change?",
  "Compare this month with last month",
];

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const saved = localStorage.getItem("theme");
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  async function handleAsk(question: string) {
    if (!question.trim() || loading) return;
    setError("");
    setInput("");
    setLoading(true);

    const history = messages
      .filter((m) => m.role === "assistant" && m.sql)
      .slice(-3)
      .map((m) => ({ question: m.question, sql: m.sql }));

    setMessages((prev) => [...prev, { role: "user", question }]);

    try {
      const res = await fetch("http://localhost:8000/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, history }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Something went wrong");

      setMessages((prev) => [
        ...prev,
        { role: "assistant", question, sql: data.sql, insights: data.insights },
      ]);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function toggleSql(index: number) {
    setMessages((prev) =>
      prev.map((m, i) => (i === index ? { ...m, showSql: !m.showSql } : m))
    );
  }

  function copySql(sql: string) {
    navigator.clipboard.writeText(sql);
  }

  return (
    <div className="app">
      {sidebarOpen && (
        <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />
      )}

      <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
        <button className="sidebar-close" onClick={() => setSidebarOpen(false)} aria-label="Close menu">
          ✕
        </button>

        <div className="sidebar-logo">
          <span className="logo-mark">DP</span>
          DataPilot
        </div>

        <button className="new-chat-btn" onClick={() => setMessages([])} aria-label="Start a new chat">
          <span>+</span> New Chat
        </button>

        <nav className="sidebar-nav">
          <button className="nav-item active" aria-label="Recent Chats">Recent Chats</button>
          <button className="nav-item" aria-label="Saved Insights">Saved Insights</button>
          <button className="nav-item" aria-label="Data Sources">Data Sources</button>
        </nav>

        <div className="sidebar-footer">
          <button className="nav-item muted" aria-label="Settings">Settings</button>
          <button className="nav-item muted" aria-label="Help & Support">Help & Support</button>
        </div>
      </aside>

      <main className="main">
        <header className="main-header">
          <div className="header-left">
            <button className="hamburger" onClick={() => setSidebarOpen(true)} aria-label="Open menu">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>
            <div>
              <h1>DataPilot</h1>
              <p className="subtitle">AI-powered business intelligence</p>
            </div>
          </div>

          <div className="header-right">
            <div className="status">
              <span className="status-dot" />
              Connected to: Sales Database
            </div>
            <button
              className="theme-toggle"
              onClick={() => setTheme(theme === "light" ? "dark" : "light")}
              aria-label="Toggle theme"
            >
              {theme === "light" ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="5" />
                  <line x1="12" y1="1" x2="12" y2="3" />
                  <line x1="12" y1="21" x2="12" y2="23" />
                  <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                  <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                  <line x1="1" y1="12" x2="3" y2="12" />
                  <line x1="21" y1="12" x2="23" y2="12" />
                  <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                  <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
                </svg>
              )}
            </button>
            <div className="avatar">AJ</div>
          </div>
        </header>

        <div className="conversation">
          {messages.length === 0 && (
            <div className="empty-state">
              <h2>How can DataPilot help you today?</h2>
              <p>Ask questions about your business data in plain English.</p>
              <div className="suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s} className="suggestion-card" onClick={() => handleAsk(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="msg-row user-row">
                <div className="msg user-msg">{m.question}</div>
              </div>
            ) : (
              <div key={i} className="msg-row assistant-row">
                <div className="msg assistant-msg">
                  <p className="insight-line">{m.insights?.what_happened}</p>
                  <p className="insight-sub">
                    <strong>Why: </strong>
                    {m.insights?.why}
                  </p>
                  <p className="insight-sub">
                    <strong>Next steps: </strong>
                    {m.insights?.next_steps}
                  </p>

                  <div className="msg-actions">
                    <button onClick={() => copySql(m.sql || "")}>Copy SQL</button>
                    <button onClick={() => toggleSql(i)}>
                      {m.showSql ? "Hide SQL" : "View SQL"}
                    </button>
                  </div>

                  {m.showSql && <pre className="sql-block">{m.sql}</pre>}
                </div>
              </div>
            )
          )}

          {loading && (
            <div className="analyzing">
              <span className="pulse-dot" />
              Analyzing your business data...
            </div>
          )}
          {error && <div className="error-banner">{error}</div>}
        </div>

        <div className="input-bar">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAsk(input)}
            placeholder="Ask anything about your business data..."
          />
          <button className="send-btn" onClick={() => handleAsk(input)} disabled={loading}>
            Send
          </button>
        </div>
      </main>
    </div>
  );
}

export default App;