export function formatOutputValue(value: unknown, column = ""): string {
  const text = String(value ?? "");
  const numericText = text.trim().replaceAll(",", "").replace(/\s+%$/, "%");
  if (/(?:^|[_\s])(?:id|code)(?:$|[_\s])/i.test(column)) return text;
  if (value == null || !/^[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:e[+-]?\d+)?%?$/i.test(numericText)) return text;
  const number = Number(numericText.replace("%", ""));
  if (!Number.isFinite(number)) return text;
  const percentageColumn = /(?:^|[_\s(])(?:pct|percent|percentage)(?:$|[_\s)])|%/i.test(column);
  const margin = /profit[ _-]*margin/i.test(column);
  const percentage = margin || percentageColumn || text.trim().endsWith("%");
  // shortcut: Unmarked profit_margin values are ratios; use pct/percent column names for already-scaled percentages.
  const displayed = margin && !percentageColumn && !text.trim().endsWith("%") ? number * 100 : number;
  const decimals = percentage || !Number.isInteger(displayed) || /[.e]/i.test(text) ? 2 : 0;
  if (!percentage && decimals === 0) return text;
  const formatted = displayed.toLocaleString("en-US", {
    minimumFractionDigits: decimals, maximumFractionDigits: decimals, useGrouping: text.includes(","),
  }).replace(/^-0\.00$/, "0.00");
  return `${text.trim().startsWith("+") ? "+" : ""}${formatted}${percentage ? "%" : ""}`;
}

export function formatAnswerText(text: string): string {
  const withMargins = text.replace(
    /(\bprofit[ _-]+margin(?:\*\*)?(?:\s+(?:is|was|of|at))?\s*[:=]?\s*(?:\*\*)?)([+-]?\d+(?:\.\d+)?)(\*\*)?(\s*%)?/gi,
    (_match, prefix: string, number: string, boldEnd: string | undefined, percent: string | undefined) =>
      `${prefix}${formatOutputValue(`${number}${percent ? "%" : ""}`, "profit_margin")}${boldEnd ?? ""}`,
  );
  return withMargins.replace(
    /(?<![\w./:-])([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?)(?![\w/:]|\.\d|-\d)/g,
    (number) => formatOutputValue(number),
  );
}
