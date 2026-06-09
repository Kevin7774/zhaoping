import { describe, expect, it } from "vitest";

import {
  calculateRetryDelay,
  isTerminalTaskStatus,
  mergeTaskEvent,
  type TaskStreamEvent,
} from "./useTaskStream";

describe("useTaskStream helpers", () => {
  it("merges unique task events and keeps id ordering", () => {
    const existing: TaskStreamEvent[] = [{ id: 2, type: "summary", message: "done" }];
    const next = mergeTaskEvent(existing, {
      id: 1,
      type: "step_start",
      message: "start",
    });

    expect(next.map((event) => event.id)).toEqual([1, 2]);
    expect(mergeTaskEvent(next, next[0])).toHaveLength(2);
  });

  it("detects terminal task statuses", () => {
    expect(isTerminalTaskStatus("done")).toBe(true);
    expect(isTerminalTaskStatus("error")).toBe(true);
    expect(isTerminalTaskStatus("cancelled")).toBe(true);
    expect(isTerminalTaskStatus("processing")).toBe(false);
  });

  it("uses capped exponential retry delay", () => {
    expect(calculateRetryDelay(0)).toBe(1_000);
    expect(calculateRetryDelay(1)).toBe(2_000);
    expect(calculateRetryDelay(4)).toBe(16_000);
    expect(calculateRetryDelay(10)).toBe(30_000);
  });
});
