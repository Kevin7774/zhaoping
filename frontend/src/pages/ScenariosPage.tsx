import { useState } from "react";

import { runCandidateEvaluation } from "../features/projects/api";
import {
  capabilityStatusLabel,
  DataError,
  DataLoading,
  isCapabilityConnected,
  MetricStrip,
  PageHeader,
  PrimaryButton,
  rememberTaskId,
  SectionPanel,
  StatusPill,
  topCandidates,
  useWorkspaceData,
} from "./projectWorkspace";

const scenarioDescriptions: Record<string, { title: string; description: string }> = {
  A: { title: "岗位分析", description: "分析岗位画像、能力约束和搜索策略。" },
  B: { title: "找候选人", description: "搜索候选人线索，生成可追踪的人才地图。" },
  C: { title: "候选人评估", description: "评估候选人证据链、匹配度、风险和推荐等级。" },
  D: { title: "招聘周报", description: "汇总项目进展、风险和下周行动建议。" },
};

export function ScenariosPage() {
  const data = useWorkspaceData({ includeIntegrations: true, includeScenarios: true });
  const [runningCandidateId, setRunningCandidateId] = useState<string | null>(null);
  const [createdTaskId, setCreatedTaskId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  if (data.loading) return <DataLoading />;
  if (data.error) return <DataError message={data.error} onRetry={data.reload} />;

  const llmCapability = data.integrations?.capabilities?.find(
    (capability) => capability.service_type === "llm" || capability.id === "llm_api",
  );
  const canRunEvaluation = llmCapability ? isCapabilityConnected(llmCapability) : false;
  const disabledReason = llmCapability ? `LLM ${capabilityStatusLabel(llmCapability.status)}` : "LLM 能力状态未知";
  const scenarios =
    data.scenarios?.scenarios && data.scenarios.scenarios.length
      ? data.scenarios.scenarios
      : Object.entries(scenarioDescriptions).map(([id, meta]) => ({ id, name_zh: meta.title, title: meta.title }));

  const runEvaluation = async (candidateId: string) => {
    const candidate = data.candidates.find((item) => item.candidateId === candidateId);
    if (!candidate) return;
    setRunningCandidateId(candidateId);
    setActionError(null);
    try {
      const created = await runCandidateEvaluation(data.projectId, candidate);
      rememberTaskId(created.task_id);
      setCreatedTaskId(created.task_id);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "候选人评估任务启动失败");
    } finally {
      setRunningCandidateId(null);
    }
  };

  return (
    <div className="pb-8">
      <PageHeader
        title="候选人评估"
        subtitle="查看后端可运行场景，并从当前候选人中启动 Agent 评估任务。评估任务会通过 task_id 进入任务记录。"
      />

      <MetricStrip
        items={[
          { label: "后端场景", value: scenarios.length, helper: "GET /scenarios/meta", tone: "text-[#2563EB]" },
          { label: "候选人", value: data.candidates.length, helper: "可评估对象" },
          {
            label: "LLM 能力",
            value: llmCapability ? capabilityStatusLabel(llmCapability.status) : "未知",
            helper: llmCapability?.id,
            tone: canRunEvaluation ? "text-[#16A34A]" : "text-[#F59E0B]",
          },
          { label: "最近任务", value: createdTaskId ? "已创建" : "—", helper: createdTaskId ?? "启动后显示 task_id" },
        ]}
      />

      {createdTaskId ? (
        <div className="mb-5 rounded-[12px] border border-[#BFDBFE] bg-[#EFF6FF] px-4 py-3 text-[13px] text-[#1E40AF]">
          已创建评估任务：{createdTaskId}。可在任务记录页继续查看。
        </div>
      ) : null}
      {actionError ? (
        <div className="mb-5 rounded-[12px] border border-[#FECACA] bg-[#FEF2F2] px-4 py-3 text-[13px] text-[#EF4444]">
          {actionError}
        </div>
      ) : null}

      <div className="grid gap-5 xl:grid-cols-[380px_minmax(0,1fr)]">
        <SectionPanel title="后端场景" subtitle={data.optionalErrors.scenarios ? `读取失败：${data.optionalErrors.scenarios}` : undefined}>
          <div className="space-y-3">
            {scenarios.map((scenario) => {
              const scenarioTitle = "title" in scenario ? scenario.title : undefined;
              const meta = scenarioDescriptions[scenario.id] ?? {
                title: scenario.name_zh || scenarioTitle || scenario.id,
                description: "后端返回的可运行场景。",
              };
              return (
                <div key={scenario.id} className="rounded-[12px] bg-[#F9FAFB] px-4 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-[13px] font-semibold text-[#111827]">{meta.title}</div>
                    <span className="rounded-full bg-white px-2 py-0.5 text-[12px] font-semibold text-[#2563EB]">{scenario.id}</span>
                  </div>
                  <p className="mt-1 text-[12px] leading-[18px] text-[#6B7280]">{meta.description}</p>
                </div>
              );
            })}
          </div>
        </SectionPanel>

        <SectionPanel title="候选人评估队列" subtitle="按匹配分排序展示，可直接启动评估任务。">
          <div className="overflow-x-auto">
            <table className="min-w-[780px] w-full text-left text-[13px] leading-5">
              <thead className="h-11 bg-[#F9FAFB] text-[12px] font-semibold text-[#6B7280]">
                <tr>
                  <th className="w-[170px] px-4">候选人</th>
                  <th className="w-[180px] px-3">公司</th>
                  <th className="w-[260px] px-3">岗位</th>
                  <th className="w-[90px] px-3">分数</th>
                  <th className="w-[110px] px-3">状态</th>
                  <th className="px-4 text-right">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#EEF2F7]">
                {topCandidates(data.candidates, 12).map((candidate) => (
                  <tr key={candidate.candidateId}>
                    <td className="px-4 py-4 font-semibold text-[#111827]">{candidate.name}</td>
                    <td className="px-3 py-4 text-[#374151]">{candidate.currentCompany ?? "—"}</td>
                    <td className="px-3 py-4 text-[#374151]">{candidate.title}</td>
                    <td className="px-3 py-4 text-[16px] font-bold text-[#2563EB]">{candidate.matchScore ?? "—"}</td>
                    <td className="px-3 py-4">
                      <StatusPill status={candidate.pipelineStatus || candidate.stepStatus} />
                    </td>
                    <td className="px-4 py-4 text-right">
                      <PrimaryButton
                        onClick={() => runEvaluation(candidate.candidateId)}
                        disabled={!canRunEvaluation || runningCandidateId === candidate.candidateId}
                        title={!canRunEvaluation ? disabledReason : undefined}
                      >
                        {runningCandidateId === candidate.candidateId ? "启动中" : "启动评估"}
                      </PrimaryButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionPanel>
      </div>
    </div>
  );
}
