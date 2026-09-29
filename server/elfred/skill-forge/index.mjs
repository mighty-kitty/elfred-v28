/**
 * 能力生成模块：让 Skill Foundry 真的产出我们的能力卡。
 *
 * 为什么单开一个模块（而不是塞进工具库）：它跨进程、有自己的两份合同 ——
 *   ① 喂事件：把这两页的真实上下文按 ContextEvent 发给 Foundry（它落成自己的任务，
 *      再按相似度分组，够 2 条才起草）；
 *   ② 取成品：把 Foundry 里"还没导过"的 skill 草稿拉回来，落成我们的 `skill` 对象
 *      （走工具库的 tool.save/activate，保持对象形状与版本一致），并标 `source:'foundry'`。
 * 任何一步不通都返回明确的 `{ok:false, reason}`，不假装生成成功。
 *
 * Foundry 侧用到的接口（`services/skill-foundry`）：
 *   POST /v1/elfred/events/batch          喂 ContextEvent
 *   POST /v1/elfred/skills/passive/scan   让它按相似度分组并起草
 *   GET  /v1/elfred/skills                列技能（含草稿）
 *   GET  /v1/elfred/skills/{skill_id}     读详情（current_version.skill_markdown 就是 SKILL.md）
 */
import { toolLibraryCommand } from '../tool-library.mjs';
import { now } from '../store.mjs';
import { safeBase, callJson, joinUrl } from '../upstream.mjs';

const RUN_TYPE = 'forge_run';
const MAX_EVENTS = 8;

const activeOutcomes = (store, user, limit) => store.list('outcome')
  .filter((item) => item.owner === user && item.data.verdict === 'accepted')
  .sort((a, b) => String(b.created).localeCompare(String(a.created)))
  .slice(0, limit);

/** 把"本人已验收的成果"翻译成 Foundry 认的 ContextEvent（一份成果一条）。 */
function eventsFromOutcomes(store, outcomes) {
  return outcomes.map((outcome) => {
    const task = store.get(outcome.data.task_id);
    const artifact = store.list('knowledge').find((item) => item.data.outcome_id === outcome.id);
    const goal = String(task?.data.goal || task?.data.title || '已完成的一件事');
    const detail = String(artifact?.data.content || '').slice(0, 600);
    const stamp = String(outcome.created || now());
    return {
      event_id: `pages24-${outcome.id}`,
      created_at: stamp,
      source: 'elfred_pages24',
      app: { name: 'Elfred', process_name: 'Elfred', window_title: goal.slice(0, 120), category: 'accepted_outcome' },
      trigger: { type: 'accepted_outcome', level: 3, score: 8, reasons: ['owner_accepted'] },
      content: { content_type: 'important', raw_text: `${goal}\n${detail}`.trim(), clean_text: `${goal}\n${detail}`.trim(), summary: goal.slice(0, 200), entities: [], tasks: [{ task: goal.slice(0, 500), deadline: '', assignee: 'unknown', project: '', confidence: 0.9 }] },
      privacy: { is_sensitive: false, sensitivity_types: [], action: 'allow', allowed_to_upload: false, allowed_to_write_long_term_memory: false, requires_user_confirmation: false },
      artifacts: {},
      suggestions: { memory_write_suggestions: [], task_card_suggestions: [] },
      status: 'temporary_context',
    };
  });
}

/** 已经导入过的 Foundry skill（存在我们 skill 对象的 data.foundry.skill_id 上）。 */
function importedFoundryIds(store, user) {
  return new Set(store.list('skill')
    .filter((item) => item.owner === user)
    .map((item) => item.data?.foundry?.skill_id)
    .filter(Boolean));
}

/** 能力服务的调用（地址白名单与超时都在 upstream.mjs 里，见那里的注释） */
const call = (fetcher, url, init) => callJson(fetcher, url, { ...init, timeout: 20000 });

/**
 * 跑一轮"生成 + 导入"。
 * input: { feed?: boolean（要不要先喂事件，默认 true）, limit?: number（这一轮最多导几张，默认 3） }
 */
export async function forgeSkills(store, user, input = {}, { config = process.env, fetcher = fetch } = {}) {
  const base = safeBase(config.ELFRED_SKILL_FOUNDRY_URL);
  if (!base) return { ok: false, reason: '未配置 Skill Foundry 地址（ELFRED_SKILL_FOUNDRY_URL）' };
  const root = joinUrl(base, '/v1/elfred');
  const limit = Math.max(1, Math.min(Number(input.limit) || 3, 10));
  const notes = [];

  // ① 喂事件：把本人已验收的成果交给 Foundry
  if (input.feed !== false) {
    const outcomes = activeOutcomes(store, user, MAX_EVENTS);
    if (outcomes.length === 0) return { ok: false, reason: '还没有已验收的成果可交给 Skill Foundry；先做成并验收一件事' };
    try {
      const batch = await call(fetcher, `${root}/events/batch`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ events: eventsFromOutcomes(store, outcomes) }) });
      notes.push(`喂了 ${outcomes.length} 条事件`);
      if (batch?.counts) notes.push(`Foundry 回执：${JSON.stringify(batch.counts)}`);
    } catch (error) {
      return { ok: false, reason: `把成果交给 Skill Foundry 失败：${error.message}` };
    }
    try {
      await call(fetcher, `${root}/skills/passive/scan`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      notes.push('触发了一次分组起草');
    } catch (error) {
      notes.push(`分组起草没跑成（不阻塞导入）：${error.message}`);
    }
  }

  // ② 取成品：把还没导过的草稿拉回来，落成我们的 skill 对象
  let listed;
  try {
    listed = await call(fetcher, `${root}/skills`, { method: 'GET' });
  } catch (error) {
    return { ok: false, reason: `读 Foundry 技能列表失败：${error.message}` };
  }
  const already = importedFoundryIds(store, user);
  const candidates = (listed?.skills || []).filter((item) => item.skill_id && !already.has(item.skill_id)).slice(0, limit);
  const imported = [];
  for (const item of candidates) {
    try {
      const detail = await call(fetcher, `${root}/skills/${encodeURIComponent(item.skill_id)}`, { method: 'GET' });
      const version = detail?.current_version || {};
      const markdown = String(version.skill_markdown || '').trim() || String(detail?.description || '').trim();
      if (!markdown) { notes.push(`跳过 ${item.skill_id}：没有 SKILL.md 正文`); continue; }
      const saved = toolLibraryCommand(store, user, 'tool.save', {
        title: String(detail?.name || item.name || item.slug || '能力卡').slice(0, 120),
        instructions: markdown,
        kind: 'Skill',
        system: 'execute',
      });
      toolLibraryCommand(store, user, 'tool.activate', { id: saved.id, version: saved.version });
      const created = store.get(saved.id);
      store.update(created, {
        ...created.data,
        source: 'foundry',
        foundry: { skill_id: item.skill_id, version_id: version.version_id || null, slug: item.slug || '', fetched_at: now() },
      }, user);
      imported.push({ id: saved.id, title: created.data.title, foundrySkillId: item.skill_id });
    } catch (error) {
      notes.push(`导入 ${item.skill_id} 失败：${error.message}`);
    }
  }

  // ③ 记一笔"这次真的调用了 Foundry"（/health/deps 的 used / last_used_at 从这里出）
  const run = store.add(RUN_TYPE, user, {
    status: 'synced',
    foundry_skill_ids: imported.map((item) => item.foundrySkillId),
    imported: imported.map((item) => ({ id: item.id, title: item.title })),
    notes,
    at: now(),
  });
  return {
    ok: imported.length > 0,
    imported,
    notes,
    reason: imported.length ? undefined : (notes.join('；') || '这一轮没有可导入的新草稿（Foundry 需要同一类事情做成 2 次以上才会起草）'),
    runId: run.id,
  };
}

const REQUEST_TYPE = 'forge_request';

/**
 * 命令：`skill.forge` —— 只**登记一次请求**，不在这里发网络请求。
 * 命令是同步事务（`store.command`），而调 Foundry 要发 HTTP；真正的执行交给运行时循环
 * （`tickSkillForge`），和记忆同步 `syncMemoryHub` 一个路子。
 */
export function skillForgeCommand(store, user, action, input) {
  if (action !== 'skill.forge') return null;
  const pending = store.list(REQUEST_TYPE).find((item) => item.owner === user && item.data.status === 'pending');
  if (pending) return { id: pending.id, status: 'pending', note: '上一次请求还在跑' };
  const request = store.add(REQUEST_TYPE, user, {
    status: 'pending',
    feed: input.feed !== false,
    limit: Math.max(1, Math.min(Number(input.limit) || 3, 10)),
    at: now(),
  });
  return { id: request.id, status: 'pending' };
}

/**
 * 运行时循环里跑：把最早的 pending 请求拿去执行，成功/失败都写回请求对象。
 * 失败不抛异常（后台任务不该把整个 tick 打断），原因写进请求里给界面看。
 */
export async function tickSkillForge(store, provider, config = process.env, fetcher = fetch) {
  const request = store.list(REQUEST_TYPE)
    .filter((item) => item.data.status === 'pending')
    .sort((a, b) => String(a.created).localeCompare(String(b.created)))[0];
  if (!request) return null;
  try {
    const result = await forgeSkills(store, request.owner, { feed: request.data.feed, limit: request.data.limit }, { config, fetcher });
    return store.update(request, { ...request.data, status: result.ok ? 'done' : 'failed', result, finished_at: now() }, request.owner);
  } catch (error) {
    return store.update(request, { ...request.data, status: 'failed', result: { ok: false, reason: error instanceof Error ? error.message : '生成失败' }, finished_at: now() }, request.owner);
  }
}

/** 上游状态里的使用证据：forge_run 里成功导入过几张。 */
export function forgeUsage(store, user) {
  const runs = store.list(RUN_TYPE).filter((item) => item.owner === user);
  const importedCount = runs.reduce((total, item) => total + (item.data.foundry_skill_ids?.length || 0), 0);
  const last = runs.map((item) => item.data.at).filter(Boolean).sort().pop() || null;
  if (!runs.length) return { used: false, last_used_at: null, evidence: '还没有调用过它生成 skill' };
  return { used: true, last_used_at: last, evidence: `已从它导入 ${importedCount} 张能力卡（调用 ${runs.length} 次）` };
}
