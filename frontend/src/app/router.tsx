import { createBrowserRouter, Navigate } from "react-router-dom";

import { MainLayout } from "./MainLayout";
import { CandidatesPage } from "../pages/CandidatesPage";
import { IntegrationsPage } from "../pages/IntegrationsPage";
import { JobsPage } from "../pages/JobsPage";
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
      { index: true, element: <Navigate to="/projects/project_2026_ai_team" replace /> },
      { path: "projects/:projectId", element: <ProjectDetailPage /> },
      { path: "jobs", element: <JobsPage /> },
      { path: "candidates", element: <CandidatesPage /> },
      { path: "talent-map", element: <TalentMapPage /> },
      { path: "scenarios", element: <ScenariosPage /> },
      { path: "tasks", element: <TasksPage /> },
      { path: "reports", element: <ReportsPage /> },
      { path: "integrations", element: <IntegrationsPage /> },
    ],
  },
]);
