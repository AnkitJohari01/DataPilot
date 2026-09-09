import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

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

    await screen.findByText("Total sales are 100.");

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
    expect(await screen.findByText("Results")).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "product_name" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Product 001")).toBeInTheDocument();
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

describe("dataset selection & strict-answer display", () => {
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

    await screen.findByText("Results");
    expect(
      screen.getByText("How many orders?", { selector: ".user-msg" }),
    ).toBeInTheDocument();

    // Changing the selection (deselecting) should clear the conversation.
    fireEvent.click(screen.getByLabelText("orders.csv"));

    expect(
      screen.queryByText("How many orders?", { selector: ".user-msg" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Results")).not.toBeInTheDocument();
  });

  it("renders evidence (sql + rows), with no narrative insight sections", async () => {
    const fetchMock = mockDatasetsAndStrictAsk({
      question: "Total revenue",
      sql: "SELECT SUM(revenue) AS total FROM imported.orders",
      rows: [{ total: 500 }],
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

    expect(await screen.findByText("Results")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "total" })).toBeInTheDocument();
    expect(screen.getByText("500")).toBeInTheDocument();
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