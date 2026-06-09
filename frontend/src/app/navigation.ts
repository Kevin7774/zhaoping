export type NavigationItem = {
  label: string;
  path: string;
  section: string;
};

export const navigationItems: NavigationItem[] = [
  { label: "工作台", path: "/projects/project_2026_ai_team", section: "dashboard" },
  { label: "招聘项目", path: "/projects/project_2026_ai_team", section: "projects" },
  { label: "岗位分析", path: "/jobs", section: "jobs" },
  { label: "找候选人", path: "/talent-map", section: "talent-map" },
  { label: "候选人评估", path: "/scenarios", section: "evaluation" },
  { label: "人群筛选", path: "/candidates", section: "segments" },
  { label: "邮件触达", path: "/candidates", section: "outreach" },
  { label: "招聘周报", path: "/reports", section: "reports" },
  { label: "任务记录", path: "/tasks", section: "tasks" },
  { label: "系统设置", path: "/integrations", section: "settings" },
];
