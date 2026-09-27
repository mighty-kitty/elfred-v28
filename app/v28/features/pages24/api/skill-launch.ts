"use client";

import {displayTitle} from '../../../core/display-labels';
import { fetchContract } from "./page2-api";

type Entity = { id: string; data: Record<string, unknown> };
type LaunchRuntime = { snapshot: { objects: Record<string, Entity[]> } | null };

export type LaunchOutcome = {
  ok: boolean;
  reason?: string;
  system?: "explore" | "advisor" | "create" | "connect" | "execute";
  prompt?: string;
  note?: string;
};

export function contractPrompt(title: string, goal: string, contract: { criteria: string; constraints: string; memories: string[] }): string {
  const lines = [goal.trim() || `我想用「${title}」做一件事，请先帮我明确目标。`, "", `已保存工具「${title}」的说明：`];
  if (contract.constraints) lines.push(contract.constraints);
  if (contract.criteria) lines.push(`完成标准：${contract.criteria}`);
  if (contract.memories.length) lines.push(`已确认的相关记忆：${contract.memories.join("；")}`);
  lines.push("请先核对这些说明是否适用于本次目标，再和我继续讨论；不要自动执行或发布。");
  return lines.join("\n");
}

/** Open the existing persistent Agent conversation with the real saved tool as an editable prefill. */
export async function launchWithSkill(runtime: unknown, title: string, goal = ""): Promise<LaunchOutcome> {
  const snapshot = (runtime as LaunchRuntime | undefined)?.snapshot;
  const tool = snapshot?.objects.skill?.find(item => item.id === title || item.data.title === title);
  if (!tool) return { ok: false, reason: "missing_tool", note: "这张能力尚未保存成可用工具，请先在「我的工具」中创建并启用。" };
  if (tool.data.status !== "active") return { ok: false, reason: "inactive_tool", note: "请先在「我的工具」中启用这项能力。" };
  const contract = await fetchContract(tool.id, goal);
  if (!contract) return { ok: false, reason: "missing_contract", note: "工具说明尚未就绪，请稍后重试。" };
  const system = String(tool.data.system);
  const agent = system === "advise" ? "advisor" : ["explore", "create", "connect", "execute"].includes(system) ? system as LaunchOutcome["system"] : "execute";
  return { ok: true, system: agent, prompt: contractPrompt(displayTitle(tool.data.title,'工具'), goal, contract) };
}
