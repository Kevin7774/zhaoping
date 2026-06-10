import { useState } from "react";

import { runProjectScenario, type RunProjectScenarioAction } from "../features/projects/api";
import {
  countBy,
  DataError,
  DataLoading,
  entriesByCount,
  GhostButton,
  MetricStrip,
  PageHeader,
  PrimaryButton,
  rememberTaskId,
  SectionPanel,
  topCandidates,
  useActiveProjectId,
  useWorkspaceData,
} from "./projectWorkspace";

function DistributionList({ entries }: { entries: Array<[string, number]> }) {
  const max = Math.max(...entries.map(([, count]) => count), 1);

  return (
    <div className="space-y-3">
      {entries.map(([label, count]) => (
        <div key={label}>
          <div className="mb-1 flex items-center justify-between gap-3 text-[12px]">
            <span className="truncate font-medium text-[#374151]">{label}</span>
            <span className="text-[#6B7280]">{count}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-[#EEF2F7]">
            <div className="h-full rounded-full bg-[#2563EB]" style={{ width: `${Math.max(8, (count / max) * 100)}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function TalentMapPage() {
  const projectId = useActiveProjectId();
  const data = useWorkspaceData({ projectId });
  const [runningJobId, setRunningJobId] = useState<string | null>(null);
  const [createdTaskId, setCreatedTaskId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  if (data.loading) return <DataLoading />;
  if (data.error) return <DataError message={data.error} onRetry={data.reload} />;

  const sourceEntries = entriesByCount(countBy(data.candidates.map((candidate) => candidate.sourcePlatform)));
  const cityEntries = entriesByCount(countBy(data.candidates.map((candidate) => candidate.city)));
  const companyEntries = entriesByCount(countBy(data.candidates.map((candidate) => candidate.currentCompany)));

  const startSourcing = async (jobId: string) => {
    const job = data.jobs.find((item) => item.jobProfileId === jobId);
    if (!job) return;
    setRunningJobId(jobId);
    setActionError(null);
    try {
      const action: RunProjectScenarioAction = "find_candidates";
      const created = await runProjectScenario(data.projectId, job, action);
      rememberTaskId(created.task_id);
      setCreatedTaskId(created.task_id);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "找候选人任务启动失败");
    } finally {
      setRunningJobId(null);
    }
  };

  return (
    <div className="pb-8">
      <PageHeader
        title="找候选人"
        subtitle="按来源、城市和公司聚合候选人线索，检查当前人才地图覆盖面，并可为具体岗位启动找候选人任务。"
      />

      <MetricStrip
        items={[
          { label: "线索总数", value: data.candidates.length, helper: "当前已加载候选人" },
          { label: "来源平台", value: sourceEntries.length, helper: "sourcePlatform 聚合", tone: "text-[#2563EB]" },
          { label: "覆盖城市", value: cityEntries.length, helper: "city 聚合", tone: "text-[#16A34A]" },
          { label: "目标公司", value: companyEntries.length, helper: "currentCompany 聚合" },
        ]}
      />

      {createdTaskId ? (
        <div className="mb-5 rounded-[12px] border border-[#BFDBFE] bg-[#EFF6FF] px-4 py-3 text-[13px] text-[#1E40AF]">
          已创建找候选人任务：{createdTaskId}。可在任务记录页查看状态。
        </div>
      ) : null}
      {actionError ? (
        <div className="mb-5 rounded-[12px] border border-[#FECACA] bg-[#FEF2F2] px-4 py-3 text-[13px] text-[#EF4444]">
          {actionError}
        </div>
      ) : null}

      <div className="grid gap-5 xl:grid-cols-3">
        <SectionPanel title="来源分布">
          <DistributionList entries={sourceEntries} />
        </SectionPanel>
        <SectionPanel title="城市分布">
          <DistributionList entries={cityEntries} />
        </SectionPanel>
        <SectionPanel title="公司分布">
          <DistributionList entries={companyEntries} />
        </SectionPanel>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <SectionPanel title="按岗位启动搜索" subtitle="调用 POST /scenarios/run，创建后端任务并记录 task_id。">
          <div className="space-y-3">
            {data.jobs.map((job) => (
              <div key={job.jobProfileId} className="flex flex-col justify-between gap-3 rounded-[12px] bg-[#F9FAFB] px-4 py-3 md:flex-row md:items-center">
                <div className="min-w-0">
                  <div className="truncate text-[13px] font-semibold text-[#111827]">{job.roleName}</div>
                  <div className="mt-0.5 text-[12px] text-[#6B7280]">HC {job.headcount ?? "—"} · 已有关联候选人 {job.candidateCount ?? 0}</div>
                </div>
                <PrimaryButton onClick={() => startSourcing(job.jobProfileId)} disabled={runningJobId === job.jobProfileId}>
                  {runningJobId === job.jobProfileId ? "启动中" : "启动搜索"}
                </PrimaryButton>
              </div>
            ))}
            {!data.jobs.length ? <div className="text-[13px] text-[#6B7280]">暂无岗位可启动搜索。</div> : null}
          </div>
        </SectionPanel>

        <SectionPanel title="高分线索" subtitle="用于快速判断当前人才地图质量。">
          <div className="space-y-3">
            {topCandidates(data.candidates, 5).map((candidate) => (
              <div key={candidate.candidateId} className="rounded-[12px] bg-[#F9FAFB] px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-[13px] font-semibold text-[#111827]">{candidate.name}</div>
                    <div className="mt-0.5 truncate text-[12px] text-[#6B7280]">{candidate.currentCompany ?? "—"}</div>
                  </div>
                  <div className="text-[18px] font-bold text-[#2563EB]">{candidate.matchScore ?? "—"}</div>
                </div>
                {candidate.sourceUrl ? (
                  <a
                    href={candidate.sourceUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 inline-flex text-[12px] font-medium text-[#2563EB]"
                  >
                    查看线索来源
                  </a>
                ) : (
                  <div className="mt-2">
                    <GhostButton disabled>暂无来源链接</GhostButton>
                  </div>
                )}
              </div>
            ))}
          </div>
        </SectionPanel>
      </div>
    </div>
  );
}
