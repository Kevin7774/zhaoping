import { Link } from "react-router-dom";

import {
  averageMatchScore,
  candidateCounts,
  DataError,
  DataLoading,
  MetricStrip,
  PageHeader,
  SectionPanel,
  StatusPill,
  useActiveProjectId,
  useWorkspaceData,
} from "./projectWorkspace";

export function JobsPage() {
  const projectId = useActiveProjectId();
  const data = useWorkspaceData({ projectId });

  if (data.loading) return <DataLoading />;
  if (data.error) return <DataError message={data.error} onRetry={data.reload} />;

  const counts = candidateCounts(data.candidates);
  const totalHeadcount = data.jobs.reduce((total, job) => total + (job.headcount ?? 0), 0);
  const score = averageMatchScore(data.candidates);

  return (
    <div className="pb-8">
      <PageHeader
        title="岗位分析"
        subtitle="集中查看当前项目的岗位画像进度、候选人关联数和招聘漏斗状态。"
        action={
          <Link
            to={`/projects/${encodeURIComponent(data.projectId)}`}
            className="inline-flex h-9 items-center rounded-[10px] bg-[#2563EB] px-3 text-[13px] font-medium text-white transition hover:bg-[#1D4ED8]"
          >
            回到项目执行
          </Link>
        }
      />

      <MetricStrip
        items={[
          { label: "开放岗位", value: data.jobs.length, helper: data.project?.name, tone: "text-[#2563EB]" },
          { label: "总 HC", value: totalHeadcount || "—", helper: "来自岗位 headcount" },
          { label: "关联候选人", value: data.candidates.length, helper: "按 jobId 聚合", tone: "text-[#16A34A]" },
          { label: "平均匹配分", value: score ?? "—", helper: "来自候选人 matchScore" },
        ]}
      />

      <SectionPanel title="岗位列表" subtitle="这些数据来自 GET /projects/{projectId}/jobs 和候选人关联接口。">
        {data.jobs.length === 0 ? (
          <div className="text-[13px] text-[#6B7280]">暂无岗位。请先在后端种子数据或项目页创建岗位。</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-[860px] w-full text-left text-[13px] leading-5">
              <thead className="h-11 bg-[#F9FAFB] text-[12px] font-semibold text-[#6B7280]">
                <tr>
                  <th className="w-[260px] px-4">岗位</th>
                  <th className="w-[82px] px-3">HC</th>
                  <th className="w-[120px] px-3">候选人</th>
                  <th className="w-[120px] px-3">平均分</th>
                  <th className="w-[120px] px-3">状态</th>
                  <th className="px-4">漏斗阶段</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#EEF2F7]">
                {data.jobs.map((job) => (
                  <tr key={job.jobProfileId} className="align-top">
                    <td className="px-4 py-4">
                      <div className="font-semibold text-[#111827]">{job.roleName}</div>
                      <div className="mt-1 text-[12px] text-[#9CA3AF]">{job.jobProfileId}</div>
                    </td>
                    <td className="px-3 py-4 text-[#374151]">{job.headcount ?? "—"}</td>
                    <td className="px-3 py-4 text-[#374151]">{counts[job.jobProfileId] ?? job.candidateCount ?? 0}</td>
                    <td className="px-3 py-4 text-[#374151]">{job.averageMatchScore ?? "—"}</td>
                    <td className="px-3 py-4">
                      <StatusPill status={job.pipelineStatus} />
                    </td>
                    <td className="px-4 py-4">
                      <div className="flex flex-wrap gap-2">
                        {job.funnel.map((stage) => (
                          <span
                            key={stage.key}
                            className="inline-flex items-center rounded-full bg-[#F3F4F6] px-2.5 py-1 text-[12px] text-[#374151]"
                          >
                            {stage.label} {stage.count}/{stage.target}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionPanel>
    </div>
  );
}
