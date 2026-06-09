import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient, taskStreamUrl } from "../api/client";

export type TaskStatus = "processing" | "awaiting_human" | "done" | "error" | "cancelled";

export type TaskStreamEventType =
  | "step_start"
  | "tool_call"
  | "evidence"
  | "summary"
  | "human_gate"
  | "done"
  | "error"
  | "cancelled";

export type TaskStreamEvent = {
  id?: number | string;
  task_id?: string;
  type: TaskStreamEventType;
  agent_id?: string | null;
  step_index?: number | null;
  step_label?: string | null;
  message?: string;
  data?: Record<string, unknown>;
  status?: TaskStatus | null;
  created_at?: string;
};

export type TaskSnapshot = {
  task_id: string;
  scenario_id?: string;
  status: TaskStatus;
  current_agent?: string | null;
  current_step?: number | null;
  total_steps?: number;
  awaiting?: unknown;
  result?: unknown;
  error?: string | null;
  audit_events: TaskStreamEvent[];
  steps_done?: unknown[];
};

export type TaskStreamConnectionState = "idle" | "connecting" | "open" | "retrying" | "polling" | "closed";

export type UseTaskStreamOptions = {
  enabled?: boolean;
  maxRetries?: number;
  fallbackPollIntervalMs?: number;
  onEvent?: (event: TaskStreamEvent) => void;
};

export const TASK_STREAM_EVENT_NAMES: TaskStreamEventType[] = [
  "step_start",
  "tool_call",
  "evidence",
  "summary",
  "human_gate",
  "done",
  "error",
  "cancelled",
];

const TERMINAL_STATUSES: ReadonlySet<TaskStatus> = new Set(["done", "error", "cancelled"]);

export function isTerminalTaskStatus(status?: string | null) {
  return TERMINAL_STATUSES.has(status as TaskStatus);
}

export function calculateRetryDelay(retryCount: number, baseDelay = 1_000, maxDelay = 30_000) {
  return Math.min(maxDelay, baseDelay * 2 ** Math.max(0, retryCount));
}

function eventIdentity(event: TaskStreamEvent) {
  if (event.id !== undefined && event.id !== null) return String(event.id);
  return [event.type, event.agent_id, event.step_index, event.created_at, event.message].join(":");
}

export function mergeTaskEvent(events: TaskStreamEvent[], event: TaskStreamEvent) {
  const identity = eventIdentity(event);
  if (events.some((item) => eventIdentity(item) === identity)) return events;

  return [...events, event].sort((left, right) => {
    const leftId = Number(left.id);
    const rightId = Number(right.id);
    if (Number.isFinite(leftId) && Number.isFinite(rightId)) return leftId - rightId;
    return 0;
  });
}

function eventStatus(event: TaskStreamEvent): TaskStatus {
  if (event.status) return event.status;
  if (event.type === "human_gate") return "awaiting_human";
  if (event.type === "done") return "done";
  if (event.type === "error") return "error";
  if (event.type === "cancelled") return "cancelled";
  return "processing";
}

function eventData<T>(event: TaskStreamEvent, key: string): T | undefined {
  return event.data?.[key] as T | undefined;
}

export function applyTaskStreamEvent(
  snapshot: TaskSnapshot | null,
  event: TaskStreamEvent,
  fallbackTaskId: string,
): TaskSnapshot {
  const next: TaskSnapshot = {
    task_id: snapshot?.task_id ?? event.task_id ?? fallbackTaskId,
    status: snapshot?.status ?? "processing",
    current_agent: snapshot?.current_agent ?? null,
    current_step: snapshot?.current_step ?? null,
    total_steps: snapshot?.total_steps,
    awaiting: snapshot?.awaiting,
    result: snapshot?.result,
    error: snapshot?.error ?? null,
    audit_events: mergeTaskEvent(snapshot?.audit_events ?? [], event),
    steps_done: snapshot?.steps_done,
  };

  next.status = eventStatus(event);

  if (event.agent_id !== undefined) next.current_agent = event.agent_id;
  if (typeof event.step_index === "number") next.current_step = event.step_index;

  const snapshotFromEvent = eventData<Partial<TaskSnapshot>>(event, "snapshot");
  if (snapshotFromEvent) {
    Object.assign(next, snapshotFromEvent);
  }

  if (event.type === "human_gate") {
    next.awaiting = eventData(event, "awaiting") ?? next.awaiting;
  }

  if (event.type === "summary") {
    const stepDone = eventData<unknown>(event, "step_done");
    if (stepDone) next.steps_done = [...(next.steps_done ?? []), stepDone];
    next.result = eventData(event, "result") ?? next.result;
  }

  if (event.type === "done") {
    next.result = eventData(event, "result") ?? next.result;
    next.awaiting = null;
  }

  if (event.type === "error" || event.type === "cancelled") {
    next.error = event.message ?? null;
    next.awaiting = null;
  }

  if (isTerminalTaskStatus(next.status)) {
    next.awaiting = null;
  }

  return next;
}

export function useTaskStream(taskId: string | null | undefined, options: UseTaskStreamOptions = {}) {
  const { enabled = true, maxRetries = 6, fallbackPollIntervalMs = 600, onEvent } = options;
  const [events, setEvents] = useState<TaskStreamEvent[]>([]);
  const [taskSnapshot, setTaskSnapshot] = useState<TaskSnapshot | null>(null);
  const [connectionState, setConnectionState] = useState<TaskStreamConnectionState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const [usedFallbackPolling, setUsedFallbackPolling] = useState(false);

  const eventSourceRef = useRef<EventSource | null>(null);
  const retryTimerRef = useRef<number | null>(null);
  const pollingTimerRef = useRef<number | null>(null);
  const snapshotRefreshTimerRef = useRef<number | null>(null);
  const retryCountRef = useRef(0);
  const closedRef = useRef(false);
  const latestStatusRef = useRef<TaskStatus | null>(null);

  const clearRetryTimer = useCallback(() => {
    if (retryTimerRef.current !== null) {
      window.clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  }, []);

  const closeStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }, []);

  const clearPollingTimer = useCallback(() => {
    if (pollingTimerRef.current !== null) {
      window.clearTimeout(pollingTimerRef.current);
      pollingTimerRef.current = null;
    }
  }, []);

  const clearSnapshotRefreshTimer = useCallback(() => {
    if (snapshotRefreshTimerRef.current !== null) {
      window.clearTimeout(snapshotRefreshTimerRef.current);
      snapshotRefreshTimerRef.current = null;
    }
  }, []);

  const resetStream = useCallback(() => {
    clearRetryTimer();
    clearPollingTimer();
    clearSnapshotRefreshTimer();
    closeStream();
    retryCountRef.current = 0;
    latestStatusRef.current = null;
    setRetryCount(0);
    setUsedFallbackPolling(false);
    setEvents([]);
    setTaskSnapshot(null);
    setError(null);
    setConnectionState("idle");
  }, [clearPollingTimer, clearRetryTimer, clearSnapshotRefreshTimer, closeStream]);

  const handleEvent = useCallback(
    (event: TaskStreamEvent, activeTaskId: string) => {
      setEvents((previous) => mergeTaskEvent(previous, event));
      setTaskSnapshot((previous) => {
        const next = applyTaskStreamEvent(previous, event, activeTaskId);
        latestStatusRef.current = next.status;
        return next;
      });
      onEvent?.(event);

      const status = event.status ?? (["done", "error", "cancelled"].includes(event.type) ? event.type : null);
      if (isTerminalTaskStatus(status)) {
        closeStream();
        clearRetryTimer();
        clearSnapshotRefreshTimer();
        setConnectionState("closed");
      }
    },
    [clearRetryTimer, clearSnapshotRefreshTimer, closeStream, onEvent],
  );

  useEffect(() => {
    resetStream();

    if (!taskId || !enabled) return undefined;

    closedRef.current = false;

    const stopForTerminal = (snapshot: TaskSnapshot) => {
      latestStatusRef.current = snapshot.status;
      if (isTerminalTaskStatus(snapshot.status)) {
        closeStream();
        clearRetryTimer();
        clearPollingTimer();
        clearSnapshotRefreshTimer();
        setConnectionState("closed");
        return true;
      }
      return false;
    };

    const loadSnapshot = async () => {
      try {
        const snapshot = await apiClient.get<TaskSnapshot>(`/tasks/${encodeURIComponent(taskId)}`);
        if (closedRef.current || !taskId) return null;
        setError(null);
        setTaskSnapshot(snapshot);
        setEvents(snapshot.audit_events ?? []);
        stopForTerminal(snapshot);
        return snapshot;
      } catch (snapshotError) {
        if (!closedRef.current) {
          setError(snapshotError instanceof Error ? snapshotError.message : "Failed to load task snapshot.");
        }
        return null;
      }
    };

    const poll = async () => {
      if (closedRef.current || !taskId || isTerminalTaskStatus(latestStatusRef.current)) return;

      setConnectionState("polling");
      setUsedFallbackPolling(true);

      const snapshot = await loadSnapshot();
      if (snapshot && stopForTerminal(snapshot)) return;

      if (!closedRef.current && !isTerminalTaskStatus(latestStatusRef.current)) {
        pollingTimerRef.current = window.setTimeout(poll, fallbackPollIntervalMs);
      }
    };

    const startFallbackPolling = () => {
      closeStream();
      clearRetryTimer();
      clearPollingTimer();
      clearSnapshotRefreshTimer();
      void poll();
    };

    const scheduleSnapshotRefresh = () => {
      clearSnapshotRefreshTimer();
      if (closedRef.current || !taskId || isTerminalTaskStatus(latestStatusRef.current)) return;
      snapshotRefreshTimerRef.current = window.setTimeout(async () => {
        if (closedRef.current || !taskId || isTerminalTaskStatus(latestStatusRef.current)) return;
        const snapshot = await loadSnapshot();
        if (snapshot && !isTerminalTaskStatus(snapshot.status)) {
          scheduleSnapshotRefresh();
        }
      }, fallbackPollIntervalMs);
    };

    let initialSnapshotRequested = false;
    const loadInitialSnapshotOnce = () => {
      if (initialSnapshotRequested) return;
      initialSnapshotRequested = true;
      void loadSnapshot();
    };

    const open = () => {
      if (closedRef.current || !taskId) return;

      closeStream();
      setConnectionState(retryCountRef.current > 0 ? "retrying" : "connecting");

      const source = new EventSource(taskStreamUrl(taskId));
      eventSourceRef.current = source;
      loadInitialSnapshotOnce();
      scheduleSnapshotRefresh();

      source.onopen = () => {
        retryCountRef.current = 0;
        setRetryCount(0);
        setError(null);
        setConnectionState("open");
        loadInitialSnapshotOnce();
      };

      for (const eventName of TASK_STREAM_EVENT_NAMES) {
        source.addEventListener(eventName, (message) => {
          try {
            handleEvent(JSON.parse(message.data) as TaskStreamEvent, taskId);
          } catch (eventError) {
            setError(eventError instanceof Error ? eventError.message : "Failed to parse task stream event.");
          }
        });
      }

      source.onerror = () => {
        closeStream();

        if (closedRef.current || isTerminalTaskStatus(latestStatusRef.current)) {
          setConnectionState("closed");
          return;
        }

        if (retryCountRef.current >= maxRetries) {
          setError("Task stream disconnected; falling back to task polling.");
          startFallbackPolling();
          return;
        }

        const delay = calculateRetryDelay(retryCountRef.current);
        retryCountRef.current += 1;
        setRetryCount(retryCountRef.current);
        setConnectionState("retrying");
        retryTimerRef.current = window.setTimeout(open, delay);
      };
    };

    open();

    return () => {
      closedRef.current = true;
      clearRetryTimer();
      clearPollingTimer();
      clearSnapshotRefreshTimer();
      closeStream();
      setConnectionState("closed");
    };
  }, [
    clearPollingTimer,
    clearRetryTimer,
    clearSnapshotRefreshTimer,
    closeStream,
    enabled,
    fallbackPollIntervalMs,
    handleEvent,
    maxRetries,
    resetStream,
    taskId,
  ]);

  return {
    events,
    taskSnapshot,
    connectionState,
    error,
    retryCount,
    usedFallbackPolling,
    reset: resetStream,
    close: closeStream,
  };
}
