/**
 * 第四页「勋章」和第二页「理解度 → 荣誉勋章」用同一份勋章。
 * 以前这份是在前端 `page2-api.ts` 里现算的 —— 同一个用户在两处看到两套算法、
 * 也没法在服务端审计，所以搬到服务端：从真实对象算，前端只读。
 *
 * 判据只用真实存在的东西：已验收成果数、能力卡数量与等级、已确认记忆数、账号存在天数。
 * 没赚到的也照实列出来（写 0/3 这种进度），让人知道怎么点亮。
 */
const TARGETS = [
  { id: 'outcome-first', title: '第一次成果', kind: 'outcome', target: 1 },
  { id: 'outcome-three', title: '三件成果', kind: 'outcome', target: 3 },
  { id: 'outcome-ten', title: '十件成果', kind: 'outcome', target: 10 },
  { id: 'skill-first', title: '第一张能力卡', kind: 'skill', target: 1 },
  { id: 'skill-five', title: '五张能力卡', kind: 'skill', target: 5 },
  { id: 'level-three', title: '卡片升到 Lv.3', kind: 'level', target: 3 },
  { id: 'memory-three', title: '记住三件事', kind: 'memory', target: 3 },
  { id: 'days-seven', title: '认识满一周', kind: 'days', target: 7 },
  { id: 'days-thirty', title: '相处满一个月', kind: 'days', target: 30 },
];

export function badgeList(store, user) {
  const outcomes = store.list('outcome').filter((item) => item.owner === user && item.data.verdict === 'accepted').length;
  const skills = store.list('skill').filter((item) => item.owner === user && !['archived', 'deleted', 'superseded', 'rejected'].includes(String(item.data.status)));
  const memories = store.list('memory').filter((item) => item.owner === user && item.data.status === 'validated').length;
  const topLevel = skills.reduce((best, item) => Math.max(best, Number(item.data.level || 1)), 1);
  const profile = store.list('profile').find((item) => item.owner === user);
  const startedAt = Date.parse(profile?.created || '');
  const days = Number.isFinite(startedAt) ? Math.max(0, Math.floor((Date.now() - startedAt) / 86400000)) : 0;

  const valueOf = (kind) => ({ outcome: outcomes, skill: skills.length, level: topLevel, memory: memories, days })[kind] ?? 0;
  const progressOf = (kind, value, target) => (kind === 'days' ? `${Math.min(value, target)}/${target} 天` : `${Math.min(value, target)}/${target}`);

  const badges = TARGETS.map(({ id, title, kind, target }) => {
    const value = valueOf(kind);
    return { id, title, earned: value >= target, progress: progressOf(kind, value, target) };
  });
  return {
    badges,
    count: badges.filter((badge) => badge.earned).length,
    topLevel,
    evidence: outcomes,
  };
}
