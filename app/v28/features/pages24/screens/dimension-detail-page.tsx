"use client";
import {displayTitle} from "../../../core/display-labels";

import { useState } from "react";
import { ChevronRight, Sparkles } from "lucide-react";
import type { Screen } from "../../../core/screen";
import { AppHeader } from "../../../legacy/legacy-ui";
import { CapabilitySheet, type SheetCard } from "../parts/capability-sheet";
import {
  DIMENSION_COLOR,
  cardsOfDimension,
  evidenceOfDimension,
  readDimension,
  readStage,
} from "../data/knowledge-data";
import styles from "../styles/knowledge.module.css";
import libraryStyles from "../styles/knowledge-library.module.css";

// 维度详情（L2）：以前点"策略 · 91"给的是一张知识卡，文不对题。
// 这一屏回答"这一维是什么水平、由哪些卡撑着、最近有什么成果、下一步做一件事"。
export function DimensionDetailPage({
  id,
  go,
  onBack,
  onCreateTask,
}: {
  id: string;
  go: (screen: Screen) => void;
  onBack: () => void;
  /** 和知识库那边同一套：带上"这次要做什么"才建得成真任务（见 skill-launch.ts） */
  onCreateTask: (card: SheetCard, goal: string) => Promise<{ ok: boolean; note?: string } | void>;
}) {
  const [opened, setOpened] = useState<SheetCard | null>(null);
  const profile = readDimension(id);
  const cards = cardsOfDimension(id);
  const records = evidenceOfDimension(id);
  const tone = DIMENSION_COLOR[id] ?? "#6d7680";

  if (!profile) {
    return (
      <main className="v277-page">
        <AppHeader title="维度" onBack={onBack} />
        <div className={styles.screen}>
          <p className={styles.empty}>没有找到这个维度</p>
        </div>
      </main>
    );
  }

  return (
    <main className="v277-page">
      <AppHeader
        title={`${profile.name} · ${profile.score ?? "未知"}`}
        subtitle={`${profile.agent} Agent 负责这一维`}
        onBack={onBack}
      />
      <div className={styles.screen}>
        <section className={libraryStyles.heroCard} style={{ borderColor: tone }}>
          <i className={libraryStyles.heroDot} style={{ background: tone }} />
          <b>
            {profile.score ?? "未知"}
            {profile.score === null ? null : <small>/100</small>}
          </b>
          <p>{profile.summary}</p>
          <span>
            这一维的卡最高能练到 Lv.{profile.capLevel} · {readStage(profile.capLevel)}
          </span>
        </section>

        <section className={styles.block}>
          <h3>
            撑着这一维的卡
            <small>{cards.length} 张</small>
          </h3>
          {cards.length === 0 ? (
            <p className={styles.empty}>
              这一维还没有能力卡。做完相关任务并验收，Elfred 会自动建卡。
            </p>
          ) : (
            <div className={libraryStyles.dimList}>
              {cards.map((card) => (
                <button
                  type="button"
                  key={card.title}
                  className={styles.cardRow}
                  onClick={() => setOpened({ ...card, dimension: id })}
                >
                  <i style={{ background: tone }} />
                  <span>
                    <b>{displayTitle(card.title,'')}</b>
                    <small>
                      {card.type} · Lv.{card.level} {readStage(card.level)} ·{" "}
                      {card.evidence} 项成果
                    </small>
                  </span>
                  <b className={libraryStyles.cardScore}>{card.score}</b>
                  <ChevronRight size={16} />
                </button>
              ))}
            </div>
          )}
        </section>

        <section className={styles.block}>
          <h3>
            最近的成果
            <small>{records.length} 条</small>
          </h3>
          {records.length === 0 ? (
            <p className={styles.empty}>这一维还没有成果</p>
          ) : (
            <div className={styles.timeline}>
              {records.map((record) => (
                <button
                  type="button"
                  key={record.id}
                  className={styles.evidenceRow}
                  onClick={() => go({ name: "evidence-detail", id: record.id })}
                >
                  <span className={styles.evidenceTime}>
                    {record.day} {record.time}
                  </span>
                  <b>{displayTitle(record.title,'')}</b>
                  <small>{record.source.label}</small>
                  <ChevronRight size={16} />
                </button>
              ))}
            </div>
          )}
        </section>

        <section className={styles.actionBox}>
          <Sparkles size={16} />
          <span>
            <b>想提升这一维，最近能做的一件事</b>
            {profile.nextAction}
          </span>
        </section>
      </div>
      {opened && (
        <CapabilitySheet
          card={opened}
          go={go}
          onClose={() => setOpened(null)}
          onOpenEvidence={(evidenceId) => {
            setOpened(null);
            go({ name: "evidence-detail", id: evidenceId });
          }}
          onOpenEvidenceList={() => {
            setOpened(null);
            go({ name: "evidence" });
          }}
          onCreateTask={onCreateTask}
        />
      )}
    </main>
  );
}
