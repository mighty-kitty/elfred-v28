"use client";
import {displayTitle} from "../../../core/display-labels";

import { useState } from "react";
import {
  ArrowUpRight,
  Check,
  ChevronRight,
  Compass,
  History,
  Lock,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import type { Screen } from "../../../core/screen";
import { RootPortal } from "../../../legacy/legacy-ui";
import { SHOW_RESERVED_ACTIONS, runSkill, usePage2Live } from "../api/page2-api";
import {
  DIMENSION_COLOR,
  LEVEL_EVIDENCE_GATE,
  evidenceRecords,
  readDimension,
  readStage,
  type AbilityType,
} from "../data/knowledge-data";
import styles from "../styles/knowledge.module.css";

export type SheetCard = {
  /** 后端卡 id（有它才能把"Agent 干完活"这条成果指认到这张卡上） */
  id?: string;
  type: AbilityType;
  dimension: string;
  title: string;
  copy: string;
  score: number;
  evidence: number;
  level: number;
  icon: typeof Compass;
};

// 使用说明的流程图（就是那张实例卡的图）。
//
// 上一版把它换成 HTML 三栏是**改坏了**：用户要的是这张图。这里把它还原，
// 同时补上两个当时没有的保护，免得再出现"文字糊成一团"：
//   ① 一行只排 5 个步骤方块；每块的宽度**按实际字数**算，装不下就省略号收尾
//      （原来固定 N 等分，6 步时每块 26px，而 SVG 的 <text> 不换行 → 互相盖住）；
//   ② 输入／输出各有上限（2 / 3），多的折叠成"…"。
// 文字本身也该读得懂：机械步骤名（step_1_skill_step）现在后端就不往外发了。
function FlowDiagram({
  structure,
  tone,
}: {
  structure: { input: string[]; process: string[]; output: string[] };
  tone: string;
}) {
  const W = 320;
  const mid = W / 2;
  const boxH = 30;
  const arrowGap = 24;
  const boxX = 26;
  const boxW = 268;
  const procH = 56;
  // 每行放得下的方块数：多了就折成"…"
  const inputs = structure.input.slice(0, 2);
  const outputs = structure.output.slice(0, 3);
  const maxSteps = 5;
  const steps =
    structure.process.length > maxSteps
      ? [...structure.process.slice(0, maxSteps - 1), "…"]
      : structure.process.slice(0, maxSteps);
  // 跟 CSS 里 .flowText 的 font-size 必须一致，否则 fit() 算出来的宽度会对不上
  const FS = 9;
  // 装不下就截断加省略号：方块宽度是按字数算的，所以永远塞得下
  const fit = (text: string, widthPx: number, fontSize: number) => {
    const room = Math.max(1, Math.floor(widthPx / fontSize));
    return text.length <= room ? text : `${text.slice(0, room - 1)}…`;
  };
  // 方块宽度**按内容算**：只有一项输入时就给它足够宽，能整句读完
  // （固定 88px 的话，"sourceText：需要提炼的网页或文档正文" 只能显示 "sourceT…"）
  const layout = (items: string[], gap: number) => {
    if (items.length === 0) return [] as Array<{ x: number; w: number; text: string }>;
    const avail = boxW - gap * (items.length - 1);
    const ideal = items.map((t) => Math.min(avail, t.length * FS + 18));
    const sum = ideal.reduce((a, b) => a + b, 0);
    const scale = sum > avail ? avail / sum : 1;
    const widths = ideal.map((w) => Math.max(52, w * scale));
    const total = widths.reduce((a, b) => a + b, 0) + gap * (items.length - 1);
    let cursor = mid - total / 2;
    return items.map((t, index) => {
      const entry = { x: cursor + widths[index] / 2, w: widths[index], text: fit(t, widths[index] - 6, FS) };
      cursor += widths[index] + gap;
      return entry;
    });
  };
  // 一条都没声明时，摆一个短横占位：图的形状还在，但不编内容
  const inBoxes = layout(inputs.length ? inputs : ["—"], 16);
  const outBoxes = layout(outputs.length ? outputs : ["—"], 10);
  const inputsEmpty = inputs.length === 0;
  const outputsEmpty = outputs.length === 0;
  // 竖向排布：没有输入／输出时不留空档，也不画悬空的箭头
  let y = 10;
  const inY = y;
  y += boxH + arrowGap;
  const procY = y;
  y += procH + arrowGap;
  const outY = y;
  y += boxH;
  const H = y + 10;
  const joinY = procY - arrowGap + 8;
  const splitY = procY + procH + 8;
  const chainW = 256;
  const chainGap = 8;
  const elbowDown = (x1: number, y1: number, x2: number, y2: number, r = 7) =>
    Math.abs(x2 - x1) < 1
      ? `M${x1},${y1} L${x2},${y2}`
      : `M${x1},${y1} L${x1},${y2 - r} Q${x1},${y2} ${x1 + (x2 > x1 ? r : -r)},${y2} L${x2},${y2}`;
  const elbowSide = (x1: number, y1: number, x2: number, y2: number, r = 7) =>
    Math.abs(x2 - x1) < 1
      ? `M${x1},${y1} L${x2},${y2}`
      : `M${x1},${y1} L${x2 - (x2 > x1 ? r : -r)},${y1} Q${x2},${y1} ${x2},${y1 + r} L${x2},${y2}`;
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className={styles.flowSvg}
      style={{ ["--tone" as string]: tone }}
      role="img"
      aria-label={`输入：${structure.input.join("、") || "无"}；处理：${structure.process.join("、") || "无"}；输出：${structure.output.join("、") || "无"}`}
    >
      <defs>
        <marker
          id="flowHead"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto"
        >
          <path d="M0 0 L10 5 L0 10 Z" fill={tone} />
        </marker>
      </defs>

      {inBoxes.map((box, index) => (
        <g key={`in-${index}`}>
          <rect x={box.x - box.w / 2} y={inY} width={box.w} height={boxH} rx="10" className={styles.flowBox} />
          <text
            x={box.x}
            y={inY + 20}
            textAnchor="middle"
            className={`${styles.flowText}${inputsEmpty ? ` ${styles.flowTextEmpty}` : ""}`}
          >
            {box.text}
          </text>
          <path d={elbowDown(box.x, inY + boxH, mid, joinY)} className={styles.flowLine} />
        </g>
      ))}
      <line
        x1={mid}
        y1={joinY}
        x2={mid}
        y2={procY - 2}
        stroke={tone}
        strokeWidth="1.4"
        markerEnd="url(#flowHead)"
      />

      {/* 处理：这条 skill 自己的步骤串成一条链 */}
      <rect
        x={boxX}
        y={procY}
        width={boxW}
        height={procH}
        rx="10"
        fill={`color-mix(in srgb, ${tone} 7%, #ffffff)`}
        stroke={`color-mix(in srgb, ${tone} 40%, #ffffff)`}
        className={styles.flowCore}
      />
      {steps.length > 0 ? (
        steps.map((step, index) => {
          const stepW = (chainW - chainGap * (steps.length - 1)) / steps.length;
          const x = boxX + (boxW - chainW) / 2 + index * (stepW + chainGap);
          return (
            <g key={`step-${index}`}>
              <rect
                x={x}
                y={procY + 18}
                width={stepW}
                height="20"
                rx="7"
                fill="#ffffff"
                stroke={`color-mix(in srgb, ${tone} 35%, #ffffff)`}
              />
              <text x={x + stepW / 2} y={procY + 32} textAnchor="middle" className={styles.flowStep}>
                {fit(step, stepW - 2, 8.5)}
              </text>
              {index < steps.length - 1 && (
                <path
                  d={`M${x + stepW + 1} ${procY + 28} L${x + stepW + chainGap - 1} ${procY + 28}`}
                  stroke={tone}
                  strokeWidth="1.2"
                  markerEnd="url(#flowHead)"
                />
              )}
            </g>
          );
        })
      ) : (
        /* 这条 skill 自己没写步骤名 —— 如实留白，不编一句 */
        <text x={mid} y={procY + 32} textAnchor="middle" className={styles.flowStep}>
          这条 skill 的步骤还没有名字
        </text>
      )}

      <line
        x1={mid}
        y1={procY + procH}
        x2={mid}
        y2={splitY}
        stroke={tone}
        strokeWidth="1.4"
      />
      {outBoxes.map((box, index) => (
        <g key={`out-${index}`}>
          <path
            d={elbowSide(mid, splitY, box.x, outY - 3)}
            stroke={tone}
            strokeWidth="1.4"
            fill="none"
            markerEnd="url(#flowHead)"
          />
          <rect x={box.x - box.w / 2} y={outY} width={box.w} height={boxH} rx="10" className={styles.flowBox} />
          <text
            x={box.x}
            y={outY + 20}
            textAnchor="middle"
            className={`${styles.flowText}${outputsEmpty ? ` ${styles.flowTextEmpty}` : ""}`}
          >
            {box.text}
          </text>
        </g>
      ))}
    </svg>
  );
}

// 能力卡详情（第二页自带，替代 legacy 那份）。
// 变化：卡面那三个数字在这屏必须齐全（分数 / 成果 / 等级），并补上"下一步解锁什么"和"这条分数由哪些成果来"。
// 注意：**不写分数怎么算**——分数像游戏评分，用户看得到、算不出来；只有等级门槛这种"目标"才露出来。

const CAN_DO: Record<AbilityType, string[]> = {
  Skill: ["寻找潜在合作人", "发现相关项目", "解释匹配理由"],
  "Mini App": ["提取核心观点", "整理内容结构", "生成复用摘要"],
  Agent: ["筛选合适对象", "判断双方匹配", "准备前置对齐"],
};

const STRUCTURE: Record<
  AbilityType,
  { input: string[]; process: string[]; output: string[] }
> = {
  Skill: {
    input: ["你的目标", "个人记忆"],
    process: ["扫描来源", "条件筛选", "匹配判断"],
    output: ["候选人", "相关机会", "匹配理由"],
  },
  "Mini App": {
    input: ["收藏内容", "目标主题"],
    process: ["内容拆分", "信息归类", "观点提炼"],
    output: ["结构摘要", "观点卡片", "行动建议"],
  },
  Agent: {
    input: ["连接目标", "双方资料"],
    process: ["候选检索", "匹配判断", "风险检查"],
    output: ["候选名单", "匹配理由", "沟通草稿"],
  },
};

// 每档多开一件事（《能力卡组设计》§6.1 的浓缩版，按维度取对应那句话）
const UNLOCK: Record<string, string[]> = {
  洞察: ["只读公开来源", "可加白名单来源", "可长期追踪一个话题", "主动推专题"],
  判断: ["只给选项与结论", "给取舍理由与依据", "可给出取舍建议", "可做风险预演", "可给出定策"],
  表达: ["只出初稿", "可换风格改写", "可定调（统一整篇语气）", "可对外发布内容", "可带观点公开发声"],
  链接: ["只给候选人名单", "备好搭话稿（你自己发）", "可备预沟通稿（需你确认）", "可代你预沟通"],
  交付: ["只在你说时动手", "可跑单步任务", "1 个轻量周期任务", "多任务并行", "端到端交付"],
};

// 等级阶梯：把"每一档解锁什么"摆成一条可以看的梯子。
// 档数受维度上限约束（洞察/链接只到 Lv.4），所以这里只切到上限为止，不再标注"到顶"——那是冗余信息。
function buildLadder(dimension: string, capLevel: number) {
  // ⚠️ 原来这里 `?? UNLOCK["洞察"]`：维度查不到就套"洞察"那套文案。
  // 真 skill 卡的维度是"未标注"，于是详情里显示的是**别的卡**的内容（实测确认过）。
  // 现在查不到就**空着**，由调用方改用这条 skill 自己的真实步骤；绝不再跨维度顶替。
  const unlocks = UNLOCK[dimension] ?? [];
  return unlocks.slice(0, capLevel).map((unlock, index) => ({
    level: index + 1,
    stage: readStage(index + 1),
    unlock,
  }));
}

export function CapabilitySheet({
  card,
  go,
  onClose,
  onOpenEvidence,
  onOpenEvidenceList,
  onCreateTask,
  onUpgrade,
  tasks = [],
}: {
  card: SheetCard;
  go: (screen: Screen) => void;
  onClose: () => void;
  onOpenEvidence: (id: string) => void;
  onOpenEvidenceList: () => void;
  /** 返回结果：整合版里会真的去建一条任务并把契约带上；失败时把原因拿回来给用户看 */
  onCreateTask: (card: SheetCard, goal: string) => Promise<{ ok: boolean; note?: string } | void>;
  onUpgrade: (card: SheetCard) => void;
  /** 应用里真实的任务（用它筛出"这张卡被用来做过的任务"） */
  tasks?: { title: string; source: string; status: string; updatedAt: string }[];
}) {
  const [showRecords, setShowRecords] = useState(false);
  // 点第三格（等级）展开的是"还差多少升级"那块；等级阶梯先收起来，等后端给真实门槛再放回来
  const [showLevel, setShowLevel] = useState(false);
  // 真跑一次：卡片是 skill 的可视化，所以要按"标题 → skill 名"找到后端那条 skill 才能真跑。
  // 映射数据来自 live store 里已经拉好的 `/page2/skills`（不另发请求）。
  const live = usePage2Live();
  const skillName = (live.data.skills ?? []).find((item) => (card.id ? item.name === card.id : item.title === card.title))?.name ?? "";
  // 跑完面板要跟着刷新：面板是用打开时的 card 快照渲染的，所以这里以 live store 里
  // 最新的那份为准（跑完 loadPage2 会把 /capabilities 拉一遍），别让用户看到旧数字。
  const liveCard = (live.data.capabilities ?? []).find((item) => card.id ? item.id === card.id : item.title === card.title);
  const shownScore = liveCard?.score == null ? "待验证" : liveCard.score;
  const shownEvidence = liveCard?.evidence ?? card.evidence;
  const [running, setRunning] = useState(false);
  const [runNote, setRunNote] = useState("");
  // 「用它做一件事」要建真任务，所以得先知道这次要做什么 —— 一句话就够，
  // 剩下的（怎么做、按什么规矩、算不算做完）由能力自身的契约补上。
  const [launching, setLaunching] = useState(false);
  const [launchNote, setLaunchNote] = useState("");

  /** 「用它做一件事」的唯一入口逻辑。失败如实说，不假装任务已经建好。 */
  const startTask = async () => {
    setLaunchNote("");
    setLaunching(true);
    const result = await onCreateTask(card, "");
    setLaunching(false);
    if (result && !result.ok) {
      // 失败如实说（比如那个系统被停用），不假装任务已经建好
      setLaunchNote(result.note || "没能建成任务，稍后再试");
      return;
    }
    setDrafted(true);
  };
  const SHOW_LADDER = false;
  const [drafted, setDrafted] = useState(false);
  const Icon = card.icon;
  const tone = DIMENSION_COLOR[card.dimension] ?? "#6d7680";
  // 档位名与"还差几项成果"**优先用后端给的**（`/capabilities` 里有 stage / gap / gapLabel）。
  // 前端这套本地表只当离线兜底：两边规则原来各写一份，改一边忘一边就会开始显示错数字。
  const stage = liveCard?.stage || readStage(card.level);
  const gap = liveCard?.gap ?? null;
  const gapLabel = liveCard?.gapLabel || "依据真实使用和验收结果成长";
  const capLevel = readDimension(card.dimension)?.capLevel ?? 5;
  // 阶梯的**门槛与档位名以后端为准**（`/capabilities` 的 ladder）；本地那份只提供每档的"多给你什么"文案，
  // 以及离线时的兜底。这样门槛表就只有后端一份权威，不会再出现两边改不同步。
  const localLadder = buildLadder(card.dimension, capLevel);
  const ladder: Array<{ level: number; stage: string; unlock: string; gate?: number }> =
    liveCard?.ladder?.length
    ? localLadder.map((row) => {
        const rung = liveCard.ladder?.find((item) => item.level === row.level);
        return rung ? { ...row, stage: rung.stage, gate: rung.gate } : row;
      })
    : localLadder;
  const unlocks = UNLOCK[card.dimension] ?? [];
  const unlocked = unlocks.slice(0, card.level);
  const nextUnlock = unlocks[card.level];
  // 「它能替你做」的来源顺序：**这条 skill 自己的真实步骤** → 类型通用的那套（只有早期演示卡才用得上）。
  // 原来直接按 card.type 取通用那套，导致真 skill 卡显示的是"机会检索"的文案（实测确认的 bug）。
  const liveSkill = (live.data.skills ?? []).find((item) => card.id ? item.name === card.id : item.title === card.title);
  const skillSteps = liveSkill?.steps ?? [];
  // ⚠️ 「它能替你做」的兜底只给**演示卡**用。
  // 真 skill 卡（liveSkill 存在）就算自己没写步骤名，也**绝不能**退回类型通用那套 ——
  // 那会让"文档要点摘要"这张卡显示"寻找潜在合作人 / 解释匹配理由"（机会检索的文案），
  // 实测确认过的 old bug，回归过一次，这里再加一道闸。
  // 后端会用 LLM 从这条 skill 的材料里提炼「它能替你做」的人话，优先用它。
  const canDo = liveSkill
    ? (liveSkill.canDo?.length ? liveSkill.canDo : skillSteps)
    : (CAN_DO[card.type] ?? []);
  const own = evidenceRecords.filter((record) =>
    record.impacts.some((impact) => impact.card === card.title),
  );
  const ownTasks = tasks.filter((task) => (task.source ?? "").includes(card.title));
  // 流程图同样只认"这条卡自己的东西"：
  //   处理 → 这条 skill 的真实步骤（后端已把 step_N_skill_step 这种机械名换成"步骤 N"）
  //   输入 → 后端从 workflow.json 的 parameters（退回 SKILL.md 的 Inputs 小节）给的真实输入
  //   产出 → 后端从 SKILL.md 的 Verification 小节给的验收标准
  // 这三样都没有时才退回类型通用那套（只有早期演示卡会走到）。**绝不拿别的卡那套顶上。**
  const structure =
    skillSteps.length || liveSkill?.inputs?.length || liveSkill?.outputs?.length
      ? {
          input: liveSkill?.inputs ?? [],
          process: skillSteps,
          output: liveSkill?.outputs ?? [],
        }
      : STRUCTURE[card.type];

  return (
    <RootPortal>
      <button
        type="button"
        className="v278-sheet-backdrop v279-capability-backdrop"
        aria-label="关闭能力详情"
        onClick={onClose}
      />
      <section
        className="v279-capability-sheet"
        role="dialog"
        aria-modal="true"
        aria-label={`${card.title}能力详情`}
      >
        <i className="v278-sheet-handle" />
        <header className="v279-capability-head">
          <span>
            <Icon size={26} />
          </span>
          <div>
            <span>
              <h2>{displayTitle(card.title,'')}</h2>
              <em>{card.type}</em>
            </span>
            <p>{card.copy}</p>
          </div>
          <button
            type="button"
            className="v277-icon-button"
            aria-label="关闭"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </header>

        <div className={styles.sheetBody}>
          {/* ① 三格数字：能力分 / 成果（量词贴着数字） / 等级 */}
          <div className={styles.statRow}>
            <span>
              <b>{shownScore}</b>{liveCard?.score == null ? "" : "能力分"}
            </span>
            <span>
              <b>
                {shownEvidence}
                <em className={styles.statUnit}>项</em>
              </b>
              成果
            </span>
            {/* 第三格是入口：点一下展开"还差多少能升级"（放卡里、不放卡面，避免误触） */}
            <button
              type="button"
              className={styles.statCell}
              onClick={() => setShowLevel((open) => !open)}
              aria-expanded={showLevel}
              aria-label={`当前 Lv.${card.level} ${stage}，点开看成长说明`}
            >
              <b>Lv.{card.level}</b>
              <span className={styles.statCaption}>
                {stage}
                <ChevronRight
                  size={11}
                  className={showLevel ? styles.statCellOpen : styles.statCellHint}
                />
              </span>
            </button>
          </div>

          {drafted && (
            <p className={styles.draftNote}>
              已带着工具说明进入对话 ·{" "}
              <button
                type="button"
                className={styles.linkBtn}
                onClick={() => {
                  onClose();
                  go({ name: "tasks" });
                }}
              >
                  查看任务
              </button>
            </p>
          )}

          {showLevel && SHOW_LADDER && (
            <section className={styles.block}>
              <h3>等级阶梯</h3>
              <ol className={styles.ladder} style={{ ["--tone" as string]: tone }}>
                {ladder.map((rung) => {
                  const reached = rung.level <= card.level;
                  const current = rung.level === card.level;
                  const gate = rung.gate ?? LEVEL_EVIDENCE_GATE[rung.level];
                  const need = Math.max(0, gate - card.evidence);
                  return (
                    <li
                      key={rung.level}
                      className={`${styles.rung}${current ? ` ${styles.rungNow}` : ""}${
                        reached ? "" : ` ${styles.rungLocked}`
                      }`}
                    >
                      <span className={styles.rungNode}>
                        {/* 当前档用白点（"我在这"），已过档用 ✓，未到档用锁 */}
                        {current ? (
                          <span className={styles.rungDot} />
                        ) : reached ? (
                          <Check size={14} />
                        ) : (
                          <Lock size={11} />
                        )}
                      </span>
                      <span className={styles.rungBody}>
                        <b>
                          Lv.{rung.level} {rung.stage}
                        </b>
                        <small>{rung.unlock}</small>
                        {!reached && (
                          <em className={styles.rungNeed}>
                            {rung.level === card.level + 1
                              ? `还差 ${need} 项成果`
                              : `共需 ${gate} 项成果`}
                          </em>
                        )}
                      </span>
                    </li>
                  );
                })}
              </ol>
            </section>
          )}

          {/* 点等级这一格展开的就是这块：还差多少能升级、升上去多给你什么、以及"去哪攒" */}
          {showLevel && (
            <div className={styles.nextBox}>
              {gap && <span className={styles.nextBar}><span style={{ width: `${Math.round((gap.have / gap.goal) * 100)}%`, background: tone }} /></span>}
              <b>{gapLabel}</b>
              {gap && <small className={styles.nextMeta}>
                <span>
                  <Check size={13} />
                  现在：{unlocked[unlocked.length - 1]}
                </span>
                {nextUnlock && (
                  <span className={styles.nextLocked}>
                    <Lock size={13} />
                    升到 Lv.{card.level + 1} 多给你：{nextUnlock}
                  </span>
                )}
              </small>}
              {/* 门槛够了就能升；不够就直接给一条"去哪攒"的路 */}
              {gap && gap.need === 0 ? (
                <button
                  type="button"
                  className={styles.nextAction}
                  onClick={() => onUpgrade(card)}
                >
                  <Sparkles size={14} />
                  可以升级了：升到 Lv.{card.level + 1} {readStage(card.level + 1)}
                </button>
              ) : (
                <button
                  type="button"
                  className={styles.nextAction}
                  disabled={launching}
                  onClick={startTask}
                >
                  <ArrowUpRight size={14} />
                  去做一件事，把还差的成果攒上
                </button>
              )}
            </div>
          )}

          {/* 真跑一次：跑的是后端那条真 skill——模型逐步产出、自动落一条成果、卡片分数跟着变。
              以前只有"去做一件事"（进对话），这条真跑的入口是补上的。 */}
          {/* 真跑一次：**预留功能，默认不展示**（产品说现阶段只做闭环、不加新入口）。
              代码留着，把 SHOW_RESERVED_ACTIONS 打开就会出来。
              只有 skill 类型的卡才有对应的后端 skill。**匹配不上要写清原因并禁用**，
              不能像之前那样悄悄不显示（用户会以为"这张卡就是不能跑"，其实是我们没接）。 */}
          {SHOW_RESERVED_ACTIONS ? (
          <div className={styles.block}>
            {skillName ? (
              <button
                type="button"
                className={styles.nextAction}
                disabled={running}
                onClick={async () => {
                  if (running) return;          // 防连点：进行中一律不重复提交
                  setRunning(true);
                  setRunNote("");
                  const result = await runSkill(skillName, "试跑：用这张卡做一件小事");
                  setRunNote(
                    result?.ran
                      ? `跑通了一次，分数已更新为 ${result.cardScore ?? "?"}`
                      : `没跑通：${result?.reason ?? "后端没返回原因"}`,
                  );
                  setRunning(false);
                }}
              >
                <Sparkles size={14} />
                {running ? "正在真跑（逐步调模型）…" : "真跑一次"}
              </button>
            ) : (
              <button type="button" className={styles.nextAction} disabled>
                <Sparkles size={14} />
                这类卡还不是 skill，暂时不能真跑
              </button>
            )}
            {runNote ? <p className={styles.draftNote}>{runNote}</p> : null}
          </div>
          ) : null}

          {showRecords ? (
            <section className={styles.block}>
              <h3>
                使用记录
                <button
                  type="button"
                  className={styles.linkBtn}
                  onClick={() => setShowRecords(false)}
                >
                  返回结构
                </button>
              </h3>
              {/* 使用记录 = 真的用它做过的任务（从应用状态里筛，不再写死三条） */}
              {ownTasks.length === 0 ? (
                <>
                  <p className={styles.empty}>
                    还没有用它做过任务。用它做一件事，就会出现在这里。
                  </p>
                  <button
                    type="button"
                    className={styles.nextAction}
                    disabled={launching}
                    onClick={startTask}
                  >
                    <ArrowUpRight size={14} />
                    用它做一件事
                  </button>
                  {launchNote ? <p className={styles.draftNote}>{launchNote}</p> : null}
                </>
              ) : (
                <div className={styles.timeline}>
                  {ownTasks.map((task) => (
                    <div key={task.title} className={styles.recordRow}>
                      <b>{displayTitle(task.title,'')}</b>
                      <small>
                        {task.status} · {task.updatedAt}
                      </small>
                    </div>
                  ))}
                </div>
              )}
            </section>
          ) : (
            <>
              {/* 这条 skill 自己没写步骤名时（canDo 为空）整块不画：
                  留一个空标题比不画更让人误会。"使用说明"里会说明原因。 */}
              {canDo.length > 0 && (
                <section className={styles.block}>
                  <h3>它能替你做</h3>
                  <div className={styles.chips}>
                    {canDo.map((item) => (
                      <span key={item}>
                        <Check size={14} />
                        {item}
                      </span>
                    ))}
                  </div>
                </section>
              )}
              <section className={styles.block}>
                <h3>使用说明</h3>
                {/* 流程图：起止（圆角）→ 处理（矩形，内含三步链）→ 起止（圆角） */}
                {structure.input.length || structure.output.length
                  ? <FlowDiagram structure={structure} tone={tone} />
                  : <p className={styles.note}>{liveSkill?.summary || card.copy}</p>}
              </section>
            </>
          )}

          {/* ③ 来历：要核对才看的第三层。卡里只留最近一条，全部在成果页 */}
          <section className={styles.block}>
            <h3>
              相关成果记录
              <button
                type="button"
                className={styles.linkBtn}
                onClick={() => onOpenEvidenceList()}
              >
                查看全部（{own.length} 项）
              </button>
            </h3>
            {own.length === 0 ? (
              <p className={styles.empty}>
                还没有成果，第一次任务验收后就会出现
              </p>
            ) : (
              <div className={styles.timeline}>
                {own.slice(0, 1).map((record) => (
                  <button
                    type="button"
                    key={record.id}
                    className={styles.evidenceRow}
                    onClick={() => onOpenEvidence(record.id)}
                  >
                    <span className={styles.evidenceTime}>
                      {record.day} {record.time}
                    </span>
                    <b>{displayTitle(record.title,'')}</b>
                    <small>
                      {record.source.label} · {record.weightLabel}
                    </small>
                    <ChevronRight size={16} />
                  </button>
                ))}
              </div>
            )}
            <p className={styles.trace}>
              <ShieldCheck size={14} />
              分数只由完成并验收过的结果产生，不使用次数不参与
            </p>
          </section>
        </div>

        {launchNote ? <p className={styles.draftNote}>{launchNote}</p> : null}
        {/* 这一栏就是原来的两列：左「使用记录」，右「用它做一件事」（黑色那个）。
            ⚠️ 别在这栏里再加元素：它是 70px 高、两列的固定网格，
            多一个子项就会换行、被裁在栏外（之前塞过"这次要做什么"，就是这么顶出屏幕的）。 */}
        <footer className="v279-capability-actions">
          <button type="button" onClick={() => setShowRecords(true)}>
            <History size={19} />
            使用记录
          </button>
          <button type="button" disabled={launching} onClick={startTask}>
            用它做一件事
          </button>
          </footer>
      </section>
    </RootPortal>
  );
}
