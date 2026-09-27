"use client";
import {memoryOverview} from '../../../core/agent-alignment.mjs';
import {memoryAdmitted,memoryActive,memoryGroup,systemNames} from '../../../core/memory-policy.mjs';
import {entityTitle,markdownExcerpt} from '../../../core/display-labels';

// Second/fourth page projection of the authenticated V28 runtime.
// The independent page2 backend described in the source PR was not shipped.
// Unsupported analytic actions return an unavailable result; real objects and commands
// are read from the existing session and never replaced with sample user data.

import { useEffect, useSyncExternalStore } from "react";
import type { Entity, Snapshot } from "../../live/types";

export const PAGE2_API = "/api/elfred";
// PR #2 does not ship the questionnaire service or its scoring implementation.
export const QUESTIONNAIRE_AVAILABLE = false;

/**
 * 预留功能的开关（**默认关，界面不展示**）。
 *
 * 产品口径（2026-09-24 确认）：现阶段只做"让现有前端闭环"——把界面上已有的东西接上真实后端、
 * 把降级和失败说清楚；**不新增功能入口**。下面这两个动作想法是好的，代码先留着，等产品要了再打开：
 *   · 记忆体检（`memory-page.tsx` 里的「体检一遍 / 归档」）
 *   · 卡片上的「真跑一次」（`capability-sheet.tsx`）
 * 打开方式：把它改成 true（后端接口都在，随时可用）。
 */
export const SHOW_RESERVED_ACTIONS = false;

export type LiveStatus = "loading" | "ready" | "offline";

export type LiveCapability = {
  id: string;
  type: string;
  dimension: string;
  title: string;
  copy: string;
  owner: string;
  score: number | null;
  evidence: number;
  level: number;
  stage: string;
  gap?: { have: number; goal: number; need: number } | null;
  gapLabel: string;
  /** 整条等级阶梯（等级 / 档位名 / 门槛成果数）——由后端给，前端不再自己存门槛表 */
  ladder?: Array<{ level: number; stage: string; gate: number }>;
  verified: boolean;
};

export type LiveEvidence = {
  id: string;
  title: string;
  note: string;
  kind: string;
  verdict: string;
  day: string;
};

export type LiveEvidenceDetail = {
  id: string;
  title: string;
  note: string;
  kind: string;
  kindLabel: string;
  weightLabel: string;
  day: string;
  time: string;
  source: { label: string; note: string; ref: { kind: "task" | "chat"; id: string } };
  summary: string;
  agent: string;
  verified: boolean;
  verdict: string;
  impacts: {
    card: string;
    capabilityId: string;
    score: { from: number; to: number } | null;
    evidence: { from: number; to: number } | null;
    upgraded?: string | null;
  }[];
};

export type LiveInsight = {
  axes: {
    label: string;
    value: number | null;
    previous: number | null;
    /** 这一维的数字现在到哪一步了（后端算好，前端只说人话）：
     *  baseline = 只有测试给的起点 · growing = 起点 + 1~2 条成果 ·
     *  evidence = 够 3 条真实成果 · insufficient = 没测试也没攒够（不给数字） */
    lower?: number | null;
    source?: "evidence" | "growing" | "baseline" | "insufficient";
    samples?: number;
    missing?: number;
    uncertainty?: number;
  }[];
  composite: number | null;
  previousComposite: number | null;
  outcomeCount: number;
  externalChecks: number;
  verifiedDimensions?: number;
  minEvidence?: number;
  /** 做过那份轻量测试没有（有起点就有图可看） */
  started?: boolean;
  baseline?: { axes: Record<string, number>; guard: number; version: number; takenAt: string } | null;
  trend: { label: string; points: number[]; weeks: number; note: string } | null;
};

export type LiveAlignment = {
  alignment: number | null;
  level: number | null;
  stage: string;
  nextGate: number | null;
  confirmedMemories: number;
  credibility: number;
  externalChecks: number;
};

export type LiveMemory = {
  headline: string;
  totalCount: number;
  // 后端还在算这两个（四类记忆有着落几类）；界面这一版没展示，留着是因为接口里有，
  // 以后要画"基础/社交/习惯/偏好"四个标签时直接用。
  coveredGroups: number;
  groupCount: number;
  daysTracked: number;
  credibility: number;
  /** 四类记忆的实际条目（社交那一类装的是"人"，在 relationships 里） */
  groups: Record<
    string,
    { id: string; group: string; label: string; value: string; source: string; status: string }[]
  >;
  identity: { headline: string; describe: string; photoLabel: string; rule: string };
  relationships: { id: string; name: string; role: string; photo: string; chatId: string }[];
  relationshipStats: { longTerm: number; pending: number };
};

export type LiveDocument = { id: string; name: string; status: string; excerpt?: string };
export type LivePending = { id: string; kind: string; title: string; from: string; excerpt?: string };

/** Skill Foundry 的产物（`existing\skills\<name>\`）——能力卡组的真数据源 */
export type LiveSkill = {
  name: string;
  title: string;
  summary: string;
  /** SKILL.md 头部里的 owner_agent（哪个子 Agent 的 skill；目录里没有就是空串） */
  ownerAgent?: string;
  /** SKILL.md 头部里的 dimension（五个维度；目录里还没有这个字段时是空串，前端不许瞎猜） */
  dimension?: string;
  steps: string[];
  /** 「它能替你做」：后端用 LLM 从这条 skill 的材料里提炼的几条人话（没有就是空数组） */
  canDo?: string[];
  /** 这条 skill 真实的步骤数；`steps` 只留了读得懂的，数量可能更少，写"N 步"要用这个 */
  stepCount?: number;
  /** 这条 skill 要什么输入（后端从 workflow.json 的 parameters 取，退回 SKILL.md 的 Inputs 小节） */
  inputs?: string[];
  /** 这条 skill 的验收标准（SKILL.md 的 Verification 小节） */
  outputs?: string[];
  hasExamples: boolean;
  files: string[];
  updatedAt: string;
};

export type Page2Data = {
  capabilities: LiveCapability[] | null;
  todayEvidence: LiveEvidence[] | null;
  evidence: LiveEvidenceDetail[] | null;
  insight: LiveInsight | null;
  alignment: LiveAlignment | null;
  memory: LiveMemory | null;
  documents: LiveDocument[] | null;
  pending: LivePending[] | null;
  skills: LiveSkill[] | null;
};

type Store = { status: LiveStatus; data: Page2Data; reason: string };

const EMPTY_DATA: Page2Data = {
  capabilities: null,
  todayEvidence: null,
  evidence: null,
  insight: null,
  alignment: null,
  memory: null,
  documents: null,
  pending: null,
  skills: null,
};
const INITIAL: Store = { status: "loading", data: EMPTY_DATA, reason: "" };

let store: Store = INITIAL;
const listeners = new Set<() => void>();

// ── 当前用户 ────────────────────────────────────────────────────────────────
// 第二/四页的数据是**按用户分开存的**（`capabilities.user_id`、`memories.user_id`、
// `profile_settings.user_id`、skill 的 frontmatter `user_id`），所以每个请求都要说
// "我是谁"。这一层是普通模块，被知识页/个人页/记忆页共用，不能直接调 React hook ——
// 由 `core/page2-identity.tsx`（挂在 RuntimeProvider 里）把当前 handle 推下来。
// 空值 = 不带这个头，后端退回它自己的 `DEMO_USER_ID`（单用户本地跑时的旧行为）。
let activeUser = "";
let activeSnapshot: Snapshot | null = null;
let activeCommand: ((action: string, input: Record<string, unknown>) => Promise<unknown>) | null = null;

const field = (item: Entity | undefined, key: string) => String(item?.data[key] ?? "");
const list = (snapshot: Snapshot, type: string) => snapshot.objects[type] ?? [];
const active = (item: Entity) => !["archived", "deleted", "superseded", "rejected"].includes(field(item, "status"));
const agentName: Record<string, string> = { explore: "探索", advise: "参谋", create: "创作", connect: "连接", execute: "执行" };

function projectSnapshot(snapshot: Snapshot): Page2Data {
  const tools = list(snapshot, "skill").filter(active);
  const outcomes = list(snapshot, "outcome").filter(item => item.data.verdict === "accepted");
  const tasks = new Map(list(snapshot, "task").map(item => [item.id, item]));
  const knowledge = list(snapshot, "knowledge").filter(active);
  const memories = list(snapshot, "memory").filter(item => active(item) && !item.data.hidden && (!item.data.expires_at || Date.parse(field(item,"expires_at"))>Date.now()));
  const documents = [...list(snapshot, "document"), ...list(snapshot, "resource")].filter(active);
  const capabilities: LiveCapability[] = tools.map(tool => {
    const uses = list(snapshot, "tool_use").filter(item => item.data.tool_id === tool.id && item.data.kind === "use").length;
    const accepted = outcomes.filter(item => tasks.get(field(item, "task_id"))?.data.skill_id === tool.id).length;
    return { id: tool.id, type: field(tool, "kind") || "Skill", dimension: "未标注", title: entityTitle(tool),
      copy: markdownExcerpt(field(tool, "instructions"),160), owner: agentName[field(tool, "system")] || "执行",
      score: null, evidence: accepted, level: 1, stage: "待验证", gapLabel: "依据真实使用和验收结果成长", verified: accepted > 0,
      ladder: [{ level: 1, stage: "待验证", gate: 0 }] };
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
  const friends = list(snapshot, "friend").filter(item => item.data.status === "accepted");
  return { capabilities, todayEvidence: evidence.filter(item => item.day === "今天").map(item => ({ id: item.id, title: item.title, note: item.note,
      kind: item.kind, verdict: item.verdict, day: item.day })), evidence,
    insight: { axes: ["洞察", "判断", "表达", "链接", "交付"].map(label => ({ label, value: null, previous: null })), composite: null,
      previousComposite: null, outcomeCount: outcomes.length, externalChecks: 0, trend: null },
    alignment: { alignment: null, level: null, stage: memoryOverview(memories).label, nextGate: null, confirmedMemories: confirmed, credibility: 0, externalChecks: 0 },
    memory: { headline: "Elfred 对你的当前理解", totalCount: confirmed, coveredGroups: Object.values(groups).filter(rows=>rows.length).length,
      groupCount: 4, daysTracked: new Set(memories.filter(m=>memoryAdmitted(m)&&memoryActive(m)).map(m=>m.updated.slice(0,10))).size, credibility: 0, groups,
      identity: { headline: "当前身份", describe: groups["基础"].filter(row=>row.status==="已确认").slice(0,3).map(row=>row.value).join("；") || "还没有确认的身份信息", photoLabel: "", rule: "用于机会推荐，可随时纠正" },
      relationships: friends.map(item => ({ id: item.id, name: field(item, "name") || field(item, "handle"), role: "好友", photo: "", chatId: field(item, "conversation_id") })),
      relationshipStats: { longTerm: friends.length, pending: 0 } },
    documents: [...documents, ...knowledge].map(item => ({ id: item.id, name: entityTitle(item), status: field(item, "status"), excerpt: markdownExcerpt(field(item, "content")) })),
    pending: [], skills: tools.map(tool => ({ name: tool.id, title: entityTitle(tool), summary: markdownExcerpt(field(tool, "instructions"),160),
      ownerAgent: field(tool, "system"), dimension: "", steps: [field(tool, "instructions")].filter(Boolean),
      canDo: [field(tool, "instructions")].filter(Boolean), stepCount: field(tool, "instructions") ? 1 : 0,
      inputs: [], outputs: [], hasExamples: false,
      files: [], updatedAt: tool.updated })) };
}

/** The merged pages share the authenticated application snapshot; no second identity header is trusted. */
export function setPage2Runtime(snapshot: Snapshot | null, command: typeof activeCommand) {
  const nextUser = snapshot?.user.id ?? "";
  if (nextUser !== activeUser) {
    activeUser = nextUser;
    activeSnapshot = null;
    publish({ status: "loading", data: EMPTY_DATA, reason: "identity_changed" });
  }
  activeCommand = command;
  activeSnapshot = snapshot;
  if (snapshot) publish({ status: "ready", data: projectSnapshot(snapshot), reason: "shared_runtime" });
  else publish({ status: "loading", data: EMPTY_DATA, reason: "signed_out" });
}

export function getPage2User() {
  return activeUser;
}

export async function createPage2Task(input: { title: string; brief: string; agent: string; knowledgeIds?: string[] }) {
  if (!activeCommand || !activeSnapshot) throw new Error("请先登录再创建任务");
  const sources = ["knowledge", "document", "resource"].flatMap(type => activeSnapshot!.objects[type] ?? []);
  const source_refs = (input.knowledgeIds ?? []).map(id => sources.find(item => item.id === id))
    .filter((item): item is Entity => Boolean(item)).map(item => ({ id: item.id, version: item.version }));
  const system = input.agent === "advisor" ? "advise" : input.agent;
  return activeCommand("task.create", { goal: `${input.title}：${input.brief}`.slice(0, 8000), criteria: "根据所选知识或工具交付可核对的结果，由本人验收",
    system, mode: "compose", source_refs });
}

/**
 * 任务契约：把「这条 skill 的步骤与规矩 + 相关记忆」组装成一次做事的执行条件。
 *
 * 为什么要有它：skill 的"真"不在于它是一张卡，在于**它能约束 agent 的行为**。
 * 所以点「用它做一件事」时，skill 必须作为执行条件进场（步骤 / 你定过的规矩 / 验收点），
 * 而不是只跳过去聊天。拿不到就返回 null，调用方退回原来的行为，不假装拿到了。
 */
export type TaskContract = {
  ok: boolean;
  goal: string;
  system: string;
  criteria: string;
  constraints: string;
  memories: string[];
  skill: { name: string; title: string; steps: string[]; rules: string[] } | null;
  note: string;
};

export async function fetchContract(skillName: string, goal = ""): Promise<TaskContract | null> {
  const tool = activeSnapshot?.objects.skill?.find(item => item.id === skillName || item.data.title === skillName);
  if (!tool) return null;
  const instructions = field(tool, "instructions");
  return { ok: true, goal, system: field(tool, "system") || "execute", criteria: "按工具说明交付可核对的结果",
    constraints: instructions, memories: [], skill: { name: tool.id, title: entityTitle(tool), steps: [], rules: [instructions] },
    note: "来自本人已保存的工具版本" };
}

// ── 新用户那份「轻量测试」（问卷 → 五维起点）──────────────────────────
// 题目由**后端**给（改题不用发前端）；选项顺序就是分值顺序（低 → 高）。
// 题面里混了反向计分的题，但那是后端的事 —— 前端只按顺序画选项，不猜方向。
export type QuestionnaireItem = { id: string; text: string; options: string[] };
export type Questionnaire = {
  version: number;
  dimensions: string[];
  items: QuestionnaireItem[];
  note: string;
};

export async function fetchQuestionnaire(): Promise<Questionnaire | null> {
  return request<Questionnaire>("/page2/questionnaire", undefined, 15000);
}

/** 提交作答 → 后端建/覆盖那份起点，并把最新的洞察估计一起带回来。 */
export async function submitQuestionnaire(answers: { id: string; choice: number }[]) {
  const result = await post<{
    ok: boolean;
    reason?: string;
    note?: string;
    axes?: Record<string, number>;
    guard?: number;
  }>("/page2/questionnaire", { answers }, 30000);
  if (result?.ok) await loadPage2(true);      // 提交完让第二页立刻按新数据重画
  return result;
}

/**
 * 换人。**必须把上一个人的数据丢掉再重拉**：缓存里还留着 A 的卡，B 进来就会
 * 看到 A 的东西（串号）。这是本地跑两个账号测出来的。
 */
export function setPage2User(handle: string | null | undefined) {
  if (!handle) setPage2Runtime(null, null);
}
/** 各数据层登记的"把真数据就地换上去"的函数：先换数据，再让 React 重渲染 */
const projectors: {
  data?: (data: Page2Data) => void;
  cards?: (cards: LiveCapability[]) => void;
}[] = [];

export function subscribePage2(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function registerProjector(projector: { data?: (data: Page2Data) => void; cards?: (cards: LiveCapability[]) => void }) {
  projectors.push(projector);
  if (store.status !== "loading") projectors.forEach((p) => p.data?.(store.data));
}

function publish(next: Store) {
  store = next;
  // 只有真拿到数据（ready）才动各数据层；offline 时前端继续用演示数据，
  // 连"就地替换"都不做，免得把兜底那套算分逻辑关掉。
  if (next.status === "ready") {
    for (const projector of projectors) {
      try {
        projector.data?.(next.data);
      } catch (error) {
        console.warn("[page2] 数据层更新失败", error);
      }
    }
  }
  for (const listener of listeners) listener();
}

function publishCards(cards: LiveCapability[]) {
  for (const projector of projectors) {
    try {
      projector.cards?.(cards);
    } catch (error) {
      console.warn("[page2] 卡片更新失败", error);
    }
  }
  for (const listener of listeners) listener();
}

export function getPage2State() {
  return store;
}

/** 后端在跑吗？在跑的话数字以后端为准，前端那份兜底就不要掺和了 */
export function isLive() {
  return store.status === "ready";
}

/** 按标题从后端那份数据里找卡 id。
 *  不直接信弹层里的 card.id：那张卡对象在几层 map 里传过，id 容易在中间被丢掉；
 *  标题是唯一的，用它回查后端那份最稳。 */
export function liveCardId(title: string): string | null {
  const cards = store.data.capabilities;
  if (!cards) return null;
  return cards.find((card) => card.title === title)?.id ?? null;
}

// ⚠️ 超时不能写死：原来固定 6 秒，导致「真跑一次 skill」（要 40~60 秒）永远被当成失败，
// 页面还会误报"没跑通"；慢接口也会被当作"后端够不着"而退回演示数据。改成按调用给。
async function request<T>(path: string, init?: RequestInit, timeoutMs = 20000): Promise<T | null> {
  void path; void init; void timeoutMs;
  return null;
}

function post<T>(path: string, body: unknown, timeoutMs = 20000) {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) }, timeoutMs);
}

/**
 * 全部拉一遍。任何一个接口挂了都不影响别的，页面缺哪块就退回哪块的演示数据。
 *
 * `loadSeq`：换用户时会有两次拉取在飞（换人前那次 + 换人后那次）。只有**最新**那次
 * 允许把结果写进 store —— 否则换人前那次晚回来，会把上一个人的数据盖在页面上（串号）。
 */
export async function loadPage2(force = false): Promise<Store> {
  void force;
  if (activeSnapshot) publish({ status: "ready", data: projectSnapshot(activeSnapshot), reason: "shared_runtime" });
  return store;
}

/** 裁定一条成果：后端会重算卡片分数与成果数，回来的卡直接盖上去 */
export async function pushVerdict(evidenceId: string, verdict: "confirmed" | "disputed" | "forgotten") {
  if (!isLive()) return;   // 后端不在，就按前端那套算
  const result = await post<{ cards: LiveCapability[] }>(`/evidence/${evidenceId}/verdict`, { verdict });
  if (result?.cards) publishCards(result.cards);
  await loadPage2(true);
}

/** 选文件导入：原件进文档库，正文当场解析，先落「待确认」 */
/** 建一张能力卡（这一页的「添加能力」和创建工具页都走这里） */
export async function createCapability(input: {
  title: string;
  copyText?: string;
  type?: string;
  dimension?: string;
  owner?: string;
}) {
  if (!activeCommand) return null;
  const existing = activeSnapshot?.objects.skill?.find(item => item.data.title === input.title && item.data.status !== "archived");
  if (existing) return { id: existing.id, title: input.title };
  const system = ({ 探索: "explore", 参谋: "advise", 创作: "create", 连接: "connect", 执行: "execute" } as Record<string, string>)[input.owner ?? "探索"] || "explore";
  const saved = await activeCommand("tool.save", { title: input.title, instructions: input.copyText || input.title,
    kind: input.type || "Skill", system }) as { id: string; version: number };
  await activeCommand("tool.activate", { id: saved.id, version: saved.version });
  await loadPage2(true);
  return { id: saved.id, title: input.title };
}

export async function importFile(file: File) {
  if (!activeCommand || !/\.(txt|md|csv|json)$/i.test(file.name)) return null;
  try {
    const content = await file.text();
    await activeCommand("document.create", { title: file.name, content });
    return { material: { title: file.name } };
  } catch { return null; }
}

/** 粘贴链接导入 */
export async function importLink(url: string) {
  if (!activeCommand || !/^https?:\/\//i.test(url)) return null;
  try {
    const title = new URL(url).hostname;
    await activeCommand("resource.create", { title, content: url });
    return { title };
  } catch { return null; }
}

/** Agent 把一件事干完了 → 写一条成果（任务那条线接上之前的触发点，也是演示用） */
export async function runAgent(cardId: string, title?: string) {
  if (!isLive()) return null;
  const result = await post<{ evidenceId: string; card: LiveCapability }>("/agent/run", {
    card_id: cardId,
    title: title ?? "",
    outcome: 86 + Math.round(Math.random() * 8),   // 每次跑出来的表现略有差别，别每次都一样
    weight: 1.2,
  });
  if (result) await loadPage2(true);
  return result;
}

/** 待确认 → 确认上架 / 丢弃 */
export async function resolveMaterial(id: string, keep: boolean) {
  const result = await post(`/materials/${id}/${keep ? "confirm" : "discard"}`, {});
  if (result) await loadPage2(true);
  return result;
}

/** 页面根上用一次：自动拉数据，数据回来时整棵树跟着重渲染 */
export function usePage2Live() {
  const state = useSyncExternalStore(
    subscribePage2,
    getPage2State,
    () => INITIAL,
  );
  useEffect(() => {
    void loadPage2();
  }, []);
  return state;
}

// ─────────────────────────────────────────────────────────────────────────────
// 第四页（我的/个人页）与记忆库的动作。
// 之前这两块**前端一行后端都没接**（编辑资料、动态、勋章、记忆体检/合并/取代/归档/反思全是本地状态），
// 后端接口是我们这边补的（见 `docs/前端闭环审查-20260924.md`）。这里把它们接上：
// 拿不到就返回 null，页面照旧退回演示数据并显式降级——不许假装成功。
// ─────────────────────────────────────────────────────────────────────────────

export type LiveProfile = {
  available: boolean;
  name: string;
  bio: string;
  tags: string[];
  avatar: string;
  background: string;
  headline: string;
  level: number | null;
  daysTracked: number | null;
  credibility: number | null;
  identityDescribe: string;
  filled: boolean;
  /** 主页要不要显示等级与理解度（存在我们后端；没设过 = true） */
  showLevel?: boolean;
};

export type LiveFeedItem = {
  kind: "evidence" | "memory";
  id: string;
  title: string;
  detail: string;
  at: string;
  /** 同一天同一条被合并了几次（后端合并的；> 1 时界面写"共 N 次"） */
  count?: number;
  verdict: string;
};

export type LiveBadge = { id: string; title: string; earned: boolean; progress: string };

export type LiveRelationship = {
  id: string;
  name: string;
  role: string;
  stage: string;
  photo: string;
  chatId: string;
};

export type LiveHygieneItem = {
  id: string;
  text: string;
  category?: string;
  score?: number | null;
  tags?: string[];
  ageDays?: number | null;
};

export type LiveHygiene = {
  available: boolean;
  reason?: string;
  total: number;
  stale: LiveHygieneItem[];
  lowConfidence: LiveHygieneItem[];
  untagged: LiveHygieneItem[];
  conflicts: LiveHygieneItem[];
  note?: string;
};

/** 个人页资料（读） */
export function fetchProfile() {
  const profile = activeSnapshot?.objects.profile?.[0];
  if (!profile) return Promise.resolve(null);
  return Promise.resolve<LiveProfile>({ available: true, name: field(profile, "name"), bio: field(profile, "bio"),
    tags: Array.isArray(profile.data.tags) ? profile.data.tags as string[] : [], avatar: field(profile, "avatar"),
    background: field(profile, "cover"), headline: "", level: null, daysTracked: null, credibility: null,
    identityDescribe: "", filled: Boolean(field(profile, "name")), showLevel: profile.data.showLevel === true });
}

/** 个人页资料（写）：存完把后端回的那份直接给调用方用，避免前端自己拼 */
export async function saveProfile(patch: Partial<Pick<LiveProfile, "name" | "bio" | "tags" | "avatar" | "background" | "showLevel">>) {
  const profile = activeSnapshot?.objects.profile?.[0];
  if (!profile || !activeCommand) throw new Error("请先登录再编辑资料");
  await activeCommand("profile.save", { id: profile.id, version: profile.version, name: patch.name ?? field(profile, "name"),
    bio: patch.bio ?? field(profile, "bio"), tags: patch.tags ?? profile.data.tags ?? [],
    ...(patch.avatar !== undefined ? { avatar: patch.avatar } : {}),
    ...(patch.background !== undefined ? { cover: patch.background } : {}),
    ...(patch.showLevel !== undefined ? { showLevel: patch.showLevel } : {}) });
  return { ok: true, saved: Object.keys(patch), profile: await fetchProfile() };
}

export function fetchFeed() {
  const items: LiveFeedItem[] = (activeSnapshot?.objects.feed ?? []).filter(active).map(item => ({
    kind: "evidence", id: item.id, title: field(item, "title"), detail: field(item, "summary"),
    at: item.created, verdict: "confirmed" }));
  return Promise.resolve({ items, count: items.length });
}

export function fetchBadges() {
  const evidence = (activeSnapshot?.objects.outcome ?? []).filter(item => item.data.verdict === "accepted").length;
  return Promise.resolve({ badges: [] as LiveBadge[], count: 0, topLevel: 0, evidence });
}

export function fetchRelationships() {
  const relationships: LiveRelationship[] = (activeSnapshot?.objects.friend ?? []).filter(item => item.data.status === "accepted")
    .map(item => ({ id: item.id, name: field(item, "name") || field(item, "handle"), role: "好友", stage: "已连接",
      photo: "", chatId: field(item, "conversation_id") }));
  return Promise.resolve({ available: true, relationships, count: relationships.length });
}

/** 上游服务状态（我们后端 /health/deps）：设置页那一栏用它把"为什么记忆库是空的"说清楚 */
export type LiveDeps = {
  allGreen: boolean;
  memory?: {ok:boolean;count:number;reason:string};
  emos: { ok: boolean; reason: string; impact: string };
  skill_foundry: { ok: boolean; reason: string; impact: string };
  gateway: { ok: boolean; reason: string; impact: string };
  jev: { configured: boolean; baseUrl: string; model: string; hint: string };
};

export async function fetchHealthDeps():Promise<LiveDeps|null> {
  const user=activeSnapshot?.user.id;if(!user)return null;
  try{
    const response=await fetch('/api/elfred/health/deps',{credentials:'same-origin',cache:'no-store'});
    if(!response.ok)return null;
    const result=await response.json() as LiveDeps;
    return activeSnapshot?.user.id===user?result:null;
  }catch{return null;}
}

/** 记忆体检：长期未用 / 低置信 / 没标签 / 冲突（只读，不改任何东西） */
export function fetchHygiene() {
  return request<LiveHygiene>("/page2/memory/hygiene", undefined, 60000);
}

/** 合并两条记忆（转发 EMOS，动完能查历史、能回滚） */
export async function mergeMemories(sourceMemoryId: string, targetMemoryId: string, reason = "") {
  const result = await post<{ ok: boolean; reason?: string }>("/page2/memory/merge", {
    sourceMemoryId, targetMemoryId, reason,
  });
  if (result?.ok) await loadPage2(true);
  return result;
}

/** 新事实取代旧的 */
export async function supersedeMemory(sourceMemoryId: string, replacementMemoryId: string, reason = "") {
  const result = await post<{ ok: boolean; reason?: string }>("/page2/memory/supersede", {
    sourceMemoryId, replacementMemoryId, reason,
  });
  if (result?.ok) await loadPage2(true);
  return result;
}

/** 归档一条记忆（可 restore 回滚） */
export async function archiveMemory(memoryId: string, reason = "记忆体检归档") {
  const result = await post<{ ok: boolean; reason?: string }>(`/page2/memory/${memoryId}/archive`, { reason });
  if (result?.ok) await loadPage2(true);
  return result;
}

/** 召回 + Jev 重排：给一段意图，回一批按相关度排好的记忆 */
export function recallMemories(q: string, rerank = true) {
  return request<{
    available: boolean; reason?: string; reranked: boolean;
    memories: Array<Record<string, unknown>>; relevance?: Array<{ id: string; relevance: number | null }>;
  }>(`/page2/memory/recall?q=${encodeURIComponent(q)}&rerank=${rerank ? "true" : "false"}`);
}

/** 周期反思：让 EMOS 归纳一段时间，模型润色成候选——**只产候选，不落库** */
export function reflectMemories(kind: "day" | "week" = "week") {
  return post<{
    available: boolean; reason?: string; polished: boolean; model?: string;
    raw: string; summary: string; candidates: string[]; memoryCount?: number | null;
  }>("/page2/memory/reflect", { kind }, 120000);
}

/** 用户点头 → 反思结果才写进记忆 */
export function acceptReflection(text: string, confirmed = true) {
  return post<{ written: boolean; reason?: string }>("/page2/memory/reflect/accept", { text, confirmed });
}

/** 真跑一次 skill：真模型产出 → 自动落成果 → 卡片分数跟着变 */
export async function runSkill(name: string, inputText: string) {
  const result = await post<{ ran: boolean; reason?: string; runId?: string; evidenceId?: string; cardScore?: number }>(
    `/page2/skills/${encodeURIComponent(name)}/run`, { inputText }, 180000,
  );
  if (result?.ran) await loadPage2(true);
  return result;
}

/** 哪些 skill 该更新了（7 天 3 次 / 7 天未用）——只产候选 */
export function fetchSkillTriggers() {
  return request<{
    candidates: Array<{ skill: string; title: string; kind: string; idleDays?: number | null; rule: Record<string, unknown> }>;
    pending: Array<{ skill: string; title: string; kind: string }>;
  }>("/page2/skill-triggers");
}

/** 版本历史 / 回退 / refine（产出候选版本，要用户点头才落盘） */
export function fetchSkillVersions(name: string) {
  return request<{ skill: string; current: number | null; versions: Array<Record<string, unknown>> }>(
    `/page2/skills/${encodeURIComponent(name)}/versions`,
  );
}

export async function rollbackSkill(name: string, version: number) {
  const result = await post<{ ok: boolean; reason?: string }>(
    `/page2/skills/${encodeURIComponent(name)}/rollback`, { version },
  );
  if (result?.ok) await loadPage2(true);
  return result;
}

export async function refineSkill(name: string, trigger = "manual", confirmed = true) {
  const result = await post<{ ok: boolean; reason?: string; version?: number; files?: string[] }>(
    `/page2/skills/${encodeURIComponent(name)}/refine`, { trigger, confirmed }, 180000,
  );
  if (result?.ok) await loadPage2(true);
  return result;
}

/** 用户指正一步：写 skill + 写记忆（记忆走 M6 闸门） */
export async function pushFeedbackStep(input: {
  skill: string; title: string; summary: string; steps: string[];
  stepId: string; kind: string; note: string; runId: string;
}) {
  const result = await post<{ rules: unknown[]; memory: { written: boolean; reason?: string }; gate?: { mode: string } }>(
    "/page2/feedback/step", input,
  );
  if (result) await loadPage2(true);
  return result;
}
