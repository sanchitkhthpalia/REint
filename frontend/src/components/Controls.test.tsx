import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Bounds, Filters } from "../lib/filters";
import { Controls } from "./Controls";

const bounds: Bounds = { min: "2026-01-02", max: "2026-02-01", horizonMin: 0, horizonMax: 48 };
const dayAhead: Filters = {
  start: "2026-01-02",
  end: "2026-02-01",
  mode: "day_ahead",
  horizonH: 24,
  gateTime: "09:00",
};

function setup(filters: Filters = dayAhead) {
  const onChange = vi.fn();
  const onReset = vi.fn();
  render(<Controls filters={filters} bounds={bounds} onChange={onChange} onReset={onReset} />);
  return { onChange, onReset };
}

describe("Controls", () => {
  it("bounds the date pickers to the dataset", () => {
    setup();

    const start = screen.getByLabelText("Start date");
    const end = screen.getByLabelText("End date");
    expect(start).toHaveAttribute("min", "2026-01-02");
    expect(start).toHaveAttribute("max", "2026-02-01");
    expect(end).toHaveAttribute("max", "2026-02-01");
  });

  it("emits valid date changes and ignores out-of-range ones", () => {
    const { onChange } = setup();

    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-01-10" } });
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2025-12-25" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2026-03-01" } });

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith({ start: "2026-01-10" });
  });

  it("shows the gate time selector in day-ahead mode, not the horizon slider", () => {
    setup();

    expect(screen.getByRole("radio", { name: "Day-ahead decision" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getByLabelText("Gate time")).toHaveValue("09:00");
    expect(screen.queryByLabelText("Forecast horizon in hours")).not.toBeInTheDocument();
  });

  it("switches mode via the toggle", async () => {
    const { onChange } = setup();

    await userEvent.click(screen.getByRole("radio", { name: "Custom horizon" }));

    expect(onChange).toHaveBeenCalledWith({ mode: "horizon" });
  });

  it("shows a 0-48 h slider in horizon mode and emits numeric changes", () => {
    const { onChange } = setup({ ...dayAhead, mode: "horizon", horizonH: 6 });

    const slider = screen.getByLabelText("Forecast horizon in hours");
    expect(slider).toHaveAttribute("min", "0");
    expect(slider).toHaveAttribute("max", "48");
    expect(screen.getByText("6 h")).toBeInTheDocument();
    expect(screen.queryByLabelText("Gate time")).not.toBeInTheDocument();

    fireEvent.change(slider, { target: { value: "12" } });

    expect(onChange).toHaveBeenCalledWith({ horizonH: 12 });
  });

  it("offers auction gate times and emits the chosen one", async () => {
    const { onChange } = setup();

    await userEvent.selectOptions(screen.getByLabelText("Gate time"), "09:50");

    expect(screen.getByRole("option", { name: "09:20 (EPEX GB auction)" })).toBeInTheDocument();
    expect(onChange).toHaveBeenCalledWith({ gateTime: "09:50" });
  });

  it("keeps a custom gate time from a shared URL selectable", () => {
    setup({ ...dayAhead, gateTime: "08:45" });

    expect(screen.getByLabelText("Gate time")).toHaveValue("08:45");
  });

  it("resets", async () => {
    const { onReset } = setup();

    await userEvent.click(screen.getByRole("button", { name: "Reset" }));

    expect(onReset).toHaveBeenCalledOnce();
  });
});
