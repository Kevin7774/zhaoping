import { useEffect, useMemo, useState } from "react";

import { filterCandidates, defaultFilterCriteria, type FilterCriteria } from "../features/projects/state";
import { uploadProjectResume } from "../features/projects/api";
import {
  DataError,
  DataLoading,
  MetricStrip,
  PageHeader,
  SectionPanel,
  StatusPill,
  uniqueValues,
  useWorkspaceData,
  rememberTaskId,
} from "./projectWorkspace";

function updateCriteria<K extends keyof FilterCriteria>(
  criteria: FilterCriteria,
  key: K,
  value: FilterCriteria[K],
) {
  return { ...criteria, [key]: value };
}

export function CandidatesPage() {
  const data = useWorkspaceData();
  const [criteria, setCriteria] = useState<FilterCriteria>(defaultFilterCriteria);
  const [importJobId, setImportJobId] = useState("");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploadError, setUploadError] = useState("");

  const cities = useMemo(() => uniqueValues(data.candidates.map((candidate) => candidate.city)), [data.candidates]);
  const sources = useMemo(
    () => uniqueValues(data.candidates.map((candidate) => candidate.sourcePlatform)),
    [data.candidates],
  );
  const visibleCandidates = useMemo(() => filterCandidates(data.candidates, criteria), [data.candidates, criteria]);
  const emailReadyCount = visibleCandidates.filter((candidate) => candidate.email).length;
  const canUpload = Boolean(importJobId && resumeFile && !uploading);

  useEffect(() => {
    if (!importJobId && data.jobs[0]?.jobProfileId) {
      setImportJobId(data.jobs[0].jobProfileId);
    }
  }, [data.jobs, importJobId]);

  async function handleResumeUpload() {
    if (!resumeFile || !importJobId) {
      setUploadError("请选择岗位和简历文件。");
      return;
    }
    setUploading(true);
    setUploadError("");
    setUploadMessage("");
    try {
      const result = await uploadProjectResume(data.projectId, importJobId, resumeFile);
      rememberTaskId(result.taskId);
      setUploadMessage(`已创建导入任务：${result.taskId}`);
      setResumeFile(null);
      data.reload();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "上传失败");
    } finally {
      setUploading(false);
    }
  }

  if (data.loading) return <DataLoading />;
  if (data.error) return <DataError message={data.error} onRetry={data.reload} />;

  return (
    <div className="pb-8">
      <PageHeader
        title="人群筛选"
        subtitle="按岗位、城市、来源、匹配分和邮箱状态筛选当前项目候选人，筛选结果用于后续触达和评估。"
      />

      <MetricStrip
        items={[
          { label: "已加载候选人", value: data.candidates.length, helper: "GET /projects/{projectId}/candidates" },
          { label: "筛选命中", value: visibleCandidates.length, helper: "当前页面筛选结果", tone: "text-[#2563EB]" },
          { label: "有邮箱", value: emailReadyCount, helper: "可生成触达草稿", tone: "text-[#16A34A]" },
          { label: "后端总数", value: data.candidateTotal ?? "—", helper: data.hasMoreCandidates ? "列表还有更多候选人" : "已加载全部" },
        ]}
      />

      <SectionPanel title="导入简历" subtitle="上传到选定岗位后，后端会创建导入任务并刷新候选人列表。">
        <div className="grid gap-4 lg:grid-cols-[minmax(220px,0.7fr)_minmax(260px,1fr)_auto] lg:items-end">
          <label className="text-[12px] font-medium text-[#6B7280]">
            导入目标岗位
            <select
              value={importJobId}
              onChange={(event) => setImportJobId(event.currentTarget.value)}
              className="mt-1 h-10 w-full rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827]"
            >
              {data.jobs.length === 0 ? <option value="">暂无岗位</option> : null}
              {data.jobs.map((job) => (
                <option key={job.jobProfileId} value={job.jobProfileId}>
                  {job.roleName}
                </option>
              ))}
            </select>
          </label>

          <label className="text-[12px] font-medium text-[#6B7280]">
            简历文件
            <input
              type="file"
              accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.md,.txt"
              onChange={(event) => setResumeFile(event.currentTarget.files?.[0] ?? null)}
              className="mt-1 block h-10 w-full rounded-[10px] border border-[#D1D5DB] bg-white px-3 py-2 text-[13px] text-[#111827] file:mr-3 file:rounded-[8px] file:border-0 file:bg-[#EFF6FF] file:px-3 file:py-1 file:text-[12px] file:font-medium file:text-[#2563EB]"
            />
          </label>

          <button
            type="button"
            onClick={handleResumeUpload}
            disabled={!canUpload}
            className="h-10 rounded-[10px] bg-[#2563EB] px-4 text-[13px] font-medium text-white transition hover:bg-[#1D4ED8] disabled:cursor-not-allowed disabled:bg-[#BFDBFE]"
          >
            {uploading ? "上传中" : "上传简历"}
          </button>
        </div>
        {uploadMessage ? <div className="mt-3 text-[13px] text-[#16A34A]">{uploadMessage}</div> : null}
        {uploadError ? <div className="mt-3 text-[13px] text-[#EF4444]">{uploadError}</div> : null}
      </SectionPanel>

      <SectionPanel
        title="筛选条件"
        subtitle="字段来自真实候选人数据；清空后恢复默认全量人群。"
        action={
          <button
            type="button"
            onClick={() => setCriteria(defaultFilterCriteria)}
            className="h-9 rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] font-medium text-[#374151] transition hover:bg-[#F9FAFB]"
          >
            清空条件
          </button>
        }
      >
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <label className="text-[12px] font-medium text-[#6B7280]">
            岗位
            <select
              value={criteria.jobProfileId}
              onChange={(event) => setCriteria(updateCriteria(criteria, "jobProfileId", event.currentTarget.value))}
              className="mt-1 h-10 w-full rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827]"
            >
              <option value="all">全部岗位</option>
              {data.jobs.map((job) => (
                <option key={job.jobProfileId} value={job.jobProfileId}>
                  {job.roleName}
                </option>
              ))}
            </select>
          </label>

          <label className="text-[12px] font-medium text-[#6B7280]">
            城市
            <select
              value={criteria.city}
              onChange={(event) => setCriteria(updateCriteria(criteria, "city", event.currentTarget.value))}
              className="mt-1 h-10 w-full rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827]"
            >
              <option value="">全部城市</option>
              {cities.map((city) => (
                <option key={city} value={city}>
                  {city}
                </option>
              ))}
            </select>
          </label>

          <label className="text-[12px] font-medium text-[#6B7280]">
            来源
            <select
              value={criteria.sourcePlatform}
              onChange={(event) => setCriteria(updateCriteria(criteria, "sourcePlatform", event.currentTarget.value))}
              className="mt-1 h-10 w-full rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827]"
            >
              <option value="all">全部来源</option>
              {sources.map((source) => (
                <option key={source} value={source}>
                  {source}
                </option>
              ))}
            </select>
          </label>

          <label className="text-[12px] font-medium text-[#6B7280]">
            邮箱状态
            <select
              value={criteria.hasEmail}
              onChange={(event) => setCriteria(updateCriteria(criteria, "hasEmail", event.currentTarget.value as FilterCriteria["hasEmail"]))}
              className="mt-1 h-10 w-full rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827]"
            >
              <option value="all">全部</option>
              <option value="yes">有邮箱</option>
              <option value="no">无邮箱</option>
            </select>
          </label>

          <label className="text-[12px] font-medium text-[#6B7280]">
            最低匹配分
            <input
              type="number"
              min={0}
              max={100}
              value={criteria.minScore}
              onChange={(event) => setCriteria(updateCriteria(criteria, "minScore", Number(event.currentTarget.value) || 0))}
              className="mt-1 h-10 w-full rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827]"
            />
          </label>

          <label className="md:col-span-2 xl:col-span-3 text-[12px] font-medium text-[#6B7280]">
            关键词
            <input
              value={criteria.keyword}
              onChange={(event) => setCriteria(updateCriteria(criteria, "keyword", event.currentTarget.value))}
              placeholder="姓名、公司、岗位、城市"
              className="mt-1 h-10 w-full rounded-[10px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827] placeholder:text-[#9CA3AF]"
            />
          </label>
        </div>
      </SectionPanel>

      <div className="mt-5">
        <SectionPanel title="候选人结果" subtitle="筛选结果会保留候选人状态、岗位、分数和触达准备信息。">
          {visibleCandidates.length === 0 ? (
            <div className="text-[13px] text-[#6B7280]">没有命中候选人，请调整筛选条件。</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-[860px] w-full text-left text-[13px] leading-5">
                <thead className="h-11 bg-[#F9FAFB] text-[12px] font-semibold text-[#6B7280]">
                  <tr>
                    <th className="w-[180px] px-4">候选人</th>
                    <th className="w-[160px] px-3">公司 / 城市</th>
                    <th className="w-[240px] px-3">目标岗位</th>
                    <th className="w-[90px] px-3">匹配分</th>
                    <th className="w-[110px] px-3">状态</th>
                    <th className="px-4">触达</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#EEF2F7]">
                  {visibleCandidates.map((candidate) => (
                    <tr key={`${candidate.targetJobProfileId}-${candidate.candidateId}`}>
                      <td className="px-4 py-4">
                        <div className="font-semibold text-[#111827]">{candidate.name}</div>
                        <div className="mt-1 text-[12px] text-[#9CA3AF]">{candidate.candidateId}</div>
                      </td>
                      <td className="px-3 py-4 text-[#374151]">
                        <div>{candidate.currentCompany ?? "—"}</div>
                        <div className="mt-1 text-[12px] text-[#9CA3AF]">{candidate.city ?? "—"}</div>
                      </td>
                      <td className="px-3 py-4 text-[#374151]">{candidate.title}</td>
                      <td className="px-3 py-4 text-[16px] font-bold text-[#2563EB]">{candidate.matchScore ?? "—"}</td>
                      <td className="px-3 py-4">
                        <StatusPill status={candidate.pipelineStatus || candidate.stepStatus} />
                      </td>
                      <td className="px-4 py-4 text-[#374151]">
                        {candidate.email ? candidate.email : <span className="text-[#9CA3AF]">无邮箱</span>}
                      </td>
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
