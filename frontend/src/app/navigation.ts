export type NavigationItem = {
  label: string;
  path: string;
  section: string;
};

export function projectPath(projectId: string, leaf = "") {
  const encoded = encodeURIComponent(projectId);
  return leaf ? `/projects/${encoded}/${leaf}` : `/projects/${encoded}`;
}

export function navigationItemsForProject(projectId: string): NavigationItem[] {
  return [
    { label: "工作台", path: "/dashboard", section: "dashboard" },
    { label: "招聘项目", path: projectPath(projectId), section: "projects" },
    { label: "岗位分析", path: projectPath(projectId, "jobs"), section: "jobs" },
    { label: "找候选人", path: projectPath(projectId, "talent-map"), section: "talent-map" },
    { label: "候选人评估", path: projectPath(projectId, "scenarios"), section: "evaluation" },
    { label: "人群筛选", path: projectPath(projectId, "candidates"), section: "segments" },
    { label: "邮件触达", path: projectPath(projectId, "outreach"), section: "outreach" },
    { label: "招聘周报", path: projectPath(projectId, "reports"), section: "reports" },
    { label: "任务记录", path: "/tasks", section: "tasks" },
    { label: "系统设置", path: "/integrations", section: "settings" },
  ];
}

export const navigationItems: NavigationItem[] = navigationItemsForProject("project_2026_ai_team");
