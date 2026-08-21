import { useState, useEffect, useRef, type ReactElement } from "react";
import "./App.css";


type Message = {
  role: "user" | "assistant";
  question: string;
  sql?: string;
  insights?: {
    text?: string;
    overview?: string;
    key_findings?: string[];
    recommendations?: string[];
    next_steps?: string[];
    data_sources?: string[];
  };
  presentation?: {
    title: string;
    summary: string;
    details: Array<{ title: string; items: string[] }>;
    metadata: { result_count?: number; source_count?: number; has_sql?: boolean };
  };
  data_sources?: Array<{ table: string; columns: string[] }>;
  expandedSections?: Record<string, boolean>;
  showSql?: boolean;
  clarificationRequired?: boolean;
  rows?: Array<Record<string, unknown>>;
};

const SUGGESTIONS = [
  "Which product category generates the most sales?",
  "Show me the top 5 products by sales amount",
  "What caused the revenue change?",
  "Which products had the most returns?",
];

function renderMarkdown(text: string): ReactElement[] {
    const lines = text.split("\n");
  const output: ReactElement[] = [];
  let index = 0;

  const isTableLine = (line: string) => {
    const value = line.trim();
    return value.includes("|") && value.split("|").length >= 3;
  };

  const cells = (line: string) => line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
  const inlineHtml = (value: string) => value.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

  while (index < lines.length) {
    const trimmed = lines[index].trim();
    if (isTableLine(trimmed)) {
      const tableLines: string[] = [];
      while (index < lines.length && isTableLine(lines[index])) {
        tableLines.push(lines[index].trim());
        index += 1;
      }
      const header = cells(tableLines[0]);
      const hasSeparator = tableLines[1]?.split("|").every((cell) => /^\s*:?-{3,}:?\s*$/.test(cell));
      const body = tableLines.slice(hasSeparator ? 2 : 1);
      output.push(
        <div className="markdown-table-wrapper" key={`table-${index}`}>
          <table className="markdown-table">
            <thead><tr>{header.map((cell, cellIndex) => <th key={cellIndex}>{cell}</th>)}</tr></thead>
            <tbody>{body.map((row, rowIndex) => <tr key={rowIndex}>{cells(row).map((cell, cellIndex) => <td key={cellIndex} dangerouslySetInnerHTML={{ __html: inlineHtml(cell) }} />)}</tr>)}</tbody>
          </table>
        </div>,
      );
      continue;
    }
    const inline = inlineHtml(trimmed);
    if (!trimmed) output.push(<br key={index} />);
    else if (trimmed.startsWith("### ")) output.push(<h4 key={index}>{trimmed.slice(4)}</h4>);
    else if (trimmed.startsWith("## ")) output.push(<h3 key={index}>{trimmed.slice(3)}</h3>);
    else if (trimmed.startsWith("# ")) output.push(<h2 key={index}>{trimmed.slice(2)}</h2>);
    else if (/^[-*] /.test(trimmed)) output.push(<p className="markdown-list-item" key={index} dangerouslySetInnerHTML={{ __html: `• ${inline.slice(2)}` }} />);
    else if (/^\d+\. /.test(trimmed)) output.push(<p className="markdown-list-item" key={index} dangerouslySetInnerHTML={{ __html: inline.replace(/^\d+\. /, "") }} />);
    else output.push(<p key={index} dangerouslySetInnerHTML={{ __html: inline }} />);
    index += 1;
  }
  return output;
}

function MarkdownContent({ text }: { text: string }) {
  return <div className="markdown-content">{renderMarkdown(text)}</div>;
}

function formatResultValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "—";
  }

  if (typeof value === "number") {
    return new Intl.NumberFormat("en-IN", {
      maximumFractionDigits: 2,
    }).format(value);
  }

  return String(value);
}

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const saved = localStorage.getItem("theme");

    if (saved === "light" || saved === "dark") return saved;

    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  });

  const lastMessage = messages[messages.length - 1];

  const isAwaitingClarification =
    lastMessage?.role === "assistant" &&
    lastMessage.clarificationRequired === true;
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  async function handleAsk(question: string) {
  if (!question.trim() || loading) return;
  setError("");
  setInput("");
  setLoading(true);
  const questionForApi =
  isAwaitingClarification && lastMessage
    ? `${lastMessage.question}\n\nClarification: ${question}`
    : question;
  const controller = new AbortController();
  abortControllerRef.current = controller;

  const history = messages
    .filter((m) => m.role === "assistant" && m.sql)
    .slice(-3)
    .map((m) => ({ question: m.question, sql: m.sql }));

  setMessages((prev) => [...prev, { role: "user", question }]);

  try {
    const res = await fetch("http://localhost:8000/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: questionForApi, history }),
      signal: controller.signal,
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Something went wrong");

    setMessages((prev) => [
      ...prev,
                  { role: "assistant", question: questionForApi, sql: data.sql, rows: data.rows ?? [], insights: data.insights, presentation: data.presentation, data_sources: data.data_sources ?? [], clarificationRequired: data.clarification_required === true, },
    ]);
  } catch (err: any) {
    if (err.name === "AbortError") {
      setError("Request stopped.");
    } else {
      setError(err.message);
    }
  } finally {
    setLoading(false);
    abortControllerRef.current = null;
  }
}

function handleStop() {
  abortControllerRef.current?.abort();
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
                  {m.clarificationRequired && (
                    <p className="clarification-label">Need clarification</p>
                  )}
                  <article className="answer-content" aria-label="Assistant response">
                    <MarkdownContent
                      text={m.insights?.text ?? m.presentation?.summary ?? m.insights?.overview ?? ""}
                    />
                  </article>


                  {m.rows && m.rows.length > 0 && (m.rows.length > 1 || Object.keys(m.rows[0] || {}).length > 1) && (
                    <div className="data-preview" aria-label="Query data preview">
                      <table className="results-table">
                        <thead><tr>{Object.keys(m.rows[0] || {}).map((column) => <th key={column}>{column}</th>)}</tr></thead>
                        <tbody>{m.rows.slice(0, 20).map((row, rowIndex) => <tr key={rowIndex}>{Object.keys(m.rows?.[0] || {}).map((column) => <td key={column}>{formatResultValue(row[column])}</td>)}</tr>)}</tbody>
                      </table>
                    </div>
                  )}
                  {false && false && (
                    <div className="insight-section">
                      <button
                        type="button"
                        className="insight-section-toggle"
                        onClick={() => undefined}
                        aria-expanded={m.expandedSections?.key_findings ?? false}
                      >
                        <strong>Key findings ({m.insights?.key_findings?.length ?? 0})</strong>
                        <span className="toggle-icon">
                          {m.expandedSections?.key_findings ? "▲" : "▼"}
                        </span>
                      </button>
                      {m.expandedSections?.key_findings && (
                        <ul>
                          {m.insights?.key_findings?.map((point: string, idx: number) => (
                            <li key={idx}>{point}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}

                  {false && false && (
                    <div className="insight-section">
                      <button
                        type="button"
                        className="insight-section-toggle"
                        onClick={() => undefined}
                        aria-expanded={m.expandedSections?.recommendations ?? false}
                      >
                        <strong>Recommendations ({m.insights?.recommendations?.length ?? 0})</strong>
                        <span className="toggle-icon">
                          {m.expandedSections?.recommendations ? "▲" : "▼"}
                        </span>
                      </button>
                      {m.expandedSections?.recommendations && (
                        <ul>
                          {m.insights?.recommendations?.map((point: string, idx: number) => (
                            <li key={idx}>{point}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}

                  {false && false && (
                    <div className="insight-section">
                      <button
                        type="button"
                        className="insight-section-toggle"
                        onClick={() => undefined}
                        aria-expanded={m.expandedSections?.next_steps ?? false}
                      >
                        <strong>Next steps ({m.insights?.next_steps?.length ?? 0})</strong>
                        <span className="toggle-icon">
                          {m.expandedSections?.next_steps ? "▲" : "▼"}
                        </span>
                      </button>
                      {m.expandedSections?.next_steps && (
                        <ul>
                          {m.insights?.next_steps?.map((point: string, idx: number) => (
                            <li key={idx}>{point}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}

                  {false && false && (
                    <div className="insight-section">
                      <button
                        type="button"
                        className="insight-section-toggle"
                        onClick={() => undefined}
                        aria-expanded={m.expandedSections?.data_sources ?? false}
                      >
                        <strong>Data sources ({m.data_sources?.length ?? 0})</strong>
                        <span className="toggle-icon">
                          {m.expandedSections?.data_sources ? "▲" : "▼"}
                        </span>
                      </button>
                      {m.expandedSections?.data_sources && (
                        <ul>
                          {m.data_sources?.map((source, idx: number) => (
                            <li key={idx}>
                              <code>{source.table}</code>: {source.columns.join(", ")}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                  {m.sql && (
                    <details className="sql-details">
                      <summary>View query details</summary>
                      <div className="msg-actions">
                        <button onClick={() => copySql(m.sql ?? "")}>Copy SQL</button>
                        <button onClick={() => toggleSql(i)}>
                          {m.showSql ? "Hide query" : "Show query"}
                        </button>
                      </div>
                      {m.showSql && <pre className="sql-block">{m.sql}</pre>}
                    </details>
                  )}
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
          {isAwaitingClarification}
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAsk(input)}
            placeholder={
              isAwaitingClarification
                ? "Tell me which data area you mean..."
                : "Ask anything about your business data..."
            }
          />
          {loading ? (
            <button className="send-btn" onClick={handleStop}>
              Stop
            </button>
          ) : (
            <button className="send-btn" onClick={() => handleAsk(input)} disabled={loading}>
              Send
            </button>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
