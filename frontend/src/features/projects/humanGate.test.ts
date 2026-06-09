import { describe, expect, it } from "vitest";

import { humanGateRequestFromEvent } from "./humanGate";
import type { TaskStreamEvent } from "../../shared/hooks/useTaskStream";

describe("human gate request helpers", () => {
  it("creates a modal request from the latest human_gate stream event", () => {
    const event: TaskStreamEvent = {
      id: 7,
      type: "human_gate",
      message: "流程暂停，等待人工确认：已生成触达邮件",
      data: {
        awaiting: {
          prompt: "已为您生成候选人 Alex 的触达邮件草稿",
          draft: {
            candidate_name: "Alex Chen",
            body: "Hi Alex, let's talk.",
          },
        },
      },
      status: "awaiting_human",
    };

    expect(humanGateRequestFromEvent(event, "task_1")).toEqual({
      eventKey: "7",
      taskId: "task_1",
      context: "已为您生成候选人 Alex 的触达邮件草稿",
      draft: "Hi Alex, let's talk.",
      candidateName: "Alex Chen",
    });
  });

  it("ignores non-human-gate events", () => {
    expect(humanGateRequestFromEvent({ id: 8, type: "summary", message: "done" }, "task_1")).toBeNull();
  });
});
