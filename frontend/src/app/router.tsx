import { createBrowserRouter, Navigate } from "react-router-dom";

import { MainLayout } from "./MainLayout";
import { CandidatesPage } from "../pages/CandidatesPage";
import { DashboardPage } from "../pages/DashboardPage";
import { IntegrationsPage } from "../pages/IntegrationsPage";
import { JobsPage } from "../pages/JobsPage";
import { OutreachPage } from "../pages/OutreachPage";
import { ProjectDetailPage } from "../pages/ProjectDetailPage";
import { ReportsPage } from "../pages/ReportsPage";
import { ScenariosPage } from "../pages/ScenariosPage";
import { TalentMapPage } from "../pages/TalentMapPage";
import { TasksPage } from "../pages/TasksPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <MainLayout />,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: "dashboard", element: <DashboardPage /> },
      { path: "projects/:projectId", element: <ProjectDetailPage /> },
      { path: "projects/:projectId/jobs", element: <JobsPage /> },
      { path: "projects/:projectId/candidates", element: <CandidatesPage /> },
      { path: "projects/:projectId/talent-map", element: <TalentMapPage /> },
      { path: "projects/:projectId/scenarios", element: <ScenariosPage /> },
      { path: "projects/:projectId/outreach", element: <OutreachPage /> },
      { path: "projects/:projectId/reports", element: <ReportsPage /> },
      { path: "jobs", element: <JobsPage /> },
      { path: "candidates", element: <CandidatesPage /> },
      { path: "talent-map", element: <TalentMapPage /> },
      { path: "scenarios", element: <ScenariosPage /> },
      { path: "outreach", element: <OutreachPage /> },
      { path: "tasks", element: <TasksPage /> },
      { path: "reports", element: <ReportsPage /> },
      { path: "integrations", element: <IntegrationsPage /> },
    ],
  },
]);
