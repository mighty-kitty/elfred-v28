import {memoryActive,memoryAdmitted} from './memory-policy.mjs';
export const alignmentStages = [
  {id:'explicit',label:'明确信息',description:'本人明确表达的目标、偏好或约束。'},
  {id:'hypothesis',label:'理解待验证',description:'已形成场景化理解，仍需本人核对。'},
  {id:'scenario_verified',label:'场景已验证',description:'具体理解有对应情境和本人确认的成果依据。'},
  {id:'stable_over_time',label:'跨时间稳定',description:'同一理解有跨时间证据，仍需关注目标变化和反证。'},
];

/** @param {Array<{id:string,version:number,data:Record<string,any>}>} memories */
export function agentAlignment(memories, system) {
  const scoped=memories.filter(item=>(item.data.scope===system||item.data.scope==='owner'&&item.data.allocation?.allowed_systems?.includes(system))&&(memoryActive(item)||item.data.status==='needs_review'&&!item.data.hidden&&(!item.data.expires_at||Date.parse(item.data.expires_at)>Date.now())));
  const entries=scoped.map(item=>{
    const state=item.data.status==='needs_review'||item.data.evidence_needs_review?'insufficient':
      ['candidate','pending_confirmation'].includes(item.data.status)?'hypothesis':
      alignmentStages.some(stage=>stage.id===(item.data.scope==='owner'&&item.data.domain_alignment?.[system]||item.data.alignment))?(item.data.scope==='owner'&&item.data.domain_alignment?.[system]||item.data.alignment):'explicit';
    return {id:item.id,version:item.version,state,label:alignmentStages.find(stage=>stage.id===state)?.label||'需要重评'};
  });
  const states=new Set(entries.map(item=>item.state));
  const state=states.size===1?[...states][0]:states.size?'mixed':'insufficient';
  const levels=entries.map(item=>alignmentStages.findIndex(stage=>stage.id===item.state)+1).filter(level=>level>0);
  const levelLabel=!entries.length?'尚未对齐':levels.length!==entries.length?'等级待核对':Math.min(...levels)===Math.max(...levels)?`第 ${levels[0]} 阶段`:`第 ${Math.min(...levels)}—${Math.max(...levels)} 阶段`;
  return {system,state,label:state==='mixed'?'理解处于不同阶段':state==='insufficient'?(entries.length?'需要重评':'尚无足够理解'):alignmentStages.find(stage=>stage.id===state).label,levelLabel,entries,counts:Object.fromEntries(alignmentStages.map(stage=>[stage.id,entries.filter(item=>item.state===stage.id).length]))};
}
export function memoryOverview(memories){
  const domains=['explore','advise','create','connect','execute'].map(system=>agentAlignment(memories,system));
  const known=domains.filter(domain=>domain.entries.length).length;
  const active=memories.filter(m=>memoryActive(m)),owner=agentAlignment(memories,'owner');
  return {domains,known,label:known?`${known}/5 个领域有记录`:owner.entries.length?owner.label:'尚无足够理解',confirmedCount:active.filter(m=>memoryAdmitted(m)).length};
}

// ── 理解度（信任那条线）──────────────────────────────────────────────
// 口径来自《第二页-数字与等级-算法调研》与旧后端 `insight.read_alignment`（合并进主库时没人搬，
// 于是页头长期显示 0%）。旧版被用户当场指出过的问题，这里都不再犯：
//   · 不再"验收几件事 / 8"这种比例制 —— 随手做 8 件小事就能吃满；
//   · 不再只会涨 —— 被指正、长期没有新证据都会把它拉下来；
//   · 不再封顶在"100% 就到头" —— 曲线渐近，允许回落。
export const ALIGNMENT_STAGE = ['', '初见', '认识你', '记得你', '懂你', '能预判你', '可托付'];
export const ALIGNMENT_GATE = [0, 0, 40, 55, 70, 90, 96];
export const ALIGNMENT_UNLOCK = [
  '',
  '每个动作都要你点一下',
  '先做到「待确认」，你点头才执行',
  '查资料、整理、起草不用每次问你',
  '常做的事它能自己做完再汇总',
  '可以先做再报，你只处理例外',
  '常规事项可代办，承诺仍要你确认',
];
export function readAlignmentStage(level) {
  return ALIGNMENT_STAGE[level] ?? `Lv.${level}`;
}

const BASE = 0.10;          // 没见过你 ≈ 一成。不给 0（0 应该是"它很确定自己不了解你"）
const W_EXTERNAL = 1.0;     // 外部可核对的结果
const W_ACCEPTED = 0.35;    // 本人点一下验收（自己说行，不该顶一次外部证实）
const HALF_LIFE_DAYS = 30;  // 30 天没有新证据，确信度减半

const alignDays = (value, now) => {
  const at = typeof value === 'number' ? value : Date.parse(String(value ?? ''));
  if (!Number.isFinite(at)) return 0;
  return Math.max(0, (now - at) / 86400000);
};

/**
 * 理解度 = PA 对你的确信度。可升可降、没有终点。
 *
 * @param {{
 *   memories?: Array<{data?: Record<string, any>}>,
 *   outcomes?: Array<{satisfaction?: string, external?: boolean, at?: string}>,
 *   hasFriends?: boolean,
 *   hasBaseline?: boolean,
 *   extraCorrections?: number,
 *   trackedSince?: string|number,
 *   now?: number,
 * }} input
 */
export function understandingScore({ memories = [], outcomes = [], hasFriends = false, hasBaseline = false, extraCorrections = 0, trackedSince = 0, now = Date.now() } = {}) {
  const rows = Array.isArray(outcomes) ? outcomes : [];
  // 只有"被本人验收通过"的成果才算证据；本人说"这条不对"的不算证据，只算指正（旧后端同口径）。
  const admitted = rows.filter((row) => row?.satisfaction === 'satisfied' || row?.satisfaction === 'unknown');
  const external = admitted.filter((row) => row?.external === true).length;
  const acceptedOnly = admitted.length - external;
  // 被指正/推翻：本人说"这条不对"的成果，以及被新理解顶掉的旧理解
  const corrections = rows.filter((row) => row?.satisfaction === 'unsatisfied').length
    + (Array.isArray(memories) ? memories.filter((item) => item?.data?.superseded_by || item?.data?.status === 'superseded').length : 0)
    // 被本人打回、还没重新验收的任务（这类不产出成果对象，调用方单独把条数传进来）
    + Math.max(0, Number(extraCorrections) || 0);

  const latest = admitted
    .map((row) => Date.parse(String(row?.at ?? '')))
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => b - a)[0];
  const idleDays = latest ? Math.max(0, (now - latest) / 86400000) : 0;

  const gain = 1 - Math.exp(-(W_EXTERNAL * external + W_ACCEPTED * acceptedOnly) / 6);
  const decay = idleDays ? 0.5 ** (idleDays / HALF_LIFE_DAYS) : 1;
  const penalty = 1 - Math.min(0.5, corrections * 0.08);
  const value = (base, closeGain, closeDecay, closePenalty) => 100 * (base + (1 - base) * closeGain * closeDecay * closePenalty);
  let alignment = Math.round(value(BASE, gain, decay, penalty));
  // 问卷（轻量测试）给一点分：你告诉它关于你的事，它对你确实更确信一点。
  // 只是一次弱信号：重测不累加（表里只留一份有效起点），量级也远小于真实证据。
  if (hasBaseline) alignment = Math.round(Math.min(100, alignment + 6 * (1 - alignment / 100)));

  let level = 1;
  for (let candidate = 1; candidate < ALIGNMENT_GATE.length; candidate += 1) {
    if (alignment >= ALIGNMENT_GATE[candidate]) level = candidate;
  }
  const nextGate = level + 1 < ALIGNMENT_GATE.length ? ALIGNMENT_GATE[level + 1] : null;

  // 还差几件"本人验收的成果"才能到下一档：按同一个公式往后试，不是拿平均值估。
  // 界面上那句"再涨 X 个点（约 N 件成果）"就靠它，不能是拍脑袋写的。
  let nextEvidence = null;
  if (nextGate !== null) {
    for (let extra = 1; extra <= 60; extra += 1) {
      const probeGain = 1 - Math.exp(-(W_EXTERNAL * external + W_ACCEPTED * (acceptedOnly + extra)) / 6);
      let probe = Math.round(value(BASE, probeGain, decay, penalty));
      if (hasBaseline) probe = Math.round(Math.min(100, probe + 6 * (1 - probe / 100)));
      if (probe >= nextGate) { nextEvidence = extra; break; }
    }
  }

  const covered = new Set((Array.isArray(memories) ? memories : [])
    .filter((item) => item?.data?.group)
    .map((item) => item.data.group));
  if (hasFriends) covered.add('社交');
  const admittedMemories = (Array.isArray(memories) ? memories : []).filter((item) => memoryAdmitted(item)).length;
  const trackedDays = alignDays(trackedSince, now);

  return {
    alignment,
    level,
    stage: readAlignmentStage(level),
    nextGate,
    nextEvidence,
    confirmedMemories: admittedMemories,
    externalChecks: external,
    newEvidence: acceptedOnly,
    corrections,
    idleDays: Math.round(idleDays * 10) / 10,
    // 样本少 → 这不是"分数低"，是"它自己不确定"（0 = 很确定）
    uncertainty: Math.round(100 * (1 - Math.min(1, admitted.length / 12))),
    halfLifeDays: HALF_LIFE_DAYS,
    parts: {
      coverage: Math.round((Math.min(4, covered.size) / 4) * 100) / 100,
      confirmed: memories?.length ? Math.round((admittedMemories / memories.length) * 100) / 100 : 0,
      days: Math.min(1, trackedDays / 30),
      external: Math.min(1, external / 8),
    },
  };
}
