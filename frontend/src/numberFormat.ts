export function currencySymbol(currency: string): string {
  if (!/^[A-Z]{3}$/.test(currency)) return currency;
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).formatToParts(0).find(part => part.type === "currency")?.value ?? currency;
}

export function formatOutputValue(value: unknown, column = "", currency: string | null = "$"): string {
  const text = String(value ?? "");
  if (/(?:^|[_\s])(?:id|code)(?:$|[_\s])/i.test(column)) return text;
  const money = text.trim().match(/^([A-Z]{3}\s+|[A-Z]{1,2}\$|\p{Sc})\s*([+-]?[\d,.]+)$/u);
  const numericText = (money?.[2] ?? text).trim().replaceAll(",", "").replace(/\s*(?:%|percent(?:age)?)$/i, "%");
  if (value == null || !/^[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:e[+-]?\d+)?%?$/i.test(numericText)) return text;
  const number = Number(numericText.replace("%", ""));
  if (!Number.isFinite(number)) return text;
  const percentageColumn = /(?:^|[_\s(])(?:pct|percent|percentage)(?:$|[_\s)])|%/i.test(column);
  const margin = /profit[ _-]*margin/i.test(column);
  const percentage = margin || percentageColumn || numericText.endsWith("%");
  // shortcut: Unmarked profit_margin values are ratios; use pct/percent column names for already-scaled percentages.
  const displayed = margin && !percentageColumn && !numericText.endsWith("%") ? number * 100 : number;
  const unit = column.match(/(?:[_\s(])([A-Z]{3})(?:$|[_\s)])/i)?.[1]?.toUpperCase();
  const columnCurrency = unit && Intl.supportedValuesOf("currency").includes(unit) ? unit : column.match(/[₹$€£¥₩₽₺₫₱฿৳₦₪]/)?.[0];
  const monetaryColumn = /(?:^|[_\s])(?:sales|revenue|profit|price|cost|costs|amount|spend|value|aov)(?:$|[_\s(])/i.test(column) && !/margin|ratio|pct|percent|growth|rate/i.test(column);
  const symbol = !percentage && (money || columnCurrency || monetaryColumn) ? currencySymbol(money?.[1].trim() ?? columnCurrency ?? currency ?? "") : "";
  const decimals = percentage || symbol || !Number.isInteger(displayed) || /[.e]/i.test(text) ? 2 : 0;
  if (!percentage && decimals === 0) return text;
  const formatted = displayed.toLocaleString("en-US", {
    minimumFractionDigits: decimals, maximumFractionDigits: decimals, useGrouping: text.includes(","),
  }).replace(/^-0\.00$/, "0.00");
  return `${symbol}${numericText.startsWith("+") ? "+" : ""}${formatted}${percentage ? " percentage" : ""}`;
}

export function formatAnswerText(text: string, currency: string | null = "$"): string {
  const withMargins = text.replace(
    /(\bprofit[ _-]+margin(?:\*\*)?(?:\s+(?:is|was|of|at))?\s*[:=]?\s*(?:\*\*)?)([+-]?\d+(?:\.\d+)?)(\*\*)?(\s*(?:%|percent(?:age)?))?/gi,
    (_match, prefix: string, number: string, boldEnd: string | undefined, percent: string | undefined) =>
      `${prefix}${formatOutputValue(`${number}${percent ? "%" : ""}`, "profit_margin")}${boldEnd ?? ""}`,
  );
  const withCurrencyCodes = withMargins.replace(/\b([A-Z]{3})\s+([+-]?[\d,]+(?:\.\d+)?)/g, (match, code: string, number: string) =>
    Intl.supportedValuesOf("currency").includes(code) ? formatOutputValue(`${code} ${number}`) : match,
  ).replace(/([+-]?[\d,]+(?:\.\d+)?)\s+([A-Z]{3})\b/g, (match, number: string, code: string) =>
    Intl.supportedValuesOf("currency").includes(code) ? formatOutputValue(`${code} ${number}`) : match,
  );
  // shortcut: Adds missing symbols after explicit monetary labels; the AI prompt covers other sentence structures.
  const withMoney = withCurrencyCodes.replace(
    /(\b(?:sales|revenue|profit(?!\s+margin)|costs?|price|amount|spend|average\s+order\s+value)\b(?:\*\*)?\s*(?:(?:is|was|were|are|of|at|totaled|reached|increased|decreased|rose|fell)(?:\s+(?:by|to|from))?\s+)?[:=]?\s*(?:\*\*)?)([+-]?[\d,]+(?:\.\d+)?)(?!\d|\.\d|\s*(?:%|percent(?:age)?))/gi,
    (_match, prefix: string, number: string) => `${prefix}${formatOutputValue(number, "amount", currency)}`,
  );
  const withRanges = withMoney.replace(/((?:[A-Z]{1,2}\$|\p{Sc}))[+-]?[\d,]+(?:\.\d+)?\s+(?:to|–|-)\s+[+-]?[\d,]+(?:\.\d+)?/gu, range => {
    const [first, separator, last] = range.split(/(\s+(?:to|–|-)\s+)/);
    const symbol = first.match(/^[A-Z]{1,2}\$|^\p{Sc}/u)![0];
    return `${first}${separator}${formatOutputValue(last, "amount", symbol)}`;
  });
  return withRanges.replace(
    /(?<![\w./:-])([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:\s*(?:%|percent(?:age)?))?)(?![\w/:]|\.\d|-\d)/gi,
    (number) => formatOutputValue(number),
  ).replace(/\s*%/g, " percentage");
}
