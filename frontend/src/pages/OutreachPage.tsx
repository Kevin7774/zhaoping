import { useState } from "react";

import { createOutreachDraft, type OutreachDraft } from "../features/projects/api";
import {
  DataError,
  DataLoading,
  formatDateTime,
  MetricStrip,
  PageHeader,
  PrimaryButton,
  SectionPanel,
  useActiveProjectId,
  useWorkspaceData,
} from "./projectWorkspace";

export function OutreachPage() {
  const projectId = useActiveProjectId();
  const data = useWorkspaceData({ projectId, includeOutreachHistory: true });
  const [busyCandidateId, setBusyCandidateId] = useState<string | null>(null);
  const [draft, setDraft] = useState<OutreachDraft | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  if (data.loading) return <DataLoading />;
  if (data.error) return <DataError message={data.error} onRetry={data.reload} />;

  const emailCandidates = data.candidates.filter((candidate) => candidate.email);
  const sentCount = data.outreachHistory.filter((item) => item.status === "sent" || item.status === "simulated").length;

  const generateDraft = async (candidateId: string) => {
    const candidate = data.candidates.find((item) => item.candidateId === candidateId);
    if (!candidate) return;
    setBusyCandidateId(candidateId);
    setActionError(null);
    try {
      const created = await createOutreachDraft({
        projectId: data.projectId,
        jobId: candidate.targetJobProfileId,
        candidateId: candidate.candidateId,
      });
      setDraft(created);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "邮件草稿生成失败");
    } finally {
      setBusyCandidateId(null);
    }
  };

  return (
    <div className="pb-8">
      <PageHeader
        title="邮件触达"
        subtitle="查看可触达候选人、生成后端邮件草稿，并读取项目触达历史。默认只生成草稿，不直接发送外部邮件。"
      />

      <MetricStrip
        items={[
          { label: "有邮箱候选人", value: emailCandidates.length, helper: "可生成草稿", tone: "text-[#16A34A]" },
          { label: "触达记录", value: data.outreachHistory.length, helper: "GET /outreach/history" },
          { label: "已记录发送", value: sentCount, helper: "sent / simulated" },
          { label: "当前草稿", value: draft ? "已生成" : "—", helper: draft?.draftId ?? "选择候选人生成" },
        ]}
      />

      {actionError ? (
        <div className="mb-5 rounded-[12px] border border-[#FECACA] bg-[#FEF2F2] px-4 py-3 text-[13px] text-[#EF4444]">
          {actionError}
        </div>
      ) : null}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <SectionPanel title="可触达候选人" subtitle="调用 POST /outreach/draft 生成后端草稿。">
          {emailCandidates.length === 0 ? (
            <div className="text-[13px] text-[#6B7280]">暂无带邮箱的候选人。</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-[760px] w-full text-left text-[13px] leading-5">
                <thead className="h-11 bg-[#F9FAFB] text-[12px] font-semibold text-[#6B7280]">
                  <tr>
                    <th className="w-[170px] px-4">候选人</th>
                    <th className="w-[180px] px-3">公司</th>
                    <th className="w-[240px] px-3">邮箱</th>
                    <th className="w-[90px] px-3">分数</th>
                    <th className="px-4 text-right">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#EEF2F7]">
                  {emailCandidates.map((candidate) => (
                    <tr key={candidate.candidateId}>
                      <td className="px-4 py-4">
                        <div className="font-semibold text-[#111827]">{candidate.name}</div>
                        <div className="mt-1 text-[12px] text-[#9CA3AF]">{candidate.title}</div>
                      </td>
                      <td className="px-3 py-4 text-[#374151]">{candidate.currentCompany ?? "—"}</td>
                      <td className="px-3 py-4 text-[#374151]">{candidate.email}</td>
                      <td className="px-3 py-4 text-[16px] font-bold text-[#2563EB]">{candidate.matchScore ?? "—"}</td>
                      <td className="px-4 py-4 text-right">
                        <PrimaryButton
                          onClick={() => generateDraft(candidate.candidateId)}
                          disabled={busyCandidateId === candidate.candidateId}
                        >
                          {busyCandidateId === candidate.candidateId ? "生成中" : "生成草稿"}
                        </PrimaryButton>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionPanel>

        <SectionPanel title="当前草稿" subtitle={draft?.backendGenerated ? "后端生成" : "选择候选人后显示"}>
          {draft ? (
            <div className="space-y-3">
              <div className="rounded-[12px] bg-[#F9FAFB] px-4 py-3">
                <div className="text-[12px] font-semibold text-[#6B7280]">主题</div>
                <div className="mt-1 text-[13px] font-semibold text-[#111827]">{draft.subject}</div>
              </div>
              <div className="max-h-[360px] overflow-auto whitespace-pre-wrap rounded-[12px] bg-[#F9FAFB] px-4 py-3 text-[13px] leading-5 text-[#374151]">
                {draft.body}
              </div>
              <div className="text-[12px] text-[#9CA3AF]">draft_id: {draft.draftId}</div>
            </div>
          ) : (
            <div className="rounded-[12px] border border-dashed border-[#D1D5DB] bg-[#F9FAFB] px-5 py-8 text-center text-[13px] text-[#6B7280]">
              还没有生成草稿。
            </div>
          )}
        </SectionPanel>
      </div>

      <div className="mt-5">
        <SectionPanel title="触达历史" subtitle={data.optionalErrors.outreachHistory ? `读取失败：${data.optionalErrors.outreachHistory}` : undefined}>
          {data.outreachHistory.length === 0 ? (
            <div className="text-[13px] text-[#6B7280]">暂无触达记录。</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-[820px] w-full text-left text-[13px] leading-5">
                <thead className="h-11 bg-[#F9FAFB] text-[12px] font-semibold text-[#6B7280]">
                  <tr>
                    <th className="w-[180px] px-4">时间</th>
                    <th className="w-[140px] px-3">状态</th>
                    <th className="w-[220px] px-3">收件人</th>
                    <th className="px-4">主题</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#EEF2F7]">
                  {data.outreachHistory.map((item) => (
                    <tr key={item.historyId}>
                      <td className="px-4 py-4 text-[#374151]">{formatDateTime(item.createdAt)}</td>
                      <td className="px-3 py-4 text-[#374151]">{item.status}</td>
                      <td className="px-3 py-4 text-[#374151]">{item.email ?? item.candidateId ?? "—"}</td>
                      <td className="px-4 py-4 text-[#374151]">{item.subject}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionPanel>
      </div>
    </div>
  );
}
