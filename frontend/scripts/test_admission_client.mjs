import assert from "node:assert/strict";
import { test } from "node:test";
import { apiFetch, ApiError } from "../lib/api/client.ts";

test("429 preserves retry guidance for search and recommendations", async () => {
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  globalThis.window = globalThis;
  try {
    for (const [header, expected] of [["17", "17 seconds"], [null, "later"], ["bad", "later"]]) {
      globalThis.fetch = async () => new Response("{}", {
        status: 429, headers: header === null ? {} : { "Retry-After": header },
      });
      await assert.rejects(apiFetch("/api/search", { method: "POST", body: { query: "robotics" } }),
        error => error instanceof ApiError && error.kind === "rate-limited"
          && error.status === 429 && error.message.includes(expected)
          && !error.message.includes("AI explanation"));
    }
  } finally {
    globalThis.fetch = originalFetch;
    if (originalWindow === undefined) delete globalThis.window;
    else globalThis.window = originalWindow;
  }
});
