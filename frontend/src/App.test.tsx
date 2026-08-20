import { fireEvent, render, screen } from "@testing-library/react";
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