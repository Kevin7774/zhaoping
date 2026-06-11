// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { MainLayout } from "./MainLayout";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("MainLayout", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/health") return jsonResponse({ status: "ok" });
      if (url === "/api/projects") {
        return jsonResponse([
          {
            id: "goal_ai_native_fde_20260610_2049",
            name: "AI Native FDE / 全栈工程师",
            status: "active",
            createdAt: "2026-06-10T12:48:36Z",
            openJobs: 0,
            totalCandidates: 0,
            awaitingHuman: 0,
            averageMatchScore: 0,
          },
        ]);
      }
      return jsonResponse({ detail: `Unhandled ${url}` }, 404);
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("keeps the header focused by removing project switcher and global search controls", async () => {
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route element={<MainLayout />}>
            <Route path="/dashboard" element={<div>工作台内容</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("工作台内容")).toBeTruthy();
    expect(screen.queryByLabelText("切换项目")).toBeNull();
    expect(screen.queryByPlaceholderText("搜索候选人、岗位、项目")).toBeNull();
  });
});
