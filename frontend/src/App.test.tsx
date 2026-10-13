import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

describe("answer presentation", () => {
  beforeEach(() => localStorage.clear());

  async function askWithAnswer(text: string, rows: Array<Record<string, unknown>> = [], currency: string | null = "$") {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ insights: { text }, rows, currency }),
    }));
    render(<App />);
    fireEvent.change(screen.getByPlaceholderText("Ask anything about your business data..."), {
      target: { value: "How did sales and profit change?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    return within(await screen.findByRole("article", { name: "Assistant response" }));
  }

  it("shows formatted summaries without a results table", async () => {
    const answer = await askWithAnswer("Sales were 14236.8950. Profit margin is 0.17210147999265289236.", [
      { year: 2019, month: 1, total_sales: "14236.8950", total_profit: "2450.1907", profit_margin: "0.17210147999265289236" },
    ]);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByText("Results")).not.toBeInTheDocument();
    expect(answer.getByText(/Sales were \$14236.90/)).toBeInTheDocument();
    expect(answer.getByText(/Profit margin is 17.21 percentage/)).toBeInTheDocument();
  });

  it("does not insert an automatic heatmap for decimal sales and profit results", async () => {
    await askWithAnswer("Sales summary", [
      { year: 2019, sales: "14236.8950", profit: "2450.1907" },
      { year: 2019, sales: "4519.8920", profit: "862.3084" },
    ]);
    expect(document.querySelector(".heatmap-grid")).toBeNull();
    expect(document.querySelector(".chart-wrapper")).toBeNull();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("colors opposing trends separately within the same sentence and preserves bold formatting", async () => {
    const answer = await askWithAnswer("**Sales increased by 12.5%**, while **profit decreased by 4.2%**. Orders remained unchanged.");
    expect(answer.getByText("Sales increased by 12.50 percentage").closest(".trend-up")).not.toBeNull();
    expect(answer.getByText("profit decreased by 4.20 percentage").closest(".trend-down")).not.toBeNull();
    expect(answer.getByText("Sales increased by 12.50 percentage").tagName).toBe("STRONG");
    expect(answer.getByText(/Orders remained unchanged/).closest(".trend-up, .trend-down")).toBeNull();
  });

  it("recognizes growing and falling figures in headings and list items without coloring negated trends", async () => {
    const answer = await askWithAnswer("## Sales are increasing\n- Revenue grew from 1,000 to 1,250.\n1. Profit fell by 5%.\nSales did not increase. Revenue was flat.");
    expect(answer.getByText("Sales are increasing").closest(".trend-up")).not.toBeNull();
    expect(answer.getByText(/Revenue grew from 1,000 to 1,250/).closest(".trend-up")).not.toBeNull();
    expect(answer.getByText("Profit fell by 5.00 percentage").closest(".trend-down")).not.toBeNull();
    expect(answer.getByText(/Sales did not increase/).closest(".trend-up, .trend-down")).toBeNull();
  });

  it("keeps older answers readable as bullets when they have rows but no generated summary", async () => {
    const answer = await askWithAnswer("", [
      { year: 2019, sales: 1000, profit_margin: "0.17210147", total_orders: 10 },
    ]);
    expect(answer.getByText(/year: 2019; sales: \$1000.00; profit margin: 17.21 percentage; total orders: 10/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("uses each row's currency for mixed-currency fallback summaries", async () => {
    const answer = await askWithAnswer("", [{ sales: 100.123, currency: "USD" }, { sales: 200.456, currency: "INR" }], null);
    expect(answer.getByText(/sales: \$100.12/)).toBeInTheDocument();
    expect(answer.getByText(/sales: ₹200.46/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("renders answer HTML as text while keeping trend highlighting", async () => {
    const answer = await askWithAnswer('Sales increased by 10%. <img src=x onerror="alert(1)">');
    expect(answer.getByText("Sales increased by 10.00 percentage").closest(".trend-up")).not.toBeNull();
    expect(document.querySelector(".answer-content img")).toBeNull();
    expect(answer.getByText(/<img src=x/)).toBeInTheDocument();
  });

  it("keeps bold formatting across opposing clauses and leaves contractions neutral", async () => {
    const answer = await askWithAnswer("**Sales increased by 10%, while profit decreased by 3%.**\nSales didn't increase.");
    expect(answer.getByText("Sales increased by 10.00 percentage").closest(".trend-up")).not.toBeNull();
    expect(answer.getByText(/profit decreased by 3.00 percentage/).closest(".trend-down")).not.toBeNull();
    expect(answer.getByText(/profit decreased by 3.00 percentage/).tagName).toBe("STRONG");
    expect(answer.getByText("Sales didn't increase.").closest(".trend-up, .trend-down")).toBeNull();
  });
});

describe("clarification responses", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          question: "How is the business doing?",
          sql: null,
          rows: [],
          clarification_required: true,
          insights: {
            overview:
              "I found more than one possible data area. Do you mean sales or shipments?",
            key_findings: [],
            recommendations: [],
            next_steps: [],
          },
        }),
      }),
    );
  });

  it("shows a clarification question without SQL actions", async () => {
    render(<App />);

    fireEvent.change(
      screen.getByPlaceholderText("Ask anything about your business data..."),
      { target: { value: "How is the business doing?" } },
    );

    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(
      await screen.findByText(
        "I found more than one possible data area. Do you mean sales or shipments?",
      ),
    ).toBeInTheDocument();

    expect(screen.getByText("Need clarification")).toBeInTheDocument();

    expect(
      screen.getByPlaceholderText(
        "Tell me which data area you mean...",
      ),
    ).toBeInTheDocument();

    expect(screen.queryByText("Copy SQL")).not.toBeInTheDocument();
    expect(screen.queryByText("View SQL")).not.toBeInTheDocument();
  });

  it("sends the original question with a clarification reply", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          question: "How is the business doing?",
          sql: null,
          rows: [],
          clarification_required: true,
          insights: {
            overview:
              "I found more than one possible data area. Do you mean sales or shipments?",
            key_findings: [],
            recommendations: [],
            next_steps: [],
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          question: "How is the business doing? Clarification: sales",
          sql: "SELECT SUM(net_sales) AS total_sales FROM fact_sales",
          rows: [{ total_sales: 100 }],
          insights: {
            overview: "Total sales are 100.",
            key_findings: [],
            recommendations: [],
            next_steps: [],
          },
        }),
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.change(
      screen.getByPlaceholderText("Ask anything about your business data..."),
      { target: { value: "How is the business doing?" } },
    );

    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText(
      "I found more than one possible data area. Do you mean sales or shipments?",
    );

    fireEvent.change(
      screen.getByPlaceholderText(
        "Tell me which data area you mean...",
      ),
      { target: { value: "sales" } },
    );

    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText("Total sales are $100.00.");

    const secondRequest = fetchMock.mock.calls[1][1] as RequestInit;
    const requestBody = JSON.parse(secondRequest.body as string);

    expect(requestBody.question).toBe(
      "How is the business doing?\n\nClarification: sales",
    );
  });

  it("shows returned query rows in a results table", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          question: "Which products had the most returns?",
          sql: "SELECT product_name, total_returns FROM fact_returns",
          rows: [
            {
              product_id: "PROD001",
              product_name: "Product 001",
              total_returns: 280,
            },
          ],
          insights: {
            overview: "Product 001 has the highest return count.",
            key_findings: [],
            recommendations: [],
            next_steps: [],
          },
        }),
      }),
    );
    render(<App />);
    fireEvent.change(
      screen.getByPlaceholderText("Ask anything about your business data..."),
      { target: { value: "Which products had the most returns?" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Product 001 has the highest return count.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

function makeCsvFile(name = "data.csv"): File {
  return new File(["a,b\n1,2\n"], name, { type: "text/csv" });
}

describe("dataset import & catalog", () => {
  it("shows an upload control and calls the import API when a file is selected", async () => {
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            id: 1,
            name: "data",
            created_at: null,
            tables: [
              {
                display_table_name: "data",
                db_table_name: "data",
                row_count: 1,
                column_map: { a: "a", b: "b" },
              },
            ],
          }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => [] });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "My Datasets" }));

    const fileInput = await screen.findByLabelText("Choose dataset file");
    fireEvent.change(fileInput, { target: { files: [makeCsvFile()] } });

    await screen.findByText("data");

    const postCall = fetchMock.mock.calls.find(
      (call) => (call[1] as RequestInit)?.method === "POST",
    );
    expect(postCall).toBeTruthy();
    expect(String(postCall?.[0])).toContain("/api/datasets");
    expect((postCall?.[1] as RequestInit).body).toBeInstanceOf(FormData);
  });

  it("shows a progress indicator while the import request is in flight", async () => {
    let resolvePost: (value: unknown) => void = () => {};
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        return new Promise((resolve) => {
          resolvePost = resolve;
        });
      }
      return Promise.resolve({ ok: true, json: async () => [] });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "My Datasets" }));

    const fileInput = await screen.findByLabelText("Choose dataset file");
    fireEvent.change(fileInput, { target: { files: [makeCsvFile()] } });

    expect(
      await screen.findByText("Importing your file..."),
    ).toBeInTheDocument();

    resolvePost({
      ok: true,
      json: async () => ({
        id: 1,
        name: "data",
        created_at: null,
        tables: [],
      }),
    });

    await waitFor(() =>
      expect(
        screen.queryByText("Importing your file..."),
      ).not.toBeInTheDocument(),
    );
  });

  it("shows an error and does not add a dataset when the import fails", async () => {
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        return Promise.resolve({
          ok: false,
          json: async () => ({
            detail: "Only .csv and .xlsx files are supported.",
          }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => [] });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "My Datasets" }));

    const fileInput = await screen.findByLabelText("Choose dataset file");
    fireEvent.change(fileInput, {
      target: { files: [makeCsvFile("notes.txt")] },
    });

    expect(
      await screen.findByText("Only .csv and .xlsx files are supported."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "No datasets imported yet — upload a CSV or Excel file above to get started.",
      ),
    ).toBeInTheDocument();
  });

  it("groups the dataset catalog by dataset, not flattened", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: async () => [
          {
            id: 1,
            name: "Sales Export",
            created_at: "2026-01-01T00:00:00Z",
            tables: [
              {
                display_table_name: "Sheet1",
                db_table_name: "sheet1",
                row_count: 10,
                column_map: { A: "a" },
              },
              {
                display_table_name: "Sheet2",
                db_table_name: "sheet2",
                row_count: 5,
                column_map: { B: "b" },
              },
            ],
          },
          {
            id: 2,
            name: "Inventory",
            created_at: "2026-01-02T00:00:00Z",
            tables: [
              {
                display_table_name: "Items",
                db_table_name: "items",
                row_count: 20,
                column_map: { C: "c" },
              },
            ],
          },
        ],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "My Datasets" }));

    expect(await screen.findByText("Sales Export")).toBeInTheDocument();
    expect(screen.getByText("Inventory")).toBeInTheDocument();
    expect(screen.getByText("2 tables")).toBeInTheDocument();
    expect(screen.getByText("1 table")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Sales Export"));
    expect(await screen.findByText("Sheet1")).toBeInTheDocument();
    // Items belongs to the Inventory group, which is still collapsed — it
    // must not appear just because Sales Export's group was expanded.
    expect(screen.queryByText("Items")).not.toBeInTheDocument();
  });

  it("deletes a dataset after confirmation and removes it from the list", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
      if (init?.method === "DELETE") {
        return Promise.resolve({ ok: true, status: 204, json: async () => ({}) });
      }
      return Promise.resolve({
        ok: true,
        json: async () => [
          {
            id: 1,
            name: "Sales Export",
            created_at: "2026-01-01T00:00:00Z",
            tables: [
              {
                display_table_name: "Sheet1",
                db_table_name: "sheet1",
                row_count: 10,
                column_map: { A: "a" },
              },
            ],
          },
        ],
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "My Datasets" }));

    expect(await screen.findByText("Sales Export")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Delete Sales Export" }));

    expect(window.confirm).toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.queryByText("Sales Export")).not.toBeInTheDocument(),
    );

    const deleteCall = fetchMock.mock.calls.find(
      (call) => (call[1] as RequestInit | undefined)?.method === "DELETE",
    );
    expect(deleteCall?.[0]).toContain("/api/datasets/1");
  });

  it("does not delete when the confirmation is declined", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
      if (init?.method === "DELETE") {
        return Promise.resolve({ ok: true, status: 204, json: async () => ({}) });
      }
      return Promise.resolve({
        ok: true,
        json: async () => [
          {
            id: 1,
            name: "Sales Export",
            created_at: "2026-01-01T00:00:00Z",
            tables: [
              {
                display_table_name: "Sheet1",
                db_table_name: "sheet1",
                row_count: 10,
                column_map: { A: "a" },
              },
            ],
          },
        ],
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "My Datasets" }));

    await screen.findByText("Sales Export");
    fireEvent.click(screen.getByRole("button", { name: "Delete Sales Export" }));

    expect(
      fetchMock.mock.calls.some(
        (call) => (call[1] as RequestInit | undefined)?.method === "DELETE",
      ),
    ).toBe(false);
    expect(screen.getByText("Sales Export")).toBeInTheDocument();
  });

  it("shows an error and keeps the dataset when delete fails", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
      if (init?.method === "DELETE") {
        return Promise.resolve({
          ok: false,
          status: 400,
          json: async () => ({ detail: "Delete failed: still in use" }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => [
          {
            id: 1,
            name: "Sales Export",
            created_at: "2026-01-01T00:00:00Z",
            tables: [
              {
                display_table_name: "Sheet1",
                db_table_name: "sheet1",
                row_count: 10,
                column_map: { A: "a" },
              },
            ],
          },
        ],
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "My Datasets" }));

    await screen.findByText("Sales Export");
    fireEvent.click(screen.getByRole("button", { name: "Delete Sales Export" }));

    expect(
      await screen.findByText("Delete failed: still in use"),
    ).toBeInTheDocument();
    expect(screen.getByText("Sales Export")).toBeInTheDocument();
  });
});

const ONE_DATASET = [
  {
    id: 1,
    name: "orders.csv",
    created_at: null,
    tables: [
      {
        display_table_name: "orders",
        db_table_name: "orders",
        row_count: 10,
        column_map: { Order: "order", Revenue: "revenue" },
      },
    ],
  },
];

function mockDatasetsAndStrictAsk(strictResponse: unknown) {
  return vi.fn((url: string, init?: RequestInit) => {
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    if (path === "/api/datasets" && init?.method === undefined) {
      return Promise.resolve({ ok: true, json: async () => ONE_DATASET });
    }
    if (path === "/api/ask/strict") {
      return Promise.resolve({ ok: true, json: async () => strictResponse });
    }
    return Promise.resolve({ ok: true, json: async () => [] });
  });
}

async function enterDataModeAndSelectDataset() {
  fireEvent.click(screen.getByRole("tab", { name: "My Data" }));
  await screen.findByText("orders.csv");
  fireEvent.click(screen.getByLabelText("orders.csv"));
}

function seedSeparateChats() {
  localStorage.clear();
  localStorage.setItem("datapilot_sessions", JSON.stringify([
    { id: "business", title: "Business question", createdAt: 1, updatedAt: 1,
      messages: [{ role: "user", question: "Business question" },
        { role: "assistant", question: "Business question", insights: { text: "Saved business answer" } }] },
    { id: "data", title: "Data question", createdAt: 2, updatedAt: 2,
      messages: [{ role: "user", question: "Data question", mode: "data" },
        { role: "assistant", question: "Data question", mode: "data", strictMessage: "Saved data answer" }] },
  ]));
}

describe("dataset selection & strict-answer display", () => {
  it("opens saved chats in their own tab and deletes a hidden conversation", async () => {
    seedSeparateChats();
    vi.stubGlobal("fetch", mockDatasetsAndStrictAsk({}));
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Open chat: Business question" }));
    fireEvent.click(screen.getByRole("button", { name: "Open chat: Data question" }));
    expect(screen.getByRole("tab", { name: "My Data" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Saved data answer")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Business Chat" }));
    expect(screen.getByText("Saved business answer")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete chat: Data question" }));
    fireEvent.click(screen.getByRole("tab", { name: "My Data" }));
    expect(screen.queryByText("Saved data answer")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open chat: Data question" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Business Chat" }));
    expect(screen.getByText("Saved business answer")).toBeInTheDocument();
    await waitFor(() => expect(localStorage.getItem("datapilot_sessions")).not.toContain('"id":"data"'));
  });

  it("clears both cached conversations from Settings", async () => {
    seedSeparateChats();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.stubGlobal("fetch", mockDatasetsAndStrictAsk({}));
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Open chat: Business question" }));
    fireEvent.click(screen.getByRole("button", { name: "Open chat: Data question" }));
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear all chats" }));
    fireEvent.click(screen.getByRole("button", { name: "Recent Chats" }));
    expect(screen.queryByText("Saved data answer")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Business Chat" }));
    expect(screen.queryByText("Saved business answer")).not.toBeInTheDocument();
    await waitFor(() => expect(localStorage.getItem("datapilot_sessions")).toBe("[]"));
  });

  it("deleting a selected dataset clears My Data while preserving the hidden business conversation", async () => {
    seedSeparateChats();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.stubGlobal("fetch", vi.fn((_url: string, init?: RequestInit) =>
      Promise.resolve({ ok: true, json: async () => init?.method === "DELETE" ? {} : ONE_DATASET }),
    ));
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Open chat: Business question" }));
    await enterDataModeAndSelectDataset();
    fireEvent.click(screen.getByRole("button", { name: "Open chat: Data question" }));
    fireEvent.click(screen.getByRole("tab", { name: "Business Chat" }));
    fireEvent.click(screen.getByRole("button", { name: "My Datasets" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete orders.csv" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Delete orders.csv" })).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Recent Chats" }));
    expect(screen.getByText("Saved business answer")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "My Data" }));
    expect(screen.queryByText("Saved data answer")).not.toBeInTheDocument();
  });

  it("keeps separate conversations, drafts, and dataset selection across mode switches", async () => {
    localStorage.clear();
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (!init?.method) {
        return Promise.resolve({ ok: true, json: async () => ONE_DATASET });
      }
      return Promise.resolve({
        ok: true,
        json: async () => url.endsWith("/strict")
          ? { sql: "SELECT COUNT(*) AS count FROM imported.orders", rows: [{ count: 10 }] }
          : { sql: "SELECT SUM(sales) FROM sales", insights: { text: "Business sales answer" } },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    const input = () => screen.getByPlaceholderText("Ask anything about your business data...");
    fireEvent.change(input(), { target: { value: "Business sales?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Business sales answer");
    fireEvent.change(input(), { target: { value: "Business draft" } });

    await enterDataModeAndSelectDataset();
    expect(screen.queryByText("Business sales answer")).not.toBeInTheDocument();
    expect(input()).toHaveValue("");
    fireEvent.change(input(), { target: { value: "How many orders?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("• count: 10");
    fireEvent.change(input(), { target: { value: "Data draft" } });

    fireEvent.click(screen.getByRole("tab", { name: "Business Chat" }));
    expect(screen.getByText("Business sales answer")).toBeInTheDocument();
    expect(screen.queryByText("• count: 10")).not.toBeInTheDocument();
    expect(input()).toHaveValue("Business draft");

    fireEvent.click(screen.getByRole("tab", { name: "My Data" }));
    expect(screen.getByText("• count: 10")).toBeInTheDocument();
    expect(screen.getByLabelText("orders.csv")).toBeChecked();
    expect(input()).toHaveValue("Data draft");
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Send" })).toBeEnabled());
    const dataRequest = JSON.parse(fetchMock.mock.calls.at(-1)![1]!.body as string);
    expect(dataRequest.dataset_ids).toEqual([1]);
    expect(dataRequest.history).toEqual([
      { question: "How many orders?", sql: "SELECT COUNT(*) AS count FROM imported.orders" },
    ]);

    fireEvent.click(screen.getByRole("tab", { name: "Business Chat" }));
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Send" })).toBeEnabled());
    expect(JSON.parse(fetchMock.mock.calls.at(-1)![1]!.body as string).history).toEqual([
      { question: "Business sales?", sql: "SELECT SUM(sales) FROM sales" },
    ]);
  });

  it("delivers a pending reply to its original tab and saves it while that tab is hidden", async () => {
    localStorage.clear();
    let resolveAsk!: (value: unknown) => void;
    vi.stubGlobal("fetch", vi.fn((_url: string, init?: RequestInit) =>
      init?.method === "POST"
        ? new Promise((resolve) => { resolveAsk = resolve; })
        : Promise.resolve({ ok: true, json: async () => ONE_DATASET }),
    ));
    render(<App />);
    fireEvent.change(screen.getByPlaceholderText("Ask anything about your business data..."), {
      target: { value: "Pending business question" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await enterDataModeAndSelectDataset();
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();

    resolveAsk({ ok: true, json: async () => ({ insights: { text: "Pending business answer" } }) });
    await waitFor(() => expect(localStorage.getItem("datapilot_sessions")).toContain("Pending business answer"));
    expect(screen.queryByText("Pending business answer")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Business Chat" }));
    expect(screen.getByText("Pending business answer")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
  });

  it("blocks asking until a dataset is selected", async () => {
    vi.stubGlobal("fetch", mockDatasetsAndStrictAsk({}));
    render(<App />);

    fireEvent.click(screen.getByRole("tab", { name: "My Data" }));
    await screen.findByText("orders.csv");

    expect(
      screen.getByPlaceholderText("Ask anything about your business data..."),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(
      screen.getByText("Select at least one dataset above to ask a question."),
    ).toBeInTheDocument();
  });

  it("starts a new chat when the dataset selection changes", async () => {
    const fetchMock = mockDatasetsAndStrictAsk({
      question: "How many orders?",
      sql: "SELECT COUNT(*) AS count FROM imported.orders",
      rows: [{ count: 10 }],
      result_count: 1,
      sources: [{ table: "orders", columns: ["count"] }],
      declined: false,
      message: null,
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await enterDataModeAndSelectDataset();

    fireEvent.change(
      screen.getByPlaceholderText("Ask anything about your business data..."),
      { target: { value: "How many orders?" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText("• count: 10");
    expect(
      screen.getByText("How many orders?", { selector: ".user-msg" }),
    ).toBeInTheDocument();

    // Changing the selection (deselecting) should clear the conversation.
    fireEvent.click(screen.getByLabelText("orders.csv"));

    expect(
      screen.queryByText("How many orders?", { selector: ".user-msg" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("• count: 10")).not.toBeInTheDocument();
  });

  it("renders a Business Chat style summary with formatted results and lets it be saved", async () => {
    const fetchMock = mockDatasetsAndStrictAsk({
      question: "Total revenue",
      sql: "SELECT SUM(revenue) AS total FROM imported.orders",
      rows: [{ total: "500.1234", profit_margin: "0.17210147" }],
      insights: { text: "## Sales summary\n- Sales were 500.1234.\n- Sales increased by 12.5%.\n- Profit decreased by 4.2%.\n- Profit margin is 0.17210147." },
      currency: "INR",
      result_count: 1,
      sources: [{ table: "orders", columns: ["revenue"] }],
      declined: false,
      message: null,
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await enterDataModeAndSelectDataset();

    fireEvent.change(
      screen.getByPlaceholderText("Ask anything about your business data..."),
      { target: { value: "Total revenue" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText(/Sales were ₹500.12/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    const answer = within(screen.getByRole("article", { name: "Assistant response" }));
    expect(answer.getByRole("heading", { name: "Sales summary" })).toBeInTheDocument();
    expect(answer.getByText("Sales increased by 12.50 percentage").closest(".trend-up")).not.toBeNull();
    expect(answer.getByText("Profit decreased by 4.20 percentage").closest(".trend-down")).not.toBeNull();
    expect(answer.getByText(/Profit margin is 17.21 percentage/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "☆ Save insight" }));
    expect(JSON.parse(localStorage.getItem("datapilot_saved_insights")!)[0].answerText).toContain("Sales summary");
    expect(screen.getByText("View query details")).toBeInTheDocument();

    expect(screen.queryByText(/Key findings/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Recommendations/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Next steps/i)).not.toBeInTheDocument();
  });

  it("shows the deterministic no-evidence message for an empty result", async () => {
    const fetchMock = mockDatasetsAndStrictAsk({
      question: "Orders from Mars",
      sql: "SELECT * FROM imported.orders WHERE planet = 'Mars'",
      rows: [],
      result_count: 0,
      sources: [],
      declined: false,
      message: "No matching evidence was found in the selected datasets.",
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await enterDataModeAndSelectDataset();

    fireEvent.change(
      screen.getByPlaceholderText("Ask anything about your business data..."),
      { target: { value: "Orders from Mars" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(
      await screen.findByText(
        "No matching evidence was found in the selected datasets.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("Results")).not.toBeInTheDocument();
  });
});
