"use client";

// 第二页/第四页的**动作层**（同时是这两个页面对外的门面）：
// 把界面上的操作翻译成登录会话里的命令或读取，别的活都交给拆出去的三块：
//   投影 → page2-projector.ts（纯函数，能被 Node 单测）
//   状态 → page2-runtime.ts（唯一持有快照与命令通道）
//   契约 → page2-types.ts（纯类型）
//
// 这一层只做两件事：读当前快照 → 拼参数 → 调命令；拿不到会话就如实说"请先登录"，
// 不退回演示数据（演示兜底在 `data/*` 里，只有真拿不到数据时才用）。
import { currentCommand, currentSnapshot, loadPage2 } from "./page2-runtime";
import { active, field } from "./page2-projector";
import { questionnairePaper } from '../../../core/dimensions.mjs';
import { entityTitle } from '../../../core/display-labels';
import type { Entity } from "../../live/types";
import type {
  LiveBadge, LiveFeedItem, LiveProfile, LiveRelationship, Questionnaire, TaskContract,
} from "./page2-types";

export const PAGE2_API = "/api/elfred";
// 这份轻量测试的题目、计分和能力估计都**在本仓库里**：
// 题目与打分是 `app/v28/core/dimensions.mjs`（服务端同一份），作答通过
// `questionnaire.submit` 落到当前会话的对象表（`dimension_baseline`）。
// 所以没有"服务没接通"这一档，界面上也就不需要那个开关（原 QUESTIONNAIRE_AVAILABLE 已删）。

/** 建一条任务草稿：来源只取本人已选的知识/文档/资源，别的参数由服务端补 */
export async function createPage2Task(input: { title: string; brief: string; agent: string; knowledgeIds?: string[] }) {
  const command = currentCommand(), snapshot = currentSnapshot();
  if (!command || !snapshot) throw new Error("请先登录再创建任务");
  const sources = ["knowledge", "document", "resource"].flatMap(type => snapshot.objects[type] ?? []);
  const source_refs = (input.knowledgeIds ?? []).map(id => sources.find(item => item.id === id))
    .filter((item): item is Entity => Boolean(item)).map(item => ({ id: item.id, version: item.version }));
  const system = input.agent === "advisor" ? "advise" : input.agent;
  return command("task.create", { goal: `${input.title}：${input.brief}`.slice(0, 8000), criteria: "根据所选知识或工具交付可核对的结果，由本人验收",
    system, mode: "compose", source_refs });
}

/**
 * 任务契约：把「这条 skill 的步骤与规矩」组装成一次做事的执行条件。
 * 拿不到就返回 null，调用方退回原来的行为，不假装拿到了。
 */
export async function fetchContract(skillName: string, goal = ""): Promise<TaskContract | null> {
  const tool = currentSnapshot()?.objects.skill?.find(item => item.id === skillName || item.data.title === skillName);
  if (!tool) return null;
  const instructions = field(tool, "instructions");
  return { ok: true, goal, system: field(tool, "system") || "execute", criteria: "按工具说明交付可核对的结果",
    constraints: instructions, memories: [], skill: { name: tool.id, title: entityTitle(tool), steps: [], rules: [instructions] },
    note: "来自本人已保存的工具版本" };
}

export async function fetchQuestionnaire(): Promise<Questionnaire | null> {
  // 题目以后端为准（GET /page2/questionnaire，同一份 core/dimensions.mjs）；
  // 取不到就退回本地那份同样的题，不把"网络抖一下"变成"这份测试做不了"。
  try {
    const response = await fetch(`${PAGE2_API}/page2/questionnaire`, { credentials: "same-origin" });
    if (response.ok) {
      const paper = (await response.json()) as Questionnaire;
      if (paper?.items?.length) return paper;
    }
  } catch {
    /* 下面退回本地同一份题库 */
  }
  const local = questionnairePaper() as Questionnaire;
  return local?.items?.length ? local : null;
}

/** 提交作答 → 服务端建/覆盖那份起点；返回后让第二页立刻按新数据重画。 */
export async function submitQuestionnaire(answers: { id: string; choice: number }[]): Promise<{
  ok: boolean;
  axes?: Record<string, number>;
  guard?: number;
  note?: string;
}> {
  const command = currentCommand();
  if (!command) return { ok: false, note: "请先登录再答这份测试" };
  try {
    const result = (await command("questionnaire.submit", { answers })) as { ok: boolean; axes?: Record<string, number>; guard?: number };
    if (result?.ok) await loadPage2(true);
    return result;
  } catch (error) {
    return { ok: false, note: error instanceof Error ? error.message : "提交没成功，稍后再试" };
  }
}

/** 从知识/文档固化出一张能力卡：先看有没有同名的，没有就落成工具并启用（工具库是唯一真源） */
/**
 * 第一张能力卡的初始化：把"选框 + 偏好"交给服务端生成卡片。
 * 服务端会一次性写齐说明书 / 输入 / 前置步骤，并配好任务草稿（见 `server/elfred/card-onboarding/`）。
 */
export type OnboardResult = {
  id: string;
  created: { preset_id: string; title: string; system: string; skill_id: string; task_id: string }[];
  skipped: { preset_id: string; title: string; reason: string }[];
  preferences: Record<string, string>;
  remembered: string[];
  notes: string[];
};

export async function onboardCards(input: {
  /** 分支选择树的路径（选项 id，按答题顺序）；和 preset_ids 二选一 */
  path?: string[];
  preset_ids?: string[];
  custom_text?: string;
  custom_system?: string;
  preferences?: Record<string, string>;
}): Promise<OnboardResult> {
  const command = currentCommand();
  if (!command) throw new Error("请先登录再做这张卡");
  const result = (await command("card.onboard", { ...input })) as OnboardResult;
  await loadPage2(true);
  return result;
}

export async function createCapability(input: {
  title: string;
  copyText?: string;
  type?: string;
  dimension?: string;
  owner?: string;
}) {
  const command = currentCommand();
  if (!command) return null;
  const existing = currentSnapshot()?.objects.skill?.find(item => item.data.title === input.title && item.data.status !== "archived");
  if (existing) return { id: existing.id, title: input.title };
  const system = ({ 探索: "explore", 参谋: "advise", 创作: "create", 连接: "connect", 执行: "execute" } as Record<string, string>)[input.owner ?? "探索"] || "explore";
  const saved = await command("tool.save", { title: input.title, instructions: input.copyText || input.title,
    kind: input.type || "Skill", system }) as { id: string; version: number };
  await command("tool.activate", { id: saved.id, version: saved.version });
  await loadPage2(true);
  return { id: saved.id, title: input.title };
}

export async function importFile(file: File) {
  const command = currentCommand();
  if (!command || !/\.(txt|md|csv|json)$/i.test(file.name)) return null;
  try {
    const content = await file.text();
    await command("document.create", { title: file.name, content });
    return { material: { title: file.name } };
  } catch { return null; }
}

/** 粘贴链接导入 */
export async function importLink(url: string) {
  const command = currentCommand();
  if (!command || !/^https?:\/\//i.test(url)) return null;
  try {
    const title = new URL(url).hostname;
    await command("resource.create", { title, content: url });
    return { title };
  } catch { return null; }
}

/** 个人页资料（读）：直接取当前快照里那份，没有就返回 null（页面走空态） */
export function fetchProfile() {
  const profile = currentSnapshot()?.objects.profile?.[0];
  if (!profile) return Promise.resolve(null);
  return Promise.resolve<LiveProfile>({ available: true, name: field(profile, "name"), bio: field(profile, "bio"),
    tags: Array.isArray(profile.data.tags) ? profile.data.tags as string[] : [], avatar: field(profile, "avatar"),
    background: field(profile, "cover"), headline: "", level: null, daysTracked: null, credibility: null,
    identityDescribe: "", filled: Boolean(field(profile, "name")), showLevel: profile.data.showLevel === true });
}

/** 个人页资料（写）：存完把后端回的那份直接给调用方用，避免前端自己拼 */
export async function saveProfile(patch: Partial<Pick<LiveProfile, "name" | "bio" | "tags" | "avatar" | "background" | "showLevel">>) {
  const profile = currentSnapshot()?.objects.profile?.[0];
  const command = currentCommand();
  if (!profile || !command) throw new Error("请先登录再编辑资料");
  await command("profile.save", { id: profile.id, version: profile.version, name: patch.name ?? field(profile, "name"),
    bio: patch.bio ?? field(profile, "bio"), tags: patch.tags ?? profile.data.tags ?? [],
    ...(patch.avatar !== undefined ? { avatar: patch.avatar } : {}),
    ...(patch.background !== undefined ? { cover: patch.background } : {}),
    ...(patch.showLevel !== undefined ? { showLevel: patch.showLevel } : {}) });
  return { ok: true, saved: Object.keys(patch), profile: await fetchProfile() };
}

export function fetchFeed() {
  const items: LiveFeedItem[] = (currentSnapshot()?.objects.feed ?? []).filter(active).map(item => ({
    kind: "evidence", id: item.id, title: field(item, "title"), detail: field(item, "summary"),
    at: item.created, verdict: "confirmed" }));
  return Promise.resolve({ items, count: items.length });
}

/**
 * 勋章：由服务端按"成果数 / 能力卡数与等级 / 已确认记忆 / 用了多久"实时算，随 bootstrap 下发
 * （server/elfred/profile-stats/badges.mjs）。第二页「理解度 → 荣誉勋章」和第四页「勋章」
 * 用的是同一份数据、同一个组件，所以不会出现两套名单。
 */
export function fetchBadges() {
  const snapshot = currentSnapshot();
  const data = (snapshot as { badges?: LiveBadge[] } | null)?.badges;
  return Promise.resolve({ badges: (data ?? []) as LiveBadge[], count: (data ?? []).filter((badge) => badge.earned).length, topLevel: 0, evidence: (snapshot?.objects.outcome ?? []).filter((item) => item.data.verdict === "accepted").length });
}

export function fetchRelationships() {
  const relationships: LiveRelationship[] = (currentSnapshot()?.objects.friend ?? []).filter(item => item.data.status === "accepted")
    .map(item => ({ id: item.id, name: field(item, "name") || field(item, "handle"), role: "好友", stage: "已连接",
      photo: "", chatId: field(item, "conversation_id") }));
  return Promise.resolve({ available: true, relationships, count: relationships.length });
}

/**
 * 让 Skill Foundry 生成并导入能力卡。
 * 前端只登记一次请求（命令 `skill.forge`）；真正调 Foundry 的 HTTP 在服务端运行时循环里跑
 * （和记忆同步一个路子），跑完会更新快照，能力卡组跟着刷新。
 *
 * ⚠️ 界面上暂时没有入口：能力卡组右上那颗魔棒按钮按反馈删掉了（用户不要它）。
 * 命令、运行时与投影里的 `forge` 状态都还在，哪天恢复入口只需要接上这个函数；
 * 在那之前它没有调用方，属于"留着的接口"，不是死代码。
 */
export async function forgeSkill(input: { feed?: boolean; limit?: number } = {}) {
  const command = currentCommand();
  if (!command) return { ok: false, reason: "请先登录" };
  const result = await command("skill.forge", { ...input });
  await loadPage2(true);
  return { ok: true, ...(result as Record<string, unknown>) };
}

// ── 转发：页面一直从 `api/page2-api` 取这些，入口保持不变 ──────────────────
export * from "./page2-types";
export { projectSnapshot } from "./page2-projector";
export {
  setPage2Runtime, setPage2User, getPage2User, getPage2State, loadPage2,
  registerProjector, usePage2Live, currentSnapshot, currentCommand,
} from "./page2-runtime";
