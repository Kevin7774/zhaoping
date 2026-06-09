import { Link } from "react-router-dom";

import {
  averageMatchScore,
  DataError,
  DataLoading,
  DEFAULT_PROJECT_ID,
  emptyWeeklyReport,
  formatDateTime,
  hasWeeklyReport,
  isCapabilityConnected,
  MetricStrip,
  PageHeader,
  SectionPanel,
  StatusPill,
  topCandidates,
  useWorkspaceData,
} from "./projectWorkspace";

const pipeline = [
  { label: "岗位分析", path: "/jobs", description: "查看岗位画像、人数、候选人关联和当前状态" },
  { label: "找候选人", path: "/talent-map", description: "按来源、城市、公司分布检查人才地图" },
  { label: "候选人评估", path: "/scenarios", description: "从候选人列表启动 Agent 评估任务" },
  { label: "人群筛选", path: "/candidates", description: "按岗位、城市、分数、邮箱状态筛选候选人" },
  { label: "邮件触达", path: "/outreach", description: "生成后端邮件草稿并查看触达记录" },
  { label: "招聘周报", path: "/reports", description: "读取或启动本周招聘周报任务" },
];

export function DashboardPage() {
  const data = useWorkspaceData({
    includeIntegrations: true,
    includeLatestReport: true,
    includeScenarios: true,
  });

  if (data.loading) return <DataLoading />;
  if (data.error) return <DataError message={data.error} onRetry={data.reload} />;

  const score = data.project?.averageMatchScore || averageMatchScore(data.candidates);
  const connectedCapabilities =
    data.integrations?.capabilities?.filter((capability) => isCapabilityConnected(capability)).length ?? 0;
  const report = data.latestReport?.content ?? emptyWeeklyReport();

  return (
    <div className="pb-8">
      <PageHeader
        title="工作台"
        subtitle="汇总当前招聘项目的真实后端数据，并把岗位、候选人、任务、周报等能力入口放到一个工作面。"
        action={
          <Link
            to={`/projects/${DEFAULT_PROJECT_ID}`}
            className="inline-flex h-9 items-center rounded-[10px] bg-[#2563EB] px-3 text-[13px] font-medium text-white transition hover:bg-[#1D4ED8]"
          >
            进入招聘项目
          </Link>
        }
      />

      <MetricStrip
        items={[
          { label: "当前项目", value: data.project?.name ?? "—", helper: formatDateTime(data.project?.updatedAt) },
          { label: "开放岗位", value: data.jobs.length, helper: "GET /projects/{projectId}/jobs", tone: "text-[#2563EB]" },
          {
            label: "候选人",
            value: data.candidateTotal ?? data.candidates.length,
            helper: data.hasMoreCandidates ? "已加载前 80 条" : "已加载全部",
            tone: "text-[#16A34A]",
          },
          {
            label: "平均匹配分",
            value: score ?? "—",
            helper: `${connectedCapabilities} 个后端能力已接入`,
            tone: "text-[#111827]",
          },
        ]}
      />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)]">
        <SectionPanel title="招聘流程入口" subtitle="侧栏每个入口都对应一个可独立查看的数据页。">
          <div className="grid gap-3 md:grid-cols-2">
            {pipeline.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                className="rounded-[12px] border border-[#EEF2F7] bg-[#FCFCFD] p-4 transition hover:border-[#BFDBFE] hover:bg-[#EFF6FF]"
              >
                <div className="text-[14px] font-semibold text-[#111827]">{item.label}</div>
                <p className="mt-1 text-[12px] leading-[18px] text-[#6B7280]">{item.description}</p>
              </Link>
            ))}
          </div>
        </SectionPanel>

        <SectionPanel title="本周状态" subtitle="周报和人工确认状态来自任务与项目接口。">
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-3 rounded-[12px] bg-[#F9FAFB] px-4 py-3">
              <div>
                <div className="text-[13px] font-semibold text-[#111827]">项目状态</div>
                <div className="mt-0.5 text-[12px] text-[#6B7280]">{data.project?.projectId}</div>
              </div>
              <StatusPill status={data.project?.status} />
            </div>
            <div className="rounded-[12px] bg-[#F9FAFB] px-4 py-3">
              <div className="text-[13px] font-semibold text-[#111827]">招聘周报</div>
              <div className="mt-1 text-[12px] leading-[18px] text-[#6B7280]">
                {hasWeeklyReport(report) ? report.conclusion || "已有持久化周报" : "暂无持久化周报，可在招聘周报页生成。"}
              </div>
            </div>
            <div className="rounded-[12px] bg-[#F9FAFB] px-4 py-3">
              <div className="text-[13px] font-semibold text-[#111827]">待人工确认</div>
              <div className="mt-1 text-[20px] font-bold text-[#F59E0B]">{data.project?.awaitingHuman ?? 0}</div>
            </div>
          </div>
        </SectionPanel>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <SectionPanel title="岗位概览" subtitle="来自当前项目岗位接口。">
          {data.jobs.length ? (
            <div className="space-y-3">
              {data.jobs.map((job) => (
                <div key={job.jobProfileId} className="flex items-center justify-between gap-4 rounded-[12px] bg-[#F9FAFB] px-4 py-3">
                  <div className="min-w-0">
                    <div className="truncate text-[13px] font-semibold text-[#111827]">{job.roleName}</div>
                    <div className="mt-0.5 text-[12px] text-[#6B7280]">HC {job.headcount ?? "—"} · 候选人 {job.candidateCount ?? 0}</div>
                  </div>
                  <StatusPill status={job.pipelineStatus} />
                </div>
              ))}
            </div>
          ) : (
            <div className="text-[13px] text-[#6B7280]">暂无岗位。</div>
          )}
        </SectionPanel>

        <SectionPanel title="Top 候选人" subtitle="按当前匹配分排序。">
          <div className="space-y-3">
            {topCandidates(data.candidates, 5).map((candidate) => (
              <div key={candidate.candidateId} className="flex items-center justify-between gap-4 rounded-[12px] bg-[#F9FAFB] px-4 py-3">
                <div className="min-w-0">
                  <div className="truncate text-[13px] font-semibold text-[#111827]">{candidate.name}</div>
                  <div className="mt-0.5 truncate text-[12px] text-[#6B7280]">
                    {candidate.currentCompany ?? "—"} · {candidate.city ?? "—"}
                  </div>
                </div>
                <div className="text-[18px] font-bold text-[#2563EB]">{candidate.matchScore ?? "—"}</div>
              </div>
            ))}
          </div>
        </SectionPanel>
      </div>
    </div>
  );
}
