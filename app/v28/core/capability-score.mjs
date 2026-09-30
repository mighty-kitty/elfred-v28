/**
 * 能力分与能力卡等级。口径照 `docs/实现-维度分与轻量测试-20260926.md` 与
 * 《第二页-数字与等级-算法调研》里定的那套（原来是独立后端的 `scoring.py`，合并进主库时没人搬，
 * 于是卡片停在"待验证 / Lv.1"）。这里搬过来，前后端共用一份。
 *
 * 铁律（都是被实测指出过才写成规则的）：
 *   ① 分数只能由**完成并验收过**的成果推；使用次数不参与。
 *   ② 0 项成果**不给分**（给个 60 分的"及格分"等于白送）。
 *   ③ 分数是置信下界 L = μ − 1.5σ，不是平均分：证据少时 σ 大，一次好运升不了级。
 *   ④ 本人点"验收"不是最高档证据：外部可核对 1.0，本人验收 0.8。
 */

/** 档位名（下标即等级；0 位留空，等级从 1 开始） */
export const LEVEL_STAGE = ['', '发现', '有证据', '已验证', '可靠复用', '稳定交付'];
/** 升到第 N 档需要的成果数 */
export const LEVEL_GATE = [0, 0, 3, 6, 10, 15];
/** 一条成果都没有时的量表起点 */
export const BASE_SCORE = 60;
const SIGMA0 = 8;
const MIN_SIGMA = 2;

/** 证据权重：外部结果最高，本人验收是"能被采信"的门槛，未核验最低 */
export const CARD_WEIGHT = { external: 1.0, accepted: 0.8, unverified: 0.3 };

/**
 * 一条成果的表现分（0–100），只认可观测事实：
 *   satisfied   本人验收通过（对应旧口径里"零指正通过"的 92）
 *   unknown     验收了但没给满意度（对应旧口径"改过几次"的 88）
 *   unsatisfied 本人说这条不对（对应旧口径 disputed 的 30）
 */
export const CARD_PERFORMANCE = { satisfied: 92, unknown: 88, unsatisfied: 30 };

/** 证据越多，σ 越小（分越稳）。全站只有这一个公式。 */
export function sigmaFor(evidence) {
  return SIGMA0 / Math.sqrt(1 + Math.max(0, Number(evidence) || 0));
}

/** 界面上的分：置信下界 */
export function scoreOf(mu, sigma) {
  return Math.min(100, Math.max(0, mu - 1.5 * sigma));
}

/** 一条成果进来，贝叶斯更新 (μ, σ)（与调研里选的 Weng-Lin 同量纲的等价实现） */
export function updateRating(mu, sigma, outcome, weight = CARD_WEIGHT.accepted) {
  const k = 1 / (1 + weight);
  return {
    mu: mu + k * (outcome - mu),
    sigma: Math.max(MIN_SIGMA, sigma * Math.sqrt(1 - k * 0.6)),
  };
}

/** 按成果数门槛 + 分数下界决定档位 */
export function readLevel(evidence, score) {
  let level = 1;
  for (let candidate = 1; candidate < LEVEL_STAGE.length; candidate += 1) {
    if (Number(evidence) >= LEVEL_GATE[candidate] && Number(score) >= 55 + (candidate - 2) * 8) level = candidate;
  }
  return level;
}

export function readStage(level) {
  return level > 0 && level < LEVEL_STAGE.length ? LEVEL_STAGE[level] : `Lv.${level}`;
}

export function readGap(level, evidence) {
  if (level + 1 >= LEVEL_GATE.length) return null;
  const goal = LEVEL_GATE[level + 1];
  return { have: Number(evidence) || 0, goal, need: Math.max(0, goal - (Number(evidence) || 0)) };
}

export function readGapLabel(level, evidence) {
  const gap = readGap(level, evidence);
  if (!gap) return '已达最高档';
  if (gap.need === 0) return `成果已够 · 待升 Lv.${level + 1}`;
  return `还差 ${gap.need} 项成果 → Lv.${level + 1}`;
}

/** 整条阶梯（等级 / 档位名 / 门槛成果数）：权威只有这一份，前端不再自己存表 */
export function ladderView() {
  return LEVEL_STAGE.slice(1).map((stage, index) => ({ level: index + 1, stage, gate: LEVEL_GATE[index + 1] }));
}

/**
 * 一条能力卡现在的分与等级。
 * @param {Array<{satisfaction?: string, external?: boolean, at?: string}>} outcomes 该卡自己的已验收成果（按时间正序）
 * @returns {{score: number|null, evidence: number, level: number, stage: string,
 *   verified: boolean, gap: {have: number, goal: number, need: number}|null,
 *   gapLabel: string, ladder: Array<{level: number, stage: string, gate: number}>, external: number}}
 */
export function cardRating(outcomes = []) {
  const rows = (Array.isArray(outcomes) ? outcomes : [])
    .filter((row) => CARD_PERFORMANCE[row?.satisfaction] !== undefined)
    .sort((a, b) => String(a?.at ?? '').localeCompare(String(b?.at ?? '')));
  let mu = BASE_SCORE + 1.5 * SIGMA0;
  let sigma = SIGMA0;
  let external = 0;
  for (const row of rows) {
    const isExternal = row.external === true;
    if (isExternal) external += 1;
    const weight = isExternal ? CARD_WEIGHT.external : CARD_WEIGHT.accepted;
    const next = updateRating(mu, sigma, CARD_PERFORMANCE[row.satisfaction], weight);
    mu = next.mu;
    sigma = next.sigma;
  }
  const evidence = rows.length;
  const score = evidence > 0 ? Math.round(scoreOf(mu, sigma) * 10) / 10 : null;
  const level = readLevel(evidence, score ?? 0);
  return {
    // 0 项成果不给分：基线分是量表的起点，不是"你的能力分"
    score,
    evidence,
    level,
    stage: readStage(level),
    verified: evidence > 0,
    gap: readGap(level, evidence),
    gapLabel: readGapLabel(level, evidence),
    ladder: ladderView(),
    external,
  };
}
