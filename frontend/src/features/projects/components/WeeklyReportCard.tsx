import type { WeeklyReport } from "../api";

type WeeklyReportCardProps = {
  report: WeeklyReport;
};

function ReportList({ title, items }: { title: string; items: string[] }) {
  return (
    <section>
      <h3 className="text-xs font-semibold uppercase text-slate-400">{title}</h3>
      <ul className="mt-2 space-y-2">
        {items.map((item) => (
          <li key={item} className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700">
            {item}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function WeeklyReportCard({ report }: WeeklyReportCardProps) {
  return (
    <aside className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="border-b border-slate-100 pb-4">
        <div className="text-sm font-medium text-blue-700">招聘周报</div>
        <p className="mt-2 text-sm leading-6 text-slate-700">{report.conclusion}</p>
      </div>
      <div className="mt-4 space-y-5">
        <ReportList title="关键进展" items={report.keyProgress} />
        <ReportList title="Top 候选人" items={report.topCandidates} />
        <ReportList title="风险" items={report.risks} />
        <ReportList title="下周动作" items={report.nextActions} />
      </div>
    </aside>
  );
}
