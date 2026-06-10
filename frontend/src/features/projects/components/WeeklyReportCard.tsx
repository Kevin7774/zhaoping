import type { WeeklyReport } from "../api";

type WeeklyReportCardProps = {
  report: WeeklyReport;
  onGenerate?: () => void;
  canGenerate?: boolean;
  disabledReason?: string;
  error?: string | null;
};

function hasReport(report: WeeklyReport) {
  return Boolean(
    report.conclusion ||
      report.keyProgress.length ||
      report.risks.length ||
      report.nextActions.length ||
      report.topCandidates.length,
  );
}

function ReportBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <section>
      <h3 className="text-[12px] font-semibold leading-[18px] text-[#111827]">{title}</h3>
      {items.length ? (
        <ul className="mt-2 space-y-1.5">
          {items.map((item) => (
            <li key={item} className="text-[13px] leading-5 text-[#374151]">
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-[13px] leading-5 text-[#9CA3AF]">暂无内容</p>
      )}
    </section>
  );
}

export function WeeklyReportCard({ report, onGenerate, canGenerate = true, disabledReason, error }: WeeklyReportCardProps) {
  const reportReady = hasReport(report);

  return (
    <aside className="rounded-[14px] border border-[#E5E7EB] bg-white p-[18px] shadow-[0_1px_2px_rgba(16,24,40,0.04),0_10px_28px_-18px_rgba(16,24,40,0.14)]">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-[16px] font-semibold leading-6 text-[#111827]">本周招聘周报</h2>
        <button
          type="button"
          onClick={onGenerate}
          disabled={!canGenerate}
          title={!canGenerate ? disabledReason : undefined}
          className="text-[13px] font-medium text-[#2563EB] disabled:cursor-not-allowed disabled:text-[#9CA3AF]"
        >
          生成周报
        </button>
      </div>

      {error ? (
        <div className="mt-4 rounded-[10px] border border-[#FECACA] bg-[#FEF2F2] px-4 py-3 text-[13px] leading-5 text-[#B91C1C]">
          {error}
        </div>
      ) : null}

      {reportReady ? (
        <div className="mt-4 space-y-4">
          {report.conclusion ? <p className="text-[13px] leading-5 text-[#374151]">{report.conclusion}</p> : null}
          <ReportBlock title="进展" items={report.keyProgress} />
          <ReportBlock title="风险" items={report.risks} />
          <ReportBlock title="下周计划" items={report.nextActions} />
        </div>
      ) : (
        <div className="mt-4 rounded-[10px] border border-dashed border-[#E5E7EB] bg-[#F9FAFB] px-4 py-6 text-center text-[13px] leading-5 text-[#6B7280]">
          暂无周报，运行招聘周报后生成
        </div>
      )}
    </aside>
  );
}
