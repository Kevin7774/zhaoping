import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";

import type { Candidate } from "../features/candidates/types";
import type { JobProfile } from "../features/jobs/types";
import {
  getIntegrationsStatus,
  getLatestWeeklyReport,
  getOutreachHistory,
  getProject,
  getProjectCandidatesPage,
  getProjectJobs,
  getScenariosMeta,
  type IntegrationCapabilityStatus,
  type IntegrationsStatusResponse,
  type OutreachHistoryItem,
  type ProjectRecord,
  type ScenarioMetaResponse,
  type WeeklyReport,
  type WeeklyReportRecord,
} from "../features/projects/api";

export const DEFAULT_PROJECT_ID = "project_2026_ai_team";
export const ACTIVE_PROJECT_ID_KEY = "zhaoping_active_project_id";
export const RECENT_TASK_IDS_KEY = "zhaoping_recent_task_ids";

const DEFAULT_CANDIDATE_LIMIT = 80;
const CONNECTED_CAPABILITY_STATUSES = new Set(["active", "available"]);

export type WorkspaceDataOptions = {
  projectId?: string;
  candidateLimit?: number;
  includeIntegrations?: boolean;
  includeLatestReport?: boolean;
  includeOutreachHistory?: boolean;
  includeScenarios?: boolean;
};

export type WorkspaceOptionalErrors = {
  integrations?: string;
  latestReport?: string;
  outreachHistory?: string;
  scenarios?: string;
};

export type WorkspaceData = {
  projectId: string;
  project: ProjectRecord | null;
  jobs: JobProfile[];
  candidates: Candidate[];
  candidateTotal: number | null;
  hasMoreCandidates: boolean;
  integrations: IntegrationsStatusResponse | null;
  latestReport: WeeklyReportRecord | null;
  outreachHistory: OutreachHistoryItem[];
  scenarios: ScenarioMetaResponse | null;
  optionalErrors: WorkspaceOptionalErrors;
  loading: boolean;
  error: string | null;
  reload: () => void;
};

type OptionalResult<T> = {
  value: T | null;
  error?: string;
};

type MetricItem = {
  label: string;
  value: ReactNode;
  helper?: string;
  tone?: string;
};

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "请求失败";
}

async function optional<T>(enabled: boolean, loader: () => Promise<T>): Promise<OptionalResult<T>> {
  if (!enabled) return { value: null };
  try {
    return { value: await loader() };
  } catch (error) {
    return { value: null, error: errorMessage(error) };
  }
}

export function readActiveProjectId() {
  if (typeof window === "undefined") return null;
  try {
    const value = window.localStorage.getItem(ACTIVE_PROJECT_ID_KEY)?.trim();
    return value || null;
  } catch {
    return null;
  }
}

export function rememberActiveProjectId(projectId: string) {
  const normalized = projectId.trim();
  if (!normalized || typeof window === "undefined") return;
  try {
    window.localStorage.setItem(ACTIVE_PROJECT_ID_KEY, normalized);
  } catch {
    // localStorage can be unavailable in private browsing or tests. The URL project still drives the page.
  }
}

export function useActiveProjectId(fallback = DEFAULT_PROJECT_ID) {
  const { projectId: routeProjectId } = useParams();
  const [storedProjectId, setStoredProjectId] = useState(() => readActiveProjectId() || fallback);
  const activeProjectId = routeProjectId?.trim() || storedProjectId || fallback;

  useEffect(() => {
    if (!routeProjectId?.trim()) return;
    rememberActiveProjectId(routeProjectId);
    setStoredProjectId(routeProjectId);
  }, [routeProjectId]);

  return activeProjectId;
}

export function useWorkspaceData({
  projectId = DEFAULT_PROJECT_ID,
  candidateLimit = DEFAULT_CANDIDATE_LIMIT,
  includeIntegrations = false,
  includeLatestReport = false,
  includeOutreachHistory = false,
  includeScenarios = false,
}: WorkspaceDataOptions = {}): WorkspaceData {
  const [reloadToken, setReloadToken] = useState(0);
  const [state, setState] = useState<Omit<WorkspaceData, "reload">>({
    projectId,
    project: null,
    jobs: [],
    candidates: [],
    candidateTotal: null,
    hasMoreCandidates: false,
    integrations: null,
    latestReport: null,
    outreachHistory: [],
    scenarios: null,
    optionalErrors: {},
    loading: true,
    error: null,
  });

  const reload = useCallback(() => setReloadToken((current) => current + 1), []);

  useEffect(() => {
    let cancelled = false;

    setState((current) => ({
      ...current,
      projectId,
      loading: true,
      error: null,
      optionalErrors: {},
    }));

    async function load() {
      try {
        const [project, jobs, candidatesPage] = await Promise.all([
          getProject(projectId),
          getProjectJobs(projectId),
          getProjectCandidatesPage(projectId, { skip: 0, limit: candidateLimit }),
        ]);

        const [integrations, latestReport, outreachHistory, scenarios] = await Promise.all([
          optional(includeIntegrations, getIntegrationsStatus),
          optional(includeLatestReport, () => getLatestWeeklyReport(projectId)),
          optional(includeOutreachHistory, () => getOutreachHistory({ projectId })),
          optional(includeScenarios, getScenariosMeta),
        ]);

        if (cancelled) return;

        setState({
          projectId,
          project,
          jobs,
          candidates: candidatesPage.candidates,
          candidateTotal: candidatesPage.total,
          hasMoreCandidates: candidatesPage.hasMore,
          integrations: integrations.value,
          latestReport: latestReport.value,
          outreachHistory: outreachHistory.value?.items ?? [],
          scenarios: scenarios.value,
          optionalErrors: {
            integrations: integrations.error,
            latestReport: latestReport.error,
            outreachHistory: outreachHistory.error,
            scenarios: scenarios.error,
          },
          loading: false,
          error: null,
        });
      } catch (error) {
        if (cancelled) return;
        setState((current) => ({
          ...current,
          projectId,
          loading: false,
          error: errorMessage(error),
        }));
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, [
    candidateLimit,
    includeIntegrations,
    includeLatestReport,
    includeOutreachHistory,
    includeScenarios,
    projectId,
    reloadToken,
  ]);

  return { ...state, reload };
}

export function readRecentTaskIds() {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(RECENT_TASK_IDS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is string => typeof item === "string" && Boolean(item.trim())).slice(0, 12);
  } catch {
    return [];
  }
}

export function rememberTaskId(taskId: string) {
  const normalized = taskId.trim();
  if (!normalized || typeof window === "undefined") return;
  try {
    const next = [normalized, ...readRecentTaskIds().filter((item) => item !== normalized)].slice(0, 12);
    window.localStorage.setItem(RECENT_TASK_IDS_KEY, JSON.stringify(next));
  } catch {
    // localStorage can be unavailable in private browsing or tests. Task creation still succeeds without it.
  }
}

export function candidateCounts(candidates: Candidate[]) {
  return candidates.reduce<Record<string, number>>((counts, candidate) => {
    counts[candidate.targetJobProfileId] = (counts[candidate.targetJobProfileId] ?? 0) + 1;
    return counts;
  }, {});
}

export function averageMatchScore(candidates: Candidate[]) {
  const scores = candidates
    .map((candidate) => candidate.matchScore)
    .filter((score): score is number => typeof score === "number" && Number.isFinite(score));
  if (!scores.length) return null;
  return Math.round(scores.reduce((total, score) => total + score, 0) / scores.length);
}

export function topCandidates(candidates: Candidate[], limit = 5) {
  return [...candidates]
    .sort((left, right) => (right.matchScore ?? -1) - (left.matchScore ?? -1))
    .slice(0, limit);
}

export function uniqueValues(values: Array<string | undefined>) {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value)))).sort();
}

export function countBy(values: Array<string | undefined>) {
  return values.reduce<Record<string, number>>((counts, value) => {
    const key = value || "未标注";
    counts[key] = (counts[key] ?? 0) + 1;
    return counts;
  }, {});
}

export function entriesByCount(counts: Record<string, number>, limit = 8) {
  return Object.entries(counts)
    .sort((left, right) => right[1] - left[1])
    .slice(0, limit);
}

export function emptyWeeklyReport(): WeeklyReport {
  return {
    conclusion: undefined,
    keyProgress: [],
    topCandidates: [],
    risks: [],
    nextActions: [],
  };
}

export function hasWeeklyReport(report: WeeklyReport) {
  return Boolean(
    report.conclusion ||
      report.keyProgress.length ||
      report.topCandidates.length ||
      report.risks.length ||
      report.nextActions.length,
  );
}

export function formatDateTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("zh-CN");
}

export function statusLabel(status?: string | null) {
  if (status === "active") return "进行中";
  if (status === "done" || status === "completed") return "已完成";
  if (status === "processing") return "进行中";
  if (status === "awaiting_human") return "等待人工确认";
  if (status === "error") return "失败";
  if (status === "cancelled") return "已取消";
  if (status === "pending") return "等待中";
  if (status === "pending_outreach") return "待触达";
  if (status === "sourced") return "已入库";
  if (status === "screening") return "初筛中";
  if (status === "technical_interview") return "技术面";
  if (status === "offer") return "Offer";
  return status || "未知";
}

export function statusTone(status?: string | null) {
  if (status === "active" || status === "done" || status === "completed") return "bg-[#ECFDF3] text-[#16A34A]";
  if (status === "processing" || status === "pending_outreach") return "bg-[#EFF6FF] text-[#2563EB]";
  if (status === "awaiting_human" || status === "pending") return "bg-[#FFFBEB] text-[#F59E0B]";
  if (status === "error" || status === "cancelled") return "bg-[#FEF2F2] text-[#EF4444]";
  return "bg-[#F3F4F6] text-[#6B7280]";
}

export function capabilityStatusLabel(status?: string | null) {
  if (status === "active" || status === "available") return "已接入";
  if (status === "missing_key") return "缺少 Key";
  if (status === "disabled" || status === "not_configured") return "未接入";
  if (status === "manual_setup") return "需人工配置";
  if (status === "missing_tool") return "缺少运行工具";
  return status || "状态未知";
}

export function isCapabilityConnected(capability: IntegrationCapabilityStatus) {
  return CONNECTED_CAPABILITY_STATUSES.has(capability.status);
}

export function capabilityTitle(capability: IntegrationCapabilityStatus) {
  return capability.label || capability.name_zh || capability.id;
}

export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle: string;
  action?: ReactNode;
}) {
  return (
    <section className="mb-5 flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
      <div className="min-w-0">
        <h1 className="text-[24px] font-bold leading-8 text-[#111827]">{title}</h1>
        <p className="mt-2 max-w-3xl text-[13px] leading-5 text-[#6B7280]">{subtitle}</p>
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </section>
  );
}

export function MetricStrip({ items }: { items: MetricItem[] }) {
  return (
    <section className="mb-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4" aria-label="数据概览">
      {items.map((item) => (
        <article
          key={item.label}
          className="min-h-[104px] rounded-[14px] border border-[#E5E7EB] bg-white p-[18px] shadow-[0_1px_2px_rgba(16,24,40,0.04)]"
        >
          <div className="text-[13px] leading-5 text-[#6B7280]">{item.label}</div>
          <strong className={`mt-2 block text-[28px] font-bold leading-9 ${item.tone || "text-[#111827]"}`}>
            {item.value}
          </strong>
          {item.helper ? <div className="mt-1 text-[12px] leading-[18px] text-[#9CA3AF]">{item.helper}</div> : null}
        </article>
      ))}
    </section>
  );
}

export function SectionPanel({
  title,
  subtitle,
  action,
  children,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-[14px] border border-[#E5E7EB] bg-white shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
      <div className="flex flex-col justify-between gap-3 border-b border-[#EEF2F7] px-5 py-4 md:flex-row md:items-start">
        <div>
          <h2 className="text-[16px] font-semibold leading-6 text-[#111827]">{title}</h2>
          {subtitle ? <p className="mt-1 text-[12px] leading-[18px] text-[#6B7280]">{subtitle}</p> : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}

export function StatusPill({ status, label }: { status?: string | null; label?: string }) {
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-[12px] font-medium leading-[18px] ${statusTone(status)}`}>
      {label || statusLabel(status)}
    </span>
  );
}

export function DataLoading() {
  return (
    <div className="space-y-5">
      <div className="h-24 animate-pulse rounded-[14px] border border-[#E5E7EB] bg-white" />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((item) => (
          <div key={item} className="h-[104px] animate-pulse rounded-[14px] border border-[#E5E7EB] bg-white" />
        ))}
      </div>
      <div className="h-64 animate-pulse rounded-[14px] border border-[#E5E7EB] bg-white" />
    </div>
  );
}

export function DataError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-[14px] border border-[#FECACA] bg-[#FEF2F2] p-8 text-[14px] text-[#EF4444]">
      <div>{message}</div>
      <button
        type="button"
        onClick={onRetry}
        className="mt-4 h-[38px] rounded-[10px] bg-[#EF4444] px-3.5 text-[14px] font-medium text-white"
      >
        重新加载
      </button>
    </div>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-[12px] border border-dashed border-[#D1D5DB] bg-[#F9FAFB] px-5 py-8 text-center">
      <div className="text-[14px] font-semibold text-[#111827]">{title}</div>
      <p className="mt-2 text-[13px] leading-5 text-[#6B7280]">{body}</p>
    </div>
  );
}

export function GhostButton({
  children,
  onClick,
  disabled,
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className="h-9 rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] font-medium text-[#374151] transition hover:bg-[#F9FAFB] disabled:cursor-not-allowed disabled:opacity-50"
    >
      {children}
    </button>
  );
}

export function PrimaryButton({
  children,
  onClick,
  disabled,
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className="h-9 rounded-[10px] bg-[#2563EB] px-3 text-[13px] font-medium text-white transition hover:bg-[#1D4ED8] disabled:cursor-not-allowed disabled:opacity-50"
    >
      {children}
    </button>
  );
}
