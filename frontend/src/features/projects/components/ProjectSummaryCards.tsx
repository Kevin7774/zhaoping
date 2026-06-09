type ProjectSummaryCardsProps = {
  openJobs: number;
  totalCandidates: number;
  awaitingHuman: number;
  averageMatchScore: number;
};

const summaryCards = [
  { key: "openJobs", label: "开放岗位" },
  { key: "totalCandidates", label: "候选人" },
  { key: "awaitingHuman", label: "待人工复核" },
  { key: "averageMatchScore", label: "平均匹配分" },
] as const;

export function ProjectSummaryCards({
  openJobs,
  totalCandidates,
  awaitingHuman,
  averageMatchScore,
}: ProjectSummaryCardsProps) {
  const values = {
    openJobs,
    totalCandidates,
    awaitingHuman,
    averageMatchScore,
  };

  return (
    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="项目概览">
      {summaryCards.map((card) => (
        <article key={card.key} className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <div className="text-sm font-medium text-slate-500">{card.label}</div>
          <div className="mt-3 flex items-end justify-between gap-3">
            <strong className="text-3xl font-semibold tracking-normal text-slate-950">{values[card.key]}</strong>
            <span className="rounded-md bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700">Live Mock</span>
          </div>
        </article>
      ))}
    </section>
  );
}
