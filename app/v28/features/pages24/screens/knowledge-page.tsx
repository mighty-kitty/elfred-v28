"use client";
import {displayTitle} from "../../../core/display-labels";

import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type Dispatch,
  type SetStateAction,
} from "react";
import {
  CheckCircle2,
  ChevronRight,
  Compass,
  FileText,
  Layers3,
  MessageCircle,
  PenLine,
  Plus,
  Target,
  X,
  Sparkles,
} from "lucide-react";
import type { V277State } from "../../../../v27-7-state";
import type { Screen } from "../../../core/screen";
import {
} from "../../../legacy/legacy-ui";
import { CapabilitySheet, type SheetCard } from "../parts/capability-sheet";
import { UnderstandingSheet } from "../parts/understanding-sheet";
import { LibraryHeader } from "../parts/library-header";
import {
  DIMENSION_COLOR,
  IMPORT_SOURCES,
  abilityCardSamples,
  abilityInsight,
  documents,
  livePendingMaterials,
  readCardAdjustment,
  readStage,
  todayEvidence,
  type EvidenceKind,
} from "../data/knowledge-data";
import {
  addPendingMaterial,
  readPage2,
  resolvePendingMaterial,
  setPendingSkill,
  setCardLevel,
  takePendingCard,
} from "../api/page2-store";
import { QUESTIONNAIRE_AVAILABLE, PAGE2_API, importFile, importLink, resolveMaterial, usePage2Live } from "../api/page2-api";
import { launchWithSkill } from "../api/skill-launch";
import styles from "../styles/knowledge.module.css";

/* 雷达图与趋势线的几何：都从数据算，不写死坐标。
   雷达外圈沿用原图的五边形（顶点固定），每一维的值决定顶点落在"中心 → 外圈顶点"的第几成。 */
const RADAR_CENTER = { x: 90, y: 78.4 };
const RADAR_AXES = [
  { vertex: { x: 90, y: 12 }, text: { x: 90, y: 9 } },
  { vertex: { x: 164, y: 58 }, text: { x: 151, y: 59 } },
  { vertex: { x: 136, y: 132 }, text: { x: 127, y: 139 } },
  { vertex: { x: 44, y: 132 }, text: { x: 18, y: 139 } },
  { vertex: { x: 16, y: 58 }, text: { x: 0, y: 58 } },
];
const RADAR_RINGS = [1, 0.72, 0.47];

function ringPoints(scale: number) {
  return RADAR_AXES.map(({ vertex }) => {
    const x = RADAR_CENTER.x + (vertex.x - RADAR_CENTER.x) * scale;
    const y = RADAR_CENTER.y + (vertex.y - RADAR_CENTER.y) * scale;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

function valuePoints(values: (number | null)[]) {
  return values
    .map((value, index) => {
      if (value === null) return null;
      const { vertex } = RADAR_AXES[index];
      const scale = Math.min(100, Math.max(0, value)) / 100;
      const x = RADAR_CENTER.x + (vertex.x - RADAR_CENTER.x) * scale;
      const y = RADAR_CENTER.y + (vertex.y - RADAR_CENTER.y) * scale;
      return { x, y };
    })
    .filter(Boolean) as { x: number; y: number }[];
}

const EVIDENCE_ICON: Record<EvidenceKind, typeof FileText> = {
  outcome: CheckCircle2,
  context: FileText,
};

// 趋势线：把一串数值铺进图里，再用 Catmull-Rom 转成平滑曲线（点变了线就变）。
function trendGeometry(points: number[]) {
  if (points.length < 2) return null;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = Math.max(1, max - min);
  const nodes = points.map((value, index) => ({
    x: 12 + (index * (168 - 12)) / (points.length - 1),
    y: 124 - ((value - min) / span) * 100,
  }));
  let line = `M${nodes[0].x.toFixed(1)} ${nodes[0].y.toFixed(1)}`;
  for (let index = 0; index < nodes.length - 1; index += 1) {
    const p0 = nodes[index - 1] ?? nodes[index];
    const p1 = nodes[index];
    const p2 = nodes[index + 1];
    const p3 = nodes[index + 2] ?? p2;
    const c1 = { x: p1.x + (p2.x - p0.x) / 6, y: p1.y + (p2.y - p0.y) / 6 };
    const c2 = { x: p2.x - (p3.x - p1.x) / 6, y: p2.y - (p3.y - p1.y) / 6 };
    line += ` C${c1.x.toFixed(1)} ${c1.y.toFixed(1)} ${c2.x.toFixed(1)} ${c2.y.toFixed(1)} ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
  }
  return { line, area: `${line} L168 124 L12 124Z`, last: nodes[nodes.length - 1] };
}

export function KnowledgePage({
  state,
  go,
  setState,
  runtime,
}: {
  state: V277State;
  go: (screen: Screen) => void;
  setState: Dispatch<SetStateAction<V277State>>;
  /** 整合版里由 app-shell 传进来的那套 runtime（我这边单独跑时没有，传 undefined 即可）。
   *  只用来把「用它做一件事」的契约写进对话草稿 —— 不读它的别的数据。 */
  runtime?: unknown;
}) {
  const [filter, setFilter] = useState("全部");
  const [storeVersion, setStoreVersion] = useState(0);
  const [insightIndex, setInsightIndex] = useState(0);
  const [alignmentOpen, setAlignmentOpen] = useState(false);
  // 空态预览开关：网址后面加 ?empty=1 就切到"新用户第一次进来"的样子，
  // 平时（演示用）还是满数据。接后端后这个开关只留在验收时用。
  const [urlEmpty, setUrlEmpty] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [importHint, setImportHint] = useState<string | null>(null);
  useEffect(() => {
    setUrlEmpty(new URLSearchParams(window.location.search).has("empty"));
  }, []);
  // 空态是"真没数据的样子"，不是靠开关装出来的：
  //   · 还没拿到数据（loading）就先按空态画 —— 免得先闪三张假卡再消失；
  //   · 后端回来了但没有卡也没有成果 → 就是空态；主页那边一用起来，这里自然长出数据；
  //   · 后端够不着（offline）→ 用演示数据，不是空态；
  //   · ?empty=1 保留为手动预览开关。
  const live = usePage2Live();
  const liveEmpty =
    live.status === "loading" ||
    (live.status === "ready" &&
      (live.data.capabilities?.length ?? 0) === 0 &&
      // 有了真 skill（Skill Foundry 的产物）就不是空态——能力卡组显示的就是它们
      (live.data.skills?.length ?? 0) === 0 &&
      (live.data.evidence?.length ?? 0) === 0);
  // 【三个模块各判各的】——之前用一个总开关，导致"有了一张能力卡"之后，
  // 知识库和洞察跟着变成非空态（显示全未知的雷达 + 一句"今天还没有新成果"）。这是错的：
  //   · 能力卡组：有没有卡
  //   · 知识库：今天有没有成果
  //   · 能力洞察：做没做过（轻量测试）
  const cardsEmpty = urlEmpty || liveEmpty;
  // 哪些接口这次没拿到（只有"部分失败"时才用得上：整页 offline 是另一种提示）
  const missingParts = [
    ["卡片", live.data.capabilities],
    ["成果", live.data.evidence],
    ["洞察", live.data.insight],
    ["理解度", live.data.alignment],
    ["记忆", live.data.memory],
  ]
    .filter(([, value]) => value === null)
    .map(([label]) => String(label));
  const evidenceEmpty = todayEvidence.length === 0;
  const insightEmpty =
    abilityInsight.axes.every((axis) => axis.value === null) && abilityInsight.composite === null;
  // 全新用户（三块都空）才用"整页空态"的口径（页头 0%、理解度弹层也按空态显示）
  const emptyMode = urlEmpty || (cardsEmpty && evidenceEmpty && insightEmpty);
  const [selectedCapability, setSelectedCapability] = useState<SheetCard | null>(
    null,
  );
  const insightSwipe = useRef({ y: 0, moved: false });
  const store = readPage2();
  const fileInputRef = useRef<HTMLInputElement>(null);
  // 待确认素材：后端在跑就用后端那份（真素材、真解析结果），够不着才用本地兜底
  const pendingList = livePendingMaterials ?? store.pendingMaterials;

  const takeFile = async (file: File | null) => {
    if (!file) return;
    const result = await importFile(file);
    setImportHint(result ? `${result.material.title}：已保存到文档` : "仅支持 UTF-8 的 txt、md、csv、json 文件");
    setStoreVersion((version) => version + 1);
  };

  const takeLink = async () => {
    const url = window.prompt("粘贴链接（http:// 或 https://）");
    if (!url) return;
    const result = await importLink(url);
    setImportHint(result ? `${result.title}：链接已保存，正文尚未抓取` : "链接保存失败，请检查地址");
    setStoreVersion((version) => version + 1);
  };

  void storeVersion;
  // 固化出来的卡排在最前（刚建的能立刻看见），其余卡按成果裁定调整分数与成果数
  const cards: (SheetCard & {owner: string;notRunYet?:boolean})[] = [
    // 知识固化出来的卡：补上"归属 Agent"和图标，和内置的三张卡长得一样
    ...store.fixedCards.map((card) => ({
      ...card,
      // 手动升级过的话，以本地记录为准
      level: store.levelOverride[card.title] ?? card.level,
      owner: "探索",
      notRunYet: false,
      icon: Sparkles,
    })),
    ...abilityCardSamples.map((sample) => {
      const { scoreDelta, evidenceDelta } = readCardAdjustment(
        sample.title,
        store.verdicts,
      );
      return {
        ...sample,
        score: sample.score + scoreDelta,
        evidence: sample.evidence + evidenceDelta,
        level: store.levelOverride[sample.title] ?? sample.level,
      };
    }),
  ];
  const visibleCards =
    filter === "全部" ? cards : cards.filter((card) => card.type === filter);

  // 从成果页点卡名过来：进来自动打开那张卡（读一次就清掉，避免下次又弹）
  useEffect(() => {
    const pending = takePendingCard();
    if (!pending) return;
    const target = cards.find((card) => card.id === pending) || cards.find((card) => card.title === pending);
    if (target) setSelectedCapability(target);
    // 只在挂载时跑一次，cards 每次渲染都是新数组，不能进依赖
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // 空态（新用户）：三个模块各给各的空态，谁也不合并——
  // 空态下这一整块换成了"轻量测试"入口，五维卡不渲染，所以这里不用再为空态造数据；
  // 趋势照常算，非空态用得上。
  const radarPoints = valuePoints(abilityInsight.axes.map((axis) => axis.value));
  // 五维怎么画（用户定过的口径）：**雷达只有一种画法**。
  // 测试给的起点就是这条曲线本身的一部分，不另画虚线、不标灰、不写"不计入综合分"——
  // 只留一句话说清"现在是起点，之后按真实表现更新（也会回落）"。
  // `updatedLabels` = 已经被真实成果改动过的维度（够 3 条 → evidence，1~2 条 → growing）。
  const updatedLabels = abilityInsight.axes
    .filter((axis) => axis.source === "evidence" || axis.source === "growing")
    .map((axis) => axis.label);
  const trend = abilityInsight.trend ? trendGeometry(abilityInsight.trend.points) : null;
  const trendDelta = abilityInsight.trend
    ? abilityInsight.trend.points[abilityInsight.trend.points.length - 1] -
      abilityInsight.trend.points[0]
    : 0;
  const finishInsightSwipe = (clientY: number) => {
    const distance = clientY - insightSwipe.current.y;
    insightSwipe.current.moved = Math.abs(distance) > 34;
    if (insightSwipe.current.moved) setInsightIndex(distance < 0 ? 1 : 0);
  };
  return (
    <main
      className={`v277-page v277-library-page v277-knowledge-overview${
        insightEmpty ? ` ${styles.isEmpty}` : ""
      }`}
    >
      <LibraryHeader
        active="knowledge"
        go={go}
        onContext={() => setAlignmentOpen(true)}
        /* 空态（新用户）：理解度从零开始（不是老用户的 86%） */
        alignment={emptyMode ? 0 : undefined}
      />
      <div
        className="v277-library-scroll"
      >
        <section className="v277-ability-head">
          {/* 两个货架：能力（能干活）/ 知识（能查阅）。素材不给位置，只在导入与"来源"里露头 */}
          {/* 原来这里是「能力／知识」两个货架。现在合并成一个：
              知识不再是"另一类资产"，而是能力卡的"待验证"状态（见下面的 verifyCard）。 */}
        </section>

          <>
        {/* 待确认收件箱：有东西才出现，没有就整条不占高度 */}
        {store.pendingMaterials.length > 0 && (
          <div className={styles.rowBar}>
            <button
              type="button"
              className={styles.inboxBar}
              onClick={() => setImportOpen(true)}
            >
              <b>待确认 {store.pendingMaterials.length}</b>
              <span>· 点头之后才会变成能力卡</span>
              <ChevronRight size={16} />
            </button>
          </div>
        )}
        {/* 工具行：左边一块"导入 · 文档"（导入和文档是同一件事的两端），
            右边恢复成原来的两个圆形按钮（创建工具 / 我的工具）。
            这样"导入"和工具仍在同一族、同一行，但"我的工具"回到它原来的样子。 */}
        {/* 卡组标题行：图标 + "能力卡组"，右边两个圆钮；筛选条另起一行（和图 1 一致） */}
        <div className={styles.cardsHead}>
          <h2>
            <Layers3 size={19} />
            能力卡组
            {/* 降级要显式：整页够不着、或者**部分接口没拿到**（真数据与演示数据混着），都必须说出来 */}
            {live.status === "offline" ? (
              <span
                title={`没连上后端 ${PAGE2_API}，下面这些是演示数据`}
                style={{
                  marginLeft: 6,
                  padding: "1px 8px",
                  border: "1px solid #f0c36d",
                  borderRadius: 999,
                  background: "#fff8e6",
                  color: "#8a6100",
                  fontSize: 11,
                  fontWeight: 400,
                }}
              >
                演示数据
              </span>
            ) : live.status === "ready" && missingParts.length > 0 ? (
              <span
                title={`这些接口这次没拿到：${missingParts.join(" / ")}（对应的地方在用兜底数据）`}
                style={{
                  marginLeft: 6,
                  padding: "1px 8px",
                  border: "1px solid #f0c36d",
                  borderRadius: 999,
                  background: "#fff8e6",
                  color: "#8a6100",
                  fontSize: 11,
                  fontWeight: 400,
                }}
              >
                部分数据没拿到
              </span>
            ) : null}
          </h2>
          <span className={styles.toolRound}>
            <button
              type="button"
              aria-label="创建工具"
              onClick={() => go({ name: "create-tool" })}
            >
              <PenLine size={18} />
            </button>
            <button
              type="button"
              aria-label="查看我的工具"
              onClick={() => go({ name: "my-tools" })}
            >
              <ChevronRight size={19} />
            </button>
          </span>
        </div>
        <div className={styles.filterRow}>
        <div className="v277-ability-filters" aria-label="能力类型">
          {["全部", "Skill", "Mini App", "Agent"].map((name) => (
            <button
              type="button"
              key={name}
              className={filter === name ? "active" : ""}
              onClick={() => setFilter(name)}
            >
              {name}
            </button>
          ))}
        </div>
        </div>
        {cardsEmpty ? (
          /* 空态就放"一张和真卡同尺寸的引导卡"：它就是卡轨里的第一张卡，
             卡片长出来时位置不会跳；整张卡可点，不再在大虚线块里塞一个黑按钮。 */
          /* 空态外观照图 2：圆图标 + 标题 + 一行说明 + 黑色胶囊按钮 */
          <section className={styles.emptyBlock}>
            <i className={styles.emptyBlockIcon}>
              {/* 图标是对话气泡：这一屏唯一的动作是"去和它说"，不是"新建一份" */}
              <MessageCircle size={26} />
            </i>
            <b>Elfred 还没替你干过活</b>
            {/* 用户视角：不是"创建一张卡"，而是"让 Agent 替你干一件事"——干过一次、干成了，
                才会沉淀成一张能力卡（卡是资产，不是入口）。「创建工具」那一屏是首页
                「我的工具」的创建入口，语义不对，不走它。 */}
            <p>跟它说一句你想让它做的事，它做过一次，就会变成你的能力</p>
            <button type="button" onClick={() => go({ name: "chat", id: "elfred" })}>
              去和 Elfred 说
            </button>
          </section>
        ) : visibleCards.length === 0 ? (
          /* 有卡、只是这个筛选下没有（比如一张 Mini App 都没有）：
             原来这里直接是一块空白，看着像坏了。 */
          <section className={styles.emptyBlock}>
            <i className={styles.emptyBlockIcon}>
              <Layers3 size={26} />
            </i>
            <b>还没有这一类能力卡</b>
            <p>换个分类看看，或者让 Agent 替你做一件事，沉淀一张</p>
            <button type="button" onClick={() => setFilter("全部")}>
              看全部
            </button>
          </section>
        ) : (
        <section className={`v277-ability-cards ${styles.cards}`}>
          {visibleCards.map(
            (
              { id, type, dimension, title, copy, score, evidence, level, notRunYet, icon: Icon },
              index,
            ) => {
              const stage = readStage(level);
              const gapLabel = "依据真实成果逐步成长";
              return (
              <button
                type="button"
                key={id||title}
                style={
                  {
                    "--dim": DIMENSION_COLOR[dimension] ?? "#6d7680",
                    "--i": index,
                  } as CSSProperties
                }
                aria-label={`${title}：${dimension}维度，${notRunYet ? "尚未评分" : `Lv.${level} ${stage}`}，${gapLabel}`}
                onClick={() =>
                  setSelectedCapability({
                    id,
                    type,
                    dimension,
                    title,
                    copy,
                    score,
                    evidence,
                    level,
                    icon: Icon,
                  })
                }
              >
                <span className={styles.cardHead}>
                  <span className={styles.cardDim}>
                    <i aria-hidden="true" />
                    {dimension}
                  </span>
                  <span className={styles.cardLevel}>
                    {/* 还没跑过的真 skill：不显示假等级，写清状态 */}
                    {notRunYet ? (evidence ? "待评估" : "尚无成果") : `Lv.${level} · ${stage}`}
                  </span>
                </span>
                <i className={`v277-ability-visual visual-${index}`}>
                  <Icon size={25} />
                </i>
                <b>{title}</b>
                {/* 标题下面这行小字：一眼看出这张卡是干什么的（样式按元素选择器放在 CSS 里） */}
                <p>{copy}</p>
                <footer>
                  <strong>
                    {notRunYet ? (
                      <em>{evidence ? "待评估" : "证据不足"}</em>
                    ) : (
                      <>
                        {score}
                        <em>能力分</em>
                      </>
                    )}
                  </strong>
                  <span>{evidence} 项成果</span>
                </footer>
                <span className={styles.cardGap}>
                  <span className={styles.cardGapText}>{gapLabel}</span>
                </span>
              </button>
              );
            },
          )}
          {store.knowledgeDrafts.map((draft) => (
            <button
              type="button"
              key={draft.id}
              className={styles.verifyCard}
              onClick={() => setImportHint(`刚导入的「${draft.title}」还没跑过`)}
            >
              <span className={styles.cardHead}>
                <span className={styles.cardDim}>
                  <i aria-hidden="true" />
                  待验证
                </span>
                <span className={styles.cardLevel}>{draft.source}</span>
              </span>
              <i className={styles.knowledgeVisual}>
                <FileText size={24} />
              </i>
              <b>{displayTitle(draft.title,'')}</b>
              <p className={styles.knowledgePurpose}>{draft.purpose}</p>
              <span className={styles.knowledgeStrip}>跑出第一条成果就转正</span>
            </button>
          ))}
        </section>
        )}
          </>
        <section className="v277-progress-section">
          <div className="v277-section-title">
            <h2>
              <Sparkles size={19} />
              知识库
            </h2>
            <span className={styles.inlineActions}>
              {/* 导入放在知识库里：它俩是同一件事的两端（塞进来 / 存着的） */}
              <button
                type="button"
                className={styles.inlinePlus}
                aria-label="导入内容"
                onClick={() => setImportOpen(true)}
              >
                <Plus size={16} />
              </button>
              <button
                type="button"
                onClick={() => setImportOpen(true)}
              >
                查看资料
                <ChevronRight size={16} />
              </button>
            </span>
          </div>
          <div className="v277-progress-cards">
            {documents.slice(0, 2).map((doc) => (
              <button type="button" key={doc.id} onClick={() => go({ name: "knowledge-detail", id: doc.id })}>
                <span><FileText size={19} /></span>
                <b>{doc.name}</b>
                <small>{doc.excerpt || "已保存的资料"}</small>
              </button>
            ))}
            {/* 空态那块虚线提示已经把这句话说完了，这里不再重复第二遍（重复会把洞察那块挤到底栏下面） */}
            {!evidenceEmpty && todayEvidence.map((item) => {
              const Icon = EVIDENCE_ICON[item.kind] ?? CheckCircle2;
              return (
                <button
                  type="button"
                  key={item.id}
                  onClick={() => go({ name: "evidence-detail", id: item.id })}
                >
                  <span>
                    <Icon size={19} />
                  </span>
                  <b>{displayTitle(item.title,'')}</b>
                  <small>{item.note}</small>
                  <strong>{item.delta}</strong>
                </button>
              );
            })}
          </div>
          {evidenceEmpty && (
            <section className={styles.emptyEvidence}>
              <CheckCircle2 size={20} />
              <span>{documents.length ? `已保存 ${documents.length} 份资料；今天还没有已验收成果。` : "今天还没有沉淀。做完一件并确认结果，它就会出现在这里。"}</span>
            </section>
          )}
        </section>
        <section className="v277-cave-section">
          <div className="v277-section-title">
            <h2>
              <Compass size={19} />
              能力洞察
            </h2>
          </div>
          {/* 空态外观照图 3：不给全 0 的五维图，改成"轻量测试"的入口（问卷内容之后再定） */}
          {insightEmpty && (
            <section className={`${styles.emptyBlock} ${styles.emptyBlockTall}`}>
              <i className={styles.emptyBlockIcon}>
                <Target size={26} />
              </i>
              <b>还没有能力洞察</b>
              <p>{QUESTIONNAIRE_AVAILABLE ? "完成一次轻量测试，生成你的初始能力画像" : "轻量测试服务尚未接通，已验收成果仍会保留"}</p>
              {/* 以前这里跳到"能力画像"（对新人是一张全未知的雷达）。现在去填那份轻量测试：
                  答完就有一张**起点图**（数值低），之后按真实成果慢慢更新。 */}
              {QUESTIONNAIRE_AVAILABLE && <button type="button" onClick={() => go({ name: "questionnaire" })}>
                开始测试
              </button>}
              {QUESTIONNAIRE_AVAILABLE && <em className={styles.emptyNote}>答完就有一张起点图；之后按真实结果慢慢更新</em>}
            </section>
          )}
          <div
            className="v278-insight-stack v279-insight-stack"
            data-index={insightIndex}
            aria-live="polite"
            onPointerDown={(event) => {
              insightSwipe.current = { y: event.clientY, moved: false };
            }}
            onPointerMove={(event) => {
              const distance = event.clientY - insightSwipe.current.y;
              if (Math.abs(distance) > 34) {
                insightSwipe.current.moved = true;
                setInsightIndex(distance < 0 ? 1 : 0);
              }
            }}
            onPointerUp={(event) => finishInsightSwipe(event.clientY)}
            onPointerCancel={() => {
              insightSwipe.current.moved = false;
            }}
          >
            <button
              type="button"
              className={`v279-insight-card radar ${insightIndex === 0 ? "is-front" : "is-back"}`}
              onClick={() => {
                if (insightSwipe.current.moved) {
                  insightSwipe.current.moved = false;
                  return;
                }
                go({ name: "ability-profile" });
              }}
            >
        <header>
          <h3>
            <Compass size={17} />
            能力雷达
          </h3>
          <span>
            点击查看详情
            <ChevronRight size={16} />
          </span>
        </header>
        {/* 这条说明是**如实**、不是免责：测试给的是起点（低），做完事会跟着动 ——
            全都在这一条曲线上，不另画一条"不算分"的线。
            （原来右边还挂了一个「做完事会变，久了也会回落」的角标，用户说多余，删了。） */}
        {!insightEmpty ? (
          <p className={styles.radarNote}>
            {updatedLabels.length === 0
              ? "起点来自那次测试"
              : `${updatedLabels.join("、")} 已经按真实成果动过`}
          </p>
        ) : null}
              <div className="v277-radar-body">
                <svg viewBox="0 0 180 144" aria-label="能力雷达图">
                  <g className="grid">
                    {RADAR_RINGS.map((scale) => (
                      <polygon key={scale} points={ringPoints(scale)} />
                    ))}
                    {RADAR_AXES.map(({ vertex }) => (
                      <line
                        key={`${vertex.x}-${vertex.y}`}
                        x1={RADAR_CENTER.x}
                        y1={RADAR_CENTER.y}
                        x2={vertex.x}
                        y2={vertex.y}
                      />
                    ))}
                  </g>
        {radarPoints.length >= 3 && (
          <polygon
            className="value"
            points={radarPoints
              .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
              .join(" ")}
          />
        )}
        {radarPoints.map((point) => (
          <circle
            key={`${point.x.toFixed(1)}-${point.y.toFixed(1)}`}
            cx={point.x.toFixed(1)}
            cy={point.y.toFixed(1)}
            r="3"
          />
        ))}
                  {abilityInsight.axes.map((axis, index) => (
                    <text
                      key={axis.label}
            className={axis.value === null ? "is-unknown" : undefined}
            x={RADAR_AXES[index].text.x}
            y={RADAR_AXES[index].text.y}
          >
            {axis.label} {insightEmpty ? "—" : (axis.value ?? "未知")}
                    </text>
                  ))}
                </svg>
                <div>
                  <b>
                    {insightEmpty ? "—" : (abilityInsight.composite ?? "未知")}
                    {insightEmpty || abilityInsight.composite === null ? null : (
                      <small>/100</small>
                    )}
                  </b>
                  <p>综合能力</p>
        {/* 只有起点的时候**不再多写一行**：上面那句「起点来自那次测试」已经把话说完，
            这里再挂一遍"起点来自测试 / 做完事会跟着动"就是重复（用户点名删掉）。
            有了真实成果之后才在这儿报"几项成果 · 几次外部验证"。 */}
        {insightEmpty ? (
          <>
            <span>还没有成果</span>
            <em>做出第一条成果，这里才开始长</em>
          </>
        ) : updatedLabels.length > 0 ? (
                    <>
                      <span>{abilityInsight.outcomeCount} 项成果</span>
                      <em>{abilityInsight.externalChecks} 次外部验证 · 可追溯</em>
                    </>
                  ) : null}
                </div>
              </div>
            </button>
            <button
              type="button"
              className={`v279-insight-card trend ${insightIndex === 1 ? "is-front" : "is-back"}`}
              onClick={() => {
                if (insightSwipe.current.moved) {
                  insightSwipe.current.moved = false;
                  return;
                }
                go({ name: "ability-profile" });
              }}
            >
              <header>
                <h3>
                  <Sparkles size={17} />
                  能力变化趋势
                </h3>
                <span>
                  点击查看详情
                  <ChevronRight size={16} />
                </span>
              </header>
              <div className="v279-trend-body">
                {trend && abilityInsight.trend ? (
                  <>
                    <svg viewBox="0 0 180 144" aria-label="能力变化趋势图">
                      <line x1="12" y1="120" x2="170" y2="120" />
                      <line x1="12" y1="78" x2="170" y2="78" />
                      <line x1="12" y1="36" x2="170" y2="36" />
                      <path className="area" d={trend.area} />
                      <path className="line" d={trend.line} />
                      <circle
                        cx={trend.last.x.toFixed(1)}
                        cy={trend.last.y.toFixed(1)}
                        r="4"
                      />
                      <text x="12" y="139">
                        第 1 周
                      </text>
                      <text x="136" y="139">
                        第 {abilityInsight.trend.weeks} 周
                      </text>
                    </svg>
                    <div>
                      <b>
                        {trendDelta >= 0 ? "+" : ""}
                        {trendDelta}
                        <small>/100</small>
                      </b>
                      <p>{abilityInsight.trend.label}</p>
                      <span>{abilityInsight.trend.weeks} 周提升</span>
                      <em>{abilityInsight.trend.note}</em>
                    </div>
                  </>
                ) : (
                  <p className="v279-trend-empty">还没有连续数据，攒够两周就能看到趋势</p>
                )}
              </div>
            </button>
            <nav className="v278-insight-dots" aria-label="切换能力洞察">
              {[0, 1].map((index) => (
                <button
                  type="button"
                  key={index}
                  aria-label={`第 ${index + 1} 张能力洞察`}
                  className={insightIndex === index ? "active" : ""}
                  onClick={() => setInsightIndex(index)}
                />
              ))}
            </nav>
          </div>
        </section>
      </div>
        {alignmentOpen && (
        <UnderstandingSheet
          state={state}
          go={go}
          empty={emptyMode}
          onClose={() => setAlignmentOpen(false)}
        />
      )}
      {importOpen && (
        <>
        </>
      )}
      {/* 我的工具：从圆钮旁边弹出的方框（渲染在滚动层外面，否则会被裁掉）；
          里面可以横向滑动选工具，导入也放在这里 —— 工具和"塞东西进来"是一族。 */}
      {importOpen && (
        <>
          <button
            type="button"
            className={styles.sheetBackdrop}
            aria-label="关闭导入"
            onClick={() => setImportOpen(false)}
          />
          <section
            className={styles.sheet}
            role="dialog"
            aria-modal="true"
            aria-label="导入"
          >
            <i className={styles.sheetHandle} />
            <header className={styles.sheetHead}>
              <span>
                <h2 className={styles.sheetTitle}>导入</h2>
                <p className={styles.sheetNote}>先进「待确认」，你点头才算数</p>
              </span>
              <button
                type="button"
                className={styles.sheetClose}
                aria-label="关闭"
                onClick={() => setImportOpen(false)}
              >
                <X size={21} />
              </button>
            </header>
            {/* 选文件 / 导入简历都走这个输入框；简历按文件名认出来，导完同步进记忆库 */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,.md,.csv,.json"
              hidden
              onChange={(event) => {
                void takeFile(event.target.files?.[0] ?? null);
                event.target.value = "";
              }}
            />
            <div className={styles.importList}>
              {IMPORT_SOURCES.map(({ title, note, kind }) => (
                <button
                  type="button"
                  key={title}
                  className={styles.importRow}
                  onClick={() => {
                    if (kind === "link") {
                      void takeLink();
                      return;
                    }
                    fileInputRef.current?.click();
                  }}
                >
                  <span>
                    <b>{title}</b>
                    <small>{note}</small>
                  </span>
                  <ChevronRight size={16} />
                </button>
              ))}
            </div>
            {pendingList.length > 0 && (
              <div className={styles.pendingList}>
                <h4>待确认（{pendingList.length}）</h4>
                {pendingList.map((item) => (
                  <div key={item.id} className={styles.pendingRow}>
                    <span>
                      <b>{displayTitle(item.title,'')}</b>
                      <small>{item.from} · 确认后才会上架</small>
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        // 后端在跑：确认后它会生成一张「待验证」能力卡；够不着就走本地
                        if (livePendingMaterials !== null) void resolveMaterial(item.id, true);
                        else resolvePendingMaterial(item.id, true);
                        setStoreVersion((v) => v + 1);
                        setImportHint(`已确认：${item.title} 现在在知识货架上`);
                      }}
                    >
                      确认
                    </button>
                    <button
                      type="button"
                      className={styles.pendingDrop}
                      onClick={() => {
                        if (livePendingMaterials !== null) void resolveMaterial(item.id, false);
                        else resolvePendingMaterial(item.id, false);
                        setStoreVersion((v) => v + 1);
                        setImportHint(`已丢弃：${item.title}`);
                      }}
                    >
                      丢弃
                    </button>
                  </div>
                ))}
              </div>
            )}
            {documents.length > 0 && (
              <div className={styles.pendingList}>
                <h4>文档（{documents.length}）</h4>
                {documents.map((doc) => (
                  <div key={doc.id} className={styles.pendingRow}>
                    <span>
                      <b>{doc.name}</b>
                      <small>{doc.status}</small>
                    </span>
                    <button
                      type="button"
                      className={styles.pendingDrop}
                      onClick={() => setImportHint(`${doc.name}：预览还没接`)}
                    >
                      预览
                    </button>
                  </div>
                ))}
              </div>
            )}
            <p className={styles.importFoot}>
              {importHint ?? "这一步只收下原始素材，不会直接变成卡片。"}
            </p>
          </section>
        </>
      )}
      {selectedCapability && (
        <CapabilitySheet
          card={selectedCapability}
          go={go}
          onClose={() => setSelectedCapability(null)}
          onOpenEvidence={(evidenceId) => {
            setSelectedCapability(null);
            go({ name: "evidence-detail", id: evidenceId });
          }}
          onOpenEvidenceList={() => {
            setSelectedCapability(null);
            go({ name: "evidence" });
          }}
          onCreateTask={async (card, goal) => {
            // ⚠️ 2026-09-26 对齐你们的新契约：`launchWithSkill` 现在返回 system + prompt，
            //    直接带着可编辑的 prefill 进那个 Agent 的会话（我们原来那版是 conversationId）。
            const result = await launchWithSkill(runtime, card.id||card.title, goal);
            if (result.ok && result.system && result.prompt) {
              setPendingSkill(card.title);
              setSelectedCapability(null);
              go({ name: "chat", id: result.system, prefill: result.prompt });
              return { ok: true };
            }
            return { ok: false, note: result.note };
          }}
          tasks={state.tasks}
          onUpgrade={(card) => {
            setCardLevel(card.title, card.level + 1);
            setStoreVersion((version) => version + 1);
            setSelectedCapability({ ...card, level: card.level + 1 });
          }}
        />
      )}
    </main>
  );
}
