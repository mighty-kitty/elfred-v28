// 第二页/第四页的**投影**：把登录会话的快照折成这两页要的视图数据。
//
// 全是纯函数：进来一个 snapshot，出去一份 Page2Data —— 不碰 React、不碰网络、不自己存状态。
// 所以它能被 Node 直接 import 做单测（tests/elfred/pages24-projection.test.mjs）：
// 页面上每个数字（理解度、卡片分与等级、等级阶梯、资料列表）都从这里出来。
import { memoryOverview, understandingScore } from "../../../core/agent-alignment.mjs";
import { cardRating } from "../../../core/capability-score.mjs";
import { parseSkillMarkdown, skillCardCopy } from "../../../core/skill-markdown.mjs";
import { memoryAdmitted, memoryActive, memoryGroup, systemNames } from "../../../core/memory-policy.mjs";
import { SYSTEM_DIMENSION, dimensionInsight, observationsFromOutcomes } from "../../../core/dimensions.mjs";
// 带上 .ts 后缀：Node 的类型剥壳加载器要求显式后缀，这样这个文件才能被单测直接 import
import { entityTitle, markdownExcerpt } from "../../../core/display-labels.ts";
import type { Entity, Snapshot } from "../../live/types";
import type { LiveCapability, LiveEvidenceDetail, LiveForge, LiveMemory, Page2Data } from "./page2-types";

const field = (item: Entity | undefined, key: string) => String(item?.data[key] ?? "");
const list = (snapshot: Snapshot, type: string) => snapshot.objects[type] ?? [];
const active = (item: Entity) => !["archived", "deleted", "superseded", "rejected"].includes(field(item, "status"));
const agentName: Record<string, string> = { explore: "探索", advise: "参谋", create: "创作", connect: "连接", execute: "执行" };

function baselineOf(snapshot: Snapshot) {
  const row = list(snapshot, "dimension_baseline").filter(active)[0];
  if (!row) return null;
  return {
    axes: (row.data.axes as Record<string, number>) ?? {},
    guard: Number(row.data.guard || 0),
    version: Number(row.data.questionnaire_version || 1),
    takenAt: String(row.data.taken_at || row.created),
  };
}

/** 验收过的成果折成各维观测：维度优先看 skill 自己声明的，其次看这件活的主责 Agent。 */
function observationsOf(outcomes: Entity[], tasks: Map<string, Entity>, skills: Entity[]) {
  return observationsFromOutcomes(outcomes.map(outcome => {
    const task = tasks.get(field(outcome, "task_id"));
    return {
      dimension: field(skills.find(item => item.id === field(task, "skill_id")), "dimension"),
      system: field(task, "system"),
      satisfaction: field(task, "satisfaction"),
      at: outcome.created,
    };
  }));
}

/** 最近一次 Skill Foundry 生成请求的状态（没有就是 null） */
function forgeOf(snapshot: Snapshot): LiveForge | null {
  const rows = list(snapshot, "forge_request").sort((a, b) => String(b.created).localeCompare(String(a.created)));
  const last = rows[0];
  if (!last) return null;
  const result = (last.data.result ?? {}) as { reason?: string; imported?: { id: string; title: string }[] };
  return { status: String(last.data.status ?? "pending"), reason: result.reason, imported: result.imported };
}

function projectSnapshot(snapshot: Snapshot): Page2Data {
  const tools = list(snapshot, "skill").filter(active);
  const outcomes = list(snapshot, "outcome").filter(item => item.data.verdict === "accepted");
  const tasks = new Map(list(snapshot, "task").map(item => [item.id, item]));
  const knowledge = list(snapshot, "knowledge").filter(active);
  const memories = list(snapshot, "memory").filter(item => active(item) && !item.data.hidden && (!item.data.expires_at || Date.parse(field(item,"expires_at"))>Date.now()));
  const documents = [...list(snapshot, "document"), ...list(snapshot, "resource")].filter(active);
  // 一条已验收成果折成"这次的证据"：满意度来自它那次任务，外部可核对 = 这次来源里有可核对的资料。
  // 分数只能由这些事实推，使用次数（tool_use）不参与 —— 这是产品定过的口径。
  const evidenceRows = (skillId: string) => outcomes
    .filter(item => tasks.get(field(item, "task_id"))?.data.skill_id === skillId)
    .map(item => {
      const task = tasks.get(field(item, "task_id"));
      return { satisfaction: field(task, "satisfaction") || "unknown", external: ((task?.data.source_refs as unknown[] | undefined)?.length ?? 0) > 0, at: item.created };
    });
  const capabilities: LiveCapability[] = tools.map(tool => {
    const rating = cardRating(evidenceRows(tool.id));
    const markdown = field(tool, "instructions");
    return { id: tool.id, type: field(tool, "kind") || "Skill",
      // 卡自己的维度：说明书里写了就用它；没写就跟着这张卡的归属系统走（和成果进哪一维同一套口径），
      // 这样界面上不会再出现"未标注"这种谁也不知道该怎么理解的词。
      dimension: field(tool, "dimension") || (SYSTEM_DIMENSION as Record<string, string>)[field(tool, "system")] || "未标注",
      title: entityTitle(tool),
      // 卡面小字：从说明书里提炼的一句话，不是把 markdown 压成一行
      copy: skillCardCopy(markdown) || "本人保存的能力，说明书还没写",
      owner: agentName[field(tool, "system")] || "执行",
      score: rating.score, evidence: rating.evidence, level: rating.level, stage: rating.stage,
      gapLabel: rating.gapLabel, gap: rating.gap, verified: rating.verified, ladder: rating.ladder };
  });
  const evidence: LiveEvidenceDetail[] = outcomes.map(item => {
    const task = tasks.get(field(item, "task_id"));
    const artifact = knowledge.find(entry => entry.data.outcome_id === item.id);
    const title = entityTitle(task,"已验收成果");
    return { id: item.id, title, note: markdownExcerpt(field(artifact, "content"),240), kind: "outcome", kindLabel: "已验收成果",
      weightLabel: "本人验收", day: new Date(item.created).toDateString() === new Date().toDateString() ? "今天" : new Date(item.created).toLocaleDateString("zh-CN"),
      time: new Date(item.created).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }),
      source: { label: "真实任务", note: title, ref: { kind: "task", id: task?.id || "" } },
      summary: field(artifact, "content") || title, agent: agentName[field(task, "system")] || "执行", verified: true,
      verdict: "confirmed", impacts: [] };
  });
  const groups: LiveMemory["groups"] = { 基础: [], 社交: [], 习惯: [], 偏好: [] };
  for (const item of memories) {
    const group = (item.data.group || memoryGroup(field(item,"content"))) as keyof LiveMemory["groups"];
    groups[group].push({ id: item.id, group, label: systemNames[field(item,"scope")] || "个人理解", value: field(item, "content"),
      source: (item.data.source_refs as unknown[] | undefined)?.length ? "有来源" : "本人记录", status: field(item,"status")==="learned"?"自动记录":field(item, "status") === "validated" ? "已确认" : field(item,"status")==="needs_review"?"需重评":field(item,"status")==="deferred"?"已搁置":"待确认" });
  }
  const confirmed = memories.filter(item => memoryAdmitted(item)).length;
  // 记忆可信度 = **已确认的记忆里，档位已经走到"场景已验证 / 跨时间稳定"的占比**。
  // 这个档位是服务端自己维护在记忆对象上的（server/elfred/memory-validity.mjs 按证据改写
  // `alignment`），这里只是数一遍，不另起一套算法。
  // 没有一条已确认的记忆时是 null —— 界面写"—"，因为"没有基数"不等于"可信度 0%"。
  const admittedMemories = memories.filter(item => memoryAdmitted(item));
  const verifiedMemories = admittedMemories.filter(item => ["scenario_verified", "stable_over_time"].includes(field(item, "alignment"))).length;
  const credibility = admittedMemories.length ? Math.round((verifiedMemories / admittedMemories.length) * 100) : null;
  // 外部验证 = 成果挂到了可核对的来源上（任务带导入的材料或链接），不是"做过就算"
  const externalChecks = outcomes.filter(item => ((tasks.get(field(item, "task_id"))?.data.source_refs as unknown[] | undefined)?.length ?? 0) > 0).length;
  const friends = list(snapshot, "friend").filter(item => item.data.status === "accepted");
  // 理解度：由真实事实推（成果 + 记忆 + 有没有被指正），可升可降，没有终点。
  // 公式与门槛见 `core/agent-alignment.mjs` 的 understandingScore（旧后端实测口径：新用户 10%、三件外部核对 45%）。
  const alignmentScore = understandingScore({
    memories,
    outcomes: outcomes.map(item => {
      const task = tasks.get(field(item, "task_id"));
      return { satisfaction: field(task, "satisfaction") || "unknown", external: ((task?.data.source_refs as unknown[] | undefined)?.length ?? 0) > 0, at: item.created };
    }),
    // 被本人打回、还没重新验收的任务不产成果对象，单独把条数交进去
    extraCorrections: list(snapshot, "task").filter(item => item.data.satisfaction === "unsatisfied").length,
    hasFriends: friends.length > 0,
    hasBaseline: Boolean(baselineOf(snapshot)),
    trackedSince: list(snapshot, "profile")[0]?.created || 0,
  });
  return { capabilities, todayEvidence: evidence.filter(item => item.day === "今天").map(item => ({ id: item.id, title: item.title, note: item.note,
      kind: item.kind, verdict: item.verdict, day: item.day })), evidence,
    insight: dimensionInsight({ baseline: baselineOf(snapshot), observations: observationsOf(outcomes, tasks, tools),
      outcomeCount: outcomes.length, externalChecks }),
    alignment: {
      alignment: alignmentScore.alignment, level: alignmentScore.level, stage: alignmentScore.stage,
      nextGate: alignmentScore.nextGate, nextEvidence: alignmentScore.nextEvidence,
      confirmedMemories: confirmed, externalChecks: alignmentScore.externalChecks,
      corrections: alignmentScore.corrections, idleDays: alignmentScore.idleDays,
      uncertainty: alignmentScore.uncertainty, parts: alignmentScore.parts,
    },
    memory: { headline: "Elfred 对你的当前理解", totalCount: confirmed, coveredGroups: Object.values(groups).filter(rows=>rows.length).length,
      groupCount: 4, daysTracked: new Set(memories.filter(m=>memoryAdmitted(m)&&memoryActive(m)).map(m=>m.updated.slice(0,10))).size, credibility, groups,
      identity: { headline: "当前身份", describe: groups["基础"].filter(row=>row.status==="已确认").slice(0,3).map(row=>row.value).join("；") || "还没有确认的身份信息", photoLabel: "", rule: "用于机会推荐，可随时纠正" },
      relationships: friends.map(item => ({ id: item.id, name: field(item, "name") || field(item, "handle"), role: "好友", photo: "", chatId: field(item, "conversation_id") })),
      relationshipStats: { longTerm: friends.length, pending: 0 } },
    // 资料 = 导进来的文档与本人记的知识；**任务验收产物不在这里**（它是成果，页面上已经有一栏，
    // 两处都列同一件东西会让人以为做了两遍）。
    documents: [...documents, ...knowledge.filter(item => !item.data.outcome_id)].map(item => ({ id: item.id, name: entityTitle(item), status: field(item, "status"), excerpt: markdownExcerpt(field(item, "content")) })),
    pending: [], forge: forgeOf(snapshot),
    // 说明书按 SKILL.md 的真相拆开：能做到什么 / 步骤 / 输入 / 输出 / 验收标准，另带原文供"完整说明"渲染。
    skills: tools.map(tool => {
      const markdown = field(tool, "instructions");
      const parsed = parseSkillMarkdown(markdown);
      return { name: tool.id, title: entityTitle(tool),
        summary: parsed.summary || parsed.description || "",
        ownerAgent: field(tool, "system"),
        dimension: field(tool, "dimension") || (SYSTEM_DIMENSION as Record<string, string>)[field(tool, "system")] || "",
        instructions: markdown,
        steps: parsed.steps, canDo: parsed.canDo, stepCount: parsed.steps.length,
        inputs: parsed.inputs, outputs: parsed.outputs, checks: parsed.checks, limits: parsed.limits,
        hasExamples: parsed.sections.some(section => /示例|例子|example/i.test(section.title)),
        files: [], updatedAt: tool.updated };
    }) };
}

export { projectSnapshot, field, list, active, agentName };
