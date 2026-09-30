/**
 * Jev 判定模块：用 Jev 核对"自动学到的理解"有没有超出用户原话。
 *
 * 为什么是这里：记忆系统从上下文里提取用户信息时，模型会把原句改写成一条理解
 * （`content !== source_quote`，我们标成 hypothesis）。改写有没有加戏，靠规则看不出来，
 * 而 Jev 做的事正是"给定原文，对有限条件做判定并指出依据哪一行"——它不出文案，只出判定。
 *
 * 判定条件固定三条（不随任务变化，条件越稳，回执越可比）：
 *   ① 原句是用户本人的长期偏好/习惯/约束/目标，不是一次性安排；
 *   ② 这条理解没有超出原句说明的范围；
 *   ③ 原句不是疑问、假设或转述他人。
 * 判定为"明确不支持"时，这条理解会被降级为待本人确认（不再自动当作已学到的理解使用）。
 * 核对对象是"自动学到"的理解（低风险直接生效的那些）：规则只看得到关键词，看不出
 * "这到底是不是用户本人的长期要求"，这一层需要一个真的判定，并且要指出依据哪一行原话。
 *
 * 和记忆同步、能力生成、规划网关同一个路子：命令只登记，运行时循环里发 HTTP，回执带用量。
 */
import { now } from '../store.mjs';
import { queueMemorySync } from '../memory-hub.mjs';

const REQUEST_TYPE = 'jev_request';
const RUN_TYPE = 'jev_run';

export const CONDITIONS = [
  '原句是用户本人的长期偏好、习惯、约束或目标，不是一次性的临时安排',
  '这条理解没有超出原句说明的范围，没有添加用户在原句里没说过的事实',
  '原句不是疑问、假设，也不是转述他人的说法',
];

/**
 * 哪些理解要核对：走自动学习这条路进来的（低风险、直接被当成已学到的理解）都要。
 * 规则只能看关键词，判断不了"这是不是用户本人的长期要求"；模型改写出来的（content 与
 * 原句不一致）更要看有没有加戏。工具沉淀的方法经验不是用户偏好，不在这里核。
 */
export function needsJevVerdict(memory) {
  const data = memory?.data || memory;
  if (!data || data.kind === 'method_experience') return false;
  const content = String(data.content || '').trim();
  const quote = String(data.source_quote || '').trim();
  if (!content || !quote) return false;
  if (data.learning_mode === 'automatic_low_risk' || data.claim_type === 'hypothesis') return true;
  return content !== quote;
}

/** 登记一次核对（同一个记忆只登记一次；已经判过的也能通过命令重判）。 */
export function registerJevVerdict(store, user, memory, { force = false } = {}) {
  const existing = store.list(REQUEST_TYPE).find((item) => item.owner === user && item.data.memory_id === memory.id && item.data.status === 'pending');
  if (existing) return { id: existing.id, status: 'pending' };
  if (!force && memory.data.jev?.run_id) return { id: memory.id, status: 'done', note: '这条理解已经核对过' };
  const request = store.add(REQUEST_TYPE, user, {
    memory_id: memory.id,
    memory_version: memory.version,
    status: 'pending',
    at: now(),
  });
  return { id: request.id, status: 'pending' };
}

/** 命令：`memory.judge` —— 手动重判一条理解（界面需要时用；正常由记忆写入时自动登记）。 */
export function jevCommand(store, user, action, input) {
  if (action !== 'memory.judge') return null;
  const memory = store.owned(user, input.id, 'memory');
  return registerJevVerdict(store, user, memory, { force: true });
}

/**
 * 运行时循环里跑一格：拿最早的一条待判理解去问 Jev。
 * Jev 没配置就留着不动（配置好之后自然会被判），失败原因写进请求里给界面看。
 */
export async function tickJev(store, provider, config = process.env, fetcher = fetch) {
  if (provider.status().jev !== 'configured') return null;
  const request = store.list(REQUEST_TYPE)
    .filter((item) => item.owner && item.data.status === 'pending')
    .sort((a, b) => String(a.created).localeCompare(String(b.created)))[0];
  if (!request) return null;
  const owner = request.owner;
  const write = (data) => store.update(request, { ...request.data, ...data }, owner);
  try {
    const memory = store.get(request.data.memory_id);
    if (!memory || memory.owner !== owner) return write({ status: 'failed', result: { ok: false, reason: '这条理解已经不存在' }, finished_at: now() });
    const sentence = String(memory.data.source_quote || '').trim();
    const understanding = String(memory.data.content || '').trim();
    const verdict = await provider.judge({
      // 待核对的理解和用户的原话都给进去：Jev 才有得比，"有没有超出原句范围"才判得出来。
      context: [{ ref: { id: memory.id, version: memory.version }, title: `待核对的理解：${understanding.slice(0, 500)}`, content: sentence }],
      intent: { original: `核对这条理解是否严格来自用户本人的原话；原话：${sentence.slice(0, 500)}`, conditions: CONDITIONS },
      maxTokens: 20000,
    });
    const parsed = JSON.parse(verdict.output);
    const checks = parsed.results?.[0]?.checks || [];
    if (checks.length !== CONDITIONS.length) throw new Error('Jev 判定条件数量对不上，不能据此改这条理解');
    const unsupported = checks.filter((check) => check.status === 'unsatisfied');
    const supported = checks.every((check) => check.status === 'satisfied');
    const receipt = {
      run_id: verdict.provider_operation_id,
      model: verdict.model,
      checks: checks.map((check) => ({ condition: check.condition, status: check.status, quote: check.quote, confidence: check.confidence })),
      usage: verdict.usage,
      at: now(),
    };
    const current = store.get(memory.id);
    const updated = store.update(current, {
      ...current.data,
      jev: receipt,
      jev_verdict: unsupported.length ? 'unsupported' : supported ? 'supported' : 'unknown',
      // 明确被原句否定：不再当作"已学到的理解"自动使用，等本人确认。
      ...(unsupported.length ? { status: 'pending_confirmation', alignment: 'insufficient', jev_note: `Jev 核对：${unsupported.map((check) => check.condition).join('；')}` } : {}),
    }, owner);
    queueMemorySync(store, updated);
    store.add(RUN_TYPE, owner, { memory_id: memory.id, status: 'judged', provider_operation_id: receipt.run_id, usage: receipt.usage, verdict: updated.data.jev_verdict, at: receipt.at });
    return write({ status: 'done', result: { ok: true, verdict: updated.data.jev_verdict, unsupported: unsupported.length, usage: receipt.usage }, finished_at: now() });
  } catch (error) {
    return write({ status: 'failed', result: { ok: false, reason: error instanceof Error ? error.message : 'Jev 判定失败' }, finished_at: now() });
  }
}

/** 上游状态里的使用证据：Jev 真判过几条、用量是多少。 */
export function jevUsage(store, user) {
  const runs = store.list(RUN_TYPE).filter((item) => item.owner === user);
  if (!runs.length) return { used: false, last_used_at: null, evidence: '还没有流程调用它做判定' };
  const last = runs.map((item) => item.data.at).filter(Boolean).sort().pop() || null;
  const tokens = runs.reduce((total, item) => total + (item.data.usage?.total_tokens || 0), 0);
  return { used: true, last_used_at: last, evidence: `已用它核对 ${runs.length} 条理解（合计 ${tokens} tokens）` };
}
