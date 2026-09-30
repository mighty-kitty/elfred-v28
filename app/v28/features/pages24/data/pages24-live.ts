// 第二页/第四页的**真数据接入**：快照回来之后，把它就地写进 `pages24-view-data.ts` 那些常量里。
//
// 为什么这么写：页面直接 import 那些常量（`abilityCardSamples`、`abilityInsight`…），
// 换成 props 传下去要动 6 个屏；所以这里保持"常量的身份不变，只换里面的内容"。
// 代价是"谁在改这些常量"必须写清楚 —— 全模块只有这个文件改，别处只读。
//
// 铁律：接口够不着（offline）时**什么都不做**，页面继续用演示兜底；拿到真数据才替换。
import { Brain, Compass, FileText, Link2, Rocket, Sparkles } from "lucide-react";
import { registerProjector } from "../api/page2-api";
import type { AbilityCardSample, AbilityInsightView, AbilityType, DimensionProfile, EvidenceDetail, EvidenceKind, EvidenceItemView } from "./pages24-view-data";
import {
  abilityCardSamples, abilityInsight, dimensionProfiles, documents, evidenceRecords, libraryHeader, todayEvidence,
  markLiveAlignment,
} from "./pages24-view-data";
import type { LiveCapability, LiveDocument, LiveEvidenceDetail, Page2Data } from "../api/page2-types";

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
      // 这三个值由投影算好（`core/dimensions.mjs` 的估计），前端别再猜。
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

  // 理解度：页头胶囊、理解度弹层、第四页胶囊、设置页那一行**读的是同一份**
  // （`libraryHeader` → `alignmentView()`），所以这里一次把整份都盖上。
  // 昨天那两个数对不上，就是因为弹层自己又写了一遍 `empty ? 0 : …`。
  markLiveAlignment(typeof data.alignment?.alignment === "number");
  if (data.alignment) {
    // 后端这两个字段可能是 null（用户还没有记忆时返回的就是 null）。
    // 以前是直接赋值，等于把 86/4 洗成 null/undefined，页头会渲染出 "null%"。
    // 以后端为准 = 后端给了数字才认；没给就保持原值，只是标记"这份还不是真数"。
    if (typeof data.alignment.alignment === "number") {
      libraryHeader.alignment = data.alignment.alignment;
      markLiveAlignment(true);
    }
    if (typeof data.alignment.level === "number") {
      libraryHeader.level = data.alignment.level;
    }
  }

  if (data.documents) replaceAll(documents, data.documents);
}

/** 裁定完一条成果：后端重算过的卡片分数/成果数直接盖上来 */
function applyLiveCards(cards: LiveCapability[]) {
  const byTitle = new Map(cards.map((card) => [card.title, card]));
  for (const sample of abilityCardSamples) {
    const live = byTitle.get(sample.title);
    if (!live) continue;
    // 和 mapCard 同一套口径：没有成果就是"证据不足"，不写"0 能力分"
    // （`Math.round(null ?? 0)` 会写成 0，实测在页面上就是"0 能力分"，比不给分更误导）。
    sample.score = live.score === null ? 0 : Math.round(live.score);
    sample.evidence = live.evidence;
    sample.level = live.level;
    sample.notRunYet = live.score === null;
  }
}

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
