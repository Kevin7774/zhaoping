import type { TaskStreamEvent } from "../../shared/hooks/useTaskStream";

export type HumanGateRequest = {
  eventKey: string;
  taskId: string;
  context: string;
  draft: string;
  candidateName?: string;
  requiresLeadPreview?: boolean;
  leadPreview?: LeadPreview;
};

export type LeadPreview = {
  totalCount: number;
  omittedCount: number;
  leads: LeadPreviewItem[];
};

export type LeadPreviewItem = {
  name?: string;
  sourcePlatform?: string;
  sourceUrl?: string;
  evidenceSummary?: string;
  confidence?: number;
  matchedJob?: string;
  complianceStatus?: string;
  ingestionAction?: string;
};

type AwaitingPayload = {
  prompt?: string;
  draft?: unknown;
  requires_lead_preview?: unknown;
  requiresLeadPreview?: unknown;
  lead_preview?: unknown;
  leadPreview?: unknown;
};

export function humanGateRequestFromEvent(event: TaskStreamEvent, taskId: string): HumanGateRequest | null {
  if (event.type !== "human_gate" || event.status === "processing") return null;

  const awaiting = event.data?.awaiting as AwaitingPayload | undefined;
  if (!awaiting) return null;

  const draft = awaiting.draft;
  const candidateName = readString(draft, ["candidate_name", "candidateName", "name"]);
  const request: HumanGateRequest = {
    eventKey: String(event.id ?? `${event.created_at ?? ""}:${event.message ?? ""}`),
    taskId,
    context: awaiting.prompt || event.message || "AI Agent 请求人工确认",
    draft: draftToText(draft),
    candidateName,
  };
  const requiresLeadPreview = Boolean(awaiting.requires_lead_preview ?? awaiting.requiresLeadPreview);
  const leadPreview = normalizeLeadPreview(awaiting.lead_preview ?? awaiting.leadPreview);
  if (requiresLeadPreview) request.requiresLeadPreview = true;
  if (leadPreview) request.leadPreview = leadPreview;
  return request;
}

function normalizeLeadPreview(value: unknown): LeadPreview | undefined {
  if (!value || typeof value !== "object") return undefined;
  const record = value as Record<string, unknown>;
  const rawLeads = Array.isArray(record.leads) ? record.leads : [];
  return {
    totalCount: readNumber(record, ["total_count", "totalCount"]),
    omittedCount: readNumber(record, ["omitted_count", "omittedCount"]),
    leads: rawLeads
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
      .map((item) => ({
        name: readString(item, ["name", "entity_name", "entityName"]),
        sourcePlatform: readString(item, ["source_platform", "sourcePlatform"]),
        sourceUrl: readString(item, ["source_url", "sourceUrl"]),
        evidenceSummary: readString(item, ["evidence_summary", "evidenceSummary"]),
        confidence: readOptionalNumber(item, ["confidence"]),
        matchedJob: readString(item, ["matched_job", "matchedJob"]),
        complianceStatus: readString(item, ["compliance_status", "complianceStatus"]),
        ingestionAction: readString(item, ["ingestion_action", "ingestionAction"]),
      })),
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

function readNumber(value: Record<string, unknown>, keys: string[]) {
  return readOptionalNumber(value, keys) ?? 0;
}

function readOptionalNumber(value: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const item = value[key];
    if (typeof item === "number" && Number.isFinite(item)) return item;
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
