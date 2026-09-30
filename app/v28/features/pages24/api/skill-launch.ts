"use client";

import {displayTitle} from '../../../core/display-labels';
import { fetchContract } from "./page2-api";

type Entity = { id: string; data: Record<string, unknown> };
type LaunchRuntime = { snapshot: { objects: Record<string, Entity[]> } | null };

export type LaunchOutcome = {
  ok: boolean;
  reason?: string;
  system?: "explore" | "advisor" | "create" | "connect" | "execute";
  note?: string;
  /**
   * 跟着这一轮消息一起进对话的那份"附件"：这张能力卡的说明书。
   * 界面**不再**把它倒进输入框 —— 输入框留给用户自己写话，
   * 说明书在发送时按附件拼到消息正文里（发出去的内容和改动前一致）。
   */
  attach?: SkillAttach;
};

export type SkillAttach = {
  id: string;
  title: string;
  /** 跟着消息一起发出去的正文（这张卡的说明书） */
  text: string;
  /** 用户在输入框里一个字都没写时，替他说的一句（和改动前那条默认目标一致） */
  ask: string;
};

/**
 * 附件正文：这张卡的说明书 + 完成标准 + 相关记忆 + 那句"先核对再继续"。
 * **不含**"我想用…请先帮我明确目标"——那句只有在用户自己一个字都没写时才补上（见界面里的拼装）。
 */
export function contractBody(title: string, contract: { criteria: string; constraints: string; memories: string[] }): string {
  const lines = [`已保存工具「${title}」的说明：`];
  if (contract.constraints) lines.push(contract.constraints);
  if (contract.criteria) lines.push(`完成标准：${contract.criteria}`);
  if (contract.memories.length) lines.push(`已确认的相关记忆：${contract.memories.join("；")}`);
  lines.push("请先核对这些说明是否适用于本次目标，再和我继续讨论；不要自动执行或发布。");
  return lines.join("\n");
}

/**
 * 带着这张已保存的能力卡进它的 Agent 会话。
 * 返回的 `attach` 由界面挂在输入框上方，发送时拼进消息正文（说明书随消息一起发）。
 */
export async function launchWithSkill(runtime: unknown, title: string, goal = ""): Promise<LaunchOutcome> {
  const snapshot = (runtime as LaunchRuntime | undefined)?.snapshot;
  const tool = snapshot?.objects.skill?.find(item => item.id === title || item.data.title === title);
  if (!tool) return { ok: false, reason: "missing_tool", note: "这张能力尚未保存成可用工具，请先在「我的工具」中创建并启用。" };
  if (tool.data.status !== "active") return { ok: false, reason: "inactive_tool", note: "请先在「我的工具」中启用这项能力。" };
  const contract = await fetchContract(tool.id, goal);
  if (!contract) return { ok: false, reason: "missing_contract", note: "工具说明尚未就绪，请稍后重试。" };
  const system = String(tool.data.system);
  const agent = system === "advise" ? "advisor" : ["explore", "create", "connect", "execute"].includes(system) ? system as LaunchOutcome["system"] : "execute";
  const shown = displayTitle(tool.data.title, '工具');
  // goal 只有别的入口才会传（能力卡那个详情面板现在不问了），传了就先放在正文最前面
  const text = [goal.trim(), contractBody(shown, contract)].filter(Boolean).join("\n\n");
  return { ok: true, system: agent, attach: { id: tool.id, title: shown, text, ask: `我想用「${shown}」做一件事，请先帮我明确目标。` } };
}
