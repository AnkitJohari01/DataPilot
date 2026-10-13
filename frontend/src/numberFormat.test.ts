import { describe, expect, it } from "vitest";
import { formatAnswerText, formatOutputValue } from "./numberFormat";

describe("output number formatting", () => {
  it.each([
    ["14236.8950", "total_sales", "14236.90"],
    [2450.1907, "total_profit", "2450.19"],
    ["0.17210147999265289236", "profit_margin", "17.21%"],
    ["0.00895530371877442551", "profit_margin", "0.90%"],
    [-1.25, "profit_margin", "-125.00%"],
    [0, "profit_margin", "0.00%"],
    ["17.21014799", "profit_margin_pct", "17.21%"],
    ["17.21%", "profit_margin", "17.21%"],
    ["17.21014 %", "profit_margin", "17.21%"],
    [2019, "year", "2019"],
    [1, "month", "1"],
    [null, "profit_margin", ""],
    ["00123", "order_id", "00123"],
    ["1.2345", "product_code", "1.2345"],
    ["2019-01-01", "date", "2019-01-01"],
    ["Product 001", "product", "Product 001"],
    [1.005, "amount", "1.01"],
  ])("formats %s in %s as %s", (value, column, expected) => {
    expect(formatOutputValue(value, column)).toBe(expected);
  });

  it("rounds decimals and percentages in prose while preserving years, dates, IDs, and version numbers", () => {
    expect(formatAnswerText("Sales were $14,236.8950 in 2019. Profit fell by 4.23456%. Date: 2026-10-13; ID ABC1.234; version 1.2.3.")).toBe(
      "Sales were $14,236.90 in 2019. Profit fell by 4.23%. Date: 2026-10-13; ID ABC1.234; version 1.2.3.",
    );
  });

  it("converts a named profit-margin ratio in prose without scaling an existing percentage twice", () => {
    expect(formatAnswerText("Profit margin is **0.17210147999**. Profit margin was 17.2101%.")).toBe(
      "Profit margin is **17.21%**. Profit margin was 17.21%.",
    );
  });
});
