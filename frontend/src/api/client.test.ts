import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, buildQueryString } from "./client";

function mockFetch(response: Response | Error) {
  const fn = vi.fn(() =>
    response instanceof Error ? Promise.reject(response) : Promise.resolve(response),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("buildQueryString", () => {
  it("drops undefined, null and empty values", () => {
    expect(
      buildQueryString({ start: "2026-01-02", end: undefined, horizon_h: null, gate_time: "" }),
    ).toBe("?start=2026-01-02");
  });

  it("returns an empty string when nothing is set", () => {
    expect(buildQueryString({})).toBe("");
  });

  it("keeps zero", () => {
    expect(buildQueryString({ horizon_h: 0 })).toBe("?horizon_h=0");
  });
});

describe("api client", () => {
  it("calls the series endpoint with only the given query parameters", async () => {
    const fetchMock = mockFetch(json({ points: [] }));

    await api.series({ start: "2026-01-02", end: "2026-01-05", mode: "horizon", horizon_h: 6 });

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url] = fetchMock.mock.calls[0] as unknown as [string];
    expect(url).toBe("/api/series?start=2026-01-02&end=2026-01-05&mode=horizon&horizon_h=6");
  });

  it("returns parsed JSON on success", async () => {
    mockFetch(json({ status: "ok" }));

    await expect(api.meta()).resolves.toEqual({ status: "ok" });
  });

  it("turns a FastAPI 422 into an ApiError with per-field messages", async () => {
    mockFetch(
      json(
        {
          detail: [
            {
              type: "value_error",
              loc: ["query", "start"],
              msg: "start must be within the snapshot range 2026-01-02 to 2026-02-01",
              input: "2025-12-01",
            },
          ],
        },
        422,
      ),
    );

    const error = await api.metrics({ start: "2025-12-01" }).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.status).toBe(422);
    expect(apiError.fieldErrors).toEqual([
      { field: "start", message: "start must be within the snapshot range 2026-01-02 to 2026-02-01" },
    ]);
    expect(apiError.message).toBe(
      "Invalid request: start: start must be within the snapshot range 2026-01-02 to 2026-02-01",
    );
  });

  it("uses a generic message for non-JSON error bodies", async () => {
    mockFetch(new Response("<html>Bad gateway</html>", { status: 502 }));

    await expect(api.meta()).rejects.toMatchObject({
      status: 502,
      message: "Request failed (HTTP 502)",
    });
  });

  it("reports network failures as status 0", async () => {
    mockFetch(new TypeError("Failed to fetch"));

    await expect(api.byHorizon({ start: "2026-01-02" })).rejects.toMatchObject({
      status: 0,
      message: "Cannot reach the API. Check your connection and try again.",
    });
  });
});
