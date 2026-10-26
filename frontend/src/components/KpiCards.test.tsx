import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { metricsFixture } from "../test/fixtures";
import { KpiCards } from "./KpiCards";

describe("KpiCards", () => {
  it("states the P90 buffer in plain English, rounded", () => {
    render(<KpiCards metrics={metricsFixture()} />);

    expect(screen.getByText(/Hold ~4,160 MW extra to cover 90% of hours\./)).toBeInTheDocument();
    expect(screen.getByText(/P95: ~5,290 MW/)).toBeInTheDocument();
  });

  it("shows how the buffer did when sized only from earlier days", () => {
    render(<KpiCards metrics={metricsFixture()} />);

    expect(screen.getByText(/Sized only from earlier days, it covered 86%/)).toBeInTheDocument();
  });

  it("names half-hours when slots are half-hourly", () => {
    render(<KpiCards metrics={metricsFixture({ slotMinutes: 30 })} />);

    expect(screen.getByText(/to cover 90% of half-hours\./)).toBeInTheDocument();
  });

  it("uses plain labels and shows signed bias and how often the forecast was too high", () => {
    render(<KpiCards metrics={metricsFixture()} />);

    expect(screen.getByText("Typical miss")).toBeInTheDocument();
    expect(screen.getByText("+1,746 MW")).toBeInTheDocument();
    expect(screen.getByText(/above actual in 85% of hours/)).toBeInTheDocument();
    expect(screen.getByText("17.9%")).toBeInTheDocument();
  });
});
