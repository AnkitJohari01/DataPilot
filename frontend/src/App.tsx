import { useState, useEffect, useRef, Fragment, type ReactElement } from "react";
import "./App.css";
import { Bar, BarChart, Line, LineChart, ComposedChart, Pie, PieChart, Cell, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Funnel, FunnelChart, LabelList, Treemap, Area, AreaChart } from "recharts";

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

 const isTableLine = (_line: string) => false;

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
    if (!trimmed) { index += 1; continue; }
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


type ChartType = "bar" | "pie" | "line" | "combo" | "scatter" | "funnel" | "treemap" | "heatmap" | "ribbon" | "waterfall";

const CHART_COLORS = ["#C96442", "#4E9F6E", "#5B8DEF", "#D9A441", "#9B6BD9", "#4EA0A0"];

function wantsChart(question: string): boolean {
  return /chart|graph|plot|visuali[sz]e|trend|analy[sz]e|analysis|scatter|funnel|treemap|heatmap|heat map|ribbon|waterfall|clustered/i.test(question);
}

function detectChartTypeFromQuestion(question: string): ChartType | null {
  if (/waterfall/i.test(question)) return "waterfall";
  if (/heat\s?map/i.test(question)) return "heatmap";
  if (/ribbon/i.test(question)) return "ribbon";
  if (/funnel/i.test(question)) return "funnel";
  if (/tree\s?map/i.test(question)) return "treemap";
  if (/scatter/i.test(question)) return "scatter";
  if (/clustered|combo|column.*line|line.*column/i.test(question)) return "combo";
  if (/pie/i.test(question)) return "pie";
  if (/\bline\b/i.test(question)) return "line";
  if (/\bbar\b/i.test(question)) return "bar";
  return null;
}

function pickChartTypeFromShape(rows: Array<Record<string, unknown>>): ChartType {
  const keys = Object.keys(rows[0] || {});
  const numericKeys = keys.filter((k) => typeof rows[0][k] === "number");
  const textKeys = keys.filter((k) => !numericKeys.includes(k));
  if (textKeys.length >= 2 && numericKeys.length >= 1) return "heatmap";
  if (textKeys.length === 0 && numericKeys.length >= 2) return "scatter";
  const labelKey = textKeys[0] ?? keys[0];
  if (/date|month|year|period|week/i.test(labelKey)) return "line";
  if (rows.length <= 6 && numericKeys.length === 1) return "pie";
  if (numericKeys.length >= 2) return "combo";
  return "bar";
}

function resolveChartType(question: string, rows: Array<Record<string, unknown>>): ChartType {
  return detectChartTypeFromQuestion(question) ?? pickChartTypeFromShape(rows);
}

function HeatmapView({ rows, xKey, yKey, valueKey }: { rows: Array<Record<string, unknown>>; xKey: string; yKey: string; valueKey: string }) {
  const xValues = Array.from(new Set(rows.map((r) => String(r[xKey] ?? ""))));
  const yValues = Array.from(new Set(rows.map((r) => String(r[yKey] ?? ""))));
  const lookup = new Map(rows.map((r) => [`${r[yKey]}|${r[xKey]}`, Number(r[valueKey]) || 0]));
  const max = Math.max(...rows.map((r) => Number(r[valueKey]) || 0), 1);

  return (
    <div className="chart-wrapper heatmap-grid" style={{ gridTemplateColumns: `120px repeat(${xValues.length}, 1fr)` }}>
      <div />
      {xValues.map((x) => <div key={x} className="heatmap-label">{x}</div>)}
      {yValues.map((y) => (
        <Fragment key={y}>
          <div className="heatmap-label">{y}</div>
          {xValues.map((x) => {
            const v = lookup.get(`${y}|${x}`) ?? 0;
            const intensity = v / max;
            return (
              <div key={`${y}-${x}`} className="heatmap-cell" style={{ background: `rgba(201, 100, 66, ${0.1 + intensity * 0.8})` }} title={`${y} / ${x}: ${v}`}>
                {v ? v.toLocaleString() : "—"}
              </div>
            );
          })}
        </Fragment>
      ))}
    </div>
  );
}

function WaterfallChart({ rows, labelKey, valueKey }: { rows: Array<Record<string, unknown>>; labelKey: string; valueKey: string }) {
  let running = 0;
  const data = rows.slice(0, 20).map((row) => {
    const value = Number(row[valueKey]) || 0;
    const start = running;
    running += value;
    return { name: String(row[labelKey] ?? ""), base: Math.min(start, running), delta: Math.abs(value), rising: value >= 0 };
  });
  const tooltipStyle = { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8 };

  return (
    <div className="chart-wrapper">
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="name" stroke="var(--text-muted)" fontSize={12} />
          <YAxis stroke="var(--text-muted)" fontSize={12} />
          <Tooltip contentStyle={tooltipStyle} />
          <Bar dataKey="base" stackId="wf" fill="transparent" />
          <Bar dataKey="delta" stackId="wf" radius={[4, 4, 4, 4]}>
            {data.map((d, i) => <Cell key={i} fill={d.rising ? "var(--success)" : "var(--error)"} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function RibbonChart({ rows, labelKey, groupKey, valueKey }: { rows: Array<Record<string, unknown>>; labelKey: string; groupKey: string; valueKey: string }) {
  const groups = Array.from(new Set(rows.map((r) => String(r[groupKey] ?? ""))));
  const points = Array.from(new Set(rows.map((r) => String(r[labelKey] ?? ""))));
  const data = points.map((p) => {
    const point: Record<string, unknown> = { name: p };
    groups.forEach((g) => {
      const match = rows.find((r) => String(r[labelKey]) === p && String(r[groupKey]) === g);
      point[g] = match ? Number(match[valueKey]) || 0 : 0;
    });
    return point;
  });
  const tooltipStyle = { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8 };

  return (
    <div className="chart-wrapper">
      <ResponsiveContainer width="100%" height={280}>
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="name" stroke="var(--text-muted)" fontSize={12} />
          <YAxis stroke="var(--text-muted)" fontSize={12} />
          <Tooltip contentStyle={tooltipStyle} />
          {groups.map((g, i) => (
            <Area key={g} type="monotone" dataKey={g} stackId="ribbon" stroke={CHART_COLORS[i % CHART_COLORS.length]} fill={CHART_COLORS[i % CHART_COLORS.length]} fillOpacity={0.55} />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function ChartView({ rows, question }: { rows: Array<Record<string, unknown>>; question: string }) {
  if (!rows.length) return null;
  const keys = Object.keys(rows[0] || {});
  const numericKeys = keys.filter((k) => typeof rows[0][k] === "number");
  const textKeys = keys.filter((k) => !numericKeys.includes(k));
  const labelKey = textKeys[0] ?? keys[0];
  const secondLabelKey = textKeys[1];
  const valueKey = numericKeys[0];
  if (!valueKey) return null;

  const type = resolveChartType(question, rows);
  const tooltipStyle = { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8 };
  const data = rows.slice(0, 20).map((row) => {
    const point: Record<string, unknown> = { name: String(row[labelKey] ?? "") };
    numericKeys.forEach((k) => { point[k] = Number(row[k]) || 0; });
    return point;
  });

  if (type === "heatmap" && secondLabelKey) {
    return <HeatmapView rows={rows} xKey={secondLabelKey} yKey={labelKey} valueKey={valueKey} />;
  }
  if (type === "waterfall") {
    return <WaterfallChart rows={rows} labelKey={labelKey} valueKey={valueKey} />;
  }
  if (type === "ribbon" && secondLabelKey) {
    return <RibbonChart rows={rows} labelKey={labelKey} groupKey={secondLabelKey} valueKey={valueKey} />;
  }
  if (type === "scatter" && numericKeys.length >= 2) {
    return (
      <div className="chart-wrapper">
        <ResponsiveContainer width="100%" height={280}>
          <ScatterChart>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey={numericKeys[0]} name={numericKeys[0]} stroke="var(--text-muted)" fontSize={12} />
            <YAxis dataKey={numericKeys[1]} name={numericKeys[1]} stroke="var(--text-muted)" fontSize={12} />
            <Tooltip contentStyle={tooltipStyle} cursor={{ strokeDasharray: "3 3" }} />
            <Scatter data={data} fill="var(--accent)" />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    );
  }
  if (type === "funnel") {
    const funnelData = [...data].sort((a, b) => Number(b[valueKey]) - Number(a[valueKey]));
    return (
      <div className="chart-wrapper">
        <ResponsiveContainer width="100%" height={280}>
          <FunnelChart>
            <Tooltip contentStyle={tooltipStyle} />
            <Funnel dataKey={valueKey} data={funnelData} isAnimationActive>
              {funnelData.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
              <LabelList dataKey="name" position="right" fill="var(--text)" />
            </Funnel>
          </FunnelChart>
        </ResponsiveContainer>
      </div>
    );
  }
  if (type === "treemap") {
    return (
      <div className="chart-wrapper">
        <ResponsiveContainer width="100%" height={280}>
          <Treemap data={data.map((d) => ({ name: d.name, size: d[valueKey] }))} dataKey="size" stroke="var(--surface)" fill="var(--accent)" />
        </ResponsiveContainer>
      </div>
    );
  }
  if (type === "combo" && numericKeys.length >= 2) {
    return (
      <div className="chart-wrapper">
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="name" stroke="var(--text-muted)" fontSize={12} />
            <YAxis stroke="var(--text-muted)" fontSize={12} />
            <Tooltip contentStyle={tooltipStyle} />
            <Bar dataKey={numericKeys[0]} fill="var(--accent)" radius={[6, 6, 0, 0]} />
            <Line type="monotone" dataKey={numericKeys[1]} stroke="var(--success)" strokeWidth={2} dot={{ r: 3 }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    );
  }
  if (type === "pie") {
    return (
      <div className="chart-wrapper">
        <ResponsiveContainer width="100%" height={280}>
          <PieChart>
            <Pie data={data} dataKey={valueKey} nameKey="name" outerRadius={100} label>
              {data.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
            </Pie>
            <Tooltip contentStyle={tooltipStyle} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    );
  }
  if (type === "line") {
    return (
      <div className="chart-wrapper">
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="name" stroke="var(--text-muted)" fontSize={12} />
            <YAxis stroke="var(--text-muted)" fontSize={12} />
            <Tooltip contentStyle={tooltipStyle} />
            <Line type="monotone" dataKey={valueKey} stroke="var(--accent)" strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  }
  return (
    <div className="chart-wrapper">
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="name" stroke="var(--text-muted)" fontSize={12} />
          <YAxis stroke="var(--text-muted)" fontSize={12} />
          <Tooltip contentStyle={tooltipStyle} />
          <Bar dataKey={valueKey} fill="var(--accent)" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
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

                  {m.rows && m.rows.length > 0 && wantsChart(m.question) && (
                    <ChartView rows={m.rows} question={m.question} />
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
