type ProjectSummaryCardsProps = {
  openJobs: number;
  totalCandidates: number;
  pendingEmailCount?: number | null;
  weeklyInterviewCount?: number | null;
};

const summaryCards = [
  {
    key: "openJobs",
    label: "招聘岗位",
    helper: "来自真实岗位接口",
    tone: "bg-[#EFF6FF] text-[#2563EB]",
    mark: "岗",
  },
  {
    key: "totalCandidates",
    label: "候选人",
    helper: "来自岗位候选人关联",
    tone: "bg-[#ECFDF3] text-[#16A34A]",
    mark: "人",
  },
  {
    key: "pendingEmailCount",
    label: "待发送邮件",
    helper: "后端暂未提供",
    tone: "bg-[#FFFBEB] text-[#F59E0B]",
    mark: "邮",
  },
  {
    key: "weeklyInterviewCount",
    label: "本周面试",
    helper: "后端暂未提供",
    tone: "bg-[#F3F4F6] text-[#6B7280]",
    mark: "面",
  },
] as const;

export function ProjectSummaryCards({
  openJobs,
  totalCandidates,
  pendingEmailCount,
  weeklyInterviewCount,
}: ProjectSummaryCardsProps) {
  const values = {
    openJobs,
    totalCandidates,
    pendingEmailCount: pendingEmailCount ?? "—",
    weeklyInterviewCount: weeklyInterviewCount ?? "—",
  };

  return (
    <section className="grid min-w-0 gap-4 md:grid-cols-2 xl:grid-cols-4" aria-label="项目概览">
      {summaryCards.map((card) => (
        <article
          key={card.key}
          className="flex h-[104px] min-w-0 items-start gap-4 rounded-[14px] border border-[#E5E7EB] bg-white p-[18px] shadow-[0_1px_2px_rgba(16,24,40,0.04),0_10px_28px_-18px_rgba(16,24,40,0.14)]"
        >
          <div className={`grid h-9 w-9 shrink-0 place-items-center rounded-[10px] text-[13px] font-semibold ${card.tone}`}>
            {card.mark}
          </div>
          <div className="min-w-0">
            <div className="text-[13px] leading-5 text-[#6B7280]">{card.label}</div>
            <strong className="mt-1 block text-[28px] font-bold leading-9 text-[#111827]">{values[card.key]}</strong>
            <div className="mt-0.5 text-[12px] leading-[18px] text-[#9CA3AF]">{card.helper}</div>
          </div>
        </article>
      ))}
    </section>
  );
}
