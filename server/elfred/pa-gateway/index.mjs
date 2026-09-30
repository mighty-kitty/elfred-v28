/**
 * 规划网关模块：把"多步骤、要分工"的任务交给独立规划网关出方案，用在运行计划上。
 *
 * 为什么单开一个模块：它跨进程、有自己的一套合同，而且**不能**在同步命令里发 HTTP。
 * 所以走和记忆同步 / 能力生成同一个路子：命令只登记请求，运行时循环在空闲那一支执行。
 *
 * 三份合同：
 *   ① 建一次本人档案：POST /v1/pa/profiles（幂等键按用户，不重复建）；
 *   ② 让网关规划：POST /v1/pa/{pa_id}/messages → 轮询 GET /v1/runs/{run_id} 拿 `plan`
 *      （网关跑到 waiting_approval 就停，不会替我们执行任何工具；读完即取消，不留 parked run）；
 *   ③ 落到我们自己的计划：网关的工具名 → 我们运行时真能执行的步骤（见 TOOL_MAP）。
 *
 * 网关不可用、超时、或它的方案落不成我们的步骤时，一律回落应用内运行时的计划，
 * 并把回落原因写进计划回执；绝不假装"这次是网关规划的"。
 */
import { now } from '../store.mjs';
import { reviewPolicy, reviewerFor } from '../agent-plan.mjs';
import { safeBase, callJson, joinUrl } from '../upstream.mjs';

const REQUEST_TYPE = 'gateway_request';
const PLAN_TYPE = 'gateway_plan';
const RUN_TYPE = 'gateway_run';
const PROFILE_TYPE = 'gateway_profile';

/** 网关的工具名 → 我们运行时真的能执行的步骤。落不成的写 null，会在回执里点名。 */
const TOOL_MAP = {
  knowledge_search: { tool: 'search.local', phase: 'context' },
  task_search: { tool: 'search.local', phase: 'context' },
  emos_recall: { tool: 'context.read', phase: 'context' },
  task_create: { tool: 'text.compose', phase: 'work' },
  task_update: { tool: 'text.compose', phase: 'work' },
};

/**
 * 我们这边真的能执行的网关工具。建档案时就把这份清单交给网关：
 * 网关的规划器与策略都按它出方案（不在清单里的工具根本不会进方案），
 * 这比"等它给完再用名字去猜"可靠，也避免它规划出我们执行不了的动作。
 */
export const ELFRED_TOOL_SCOPES = ['knowledge_search', 'task_search', 'emos_recall', 'task_create'];

/** 一句话里有先后步骤（或三方分工）才算"要规划"，单句任务不打扰网关。 */
const SEQUENTIAL = /然后|接着|之后|最后|并且|同时|顺便|再(?:按|把|写|做|查|整理|补|出)/;

const goalClauses = (goal) => String(goal)
  .split(/[，,；;。！!？?\n]|然后|最后|之后|接着/)
  .map((part) => part.trim())
  .filter((part) => part.length >= 4);

/** 这个任务要不要交给网关规划。只看我们自己的任务，系统内部流程不打扰网关。 */
export function needsGatewayPlan(task) {
  const data = task?.data || task;
  if (!data || data.mode !== 'compose') return false;
  if (data.agent_chat || data.group_agent || data.internal_peer_comment || data.internal_tool_generation || data.observation_id || data.media_operation) return false;
  const goal = String(data.goal || '');
  if (!goal) return false;
  if ((data.collaboration_steps || []).length > 0) return true;
  return SEQUENTIAL.test(goal) || goalClauses(goal).length >= 3;
}

/**
 * 该不该给这个任务取一份方案：**还没跑**、**是用户自己的**多步骤任务。
 *
 * 为什么按状态判定而不是在创建时判：对话回复、群内回复、朋友圈点评、晚间反思这些系统流程，
 * 它们的"我是内部流程"标记是**创建之后**才附到任务上的（见 agent-chat / group-agent），
 * 创建那一刻看不出区别；而它们的 run 在同一个命令里就启动了，
 * 这时候再去取方案，钱花了、方案也永远用不上。
 *
 * 所以规则改成：只有还停在草稿/待启动的任务才值得预先取方案 —— 用户确认之前就位才叫有用。
 * 已经跑起来的（queued/running/...）和跑完的都不再补。
 */
export function gatewayCandidate(task, now = Date.now()) {
  const data = task?.data || task;
  if (!data || !needsGatewayPlan(task)) return false;
  if (!['draft', 'ready', 'blocked'].includes(String(data.status || ''))) return false;
  // 放了两天没人动的草稿也不再补：这个用户多半已经不要它了
  const created = Date.parse(String(task.created || ''));
  if (Number.isFinite(created) && now - created > 2 * 86400000) return false;
  return true;
}

function reasonOf(error) {
  return error instanceof Error ? error.message : '规划网关卡住了';
}

/** 网关里本人档案的 pa_id；没有就建一个（幂等键按用户，重复调用不会多建）。 */
async function ensureProfile(store, user, root, fetcher) {
  const existing = store.list(PROFILE_TYPE).find((item) => item.owner === user && item.data.pa_id);
  if (existing) {
    // 工具范围变了（比如这次起就只交给它我们真能执行的那几个）要同步过去，否则它还会规划出我们接不住的动作。
    if (JSON.stringify(existing.data.tool_scopes || null) !== JSON.stringify(ELFRED_TOOL_SCOPES)) {
      await callJson(fetcher, `${root}/v1/pa/profiles/${encodeURIComponent(existing.data.pa_id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool_scopes: ELFRED_TOOL_SCOPES }),
      });
      store.update(existing, { ...existing.data, tool_scopes: ELFRED_TOOL_SCOPES, at: now() }, user);
    }
    return existing.data.pa_id;
  }
  const profile = await callJson(fetcher, `${root}/v1/pa/profiles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': `elfred-${user}` },
    body: JSON.stringify({ user_id: `elfred:${user}`, tool_scopes: ELFRED_TOOL_SCOPES }),
  });
  if (!profile?.pa_id) throw new Error('规划网关没有返回档案 id');
  store.add(PROFILE_TYPE, user, { pa_id: profile.pa_id, state: profile.state || null, tool_scopes: ELFRED_TOOL_SCOPES, at: now() });
  return profile.pa_id;
}

/**
 * 命令：`task.plan` —— 只登记一次请求。
 * 正常情况下运行时循环会自己给"还没跑的多步任务"登记（见 `gatewayCandidate`），
 * 这个命令给界面留手动重试的口子（比如上次网关关着、这次想重排）。
 */
export function gatewayCommand(store, user, action, input) {
  if (action !== 'task.plan') return null;
  const task = store.owned(user, input.id, 'task');
  if (!needsGatewayPlan(task)) return { id: task.id, status: 'skipped', note: '这件事不需要额外规划' };
  return registerGatewayPlan(store, user, task);
}

/** 任务创建时自动登记（幂等：同一个任务只登记一次）。 */
export function registerGatewayPlan(store, user, task) {
  const existing = store.list(REQUEST_TYPE).find((item) => item.owner === user && item.data.task_id === task.id);
  if (existing) {
    // 上次没跑成（网关关着、超时）时，这个命令就是重试的口子：重新排一次，而不是永远卡在失败。
    if (existing.data.status !== 'failed') return { id: existing.id, status: existing.data.status };
    const retried = store.update(existing, { ...existing.data, status: 'pending', attempt: (existing.data.attempt || 0) + 1, gateway_run_id: null, result: null, at: now() }, user);
    return { id: retried.id, status: 'pending' };
  }
  const request = store.add(REQUEST_TYPE, user, {
    task_id: task.id,
    goal: String(task.data.goal || '').slice(0, 600),
    status: 'pending',
    gateway_run_id: null,
    at: now(),
  });
  return { id: request.id, status: 'pending' };
}

/**
 * 运行时循环里跑一格：每个 tick 只发一个 HTTP 调用，不长时间占住循环。
 *   pending  → 让网关开一次 run，记下它的 run_id
 *   waiting  → 看那次 run 出方案了没有（网关在 20 秒的预算内该到 waiting_approval）
 */
export async function tickGateway(store, provider, config = process.env, fetcher = fetch, at = Date.now()) {
  const base = safeBase(config.ELFRED_PA_GATEWAY_URL);
  if (!base) return null;
  // 先给"还没跑的、用户自己的多步任务"登记一次（登记必须晚于创建：系统流程的标记是创建后才有的）
  for (const task of store.list('task')) {
    if (!gatewayCandidate(task, at)) continue;
    if (store.list(REQUEST_TYPE).some((item) => item.data.task_id === task.id)) continue;
    registerGatewayPlan(store, task.owner, task);
  }
  const request = store.list(REQUEST_TYPE)
    .filter((item) => item.owner && ['pending', 'waiting'].includes(item.data.status))
    .sort((a, b) => String(a.created).localeCompare(String(b.created)))[0];
  if (!request) return null;
  const root = joinUrl(base, '');
  const owner = request.owner;
  const write = (data) => store.update(request, { ...request.data, ...data }, owner);

  try {
    if (request.data.status === 'pending') {
      const paId = await ensureProfile(store, owner, root, fetcher);
      const accepted = await callJson(fetcher, `${root}/v1/pa/${encodeURIComponent(paId)}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': `elfred-${request.id}` },
        body: JSON.stringify({ message: request.data.goal }),
      }, { timeout: 20000 });
      if (!accepted?.run_id) throw new Error('规划网关没有返回运行 id');
      return write({ status: 'waiting', gateway_run_id: accepted.run_id, requested_at: now() });
    }

    const run = await callJson(fetcher, `${root}/v1/runs/${encodeURIComponent(request.data.gateway_run_id)}`, { timeout: 15000 });
    if (!run) throw new Error('规划网关没有返回运行状态');
    const terminal = ['completed', 'failed', 'cancelled', 'expired'];
    if (!run.plan?.length && terminal.includes(run.state)) {
      return write({ status: 'failed', result: { ok: false, reason: `网关这次规划没有产出步骤（状态 ${run.state}）` }, finished_at: now() });
    }
    if (!run.plan?.length) {
      const waited = at - Date.parse(request.data.requested_at || request.created);
      if (waited > 60000) return write({ status: 'failed', result: { ok: false, reason: '等网关出方案超时（60 秒）' }, finished_at: now() });
      return null;
    }

    const created = (run.events || []).find((event) => event.type === 'plan.created');
    const receipt = {
      ok: true,
      gateway_run_id: run.run_id,
      planner: created?.payload?.planner || null,
      source: created?.payload?.source || null,
      planning_ms: created?.payload?.planning_ms ?? null,
      dropped_by_gateway: created?.payload?.dropped_tools || [],
      steps: run.plan,
      at: now(),
    };
    // 网关那边停在 waiting_approval；方案已经取到，别让它留一条永远等人的运行。
    try {
      await callJson(fetcher, `${root}/v1/runs/${encodeURIComponent(run.run_id)}/cancel`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }, { timeout: 8000 });
      receipt.cancelled = true;
    } catch (error) {
      receipt.cancelled = false;
      receipt.cancel_error = reasonOf(error);
    }
    store.add(PLAN_TYPE, owner, { task_id: request.data.task_id, goal: request.data.goal, ...receipt });
    store.add(RUN_TYPE, owner, { task_id: request.data.task_id, gateway_run_id: run.run_id, planner: receipt.planner, steps: receipt.steps.length, at: receipt.at });
    return write({ status: 'done', result: receipt, finished_at: now() });
  } catch (error) {
    return write({ status: 'failed', result: { ok: false, reason: reasonOf(error) }, finished_at: now() });
  }
}

/** 这个任务拿到手的网关方案（最新的那条）；没有就返回 null。 */
export function gatewayPlanFor(store, user, taskId) {
  return store.list(PLAN_TYPE)
    .filter((item) => item.owner === user && item.data.task_id === taskId)
    .sort((a, b) => String(b.created).localeCompare(String(a.created)))[0] || null;
}

/**
 * 把网关方案翻成我们运行时的步骤。翻不出来（没有可执行步骤）时 `steps` 为 null，由调用方回落，
 * 但**跳过了什么一定带回去**，回执里要点名，不能让"回落"变成一句没人看得懂的话。
 * 尾巴（独立复核 / 修正）在这一层自己算：原来靠 `agent-plan.mjs` 的 `planTail`，
 * 同事后来把那段收进 `composePlan` 里了、不再单独导出，所以这里自己拼一份等价的，
 * 保证"采纳网关方案也不丢复核"。`tail` 仍然可以由调用方覆盖（测试与将来换实现用）。
 */
export function stepsFromGatewayPlan(plan, role, task, tail = null) {
  const raw = plan?.data?.steps;
  if (!Array.isArray(raw) || raw.length === 0) return { steps: null, skipped: ['它这次没有给出步骤'], adopted: 0 };
  // 这些任务的步骤形状由自己定（检索方式、媒体操作、批量语义检索），硬套网关的名字会改掉行为。
  if (task.data.media_operation || task.data.semantic_plan) return { steps: null, skipped: ['这类任务的步骤由我们自己的形状定，不用网关的方案'], adopted: 0 };
  const allowlist = role?.tool_allowlist || null;
  const context = [];
  const work = [];
  const skipped = [];
  /** 这次任务已经声明过的检索方式：网关说"先检索"，就用它声明的那个，而不是我们自己猜。 */
  const declaredLookup = task.data.local_lookup
    ? { id: 'lookup', phase: 'context', tool: 'search.local', depends: [] }
    : task.data.web_lookup ? { id: 'lookup', phase: 'context', tool: task.data.web_lookup.tool, depends: [] } : null;
  for (const step of raw) {
    const tool = String(step?.tool || '');
    const mapped = TOOL_MAP[tool];
    if (!mapped) { skipped.push(`${tool || '未命名工具'}（我们这边没有对应动作）`); continue; }
    if (mapped.phase === 'context') {
      if (declaredLookup) {
        if (!context.some((item) => item.id === declaredLookup.id)) context.push({ ...declaredLookup, from_gateway_step: step.step ?? null, goal: String(step.goal || '').slice(0, 200) });
        continue;
      }
      // 没有授权资料时"读取资料"这一步读的是空：不摆一个走过场的步骤。
      if (mapped.tool === 'context.read' && (task.data.source_refs || []).length === 0) { skipped.push(`${tool}（这次任务没有授权资料可读）`); continue; }
      if (context.some((item) => item.tool === mapped.tool)) { skipped.push(`${tool}（这一步的动作和前面重复）`); continue; }
      if (context.length >= 2) { skipped.push(`${tool}（这次最多保留两步准备动作）`); continue; }
      if (allowlist && !allowlist.includes(mapped.tool)) { skipped.push(`${tool}（所选能力不允许这个动作）`); continue; }
      context.push({ id: `ctx-${context.length + 1}`, phase: 'context', tool: mapped.tool, depends: [], from_gateway_step: step.step ?? null, goal: String(step.goal || '').slice(0, 200) });
      continue;
    }
    if (work.length === 0) {
      work.push({ id: 'work', phase: 'work', tool: mapped.tool, depends: [], from_gateway_step: step.step ?? null, goal: String(step.goal || '').slice(0, 200) });
      continue;
    }
    // 网关把一次产出拆成两步时，我们只做一轮成果生成（预算与时间都算得过来），但这一步的差别要写出来。
    skipped.push(`${tool}（网关拆成两次产出，这次合成一次成果生成）`);
  }
  if (work.length === 0) return { steps: null, skipped, adopted: 0 };
  const support = (task.data.collaboration_steps || []).map((step) => ({
    ...step,
    id: `collab-${step.id}`,
    depends: step.depends.map((id) => `collab-${id}`),
    phase: 'collaboration',
    tool: 'text.compose',
  }));
  const before = [...context, ...support].map((step) => step.id);
  const steps = [...context, ...support, { ...work[0], depends: before, capability_id: role?.id }];
  const withTail = [...steps, ...(tail ? tail(steps.length) : gatewayPlanTail(task, role, steps.length))];
  // 步骤数超过这次任务的调用上限就没意义了：那样的"计划"跑到一半必然停住。
  if (withTail.length > Number(task.data.stop?.maxCalls || 0)) return { steps: null, skipped: [...skipped, `它给的方案要 ${withTail.length} 步，超过这次任务的调用上限`], adopted: 0 };
  return { steps: withTail, skipped, adopted: steps.length };
}

/**
 * 网关方案后面的"复核 + 修正"尾巴（等价于 `agent-plan.mjs` 以前那份 planTail）：
 * 要不要复核由 `reviewPolicy` 决定，步骤数与预算都要算得过来，否则宁可不加。
 */
export function gatewayPlanTail(task, capability, before) {
  const review = reviewPolicy(task, capability);
  if (!review.wanted || !review.available) return [];
  const total = Number(before) + 2;
  const reviews = [{
    id: 'review', tool: 'text.compose', depends: ['work'], phase: 'review',
    system: task.data.reviewer_system || task.data.system,
    capability_id: reviewerFor(task.data.reviewer_system || task.data.system).id,
  }];
  const room = total <= 12 && Number(task.data.stop?.maxCalls || 0) >= total && Number(task.data.stop?.maxUnits || 0) >= total * 1000;
  return room ? [...reviews, { id: 'repair', tool: 'text.compose', depends: ['review'], phase: 'repair', capability_id: capability?.id, when: 'revision_required' }] : reviews;
}

/** 上游状态里的使用证据：网关真出过几次方案。 */
export function gatewayUsage(store, user) {
  const runs = store.list(RUN_TYPE).filter((item) => item.owner === user);
  if (!runs.length) return { used: false, last_used_at: null, evidence: '还没有把任务规划交给它' };
  const last = runs.map((item) => item.data.at).filter(Boolean).sort().pop() || null;
  const steps = runs.reduce((total, item) => total + (item.data.steps || 0), 0);
  return { used: true, last_used_at: last, evidence: `已从它取回 ${runs.length} 次方案（共 ${steps} 步）` };
}
