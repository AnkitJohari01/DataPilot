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

type ChatSession = {
  id: string;
  title: string;
  messages: Message[];
  createdAt: number;
  updatedAt: number;
};

const SESSIONS_STORAGE_KEY = "datapilot_sessions";

function loadSessions(): ChatSession[] {
  try {
    const raw = localStorage.getItem(SESSIONS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function makeSessionTitle(question: string): string {
  const trimmed = question.trim().replace(/\s+/g, " ");
  if (!trimmed) return "New chat";
  return trimmed.length > 42 ? `${trimmed.slice(0, 42)}…` : trimmed;
}

function formatRelativeTime(timestamp: number): string {
  const diffMin = Math.round((Date.now() - timestamp) / 60000);
  if (diffMin < 1) return "Just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  if (diffDay < 7) return `${diffDay}d ago`;
  return new Date(timestamp).toLocaleDateString();
}

type SavedInsight = {
  id: string;
  key: string; // `${sessionId}-${messageIndex}` — used to detect "already saved"
  question: string;
  answerText: string;
  sql?: string;
  sessionId: string | null;
  savedAt: number;
};

const SAVED_INSIGHTS_STORAGE_KEY = "datapilot_saved_insights";

function loadSavedInsights(): SavedInsight[] {
  try {
    const raw = localStorage.getItem(SAVED_INSIGHTS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

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

const EXPLICIT_CHART_HINT = /chart|graph|plot|visuali[sz]e|scatter|funnel|treemap|heatmap|heat map|ribbon|waterfall|clustered|\bpie\b|\bline\b|\bbar\b/i;

// Shows a chart when the question explicitly asks for one, OR when the
// returned rows are naturally chartable: more than one row, at least one
// label-like column, and at least one numeric column. A single-row answer
// (e.g. "what's total profit?") or a purely text/list answer won't qualify.
function wantsChart(question: string, rows: Array<Record<string, unknown>>): boolean {
  if (EXPLICIT_CHART_HINT.test(question)) return true;
  if (!rows || rows.length < 2) return false;
  const keys = Object.keys(rows[0] || {});
  const numericKeys = keys.filter((k) => typeof rows[0][k] === "number");
  const hasLabel = keys.some((k) => !numericKeys.includes(k));
  return numericKeys.length >= 1 && hasLabel;
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


type CatalogColumn = {
  name: string;
  type: string;
  nullable: boolean;
  role: string;
  sample_values: unknown[];
};

type CatalogTable = {
  name: string;
  primary_key: string[];
  relationships: Array<{
    column: string[];
    references_table: string;
    references_column: string[];
  }>;
  columns: CatalogColumn[];
};

type Catalog = { tables: CatalogTable[] };

function DataSourcesView({
  catalog,
  loading,
  error,
  expandedTables,
  onToggleTable,
  onRefresh,
}: {
  catalog: Catalog | null;
  loading: boolean;
  error: string;
  expandedTables: Record<string, boolean>;
  onToggleTable: (name: string) => void;
  onRefresh: () => void;
}) {
  return (
    <div className="data-sources">
      <div className="data-sources-header">
        <div>
          <h2>Connected data</h2>
          <p>Tables and columns DataPilot can query in the sales database.</p>
        </div>
        <button className="refresh-btn" onClick={onRefresh} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {loading && !catalog && (
        <div className="analyzing">
          <span className="pulse-dot" />
          Loading data sources...
        </div>
      )}

      {catalog && (
        <div className="table-list">
          {catalog.tables.map((table) => {
            const expanded = expandedTables[table.name] ?? false;
            return (
              <div className="table-card" key={table.name}>
                <button
                  className="table-card-header"
                  onClick={() => onToggleTable(table.name)}
                  aria-expanded={expanded}
                >
                  <span className="table-card-name">
                    <code>{table.name}</code>
                    <span className="table-card-count">
                      {table.columns.length} column{table.columns.length === 1 ? "" : "s"}
                    </span>
                  </span>
                  <span className="toggle-icon">{expanded ? "▲" : "▼"}</span>
                </button>

                {expanded && (
                  <div className="table-card-body">
                    {table.primary_key.length > 0 && (
                      <p className="table-meta">
                        <strong>Primary key:</strong> {table.primary_key.join(", ")}
                      </p>
                    )}
                    {table.relationships.length > 0 && (
                      <p className="table-meta">
                        <strong>Relationships:</strong>{" "}
                        {table.relationships
                          .map(
                            (r) =>
                              `${r.column.join(", ")} → ${r.references_table}(${r.references_column.join(", ")})`
                          )
                          .join("; ")}
                      </p>
                    )}
                    <table className="column-table">
                      <thead>
                        <tr>
                          <th>Column</th>
                          <th>Type</th>
                          <th>Role</th>
                          <th>Examples</th>
                        </tr>
                      </thead>
                      <tbody>
                        {table.columns.map((col) => (
                          <tr key={col.name}>
                            <td><code>{col.name}</code></td>
                            <td>{col.type}</td>
                            <td>{col.role}</td>
                            <td>
                              {col.sample_values.length > 0
                                ? col.sample_values.map((v) => String(v)).join(", ")
                                : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function SettingsView({
  theme,
  onSetTheme,
  apiBaseUrl,
  onApiBaseUrlChange,
  sessionsCount,
  savedInsightsCount,
  onClearChats,
  onClearSavedInsights,
}: {
  theme: "light" | "dark";
  onSetTheme: (theme: "light" | "dark") => void;
  apiBaseUrl: string;
  onApiBaseUrlChange: (value: string) => void;
  sessionsCount: number;
  savedInsightsCount: number;
  onClearChats: () => void;
  onClearSavedInsights: () => void;
}) {
  return (
    <div className="data-sources">
      <div className="data-sources-header">
        <div>
          <h2>Settings</h2>
          <p>Preferences and connection settings, stored on this device.</p>
        </div>
      </div>

      <section className="settings-section">
        <h3>Appearance</h3>
        <div className="settings-row">
          <div>
            <p className="settings-row-title">Theme</p>
            <p className="settings-row-desc">Switch between light and dark mode.</p>
          </div>
          <div className="theme-switch">
            <button
              className={theme === "light" ? "active" : ""}
              onClick={() => onSetTheme("light")}
            >
              Light
            </button>
            <button
              className={theme === "dark" ? "active" : ""}
              onClick={() => onSetTheme("dark")}
            >
              Dark
            </button>
          </div>
        </div>
      </section>

      <section className="settings-section">
        <h3>Connection</h3>
        <div className="settings-row">
          <div>
            <p className="settings-row-title">Backend URL</p>
            <p className="settings-row-desc">Where the DataPilot API is running.</p>
          </div>
          <input
            type="text"
            className="settings-input"
            value={apiBaseUrl}
            onChange={(e) => onApiBaseUrlChange(e.target.value)}
            placeholder="http://localhost:8000"
          />
        </div>
      </section>

      <section className="settings-section">
        <h3>Data</h3>
        <div className="settings-row">
          <div>
            <p className="settings-row-title">Chat history</p>
            <p className="settings-row-desc">
              {sessionsCount} saved chat{sessionsCount === 1 ? "" : "s"} on this device.
            </p>
          </div>
          <button className="danger-btn" onClick={onClearChats} disabled={sessionsCount === 0}>
            Clear all chats
          </button>
        </div>
        <div className="settings-row">
          <div>
            <p className="settings-row-title">Saved insights</p>
            <p className="settings-row-desc">
              {savedInsightsCount} saved insight{savedInsightsCount === 1 ? "" : "s"} on this device.
            </p>
          </div>
          <button
            className="danger-btn"
            onClick={onClearSavedInsights}
            disabled={savedInsightsCount === 0}
          >
            Clear all insights
          </button>
        </div>
      </section>
    </div>
  );
}

const FAQ_ITEMS: Array<{ q: string; a: string }> = [
  {
    q: "Why does DataPilot ask me to clarify a question?",
    a: "When a question could reasonably match more than one data area (for example, several tables score similarly), DataPilot asks which one you meant instead of guessing. Answering directly — e.g. \"products\" — resolves it and continues.",
  },
  {
    q: "How do I see the SQL behind an answer?",
    a: "Open \"View query details\" underneath any answer to expand the generated SQL, and use \"Copy SQL\" to copy it.",
  },
  {
    q: "Where is my chat history stored?",
    a: "Chats and saved insights are stored locally in your browser (localStorage), not on a server. Clearing your browser data will remove them. You can also clear them yourself from Settings.",
  },
  {
    q: "Can I point DataPilot at a different backend?",
    a: "Yes — go to Settings and update the Backend URL. It defaults to http://localhost:8000.",
  },
  {
    q: "What kinds of questions can I ask?",
    a: "Anything about the connected sales database: revenue, orders, products, customers, regions, ship modes, and time trends. Check the Data Sources tab to see exactly which tables and columns are available.",
  },
];

function HelpView({ apiBaseUrl }: { apiBaseUrl: string }) {
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  const [checking, setChecking] = useState(false);
  const [apiStatus, setApiStatus] = useState<"unknown" | "ok" | "down">("unknown");
  const [dbStatus, setDbStatus] = useState<"unknown" | "ok" | "down">("unknown");

  async function runHealthCheck() {
    setChecking(true);
    const base = apiBaseUrl.trim().replace(/\/$/, "") || "http://localhost:8000";

    try {
      const res = await fetch(`${base}/api/health`);
      setApiStatus(res.ok ? "ok" : "down");
    } catch {
      setApiStatus("down");
    }

    try {
      const res = await fetch(`${base}/api/health/db`);
      setDbStatus(res.ok ? "ok" : "down");
    } catch {
      setDbStatus("down");
    }

    setChecking(false);
  }

  function statusLabel(status: "unknown" | "ok" | "down") {
    if (status === "ok") return { text: "Connected", cls: "status-ok" };
    if (status === "down") return { text: "Unreachable", cls: "status-down" };
    return { text: "Not checked yet", cls: "status-unknown" };
  }

  const api = statusLabel(apiStatus);
  const db = statusLabel(dbStatus);

  return (
    <div className="data-sources">
      <div className="data-sources-header">
        <div>
          <h2>Help &amp; Support</h2>
          <p>Answers to common questions, and a quick connection check.</p>
        </div>
      </div>

      <section className="settings-section">
        <h3>Connection check</h3>
        <div className="settings-row">
          <div>
            <p className="settings-row-title">API server</p>
            <p className={`settings-row-desc health-status ${api.cls}`}>{api.text}</p>
          </div>
          <div>
            <p className="settings-row-title">Database</p>
            <p className={`settings-row-desc health-status ${db.cls}`}>{db.text}</p>
          </div>
          <button className="refresh-btn" onClick={runHealthCheck} disabled={checking}>
            {checking ? "Checking…" : "Run check"}
          </button>
        </div>
      </section>

      <section className="settings-section">
        <h3>Frequently asked questions</h3>
        {FAQ_ITEMS.map((item, i) => (
          <div className="faq-item" key={item.q}>
            <button
              className="faq-question"
              onClick={() => setOpenFaq(openFaq === i ? null : i)}
              aria-expanded={openFaq === i}
            >
              <span>{item.q}</span>
              <span className="toggle-icon">{openFaq === i ? "▲" : "▼"}</span>
            </button>
            {openFaq === i && <p className="faq-answer">{item.a}</p>}
          </div>
        ))}
      </section>
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

  const [sessions, setSessions] = useState<ChatSession[]>(() => loadSessions());
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const skipNextSyncRef = useRef(false);

  useEffect(() => {
    localStorage.setItem(SESSIONS_STORAGE_KEY, JSON.stringify(sessions));
  }, [sessions]);

  // Keep the active session's stored messages in sync with what's on screen,
  // creating a new session the first time a message lands in a fresh chat.
  useEffect(() => {
    if (skipNextSyncRef.current) {
      skipNextSyncRef.current = false;
      return;
    }
    if (messages.length === 0) return;

    const firstUserMessage = messages.find((m) => m.role === "user");
    const title = makeSessionTitle(firstUserMessage?.question ?? "");
    const sessionId =
      activeSessionId ??
      `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

    if (!activeSessionId) {
      setActiveSessionId(sessionId);
    }

    setSessions((prev) => {
      const exists = prev.some((s) => s.id === sessionId);
      if (exists) {
        return prev.map((s) =>
          s.id === sessionId
            ? { ...s, messages, title, updatedAt: Date.now() }
            : s
        );
      }
      return [
        { id: sessionId, title, messages, createdAt: Date.now(), updatedAt: Date.now() },
        ...prev,
      ];
    });
  }, [messages, activeSessionId]);

  function startNewChat() {
    setMessages([]);
    setActiveSessionId(null);
  }

  function selectSession(id: string) {
    const target = sessions.find((s) => s.id === id);
    if (!target || id === activeSessionId) {
      setSidebarOpen(false);
      return;
    }
    skipNextSyncRef.current = true;
    setActiveSessionId(id);
    setMessages(target.messages);
    setSidebarOpen(false);
  }

  function deleteSession(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    setSessions((prev) => prev.filter((s) => s.id !== id));
    if (id === activeSessionId) {
      setActiveSessionId(null);
      setMessages([]);
    }
  }

  const sortedSessions = [...sessions].sort((a, b) => b.updatedAt - a.updatedAt);

  const [activeNav, setActiveNav] = useState<"chats" | "insights" | "sources" | "settings" | "help">("chats");
  const [savedInsights, setSavedInsights] = useState<SavedInsight[]>(() => loadSavedInsights());

  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState("");
  const [expandedTables, setExpandedTables] = useState<Record<string, boolean>>({});

  async function fetchCatalog() {
    setCatalogLoading(true);
    setCatalogError("");
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/catalog`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to load data sources");
      setCatalog(data);
    } catch (err: any) {
      setCatalogError(err.message || "Failed to load data sources");
    } finally {
      setCatalogLoading(false);
    }
  }

  function openDataSources() {
    setActiveNav("sources");
    setSidebarOpen(false);
    if (!catalog && !catalogLoading) {
      fetchCatalog();
    }
  }

  function toggleTableExpanded(name: string) {
    setExpandedTables((prev) => ({ ...prev, [name]: !prev[name] }));
  }

  useEffect(() => {
    localStorage.setItem(SAVED_INSIGHTS_STORAGE_KEY, JSON.stringify(savedInsights));
  }, [savedInsights]);

  function getMessageKey(index: number) {
    return `${activeSessionId ?? "unsaved"}-${index}`;
  }

  function isMessageSaved(index: number) {
    return savedInsights.some((s) => s.key === getMessageKey(index));
  }

  function toggleSaveInsight(m: Message, index: number) {
    const key = getMessageKey(index);
    setSavedInsights((prev) => {
      const exists = prev.some((s) => s.key === key);
      if (exists) return prev.filter((s) => s.key !== key);

      const answerText = m.insights?.text ?? m.presentation?.summary ?? m.insights?.overview ?? "";
      const newInsight: SavedInsight = {
        id: `insight-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        key,
        question: m.question,
        answerText,
        sql: m.sql,
        sessionId: activeSessionId,
        savedAt: Date.now(),
      };
      return [newInsight, ...prev];
    });
  }

  function removeSavedInsight(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    setSavedInsights((prev) => prev.filter((s) => s.id !== id));
  }

  function openSavedInsight(insight: SavedInsight) {
    if (insight.sessionId) {
      const target = sessions.find((s) => s.id === insight.sessionId);
      if (target) {
        selectSession(target.id);
        setSidebarOpen(false);
        return;
      }
    }
    setError("The chat this insight came from is no longer available.");
  }

  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const saved = localStorage.getItem("theme");

    if (saved === "light" || saved === "dark") return saved;

    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  });

  const [apiBaseUrl, setApiBaseUrl] = useState<string>(
    () => localStorage.getItem("datapilot_api_base_url") || "https://datapilot-1scv.onrender.com"
  );

  useEffect(() => {
    localStorage.setItem("datapilot_api_base_url", apiBaseUrl);
  }, [apiBaseUrl]);

  function getApiBaseUrl() {
    return apiBaseUrl.trim().replace(/\/$/, "") || "https://datapilot-1scv.onrender.com";
  }

  function clearAllChats() {
    if (!window.confirm("Delete all saved chats? This can't be undone.")) return;
    setSessions([]);
    setActiveSessionId(null);
    setMessages([]);
  }

  function clearAllSavedInsights() {
    if (!window.confirm("Delete all saved insights? This can't be undone.")) return;
    setSavedInsights([]);
  }

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
    const res = await fetch(`${getApiBaseUrl()}/api/ask`, {
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

        <button className="new-chat-btn" onClick={startNewChat} aria-label="Start a new chat">
          <span>+</span> New Chat
        </button>

        <nav className="sidebar-nav">
          <button
            className={`nav-item ${activeNav === "chats" ? "active" : ""}`}
            onClick={() => setActiveNav("chats")}
            aria-label="Recent Chats"
          >
            Recent Chats
          </button>
          <button
            className={`nav-item ${activeNav === "insights" ? "active" : ""}`}
            onClick={() => setActiveNav("insights")}
            aria-label="Saved Insights"
          >
            Saved Insights
          </button>
          <button
            className={`nav-item ${activeNav === "sources" ? "active" : ""}`}
            onClick={openDataSources}
            aria-label="About Data"
          >
            About Data
          </button>
        </nav>

        {(activeNav === "chats" || activeNav === "insights") && (
          <div className="chat-history">
            {activeNav === "chats" ? (
              sortedSessions.length === 0 ? (
                <p className="chat-history-empty">No chats yet</p>
              ) : (
                sortedSessions.map((s) => (
                  <button
                    key={s.id}
                    className={`chat-history-item ${s.id === activeSessionId ? "active" : ""}`}
                    onClick={() => selectSession(s.id)}
                    aria-label={`Open chat: ${s.title}`}
                  >
                    <span className="chat-history-text">
                      <span className="chat-history-title">{s.title}</span>
                      <span className="chat-history-time">{formatRelativeTime(s.updatedAt)}</span>
                    </span>
                    <span
                      className="chat-history-delete"
                      role="button"
                      aria-label={`Delete chat: ${s.title}`}
                      onClick={(e) => deleteSession(s.id, e)}
                    >
                      ✕
                    </span>
                  </button>
                ))
              )
            ) : savedInsights.length === 0 ? (
              <p className="chat-history-empty">No saved insights yet</p>
            ) : (
              savedInsights.map((insight) => (
                <button
                  key={insight.id}
                  className="chat-history-item"
                  onClick={() => openSavedInsight(insight)}
                  aria-label={`Open saved insight: ${insight.question}`}
                >
                  <span className="chat-history-text">
                    <span className="chat-history-title">{makeSessionTitle(insight.question)}</span>
                    <span className="chat-history-time">{formatRelativeTime(insight.savedAt)}</span>
                  </span>
                  <span
                    className="chat-history-delete"
                    role="button"
                    aria-label="Remove saved insight"
                    onClick={(e) => removeSavedInsight(insight.id, e)}
                  >
                    ✕
                  </span>
                </button>
              ))
            )}
          </div>
        )}

        <div className="sidebar-footer">
          <button
            className={`nav-item ${activeNav === "settings" ? "active" : "muted"}`}
            onClick={() => {
              setActiveNav("settings");
              setSidebarOpen(false);
            }}
            aria-label="Settings"
          >
            Settings
          </button>
          <button
            className={`nav-item ${activeNav === "help" ? "active" : "muted"}`}
            onClick={() => {
              setActiveNav("help");
              setSidebarOpen(false);
            }}
            aria-label="Help & Support"
          >
            Help &amp; Support
          </button>
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

        {activeNav === "sources" ? (
          <DataSourcesView
            catalog={catalog}
            loading={catalogLoading}
            error={catalogError}
            expandedTables={expandedTables}
            onToggleTable={toggleTableExpanded}
            onRefresh={fetchCatalog}
          />
        ) : activeNav === "settings" ? (
          <SettingsView
            theme={theme}
            onSetTheme={setTheme}
            apiBaseUrl={apiBaseUrl}
            onApiBaseUrlChange={setApiBaseUrl}
            sessionsCount={sessions.length}
            savedInsightsCount={savedInsights.length}
            onClearChats={clearAllChats}
            onClearSavedInsights={clearAllSavedInsights}
          />
        ) : activeNav === "help" ? (
          <HelpView apiBaseUrl={apiBaseUrl} />
        ) : (
          <>
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

                  {m.rows && m.rows.length > 0 && wantsChart(m.question, m.rows) && (
                    <ChartView rows={m.rows} question={m.question} />
                  )}
                  {!m.clarificationRequired &&
                    (m.insights?.text || m.presentation?.summary || m.insights?.overview) && (
                      <div className="msg-actions">
                        <button
                          className={isMessageSaved(i) ? "saved" : ""}
                          onClick={() => toggleSaveInsight(m, i)}
                        >
                          {isMessageSaved(i) ? "★ Saved" : "☆ Save insight"}
                        </button>
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
          </>
        )}
      </main>
    </div>
  );
}

export default App;