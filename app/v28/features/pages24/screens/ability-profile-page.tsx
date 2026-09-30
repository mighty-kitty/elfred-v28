"use client";
import {displayTitle} from "../../../core/display-labels";

import { ChevronRight } from "lucide-react";
import type { Screen } from "../../../core/screen";
import { AppHeader } from "../../../legacy/legacy-ui";
import {
  AbilityRadarChart,
  TrendChart,
  growProgress,
  useGrowClock,
} from "../parts/ability-charts";
import {
  DIMENSION_COLOR,
  abilityInsight,
  abilityCardSamples,
} from "../data/knowledge-data";
import { setPendingCard } from "../api/page2-store";
import styles from "../styles/knowledge.module.css";
import libraryStyles from "../styles/knowledge-library.module.css";

// 能力画像。这一屏以前是一列文字 + 一条小折线，看不出"洞察"；现在四块图：
// 综合雷达（本期面 + 上期虚线）→ 五维对比条（粗条本期、灰竖标上期）→ 分是谁撑起来的 → 最近的变化。
// 四块里的每个数字都从 abilityInsight / dimensionProfiles / abilityCardSamples 算，写死在界面里的一律不要。
export function AbilityProfilePage({
  go,
  onBack,
}: {
  go: (screen: Screen) => void;
  onBack: () => void;
}) {
  const composite = abilityInsight.composite;
  const previous = abilityInsight.previousComposite ?? null;
  const delta =
    composite !== null && previous !== null ? composite - previous : null;
  const trend = abilityInsight.trend;
  // "上期"只有服务端真的给了才有（`core/dimensions.mjs` 的 previous / previousComposite）。
  // 一股脑写上"灰竖标＝上期"，用户会去找一根永远不出现的灰竖标 —— 有才画图例。
  const hasPrevious = abilityInsight.axes.some((axis) => axis.previous !== null);
  // "分是谁撑起来的"只看卡：每张卡带了多少条成果，条数多的排前面。
  const carriers = [...abilityCardSamples].sort((a, b) => b.evidence - a.evidence);
  const carried = carriers.reduce((sum, card) => sum + card.evidence, 0);
  // 打开这一页时，四块图依次从 0 长到现在：雷达 → 五维 → 撑分卡 → 趋势。
  const clock = useGrowClock(1320);
  const radarP = growProgress(clock, 0, 820);
  const dimP = growProgress(clock, 140, 760);
  const cardP = growProgress(clock, 300, 760);
  const trendP = growProgress(clock, 420, 820);
  // 数字跟着进度跳到终值，一步不超
  const countUp = (value: number | null, progress: number) =>
    value === null ? null : Math.round(value * progress);
  // 点一张卡＝回知识库并自动打开这张卡（和成果详情里点卡名走同一条路）
  const openCard = (title: string) => {
    setPendingCard(title);
    go({ name: "knowledge" });
  };

  return (
    <main className="v277-page">
      <AppHeader
        title="能力画像"
        subtitle="五个维度 · 来自真实任务与结果"
        onBack={onBack}
      />
      <div className={styles.screen}>
        <section className={styles.block}>
          <h3>
            综合能力
            <small>
              {previous !== null
                ? `上期 ${previous}${delta ? ` · 本期 ${delta > 0 ? "+" : ""}${delta}` : ""}`
                : `${abilityInsight.outcomeCount} 项成果 · ${abilityInsight.externalChecks} 次外部验证`}
            </small>
          </h3>
          <div className={styles.radarWrap}>
            <AbilityRadarChart
              axes={abilityInsight.axes}
              tone="#525a61"
              progress={radarP}
            />
            <div className={libraryStyles.radarCenter}>
              <b>{countUp(composite, radarP) ?? "未知"}</b>
              {composite === null ? null : <span>/100</span>}
            </div>
          </div>
          {hasPrevious ? (
            <p className={libraryStyles.chartLegend}>
              <i className={libraryStyles.legendNow} /> 本期
              <i className={libraryStyles.legendPrev} /> 上期
            </p>
          ) : null}
        </section>

        <section className={styles.block}>
          <h3>
            五个维度
            <small>{hasPrevious ? "粗条＝本期，灰竖标＝上期" : "条的长度＝这一维现在的水平"}</small>
          </h3>
          <div className={libraryStyles.dimList}>
            {abilityInsight.axes.map((axis) => {
              const value = axis.value;
              const before = axis.previous ?? null;
              const gap =
                value !== null && before !== null ? value - before : null;
              const tone = DIMENSION_COLOR[axis.label] ?? "#6d7680";
              // 条从 0 长到这一维的分；上期那根灰竖标不动，一上来就在它的位置上
              const grown =
                value === null ? 0 : Math.min(100, value * dimP);
              return (
                <button
                  type="button"
                  key={axis.label}
                  className={styles.dimRow}
                  onClick={() => go({ name: "dimension", id: axis.label })}
                >
                  <span className={libraryStyles.dimName}>{axis.label}</span>
                  <span className={libraryStyles.dimTrack}>
                    {value === null ? (
                      <i className={libraryStyles.dimUnknown} />
                    ) : (
                      <>
                        <i
                          className={libraryStyles.dimFill}
                          style={{
                            width: `${Math.max(0, grown)}%`,
                            background: tone,
                          }}
                        />
                        {before !== null && (
                          <i
                            className={libraryStyles.dimPrev}
                            style={{ left: `${before}%` }}
                          />
                        )}
                      </>
                    )}
                  </span>
                  <span className={libraryStyles.dimValue}>
                    {countUp(value, dimP) ?? "未知"}
                    {gap !== null && (
                      <em
                        className={
                          gap > 0
                            ? libraryStyles.dimUp
                            : gap < 0
                              ? libraryStyles.dimDown
                              : libraryStyles.dimFlat
                        }
                      >
                        {gap > 0 ? `+${gap}` : gap < 0 ? `${gap}` : "—"}
                      </em>
                    )}
                  </span>
                  <ChevronRight size={13} className={libraryStyles.dimArrow} />
                </button>
              );
            })}
          </div>
          <p className={libraryStyles.chartHint}>点某一条进那一维：看它的卡和最近的成果</p>
        </section>

        <section className={styles.block}>
          <h3>
            分是谁撑起来的
            <small>按卡上的成果条数</small>
          </h3>
          <div className={libraryStyles.contribList}>
            {carriers.length === 0 && (
              <p className={libraryStyles.contribEmptyNote}>还没有卡，做出第一件成果就会长出来</p>
            )}
            {carriers.map((card) => {
              const tone = DIMENSION_COLOR[card.dimension] ?? "#6d7680";
              const share = carried === 0 ? 0 : (card.evidence / carried) * 100;
              const grown = Math.min(100, Math.max(6, share) * cardP);
              return (
                <button
                  type="button"
                  key={card.title}
                  className={libraryStyles.contribRow}
                  onClick={() => openCard(card.id||card.title)}
                >
                  <span className={libraryStyles.contribHead}>
                    <b>{displayTitle(card.title,'')}</b>
                    <i style={{ background: `${tone}1a`, color: tone }}>
                      {card.dimension} · Lv.{card.level}
                    </i>
                  </span>
                  <span className={libraryStyles.contribMeta}>{card.evidence} 条</span>
                  <ChevronRight size={13} className={libraryStyles.contribArrow} />
                  <span className={libraryStyles.contribBar}>
                    <i
                      style={{
                        width: `${Math.min(100, Math.max(0, grown))}%`,
                        background: tone,
                      }}
                    />
                  </span>
                </button>
              );
            })}
          </div>
          <p className={libraryStyles.chartHint}>点一张，看它的分是怎么来的</p>
        </section>

        {/* 少于两周的点画不出趋势，那就不出这块，别留个空壳 */}
        {trend && trend.points.length >= 2 && (
          <section className={styles.block}>
            <h3>
              最近的变化
              <small>
                {trend.weeks} 周 · {trend.note}
              </small>
            </h3>
            <TrendChart
              points={trend.points}
              tone="#525a61"
              weeks={trend.weeks}
              progress={trendP}
            />
          </section>
        )}

        <p className={styles.footNote}>
          只算做完并确认过的事；用得再多也不算，也不跟别人比。
        </p>
      </div>
    </main>
  );
}
