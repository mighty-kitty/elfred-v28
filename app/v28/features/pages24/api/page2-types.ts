// 第二页/第四页的数据契约（投影的输入输出形状）。纯类型，没有运行时代码。

export type LiveStatus = "loading" | "ready" | "offline";

export type LiveCapability = {
  id: string;
  type: string;
  dimension: string;
  title: string;
  copy: string;
  owner: string;
  score: number | null;
  evidence: number;
  level: number;
  stage: string;
  gap?: { have: number; goal: number; need: number } | null;
  gapLabel: string;
  /** 整条等级阶梯（等级 / 档位名 / 门槛成果数）——由后端给，前端不再自己存门槛表 */
  ladder?: Array<{ level: number; stage: string; gate: number }>;
  verified: boolean;
};

export type LiveEvidence = {
  id: string;
  title: string;
  note: string;
  kind: string;
  verdict: string;
  day: string;
};

export type LiveEvidenceDetail = {
  id: string;
  title: string;
  note: string;
  kind: string;
  kindLabel: string;
  weightLabel: string;
  day: string;
  time: string;
  source: { label: string; note: string; ref: { kind: "task" | "chat"; id: string } };
  summary: string;
  agent: string;
  verified: boolean;
  verdict: string;
  impacts: {
    card: string;
    capabilityId: string;
    score: { from: number; to: number } | null;
    evidence: { from: number; to: number } | null;
    upgraded?: string | null;
  }[];
};

export type LiveInsight = {
  axes: {
    label: string;
    value: number | null;
    previous: number | null;
    /** 这一维的数字现在到哪一步了（后端算好，前端只说人话）：
     *  baseline = 只有测试给的起点 · growing = 起点 + 1~2 条成果 ·
     *  evidence = 够 3 条真实成果 · insufficient = 没测试也没攒够（不给数字） */
    lower?: number | null;
    source?: "evidence" | "growing" | "baseline" | "insufficient";
    samples?: number;
    missing?: number;
    uncertainty?: number;
  }[];
  composite: number | null;
  previousComposite: number | null;
  outcomeCount: number;
  externalChecks: number;
  verifiedDimensions?: number;
  minEvidence?: number;
  /** 做过那份轻量测试没有（有起点就有图可看） */
  started?: boolean;
  baseline?: { axes: Record<string, number>; guard: number; version: number; takenAt: string } | null;
  trend: { label: string; points: number[]; weeks: number; note: string } | null;
};

export type LiveAlignment = {
  alignment: number | null;
  level: number | null;
  stage: string;
  nextGate: number | null;
  /** 还差几件"本人验收的成果"才能到下一档（按同一个公式试算出来的，不是拍脑袋） */
  nextEvidence: number | null;
  confirmedMemories: number;
  externalChecks: number;
  /** 被本人指正/退回的条数（会把它拉下来） */
  corrections: number;
  /** 最近一条成果距今多少天（30 天没有新证据，确信度减半） */
  idleDays: number;
  /** 样本少 ≠ 分数低，是"它自己不确定"（0 = 很确定） */
  uncertainty: number;
  parts: { coverage: number; confirmed: number; days: number; external: number };
};

export type LiveMemory = {
  headline: string;
  totalCount: number;
  // 后端还在算这两个（四类记忆有着落几类）；界面这一版没展示，留着是因为接口里有，
  // 以后要画"基础/社交/习惯/偏好"四个标签时直接用。
  coveredGroups: number;
  groupCount: number;
  daysTracked: number;
  credibility: number;
  /** 四类记忆的实际条目（社交那一类装的是"人"，在 relationships 里） */
  groups: Record<
    string,
    { id: string; group: string; label: string; value: string; source: string; status: string }[]
  >;
  identity: { headline: string; describe: string; photoLabel: string; rule: string };
  relationships: { id: string; name: string; role: string; photo: string; chatId: string }[];
  relationshipStats: { longTerm: number; pending: number };
};

export type LiveDocument = { id: string; name: string; status: string; excerpt?: string };
export type LivePending = { id: string; kind: string; title: string; from: string; excerpt?: string };

/** Skill Foundry 的产物（`existing\skills\<name>\`）——能力卡组的真数据源 */
export type LiveSkill = {
  name: string;
  title: string;
  summary: string;
  /** SKILL.md 头部里的 owner_agent（哪个子 Agent 的 skill；目录里没有就是空串） */
  ownerAgent?: string;
  /** SKILL.md 头部里的 dimension（五个维度；目录里还没有这个字段时是空串，前端不许瞎猜） */
  dimension?: string;
  steps: string[];
  /** 「它能替你做」：从 SKILL.md 的 When to Use / 什么时候用 小节解析出来的几条人话（没有就是空数组） */
  canDo?: string[];
  /** 这条 skill 真实的步骤数；`steps` 只留了读得懂的，数量可能更少，写"N 步"要用这个 */
  stepCount?: number;
  /** 这条 skill 要什么输入（SKILL.md 的 Inputs / 输入 / 前提 小节，必填的标出来） */
  inputs?: string[];
  /** 这条 skill 交付什么（SKILL.md 的 Outputs / 交付 小节） */
  outputs?: string[];
  /** SKILL.md 原文（"完整说明"直接渲染它，不再压成一行字） */
  instructions?: string;
  /** SKILL.md 的验收标准（Verification / 验收 小节） */
  checks?: string[];
  /** SKILL.md 的边界与注意事项（Pitfalls / 注意 / Do Not Use） */
  limits?: string[];
  hasExamples: boolean;
  files: string[];
  updatedAt: string;
};

/** Skill Foundry 的能力生成状态：第二页卡片组那颗按钮用它显示"正在生成/导入了 N 张" */
export type LiveForge = { status: string; reason?: string; imported?: { id: string; title: string }[] };

export type Page2Data = {
  capabilities: LiveCapability[] | null;
  todayEvidence: LiveEvidence[] | null;
  evidence: LiveEvidenceDetail[] | null;
  insight: LiveInsight | null;
  alignment: LiveAlignment | null;
  memory: LiveMemory | null;
  documents: LiveDocument[] | null;
  pending: LivePending[] | null;
  skills: LiveSkill[] | null;
  /** 最近一次 Skill Foundry 生成请求的状态（没有就是 null） */
  forge: LiveForge | null;
};

export type Store = { status: LiveStatus; data: Page2Data; reason: string };

/**
 * 任务契约：把「这条 skill 的步骤与规矩 + 相关记忆」组装成一次做事的执行条件。
 *
 * 为什么要有它：skill 的"真"不在于它是一张卡，在于**它能约束 agent 的行为**。
 * 所以点「用它做一件事」时，skill 必须作为执行条件进场（步骤 / 你定过的规矩 / 验收点），
 * 而不是只跳过去聊天。拿不到就返回 null，调用方退回原来的行为，不假装拿到了。
 */
export type TaskContract = {
  ok: boolean;
  goal: string;
  system: string;
  criteria: string;
  constraints: string;
  memories: string[];
  skill: { name: string; title: string; steps: string[]; rules: string[] } | null;
  note: string;
};

// ── 新用户那份「轻量测试」（问卷 → 五维起点）──────────────────────────
// 题目由**后端**给（改题不用发前端）；选项顺序就是分值顺序（低 → 高）。
// 题面里混了反向计分的题，但那是后端的事 —— 前端只按顺序画选项，不猜方向。
export type QuestionnaireItem = { id: string; text: string; options: string[] };
export type Questionnaire = {
  version: number;
  dimensions: string[];
  items: QuestionnaireItem[];
  note: string;
};

export type LiveProfile = {
  available: boolean;
  name: string;
  bio: string;
  tags: string[];
  avatar: string;
  background: string;
  headline: string;
  level: number | null;
  daysTracked: number | null;
  credibility: number | null;
  identityDescribe: string;
  filled: boolean;
  /** 主页要不要显示等级与理解度（存在我们后端；没设过 = true） */
  showLevel?: boolean;
};

export type LiveFeedItem = {
  kind: "evidence" | "memory";
  id: string;
  title: string;
  detail: string;
  at: string;
  /** 同一天同一条被合并了几次（后端合并的；> 1 时界面写"共 N 次"） */
  count?: number;
  verdict: string;
};

export type LiveBadge = { id: string; title: string; earned: boolean; progress: string };

export type LiveRelationship = {
  id: string;
  name: string;
  role: string;
  stage: string;
  photo: string;
  chatId: string;
};
