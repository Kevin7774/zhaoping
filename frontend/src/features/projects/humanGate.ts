import type { TaskStreamEvent } from "../../shared/hooks/useTaskStream";

export type HumanGateRequest = {
  eventKey: string;
  taskId: string;
  context: string;
  draft: string;
  candidateName?: string;
};

type AwaitingPayload = {
  prompt?: string;
  draft?: unknown;
};

export function humanGateRequestFromEvent(event: TaskStreamEvent, taskId: string): HumanGateRequest | null {
  if (event.type !== "human_gate" || event.status === "processing") return null;

  const awaiting = event.data?.awaiting as AwaitingPayload | undefined;
  if (!awaiting) return null;

  const draft = awaiting.draft;
  const candidateName = readString(draft, ["candidate_name", "candidateName", "name"]);
  return {
    eventKey: String(event.id ?? `${event.created_at ?? ""}:${event.message ?? ""}`),
    taskId,
    context: awaiting.prompt || event.message || "AI Agent 请求人工确认",
    draft: draftToText(draft),
    candidateName,
  };
}

function readString(value: unknown, keys: string[]) {
  if (!value || typeof value !== "object") return undefined;
  const record = value as Record<string, unknown>;
  for (const key of keys) {
    const item = record[key];
    if (typeof item === "string" && item.trim()) return item;
  }
  return undefined;
}

function draftToText(value: unknown) {
  if (typeof value === "string") return value;
  if (!value || typeof value !== "object") return "";
  const record = value as Record<string, unknown>;
  for (const key of ["body", "draft", "message", "content", "email_body"]) {
    const item = record[key];
    if (typeof item === "string") return item;
  }
  return JSON.stringify(value, null, 2);
}
