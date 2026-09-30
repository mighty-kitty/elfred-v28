/** A visible, evidence-backed growth level; never grants new data or action permissions. */
export const GROWTH_GATES = [0, 0, 1, 3, 5, 8, 12, 17, 23, 30, 38, 47, 57, 68, 80, 93];
export const GROWTH_STAGES = [
  {from:1,to:3,label:'建立'},
  {from:4,to:5,label:'校准'},
  {from:6,to:8,label:'初步理解'},
  {from:9,to:12,label:'主动协作'},
  {from:13,to:15,label:'稳定受托'},
];

const active = row => row && !row.data?.hidden && !['deleted','rejected','superseded','needs_review'].includes(String(row.data?.status));
const admitted = row => active(row) && ['learned','validated','confirmed'].includes(String(row.data?.status));

/** @param {any} snapshot @param {string} system */
export function agentGrowth(snapshot, system) {
  const objects = snapshot?.objects || {};
  const tasks = new Map((objects.task || []).map(task => [task.id, task]));
  const outcomes = (objects.outcome || []).filter(row => {
    const task = tasks.get(row.data?.task_id);
    return task?.data?.system === system && row.data?.verdict === 'accepted';
  });
  const memories = (objects.memory || []).filter(row => row.data?.scope === system && admitted(row));
  const verified = memories.filter(row => ['scenario_verified','stable_over_time'].includes(String(row.data?.alignment)));
  const distinctDays = new Set(outcomes.map(row => String(row.created || '').slice(0,10)).filter(Boolean)).size;
  const corrections = (objects.memory || []).filter(row => row.data?.scope === system && (row.data?.superseded_by || row.data?.status === 'superseded')).length;
  const initialized = Boolean((objects.onboarding || [])[0]?.data?.choice_confirmed_at);
  const points = Math.max(0, (initialized ? 1 : 0) + outcomes.length * 2 + verified.length * 2 + Math.min(10, distinctDays) - corrections);
  let level = 1;
  for (let candidate = 2; candidate <= 15; candidate++) if (points >= GROWTH_GATES[candidate]) level = candidate;
  // L6 and beyond require repeated real outcomes; numerous statements alone cannot produce a "trusted" Agent.
  if (outcomes.length < 3) level = Math.min(level, 5);
  const stage = GROWTH_STAGES.find(row => level >= row.from && level <= row.to)?.label || '建立';
  const next = level < 15 ? GROWTH_GATES[level + 1] : null;
  const latest = outcomes.slice().sort((a,b) => String(b.created).localeCompare(String(a.created)))[0];
  return {
    level, stage, points, nextPoints: next === null ? null : Math.max(0, next - points),
    outcomeCount: outcomes.length, verifiedMemoryCount: verified.length,
    recentReason: latest ? `最近验收了「${tasks.get(latest.data.task_id)?.data?.title || '一项任务'}」` : initialized ? '已完成初始方向设置' : '等待完成初始方向设置',
    nextCondition: level === 15 ? '继续用真实成果维护当前水平' : level >= 5 && outcomes.length < 3 ? `再验收 ${3 - outcomes.length} 项本领域真实成果` : '完成并验收本领域任务，或核对有来源的理解',
  };
}
