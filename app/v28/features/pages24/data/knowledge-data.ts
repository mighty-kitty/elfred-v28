"use client";

// Second-page view data. In the merged build the authenticated V28 snapshot
// replaces these arrays on login; sample definitions below are cleared before first use.

import { Brain, Compass, FileText, Link2, Rocket, Sparkles } from "lucide-react";

import {
  registerProjector,
  type LiveCapability,
  type LiveEvidenceDetail,
  type LiveDocument,
  type Page2Data,
} from "../api/page2-api";

/* ── 能力卡 ─────────────────────────────────────────────────── */

export type AbilityType = "Skill" | "Mini App" | "Agent";

export type AbilityCardSample = {
  /** true = 真实 skill 但还没跑过（不显示分数，显示"证据不足"） */
  notRunYet?: boolean;
  /** 后端的卡 id（演示数据里也有，写成果时要指认是哪张卡） */
  id?: string;
  type: AbilityType;
  dimension: string;
  title: string;
  copy: string;
  score: number;
  evidence: number;
  level: number;
  owner: string;
  icon: typeof Compass;
};

// 五档阶段名（《能力卡组设计》§2.3）；等级数字从后端来，阶段名由它决定。
export const LEVEL_STAGE = [
  "",
  "发现",
  "有证据",
  "已验证",
  "可靠复用",
  "稳定交付",
];

// 升到第 N 档需要的成果数。成果不够时进度条和"还差几件"都从这里算。
export const LEVEL_EVIDENCE_GATE = [0, 0, 3, 6, 10, 15];

export function readStage(level: number) {
  return LEVEL_STAGE[level] ?? `Lv.${level}`;
}

// 到下一档还差几项成果。已经是最高档时返回 null（界面写"已达最高档"）。
export function readGap(level: number, evidence: number) {
  const gate = LEVEL_EVIDENCE_GATE[level + 1];
  if (!gate) return null;
  return { have: evidence, goal: gate, need: Math.max(0, gate - evidence) };
}

export function readGapLabel(level: number, evidence: number) {
  const gap = readGap(level, evidence);
  if (!gap) return "已达最高档";
  if (gap.need === 0) return `成果已够 · 待升 Lv.${level + 1}`;
  return `还差 ${gap.need} 项成果 → Lv.${level + 1}`;
}

// 五个维度各一个颜色：卡上彩点、"到下一档"的进度条都用它。
export const DIMENSION_COLOR: Record<string, string> = {
  洞察: "#4c6ef5",
  判断: "#7048e8",
  表达: "#e8590c",
  链接: "#0e8c6a",
  交付: "#b45309",
};

export const abilityCardSamples: AbilityCardSample[] = [
  {
    id: "opp",
    type: "Skill",
    dimension: "洞察",
    title: "机会检索",
    copy: "持续扫描与你相关的人和机会",
    score: 68,
    evidence: 2,
    level: 1,
    owner: "探索",
    icon: Compass,
  },
  {
    id: "content",
    type: "Mini App",
    dimension: "表达",
    title: "内容提炼",
    copy: "把收藏内容整理为可复用观点",
    score: 74,
    evidence: 4,
    level: 2,
    owner: "创作",
    icon: FileText,
  },
  {
    id: "connect",
    type: "Agent",
    dimension: "链接",
    title: "主动连接",
    copy: "筛选候选人并解释匹配理由",
    score: 81,
    evidence: 8,
    level: 3,
    owner: "连接",
    icon: Link2,
  },
];

/* ── 今天的新成果 ───────────────────────────────────────────── */

export type EvidenceKind = "outcome" | "context";

export type EvidenceItemView = {
  id: string;
  title: string;
  note: string;
  delta: string;
  kind: EvidenceKind;
/** 这条成果动了哪张卡（卡面文案要说清"对谁 +1"） */
  card: string;
};

export const todayEvidence: EvidenceItemView[] = [
  {
    id: "interview",
    title: "用户访谈",
    note: "机会检索 · 成果 +1",
    delta: "+1",
    kind: "outcome",
    card: "机会检索",
  },
  {
    id: "review",
    title: "产品审阅",
    note: "内容提炼 · 上下文 +2",
    delta: "+2",
    kind: "context",
    card: "内容提炼",
  },
];

/* ── 成果的原始记录（点开一条成果要看到的东西）──────────────── */

export type EvidenceSourceRef = { kind: "task" | "chat"; id: string };

export type EvidenceDetail = {
  id: string;
  title: string;
  day: string;
  time: string;
  kind: EvidenceKind;
  kindLabel: string;
  weightLabel: string;
  source: { label: string; note: string; ref: EvidenceSourceRef };
  summary: string;
  agent: string;
  verified: boolean;
  /** 这条成果改变了什么：卡、分数、成果数、是否升级 */
  impacts: {
    card: string;
    score?: { from: number; to: number };
    evidence?: { from: number; to: number };
    upgraded?: string;
  }[];
  note?: string;
};

export const evidenceRecords: EvidenceDetail[] = [
  {
    id: "interview",
    title: "完成一次用户访谈并确认结论",
    day: "今天",
    time: "16:40",
    kind: "outcome",
    kindLabel: "结果沉淀",
    weightLabel: "计为 1 次外部验证",
    source: {
      label: "任务 · 验证新用户能否独立完成主任务",
      note: "访谈 1 位用户，记录停顿位置",
      ref: { kind: "task", id: "schedule-interview" },
    },
    summary:
      "用户在「创建任务」这一步停了 40 秒，说明入口文案没说清「创建完会发生什么」。",
    agent: "探索 Agent",
    verified: true,
    impacts: [
      {
        card: "机会检索",
        score: { from: 65, to: 68 },
        evidence: { from: 1, to: 2 },
      },
    ],
  },
  {
    id: "review",
    title: "审阅产品方案并留下取舍意见",
    day: "今天",
    time: "14:05",
    kind: "context",
    kindLabel: "上下文更新",
    weightLabel: "计为 1 次已确认结果",
    source: {
      label: "对话 · 与参谋 Agent 的方案讨论",
      note: "8 轮往返，收敛到一版方案",
      ref: { kind: "chat", id: "elfred" },
    },
    summary: "把首页三张卡从「信息展示」改成「今天做什么」，并删掉两处解释性文案。",
    agent: "参谋 Agent",
    verified: true,
    impacts: [
      {
        card: "内容提炼",
        evidence: { from: 2, to: 4 },
        upgraded: "Lv.1 发现 → Lv.2 有证据",
      },
    ],
    note: "只更新了上下文，没有外部结果，所以不动能力分",
  },
  {
    id: "weekly-scan",
    title: "扫出一批可合作的人并解释匹配理由",
    day: "昨天",
    time: "20:12",
    kind: "outcome",
    kindLabel: "结果沉淀",
    weightLabel: "计为 1 次外部验证",
    source: {
      label: "任务 · 找到 3 位可聊的人",
      note: "从 18 位候选人收敛到 3 位",
      ref: { kind: "task", id: "schedule-client" },
    },
    summary: "给出 3 位候选人与匹配理由，其中 1 位已回复。",
    agent: "连接 Agent",
    verified: true,
    impacts: [
      {
        card: "主动连接",
        score: { from: 79, to: 81 },
        evidence: { from: 7, to: 8 },
      },
    ],
  },
];

/* ── 五个维度（维度详情用）──────────────────────────────────── */

export type DimensionProfile = {
  name: string;
  agent: string;
  score: number | null;
  summary: string;
  capLevel: number;
  nextAction: string;
};

export const dimensionProfiles: DimensionProfile[] = [
  {
    name: "判断",
    agent: "参谋",
    score: 91,
    summary: "能围绕目标比较方案并给出取舍",
    capLevel: 5,
    nextAction: "把一个正在犹豫的决定交给参谋 Agent 做风险预演",
  },
  {
    name: "洞察",
    agent: "探索",
    score: 88,
    summary: "能从访谈中识别稳定的用户卡点",
    capLevel: 4,
    nextAction: "再完成 1 次访谈，机会检索就能升到 Lv.2",
  },
  {
    name: "交付",
    agent: "执行",
    score: 76,
    summary: "任务完成后会继续更新能力评分",
    capLevel: 5,
    nextAction: "挑一个任务让执行 Agent 端到端做完，你只验收结果",
  },
  {
    name: "表达",
    agent: "创作",
    score: 84,
    summary: "已形成简洁、结果导向的表达偏好",
    capLevel: 5,
    nextAction: "把收藏的 3 篇内容交给内容提炼，产出 1 个专题",
  },
  {
    name: "链接",
    agent: "连接",
    score: 87,
    summary: "能筛出值得认识的人并说清匹配理由",
    capLevel: 4,
    nextAction: "让连接 Agent 备一份搭话稿，先聊 1 位候选人",
  },
];

export function readDimension(name: string) {
  return dimensionProfiles.find((profile) => profile.name === name) ?? null;
}

export function evidenceOfDimension(name: string) {
  const cards = abilityCardSamples
    .filter((card) => card.dimension === name)
    .map((card) => card.title);
  return evidenceRecords.filter((record) =>
    record.impacts.some((impact) => cards.includes(impact.card)),
  );
}

export function cardsOfDimension(name: string) {
  return abilityCardSamples.filter((card) => card.dimension === name);
}

export function readEvidence(id: string) {
  return evidenceRecords.find((record) => record.id === id) ?? null;
}

/* ── 成果裁定对卡片数字的影响（确认 / 这条不对 / 忘掉）────────────
 * 一条成果被标成"待核对"或"忘掉"之后，它带来的那份分数和成果数就要从卡上扣掉。
 * 界面只读这里算出来的结果，不自己改数——这样"点一下就真的算数"。
 */
export function readCardAdjustment(
  title: string,
  verdicts: Record<string, "confirmed" | "disputed" | "forgotten">,
) {
  // 后端在跑的时候，裁定已经由它算进卡片数字里了（POST /evidence/{id}/verdict 会回新的卡），
  // 前端再扣一次就成了双重扣分——所以这里直接归零。
  if (liveMode) return { scoreDelta: 0, evidenceDelta: 0 };
  let scoreDelta = 0;
  let evidenceDelta = 0;
  for (const record of evidenceRecords) {
    const verdict = verdicts[record.id];
    if (verdict !== "disputed" && verdict !== "forgotten") continue;
    for (const impact of record.impacts) {
      if (impact.card !== title) continue;
      if (impact.score) scoreDelta -= impact.score.to - impact.score.from;
      if (impact.evidence) evidenceDelta -= impact.evidence.to - impact.evidence.from;
    }
  }
  return { scoreDelta, evidenceDelta };
}

/* ── 能力洞察（雷达 + 趋势）────────────────────────────────── */

// value 为 null = 这一维还没有成果。界面必须写"未知"，不许画成 0。
// previous = 上一期的分数（用于"这一期比上期涨/跌多少"），没有就写 null，界面不画对比层。
export type RadarAxisView = {
  label: string;
  value: number | null;
  previous?: number | null;
  /** 这一维现在到哪一步：只有起点 / 起点+少量成果 / 够 3 条成果 / 还没数（后端算好，
   *  前端只负责说人话 —— 画法**只有一种**，起点不是"不算分"的线） */
  source?: "evidence" | "growing" | "baseline" | "insufficient";
  /** 支撑这一维的真实成果条数；不足 minEvidence 时不给"已验证"的说法 */
  samples?: number;
  /** 还差几条才能"已验证"（界面写"还差 N 条"用它） */
  missing?: number;
  /** 置信下界（保守值），与卡的分同一坐标系 */
  lower?: number | null;
};

export type AbilityInsightView = {
  axes: RadarAxisView[];
  composite: number | null;
  previousComposite?: number | null;
  outcomeCount: number;
  externalChecks: number;
  /** 已经站住的维度数（够 3 条真实成果）；综合分只要有 ≥3 维有值就给，起点也算 */
  verifiedDimensions?: number;
  /** 做过那份轻量测试没有（有起点就有图可看） */
  started?: boolean;
  /** 有没有做过那份问卷（起点）；界面据此决定"引导测试"还是"重新测试" */
  hasBaseline?: boolean;
  trend: {
    label: string;
    points: number[];
    weeks: number;
    note: string;
  } | null;
};

export const abilityInsight: AbilityInsightView = {
  axes: [
    { label: "判断", value: 91, previous: 88 },
    { label: "洞察", value: 88, previous: 82 },
    { label: "交付", value: 76, previous: 79 },
    { label: "表达", value: 84, previous: 83 },
    { label: "链接", value: 87, previous: 87 },
  ],
  composite: 82,
  previousComposite: 78,
  outcomeCount: 5,
  externalChecks: 3,
  trend: {
    label: "成长指数",
    points: [58, 60, 63, 66, 69, 70],
    weeks: 6,
    note: "连续 4 周保持增长",
  },
};

/* ── 页头（知识库 / 记忆库共用）────────────────────────────── */

export const libraryHeader = {
  alignment: 86, // 理解度百分比（演示兜底值：后端给了真数就会被覆盖）
  level: 4, // 对齐等级（同上）
};

/** 后端到底给没给"理解度 / 等级"这两个真数？
 *  没给的时候，界面上就别把上面那两个演示兜底值当成用户真数据用
 *  （否则新用户第一眼看到的是别人的 Lv.4 / 86%）。 */
export let hasLiveAlignment = false;

// 对齐等级（信任那条线）的 6 档名。与卡片那 5 档（发现→稳定交付）**不是一套词**，
// 依据《能力卡组设计》§6.3 / §6.4：卡片量"能力"，这条量"信任"（这件事还要不要每次都问我）。
export const ALIGNMENT_STAGE = [
  "",
  "初见",
  "认识你",
  "记得你",
  "懂你",
  "能预判你",
  "可托付",
];

export function readAlignmentStage(level: number) {
  return ALIGNMENT_STAGE[level] ?? `Lv.${level}`;
}

// 信任这条线的门槛：理解度到多少，才进下一档（下标＝档位）。与卡片那五档分开算。
// 现在这一档是 Lv.4「懂你」（70–90），所以 86% 落在它里面，下一档要 90%。
export const ALIGNMENT_GATE = [0, 0, 40, 55, 70, 90, 96];

// 每一档"它少问你多少事"的一句话。界面上不写档名的地方只写百分比，这里只给弹层用。
export const ALIGNMENT_UNLOCK = [
  "",
  "每个动作都要你点一下",
  "先做到「待确认」，你点头才执行",
  "查资料、整理、起草不用每次问你",
  "常做的事它能自己做完再汇总",
  "可以先做再报，你只处理例外",
  "常规事项可代办，承诺仍要你确认",
];

/* ── 导入来源（三种入口）────────────────────────────────────
 * 【接后端时】这三个入口本身是固定的，可以继续写在前端；真正要落库的是
 * 用户点了之后产生的素材 → POST /materials { kind: file|link|resume }
 */
export const IMPORT_SOURCES = [
  { title: "选文件", note: "UTF-8 文本 / Markdown / CSV / JSON", kind: "file" },
  { title: "保存链接", note: "保存网址，不自动抓取正文", kind: "link" },
] as const;

/* ── 文档库（导进来的原始文件）──────────────────────────────
 * 【接后端时】换成 GET /documents → [{ id, name, status }]
 * status: "待提取" | "已提取"（提取是后台的周期任务，手机端只负责导入与预览）
 */
export const documents: LiveDocument[] = [
  { id: "d1", name: "我的简历.pdf", status: "待提取" },
  { id: "d2", name: "访谈录音.m4a", status: "已提取" },
];

/* ── 接后端：真数据到了就地替换 ────────────────────────────────
 * 上面这些常量的"身份"不变（同一个数组/对象），只换里面的内容——所以视图一行都不用动。
 * 接口够不着时什么都不做，页面继续用演示数据顶着（见 page2-api.ts）。
 */

const CARD_ICON: Record<string, typeof Compass> = {
  Skill: Compass,
  "Mini App": FileText,
  Agent: Link2,
  判断: Brain,
  交付: Rocket,
};


function iconOf(card: LiveCapability) {
  return CARD_ICON[card.title] ?? CARD_ICON[card.type] ?? CARD_ICON[card.dimension] ?? Sparkles;
}

function replaceAll<T>(target: T[], next: T[]) {
  target.length = 0;
  target.push(...next);
}

function mapCard(card: LiveCapability): AbilityCardSample {
  return {
    id: card.id,
    type: (["Skill", "Mini App", "Agent"].includes(card.type) ? card.type : "Skill") as AbilityType,
    dimension: card.dimension,
    title: card.title,
    copy: card.copy,
    // ⚠️ 后端在没有成果时给的是 score=null（不给"不劳而获的基线分"），
    // 而 `Math.round(null)` 是 0 —— 卡片上会写"0 能力分"，比原来的 60 更误导。
    // 没有成果就按"证据不足"画（notRunYet 那条分支）。
    score: card.score === null ? 0 : Math.round(card.score),
    notRunYet: card.score === null,
    evidence: card.evidence,
    level: card.level,
    owner: card.owner,
    icon: iconOf(card),
  };
}

function mapEvidence(record: LiveEvidenceDetail): EvidenceDetail {
  return {
    id: record.id,
    title: record.title,
    day: record.day,
    time: record.time,
    kind: record.kind === "context" ? "context" : "outcome",
    kindLabel: record.kindLabel,
    weightLabel: record.weightLabel,
    source: record.source,
    summary: record.summary,
    agent: record.agent,
    verified: record.verified,
    impacts: record.impacts.map((impact) => ({
      card: impact.card,
      score: impact.score ?? undefined,
      evidence: impact.evidence ?? undefined,
      upgraded: impact.upgraded ?? undefined,
    })),
    note: record.note || undefined,
  };
}

/** 真数据一到：五维、综合分、上一期、成长曲线、理解度、文档、待确认，全部换掉 */
function applyLiveData(data: Page2Data) {
  liveMode = true;
  // 能力卡组 = skill 的可视化。有真 skill 就显示真 skill（不管它跑没跑过）；
  // 只有后端连不上时才退回下面那份演示样例。
  if (data.skills && data.skills.length > 0) {
    const byTitle = new Map((data.capabilities ?? []).map((card) => [card.title, card]));
    replaceAll(
      abilityCardSamples,
      data.skills.map((skill) => {
        const ran = byTitle.get(skill.title);
        return {
          id: skill.name,
          type: "Skill" as AbilityType,
          // skill 目录的 frontmatter 里还没有 dimension 字段时，**不猜**——写"未标注"，
          // 等 Skill Foundry 补字段（已记进《第二页-需求与约束记录》）。index 只用来留坑位。
          dimension: skill.dimension || "未标注",
          title: skill.title || skill.name,
          copy:
            skill.summary ||
            // 步数用后端的 stepCount：`steps` 只留了读得懂的（机械名会被丢掉）
            `${skill.stepCount ?? skill.steps.length} 步${skill.hasExamples ? " · 带输入产出样例" : ""}`,
          // ⚠️ 后端在没有成果时给的是 score=null（不给"不劳而获的基线分"），
          // 而 `Math.round(null)` 是 0 —— 卡面会写"0 能力分"，比原来的 60 更误导
          // （实测在页面上就是这样）。没有分就算"没跑过"，走"证据不足"那条分支。
          score: ran && ran.score !== null ? Math.round(ran.score) : 0,
          evidence: ran ? ran.evidence : 0,
          level: ran ? ran.level : 1,
          notRunYet: !ran || ran.score === null,
          owner: "探索",
          icon: iconOf({ title: skill.name, type: "Skill", dimension: "" } as LiveCapability),
        };
      }),
    );
  } else if (data.capabilities) {
    replaceAll(abilityCardSamples, data.capabilities.map(mapCard));
  }

  if (data.evidence) {
    replaceAll(evidenceRecords, data.evidence.map(mapEvidence));
    const byId = new Map(data.evidence.map((record) => [record.id, record]));
    if (data.todayEvidence) {
      replaceAll(
        todayEvidence,
        data.todayEvidence.map((item) => {
          const detail = byId.get(item.id);
          const impact = detail?.impacts[0];
          const gain = impact?.evidence ? impact.evidence.to - impact.evidence.from : 0;
          return {
            id: item.id,
            title: item.title,
            note: item.note,
            delta: gain > 0 ? `+${gain}` : "",
            kind: (item.kind === "context" ? "context" : "outcome") as EvidenceKind,
            card: impact?.card ?? "",
          };
        }),
      );
    }
  }

  if (data.insight) {
    abilityInsight.axes = data.insight.axes.map((axis) => ({
      label: axis.label,
      value: axis.value,
      previous: axis.previous,
      // ⚠️ 这三个字段决定界面怎么"说人话"（起点 / 已经在动 / 还差几条）。
      // 后端已经把它们算好了（services/dimensions.py），前端别再猜。
      source: axis.source,
      samples: axis.samples,
      missing: axis.missing,
      lower: axis.lower,
    }));
    abilityInsight.composite = data.insight.composite === null ? null : Math.round(data.insight.composite);
    abilityInsight.previousComposite =
      data.insight.previousComposite === null ? null : Math.round(data.insight.previousComposite);
    abilityInsight.outcomeCount = data.insight.outcomeCount;
    abilityInsight.externalChecks = data.insight.externalChecks;
    abilityInsight.verifiedDimensions = data.insight.verifiedDimensions ?? 0;
    abilityInsight.started = Boolean(data.insight.started ?? data.insight.baseline);
    abilityInsight.hasBaseline = Boolean(data.insight.baseline);
    abilityInsight.trend = data.insight.trend;

    // 维度详情页：分数来自后端，卡与等级从这一维的卡里挑
    for (const profile of dimensionProfiles) {
      const axis = data.insight.axes.find((item) => item.label === profile.name);
      const cards = abilityCardSamples.filter((card) => card.dimension === profile.name);
      profile.score = axis?.value ?? null;
      if (cards.length > 0) {
        const best = [...cards].sort((a, b) => b.evidence - a.evidence)[0];
        profile.capLevel = Math.max(...cards.map((card) => card.level));
        profile.agent = best.owner || profile.agent;
      }
    }
  }

  hasLiveAlignment = typeof data.alignment?.alignment === "number";
  if (data.alignment) {
    // 后端这两个字段可能是 null（用户还没有记忆时返回的就是 null）。
    // 以前是直接赋值，等于把 86/4 洗成 null/undefined，页头会渲染出 "null%"。
    // 以后端为准 = 后端给了数字才认；没给就保持原值，只是标记 hasLiveAlignment 仍为 false。
    if (typeof data.alignment.alignment === "number") {
      libraryHeader.alignment = data.alignment.alignment;
      hasLiveAlignment = true;
    }
    if (typeof data.alignment.level === "number") {
      libraryHeader.level = data.alignment.level;
    }
  }

  if (data.documents) replaceAll(documents, data.documents);
  livePendingMaterials = data.pending ?? null;
}

/** 裁定完一条成果：后端重算过的卡片分数/成果数直接盖上来 */
function applyLiveCards(cards: LiveCapability[]) {
  const byTitle = new Map(cards.map((card) => [card.title, card]));
  for (const sample of abilityCardSamples) {
    const live = byTitle.get(sample.title);
    if (!live) continue;
    sample.score = Math.round(live.score ?? 0);
    sample.evidence = live.evidence;
    sample.level = live.level;
  }
}

/** 待确认素材：后端有就用后端的，没有就用本地兜底 */
export let livePendingMaterials: Page2Data["pending"] = null;

/** 后端在跑（真数据已就位）。裁定、分数以后端为准，前端那份兜底不掺和。 */
let liveMode = false;

// The imported module carried sample cards and outcomes. A signed-in account must never
// see them as its own history while the authenticated snapshot is loading.
abilityCardSamples.length = 0;
todayEvidence.length = 0;
evidenceRecords.length = 0;
documents.length = 0;
abilityInsight.axes = abilityInsight.axes.map(axis => ({ ...axis, value: null, previous: null }));
abilityInsight.composite = null;
abilityInsight.previousComposite = null;
abilityInsight.outcomeCount = 0;
abilityInsight.externalChecks = 0;
abilityInsight.trend = null;
libraryHeader.alignment = 0;
libraryHeader.level = 1;
for (const profile of dimensionProfiles) { profile.score = null; profile.capLevel = 1; }

registerProjector({ data: applyLiveData, cards: applyLiveCards });
