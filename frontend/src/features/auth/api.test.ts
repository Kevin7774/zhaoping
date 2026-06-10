// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getProject } from "../projects/api";
import { getStoredAuthUser, loginWithCompanyEmail, signOut } from "./api";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("auth api", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    window.localStorage.clear();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    signOut();
    vi.unstubAllGlobals();
  });

  it("logs in with company email, stores the user, and injects bearer auth into later API calls", async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          accessToken: "token_123",
          tokenType: "bearer",
          user: {
            userId: "user_1",
            orgId: "org_hanno_ai",
            email: "recruiter@hanno.ai",
            name: "Recruiter",
          },
          org: {
            orgId: "org_hanno_ai",
            name: "hanno.ai",
            domain: "hanno.ai",
          },
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          id: "project_hanno_ai_hardware",
          name: "汉诺云智招聘",
          status: "active",
          createdAt: "2026-06-10T00:00:00Z",
        }),
      );

    await loginWithCompanyEmail("Recruiter@Hanno.AI");
    await getProject("project_hanno_ai_hardware");

    expect(getStoredAuthUser()).toMatchObject({ email: "recruiter@hanno.ai", orgId: "org_hanno_ai" });
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/projects/project_hanno_ai_hardware",
      expect.objectContaining({
        headers: expect.any(Headers),
        method: "GET",
      }),
    );
    const headers = fetchMock.mock.calls[1][1].headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer token_123");
  });
});
