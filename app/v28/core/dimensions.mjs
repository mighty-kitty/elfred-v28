// 五维能力：题库、计分、估计。服务端（接题与落库）和前端（画图）共用同一份实现，
// 和 memory-policy.mjs 一样是两边都 import 的纯逻辑，避免两套算法各算各的。
//
// 口径（产品定过，改这份文件之前先读）：
//   · 新用户进来是空态：没有测试就没有图，不画全 0 的五维；
//   · 答完那份轻量测试立刻得到一张**偏低的起点图**，起点计入综合分（它不是成绩，是坐标系的低端）；
//   · 之后按**每条被本人验收的真实成果自己的表现**更新：做得好往上走，被指正会回落，
//     证据按 30 天半衰期衰减（很久不碰会慢慢退回到只剩起点那个不确定状态）；
//   · 没测过、成果又不够 3 条的维不给数字，界面走"还差 N 条"。
export const DIMENSIONS = ["洞察", "判断", "表达", "链接", "交付"];
export const QUESTIONNAIRE_VERSION = 2;
export const MIN_EVIDENCE = 3;

// 一条证据的观测噪声；调小 = 做一件事就跳一大截（用户明确说过"随便做一件事就 64 分"不对）。
const TAU = 12;
// 测试起点的标准差：起点是坐标系低端，不当成绩，但也不轻信（答得越不一致，起点越不确定）。
const SIGMA_PRIOR = 10;
const GUARD_WIDEN = 4;
const HALF_LIFE_DAYS = 30;
const CONFIDENCE_K = 1.5;
const START_BAND = [22, 52];

// 5 档选项（IPIP 量表题用）。方向由每题的 key 决定：key=-1 的题反向计分。
const AGREE = ["非常不同意", "比较不同意", "说不好", "比较同意", "非常同意"];

// 题库：16 道 IPIP（公有领域）量表题 + 6 道自研「判断」情境题；正反向项混在一起（13 正 / 9 反），
// 一路点"同意"不会被算成"全都强"。题目顺序交错（不把同一维的题挨着放），避免答题人上一题带着走。
export const QUESTIONNAIRE_ITEMS = [
  { id: "o1", dimension: "洞察", key: 1, text: "我脑子里总有不少新想法。", options: AGREE },
  { id: "c1", dimension: "交付", key: 1, text: "手头的事我马上就会去做，不拖。", options: AGREE },
  { id: "e1", dimension: "表达", key: 1, text: "人多的时候，我常是活跃的那个。", options: AGREE },
  { id: "a1", dimension: "链接", key: 1, text: "别人难过时，我能体会到他的感受。", options: AGREE },
  {
    id: "j1",
    dimension: "判断",
    key: 1,
    text: "别人跟你争一件事，你通常先做什么？",
    options: ["先讲我的看法", "先要证据", "先问清对方到底在说什么"],
  },

  { id: "o2", dimension: "洞察", key: -1, text: "抽象的话题我提不起兴趣。", options: AGREE },
  { id: "c2", dimension: "交付", key: -1, text: "东西用完，我常忘记放回原处。", options: AGREE },
  { id: "e2", dimension: "表达", key: -1, text: "我话不多。", options: AGREE },
  { id: "a2", dimension: "链接", key: -1, text: "别人遇到麻烦，我不太关心。", options: AGREE },
  {
    id: "j2",
    dimension: "判断",
    key: 1,
    text: "要下结论、但信息还不全的时候，你会？",
    options: ["先按经验定下来", "标出哪些是自己猜的", "先不下结论，去补最关键的那一条"],
  },

  { id: "o3", dimension: "洞察", key: -1, text: "抽象的东西我常常听不明白。", options: AGREE },
  { id: "c3", dimension: "交付", key: 1, text: "我喜欢把东西归置得整整齐齐。", options: AGREE },
  { id: "e3", dimension: "表达", key: 1, text: "我常跟不同的人聊起来。", options: AGREE },
  { id: "a3", dimension: "链接", key: 1, text: "我容易被别人的情绪打动。", options: AGREE },
  {
    id: "j3",
    dimension: "判断",
    key: 1,
    text: "一件事听起来很顺，可跟你的直觉对不上，你会？",
    options: ["按直觉否掉", "先照着做，做完再说", "回头查一下它成立的前提"],
  },

  { id: "o4", dimension: "洞察", key: -1, text: "我算不上一个有想象力的人。", options: AGREE },
  { id: "c4", dimension: "交付", key: -1, text: "我常把事情弄得一团乱。", options: AGREE },
  { id: "e4", dimension: "表达", key: -1, text: "我习惯待在不起眼的位置。", options: AGREE },
  { id: "a4", dimension: "链接", key: -1, text: "我对别人的事提不起兴趣。", options: AGREE },
  {
    id: "j4",
    dimension: "判断",
    key: 1,
    text: "有人转给你一条耸动的消息，你会？",
    options: ["直接转给用得上的人", "先存下，不表态", "先看是谁说的、有没有原始出处"],
  },

  {
    id: "j5",
    dimension: "判断",
    key: 1,
    text: "同一件事有两种说法，你会怎么处理？",
    options: ["选更合我意的那个", "两个都先记下来", "找出两边其实一致的那一点"],
  },
  {
    id: "j6",
    dimension: "判断",
    key: 1,
    text: "别人替你把结论定下来了，你更接近哪种？",
    options: ["省事，挺好", "看情况", "不太放心，我自己再核一遍"],
  },
];

/** 给前端的题目：**不含任何内部字段**（没有 key、没有 guard 这类东西，改题不用发前端）。 */
export function questionnairePaper() {
  return {
    version: QUESTIONNAIRE_VERSION,
    dimensions: DIMENSIONS,
    items: QUESTIONNAIRE_ITEMS.map((item) => ({ id: item.id, text: item.text, options: [...item.options] })),
    note: "答完给你一个起点；之后每做成一件事，这一维会按真实结果慢慢更新。",
  };
}

const average = (rows) => rows.reduce((total, value) => total + value, 0) / rows.length;

/**
 * 作答 → 五维**起点值** + 作答一致性 `guard`。
 *   · 选项顺序即分值顺序（低 → 高）；`key=-1` 的题把分值翻过来（反向计分）；
 *   · 每题先归一 0..1 再按维取平均，最后映射到 START_BAND ——
 *     5 档量表题和 3 档情境题不会因为档数不同被拉高或压低；
 *   · `guard` = 正/反向项的均值差（一路点"同意"的人两侧会打架 → 接近 1），
 *     它只用来放大起点的 σ，不额外给分、也不单独算分。
 */
export function scoreQuestionnaire(answers) {
  const byId = new Map(QUESTIONNAIRE_ITEMS.map((item) => [item.id, item]));
  const picked = new Map();
  for (const row of Array.isArray(answers) ? answers : []) {
    if (!row || typeof row !== "object") continue;
    const item = byId.get(String(row.id ?? ""));
    const choice = Number(row.choice);
    if (!item || !Number.isInteger(choice) || choice < 0 || choice >= item.options.length) continue;
    picked.set(item.id, choice);
  }

  const perDimension = Object.fromEntries(DIMENSIONS.map((name) => [name, []]));
  const perDirection = Object.fromEntries(DIMENSIONS.map((name) => [name, new Map()]));
  for (const item of QUESTIONNAIRE_ITEMS) {
    if (!picked.has(item.id)) continue;
    const count = item.options.length;
    let points = picked.get(item.id) + 1;
    if (item.key < 0) points = count + 1 - points;
    const ratio = count > 1 ? (points - 1) / (count - 1) : 0.5;
    perDimension[item.dimension].push(ratio);
    const direction = item.key < 0 ? -1 : 1;
    if (!perDirection[item.dimension].has(direction)) perDirection[item.dimension].set(direction, []);
    perDirection[item.dimension].get(direction).push(ratio);
  }

  const [low, high] = START_BAND;
  const axes = {};
  for (const name of DIMENSIONS) {
    const rows = perDimension[name];
    if (!rows.length) continue;
    axes[name] = Math.round((low + average(rows) * (high - low)) * 10) / 10;
  }

  const gaps = [];
  for (const groups of Object.values(perDirection)) {
    const forward = groups.get(1) ?? [];
    const reverse = groups.get(-1) ?? [];
    if (forward.length && reverse.length) gaps.push(Math.abs(average(forward) - average(reverse)));
  }
  const guard = gaps.length ? Math.round(average(gaps) * 1000) / 1000 : 0;
  return { axes, guard: Math.max(0, Math.min(1, guard)), answered: picked.size };
}

const clamp100 = (value) => Math.round(Math.max(0, Math.min(100, value)) * 10) / 10;

/**
 * 五维的后验估计。每维维护一个 `(θ, σ)`：
 *   先验 = 那份测试给的起点（σ 大 —— 自评不可全信）；
 *   观测 = 每条被本人验收的成果自己的表现分 y（**不是**这张卡的分）；
 *   证据权重由调用方给（外部可核对 1.0 / 本人验收 0.35 / 纯待办 0.2），并按 30 天半衰期衰减。
 * 闭式高斯更新，不需要迭代求解，也不引第三方库：
 *   precision = 1/σ₀² + Σ w_i/τ² ；θ = (θ₀/σ₀² + Σ w_i·y_i/τ²) / precision ；σ = √(1/precision)。
 * 样本越多 σ 越小 —— 下一件事能撬动的幅度就越小（边际递减，天然如此）。
 *
 * `observations` 形状：`{ [维]: [{ score, weight, ageDays }] }`。
 */
export function estimateDimensions(baseline, observations = {}) {
  const priorAxes = baseline?.axes ?? {};
  const priorSigma = SIGMA_PRIOR + (baseline ? GUARD_WIDEN * Number(baseline.guard || 0) : 0);
  const result = {};
  for (const name of DIMENSIONS) {
    const rows = (observations[name] ?? []).filter((row) => Number.isFinite(row?.score));
    const samples = rows.length;
    const hasPrior = baseline ? Number.isFinite(priorAxes[name]) : false;

    let precision = 0;
    let weighted = 0;
    if (hasPrior) {
      precision += 1 / priorSigma ** 2;
      weighted += priorAxes[name] / priorSigma ** 2;
    }
    for (const row of rows) {
      const weight = Math.max(0, Number(row.weight || 0)) * 0.5 ** (Math.max(0, Number(row.ageDays || 0)) / HALF_LIFE_DAYS);
      precision += weight / TAU ** 2;
      weighted += (weight * row.score) / TAU ** 2;
    }

    if (precision <= 0) {
      result[name] = { value: null, lower: null, sigma: null, samples: 0, source: "insufficient", uncertainty: 100, missing: MIN_EVIDENCE };
      continue;
    }
    const mean = weighted / precision;
    const sigma = Math.sqrt(1 / precision);
    const shared = {
      sigma: Math.round(sigma * 100) / 100,
      samples,
      uncertainty: Math.round(100 * (1 - Math.min(1, samples / 12))),
      missing: Math.max(0, MIN_EVIDENCE - samples),
    };
    // 真实成果够 3 条 = 这一维靠证据站住了；起点 + 1~2 条 = 正在被真实表现改动；
    // 只有起点 = 起点图；什么都没有 = 不给数字（界面走空态）。
    const source = samples >= MIN_EVIDENCE ? "evidence" : hasPrior ? (samples > 0 ? "growing" : "baseline") : "insufficient";
    if (source === "insufficient") {
      result[name] = { ...shared, value: null, lower: null, source };
      continue;
    }
    const value = clamp100(mean);
    result[name] = { ...shared, value, lower: clamp100(mean - CONFIDENCE_K * sigma), source };
  }
  return result;
}

/** 综合分 = 有值的维的平均（起点也算）；至少 3 维有值才给 —— 不让 1/5 维冒充"综合能力"。 */
export function compositeOf(estimate) {
  const known = Object.values(estimate).map((row) => row.value).filter((value) => value !== null);
  return known.length >= 3 ? Math.round(average(known)) : null;
}

// ── 成果 → 各维的观测 ──────────────────────────────────────────────────────
// 每维的数字来自**这个人**（起点 = 那份轻量测试，观测 = 每条被本人验收的成果自己的表现），
// **不拿这张卡的分**：卡的分是 skill 的，随手多做几张卡不该抬高一个人。
//   · 维度归属：skill 自己声明了 dimension 就用它；没声明就按这件活的主责 Agent 归属；
//   · 表现分：本人验收时填的满意度（满意 / 没说 / 不满意）——没被验收的成果不进观测，
//     所以"随手点一下记下"不会推高分数；
//   · 权重 0.35 是"本人验收"那一档（外部可核对的才 1.0），再由估计按 30 天半衰期衰减。
export const SYSTEM_DIMENSION = { explore: "洞察", advise: "判断", create: "表达", connect: "链接", execute: "交付" };
export const OWNER_ACCEPTED_WEIGHT = 0.35;
const PERFORMANCE = { satisfied: 65, unknown: 52, unsatisfied: 38 };

/**
 * 把"每条被本人验收的成果"折成各维的观测。
 * `rows` 由调用方给（服务端从对象表取、前端从快照取，字段同一批）：
 *   `{ dimension, system, satisfaction, at }`。
 * @param {Array<{dimension?: string, system?: string, satisfaction?: string, at?: string}>} rows
 * @returns {Record<string, Array<{score: number, weight: number, ageDays: number}>>}
 */
export function observationsFromOutcomes(rows, { now = Date.now() } = {}) {
  /** @type {Record<string, Array<{score: number, weight: number, ageDays: number}>>} */
  const byDimension = {};
  for (const row of Array.isArray(rows) ? rows : []) {
    const dimension = DIMENSIONS.includes(row?.dimension) ? row.dimension : SYSTEM_DIMENSION[row?.system];
    if (!DIMENSIONS.includes(dimension)) continue;
    const at = Date.parse(String(row?.at ?? ""));
    const ageDays = Number.isFinite(at) ? Math.max(0, (now - at) / 86400000) : 0;
    const score = PERFORMANCE[row?.satisfaction] ?? PERFORMANCE.unknown;
    if (!byDimension[dimension]) byDimension[dimension] = [];
    byDimension[dimension].push({ score, weight: OWNER_ACCEPTED_WEIGHT, ageDays });
  }
  return byDimension;
}

/**
 * 拼成第二页要的那份洞察（每维给数字、到哪一步了、还差几条）。
 * @param {{
 *   baseline?: {axes: Record<string, number>, guard: number, version: number, takenAt: string} | null,
 *   observations?: Record<string, Array<{score: number, weight: number, ageDays: number}>>,
 *   outcomeCount?: number,
 *   externalChecks?: number,
 * }} input
 * @returns {{
 *   axes: Array<{label: string, value: number|null, lower: number|null, previous: number|null, source: "evidence"|"growing"|"baseline"|"insufficient", samples: number, missing: number, uncertainty: number}>,
 *   composite: number|null,
 *   previousComposite: number|null,
 *   outcomeCount: number,
 *   externalChecks: number,
 *   verifiedDimensions: number,
 *   minEvidence: number,
 *   started: boolean,
 *   baseline: {axes: Record<string, number>, guard: number, version: number, takenAt: string}|null,
 *   trend: null,
 * }}
 */
export function dimensionInsight({ baseline = null, observations = {}, outcomeCount = 0, externalChecks = 0 } = {}) {
  const estimate = estimateDimensions(baseline, observations);
  return {
    axes: DIMENSIONS.map((label) => ({
      label,
      value: estimate[label].value,
      lower: estimate[label].lower,
      previous: null,
      source: estimate[label].source,
      samples: estimate[label].samples,
      missing: estimate[label].missing,
      uncertainty: estimate[label].uncertainty,
    })),
    composite: compositeOf(estimate),
    previousComposite: null,
    outcomeCount,
    externalChecks,
    verifiedDimensions: DIMENSIONS.filter((name) => estimate[name].source === "evidence").length,
    minEvidence: MIN_EVIDENCE,
    started: Boolean(baseline),
    baseline,
    trend: null,
  };
}
