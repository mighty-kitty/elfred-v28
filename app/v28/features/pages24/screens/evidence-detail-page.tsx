"use client";
import {displayTitle} from "../../../core/display-labels";

import {
  ArrowUpRight,
  BadgeCheck,
  RotateCcw,
  Sparkles,
} from "lucide-react";
import type { Screen } from "../../../core/screen";
import { AppHeader } from "../../../legacy/legacy-ui";
import {
  setPendingCard,
} from "../api/page2-store";
import { readEvidence } from "../data/knowledge-data";
import styles from "../styles/knowledge.module.css";

// 成果详情：以前点一条成果给的是"用户访谈提纲"知识卡，文不对题。
// 这一屏回答四件事：这是什么 · 从哪来 · 改变了什么 · 我能怎么办。
export function EvidenceDetailPage({
  id,
  go,
  onBack,
}: {
  id: string;
  go: (screen: Screen) => void;
  onBack: () => void;
}) {
  const record = readEvidence(id);

  if (!record) {
    return (
      <main className="v277-page">
        <AppHeader title="成果" onBack={onBack} />
        <div className={styles.screen}>
          <p className={styles.empty}>这条成果已经不在了</p>
        </div>
      </main>
    );
  }

  return (
    <main className="v277-page">
      <AppHeader
        title="成果详情"
        // agent 为空时别写成"由  写入"（后端在某些卡片上确实给不出署名）
        subtitle={
          record.agent
            ? `${record.day} ${record.time} · 由 ${record.agent} 写入`
            : `${record.day} ${record.time}`
        }
        onBack={onBack}
      />
      <div className={styles.screen}>
        <section className={styles.block}>
          <h3>
            {displayTitle(record.title,'')}
            {record.verified && (
              <small>
                <BadgeCheck size={13} /> 已验收
              </small>
            )}
          </h3>
          <div className={styles.chips}>
            <span>{record.kindLabel}</span>
            <span>{record.weightLabel}</span>
          </div>
        </section>

        <section className={styles.block}>
          <h3>来源</h3>
          <button
            type="button"
            className={styles.sourceRow}
            onClick={() =>
              go(
                record.source.ref.kind === "task"
                  ? { name: "task", id: record.source.ref.id }
                  : { name: "chat", id: record.source.ref.id },
              )
            }
          >
            <span>
              <b>{record.source.label}</b>
              <small>{record.source.note}</small>
            </span>
            <ArrowUpRight size={16} />
          </button>
        </section>

        <section className={styles.block}>
          <h3>原始摘要</h3>
          <p className={styles.quote}>{record.summary}</p>
        </section>

        <section className={styles.block}>
          <h3>
            带来了什么变化
            <small>
              {record.impacts.length === 0 ? "没有影响卡片" : "影响的能力卡"}
            </small>
          </h3>
          {record.impacts.map((impact) => (
            <div className={styles.impactRow} key={impact.card}>
              {/* 卡名可点：点了直接回到知识库并打开那张卡（以前只是回列表，不定位） */}
              <button
                type="button"
                className={styles.impactCard}
                onClick={() => {
                  setPendingCard(impact.card);
                  go({ name: "knowledge" });
                }}
              >
                {impact.card}
                <ArrowUpRight size={13} />
              </button>
              <span>
                {impact.score && (
                  <em>
                    能力分 {impact.score.from} → {impact.score.to}
                  </em>
                )}
                {impact.evidence && (
                  <em>
                  成果 {impact.evidence.from} → {impact.evidence.to}
                  </em>
                )}
                {impact.upgraded && (
                  <em className={styles.upgrade}>
                    <Sparkles size={12} />
                    {impact.upgraded}
                  </em>
                )}
              </span>
            </div>
          ))}
          {record.note && <p className={styles.note}>{record.note}</p>}
          <button
            type="button"
            className={styles.linkBtn}
            onClick={() => {
              const first = record.impacts[0];
              if (first) setPendingCard(first.card);
              go({ name: "knowledge" });
            }}
          >
            {record.impacts[0]
              ? `去卡组看「${record.impacts[0].card}」`
              : "去能力卡组看看"}
          </button>
        </section>

        <section className={styles.block}>
          <h3>我能怎么办</h3>
          <p className={styles.note}>这条成果来自本人已验收的任务。需要修正时，请回原任务核对来源和结果。</p>
          <div className={styles.actions}>
            {record.source.ref.kind === "task" && <button type="button" onClick={() => go({ name: "task", id: record.source.ref.id })}>
              <BadgeCheck size={16} />查看原任务
            </button>}
            <button
              type="button"
              onClick={() => {
                onBack();
                go({ name: "new-task" });
              }}
            >
              <RotateCcw size={16} />
              再跑一次
            </button>
          </div>
        </section>
      </div>
    </main>
  );
}
