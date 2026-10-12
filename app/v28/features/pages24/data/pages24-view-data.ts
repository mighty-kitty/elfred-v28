// 第二页/第四页的**视图数据**：页面直接读的那些常量与视图类型。
//
// 分两类，别混：
//   · 恒定的：颜色表、导入来源、五档/六档的档位名与门槛（后两者从 core 转发，权威只一份）
//   · 不再放任何样例卡 / 样例成果 / 样例维度画像：这几份数组一律是空的，
//     有数据就从后端快照盖进来（`pages24-live.ts`），没有就显示空态。
//     只有"后端够不着"时才拿来顶一下，绝不冒充用户自己的数据
//
// 真数据怎么替进来：见 `pages24-live.ts`（它 import 本文件，再就地改这些数组/对象的内容）。
// 样例卡要带图标组件（是值，不是类型），所以这里用值导入
import { Compass, FileText, Link2 } from "lucide-react";
import type { LiveCapability, LiveDocument } from "../api/page2-types";
// 档位表是"理解度"这条线的权威（core 一份），下面 alignmentView 要用它夹取档位；
// 文件末尾还有一条 export…from 把它转发出去，两处指的都是同一个模块。
import { ALIGNMENT_STAGE } from "../../../core/agent-alignment.mjs";

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

// 五档阶段名与门槛（《能力卡组设计》§2.3）。**权威只有 `core/capability-score.mjs` 一份**：
// 服务端用它算分和等级，界面这些只是转发出去，离线和测试时也能用同一套规则。
export { LEVEL_STAGE, ladderView, readGap, readGapLabel, readLevel, readStage } from "../../../core/capability-score.mjs";
// 等级门槛只有 core/capability-score.mjs 一份（`LEVEL_GATE`），这里直接转发，
// 不再抄一份字面量 —— 抄一份就意味着"改一处忘一处"，而门槛错了没人看得出来。
export { LEVEL_GATE, LEVEL_GATE as LEVEL_EVIDENCE_GATE } from "../../../core/capability-score.mjs";

// 五个维度各一个颜色：卡上彩点、"到下一档"的进度条都用它。
export const DIMENSION_COLOR: Record<string, string> = {
  洞察: "#4c6ef5",
  判断: "#7048e8",
  表达: "#e8590c",
  链接: "#0e8c6a",
  交付: "#b45309",
};

export const abilityCardSamples: AbilityCardSample[] = [];

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

export const todayEvidence: EvidenceItemView[] = [];

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

export const evidenceRecords: EvidenceDetail[] = [];

/* ── 五个维度（维度详情用）──────────────────────────────────── */

export type DimensionProfile = {
  name: string;
  agent: string;
  score: number | null;
  summary: string;
  capLevel: number;
  nextAction: string;
};

export const dimensionProfiles: DimensionProfile[] = [];

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

// 一份"没有数据"的骨架：五维名字在，数值一律 null —— 界面按"还没数 / 还差 N 条"显示。
// 真数值只从后端快照来（`pages24-live.ts` 往这份骨架上盖）。
export const abilityInsight: AbilityInsightView = {
  axes: ["判断", "洞察", "交付", "表达", "链接"].map((label) => ({ label, value: null, previous: null })),
  composite: null,
  previousComposite: null,
  outcomeCount: 0,
  externalChecks: 0,
  trend: null,
};

/* ── 页头（知识库 / 记忆库共用）────────────────────────────── */

// 不再放兜底值：没拿到后端真数就是 null，界面显示"—"，绝不拿别人的 Lv.4 / 86% 当你的。
export const libraryHeader: { alignment: number | null; level: number | null } = {
  alignment: null,
  level: null,
};

/** 后端到底给没给"理解度 / 等级"这两个真数？
 *  没给的时候，界面上就别把上面那两个演示兜底值当成用户真数据用
 *  （否则新用户第一眼看到的是别人的 Lv.4 / 86%）。 */
export let hasLiveAlignment = false;

/**
 * 真数据到了之后由 `pages24-live.ts` 调一次。
 * 为什么要一个 setter：ES module 的 import 绑定是只读的，别的文件不能直接给这里赋值。
 */
export function markLiveAlignment(value: boolean) {
  hasLiveAlignment = value;
}

/** 界面上唯一该读的"理解度"对象：页头、理解度弹层、第四页胶囊、设置页都读这一份。
 *  `live=false` 表示后端还没给真数（还没加载完 / 够不着）——这时界面写"—"，
 *  不写 0%：0 的意思是"它确定自己不了解你"，和"还没数"不是一回事。 */
export type AlignmentView = {
  live: boolean;
  percent: number;
  level: number;
};

export function alignmentView(): AlignmentView {
  const top = ALIGNMENT_STAGE.length - 1;
  const level = libraryHeader.level === null ? 1 : Math.min(Math.max(1, Math.round(libraryHeader.level)), top);
  return {
    live: hasLiveAlignment,
    percent: libraryHeader.alignment ?? 0,   // live=false 时页面走"—"，这个 0 不会被显示
    level,
  };
}

/** 显示用的百分比：没有真数就是"—"（唯一的格式化入口，页面不要再各自拼字符串）。 */
export function readAlignmentPercent(view: AlignmentView = alignmentView()) {
  return view.live ? `${view.percent}%` : "—";
}

// 对齐等级（信任那条线）：档名、门槛、每档"少问你多少事"的一句话。
// 与卡片那 5 档（发现→稳定交付）**不是一套词**：卡片量"能力"，这条量"信任"
// （这件事还要不要每次都问我）。权威同样只有 `core/agent-alignment.mjs` 一份，
// 因为理解度就是按那张门槛表定档的，界面转发即可。
export { ALIGNMENT_GATE, ALIGNMENT_STAGE, ALIGNMENT_UNLOCK, readAlignmentStage } from "../../../core/agent-alignment.mjs";

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
export const documents: LiveDocument[] = [];
