import { describe, expect, it } from "vitest";
import { formatAnswerText, formatOutputValue } from "./numberFormat";

describe("output number formatting", () => {
  it.each([
    ["14236.8950", "total_sales", "$14236.90"],
    [2450.1907, "total_profit", "$2450.19"],
    ["0.17210147999265289236", "profit_margin", "17.21 percentage"],
    ["0.00895530371877442551", "profit_margin", "0.90 percentage"],
    [-1.25, "profit_margin", "-125.00 percentage"],
    [0, "profit_margin", "0.00 percentage"],
    ["17.21014799", "profit_margin_pct", "17.21 percentage"],
    ["17.21%", "profit_margin", "17.21 percentage"],
    ["17.21014 %", "profit_margin", "17.21 percentage"],
    ["17.21014 percentage", "profit_margin", "17.21 percentage"],
    [2019, "year", "2019"],
    [1, "month", "1"],
    [null, "profit_margin", ""],
    ["00123", "order_id", "00123"],
    ["1.2345", "product_code", "1.2345"],
    ["2019-01-01", "date", "2019-01-01"],
    ["Product 001", "product", "Product 001"],
    [1.005, "amount", "$1.01"],
    [123.456, "sales_INR", "₹123.46"],
    [123.456, "sales (EUR)", "€123.46"],
  ])("formats %s in %s as %s", (value, column, expected) => {
    expect(formatOutputValue(value, column)).toBe(expected);
  });

  it("rounds decimals and percentages in prose while preserving years, dates, IDs, and version numbers", () => {
    expect(formatAnswerText("Sales were $14,236.8950 in 2019. Profit fell by 4.23456%. Date: 2026-10-13; ID ABC1.234; version 1.2.3.")).toBe(
      "Sales were $14,236.90 in 2019. Profit fell by 4.23 percentage. Date: 2026-10-13; ID ABC1.234; version 1.2.3.",
    );
  });

  it("converts a named profit-margin ratio in prose without scaling an existing percentage twice", () => {
    expect(formatAnswerText("Profit margin is **0.17210147999**. Profit margin was 17.2101%.")).toBe(
      "Profit margin is **17.21 percentage**. Profit margin was 17.21 percentage.",
    );
  });

  it("uses the identified currency only on monetary amounts, including chart values", () => {
    expect(formatOutputValue(100, "total_sales", "INR")).toBe("₹100.00");
    expect(formatOutputValue(10, "total_orders", "INR")).toBe("10");
    expect(formatOutputValue(2019, "year", "INR")).toBe("2019");
    expect(formatOutputValue(12.5, "sales_change_pct", "INR")).toBe("12.50 percentage");
    expect(formatAnswerText("Sales were 1234.5678. Profit fell by 4.2%. Orders: 10 in 2019.", "INR")).toBe("Sales were ₹1234.57. Profit fell by 4.20 percentage. Orders: 10 in 2019.");
    expect(formatAnswerText("Sales were USD 100.123 and cost was 20.567 INR.", null)).toBe("Sales were $100.12 and cost was ₹20.57.");
    expect(formatOutputValue(100.123, "sales", null)).toBe("100.12");
    expect(formatOutputValue(100, "sales", "XAF")).toBe("FCFA100.00");
    expect(formatAnswerText("Sales increased from 100.123 to 200.567.", "INR")).toBe("Sales increased from ₹100.12 to ₹200.57.");
  });
});
