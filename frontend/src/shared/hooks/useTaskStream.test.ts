// @vitest-environment jsdom

import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  calculateRetryDelay,
  isTerminalTaskStatus,
  mergeTaskEvent,
  useTaskStream,
  type TaskStreamEvent,
} from "./useTaskStream";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

class MockEventSource {
  static instances: MockEventSource[] = [];

  url: string;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  listeners = new Map<string, (message: MessageEvent<string>) => void>();
  close = vi.fn();

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListener) {
    this.listeners.set(type, listener as (message: MessageEvent<string>) => void);
  }

  emit(type: string, payload: unknown) {
    this.listeners.get(type)?.({ data: JSON.stringify(payload) } as MessageEvent<string>);
  }

  fail() {
    this.onerror?.();
  }
}

describe("useTaskStream helpers", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    MockEventSource.instances = [];
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("EventSource", MockEventSource);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

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

  it("falls back to polling GET /tasks/{taskId} after the SSE retry limit is reached", async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          task_id: "task_1",
          status: "processing",
          audit_events: [{ id: 1, type: "summary", message: "fallback snapshot" }],
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          task_id: "task_1",
          status: "done",
          result: { ok: true },
          audit_events: [{ id: 2, type: "summary", message: "done from polling", status: "done" }],
        }),
      );

    const { result } = renderHook(() =>
      useTaskStream("task_1", {
        maxRetries: 0,
        fallbackPollIntervalMs: 10,
      }),
    );

    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    act(() => {
      MockEventSource.instances[0].fail();
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/tasks/task_1", expect.objectContaining({ method: "GET" })));
    await waitFor(() => expect(result.current.taskSnapshot?.status).toBe("done"));

    expect(result.current.usedFallbackPolling).toBe(true);
    expect(result.current.connectionState).toBe("closed");
  });

  it("loads an initial task snapshot while the SSE connection is open", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        task_id: "task_awaiting",
        status: "awaiting_human",
        awaiting: { prompt: "请确认", draft: { body: "确认内容" } },
        audit_events: [
          {
            id: 1,
            type: "human_gate",
            status: "awaiting_human",
            data: { awaiting: { prompt: "请确认", draft: { body: "确认内容" } } },
          },
        ],
      }),
    );

    const { result } = renderHook(() => useTaskStream("task_awaiting"));

    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    act(() => {
      MockEventSource.instances[0].onopen?.();
    });

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/tasks/task_awaiting", expect.objectContaining({ method: "GET" })),
    );
    await waitFor(() => expect(result.current.taskSnapshot?.status).toBe("awaiting_human"));

    expect(result.current.events).toHaveLength(1);
    expect(result.current.usedFallbackPolling).toBe(false);
    expect(result.current.connectionState).toBe("open");
  });

  it("loads an initial task snapshot even before EventSource onopen fires", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        task_id: "task_preopen",
        status: "awaiting_human",
        awaiting: { prompt: "请确认", draft: { body: "确认内容" } },
        audit_events: [],
      }),
    );

    const { result } = renderHook(() => useTaskStream("task_preopen"));

    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/tasks/task_preopen", expect.objectContaining({ method: "GET" })),
    );
    await waitFor(() => expect(result.current.taskSnapshot?.status).toBe("awaiting_human"));
  });

  it("refreshes nonterminal snapshots while waiting for SSE events", async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          task_id: "task_refresh",
          status: "processing",
          audit_events: [{ id: 1, type: "summary", message: "processing" }],
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          task_id: "task_refresh",
          status: "awaiting_human",
          awaiting: { prompt: "请确认", draft: { body: "确认内容" } },
          audit_events: [
            { id: 1, type: "summary", message: "processing" },
            {
              id: 2,
              type: "human_gate",
              status: "awaiting_human",
              data: { awaiting: { prompt: "请确认", draft: { body: "确认内容" } } },
            },
          ],
        }),
      );

    const { result } = renderHook(() => useTaskStream("task_refresh", { fallbackPollIntervalMs: 10 }));

    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2));
    await waitFor(() => expect(result.current.taskSnapshot?.status).toBe("awaiting_human"));
    expect(result.current.events.map((event) => event.type)).toContain("human_gate");
  });
});
