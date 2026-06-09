export type NavigationItem = {
  label: string;
  path: string;
};

export const navigationItems: NavigationItem[] = [
  { label: "工作台", path: "/projects/project_2026_ai_team" },
  { label: "岗位", path: "/jobs" },
  { label: "候选人", path: "/candidates" },
  { label: "人才地图", path: "/talent-map" },
  { label: "场景任务", path: "/scenarios" },
  { label: "任务流", path: "/tasks" },
  { label: "周报", path: "/reports" },
  { label: "集成", path: "/integrations" },
];
