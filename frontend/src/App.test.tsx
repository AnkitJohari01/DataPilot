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
            what_happened:
              "I found more than one possible data area. Do you mean sales or shipments?",
            why: [],
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
            what_happened:
              "I found more than one possible data area. Do you mean sales or shipments?",
            why: [],
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
            what_happened: "Total sales are 100.",
            why: [],
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
});