import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { metricsFixture } from "../test/fixtures";
import { Summary } from "./Summary";

describe("Summary", () => {
  it("answers the buyer's question in one sentence for day-ahead decisions", () => {
    const { container } = render(<Summary metrics={metricsFixture()} />);

    expect(container.textContent).toBe(
      "2 Jan 2026 to 1 Feb 2026: the wind forecast available at 09:00 the day before missed by " +
        "2,022 MW in a typical hour and was too high in 85% of hours. Holding ~4,160 MW extra " +
        "would have covered the shortfall in 90% of hours (86% if sized only from earlier days, " +
        "as you would in practice).",
    );
  });

  it("describes horizon mode in the same words", () => {
    const { container } = render(<Summary metrics={metricsFixture({ mode: "horizon" })} />);

    expect(container.textContent).toContain("the wind forecast published at least 6 h ahead");
  });
});
