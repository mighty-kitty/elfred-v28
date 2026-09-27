"use client";
import {displayTitle} from "../../../core/display-labels";

import { ChevronRight, ShieldCheck } from "lucide-react";
import type { Screen } from "../../../core/screen";
import { AppHeader } from "../../../legacy/legacy-ui";
import { evidenceRecords } from "../data/knowledge-data";
import styles from "../styles/knowledge.module.css";

// 成果列表：以前"查看全部"跳到能力洞察，是跳错页；这一屏才是"今天/最近产生了哪些成果"。
export function EvidenceListPage({
  go,
  onBack,
}: {
  go: (screen: Screen) => void;
  onBack: () => void;
}) {
  const days = [...new Set(evidenceRecords.map((record) => record.day))];
  const cards = new Set(
    evidenceRecords.flatMap((record) => record.impacts.map((i) => i.card)),
  );

  return (
    <main className="v277-page">
      <AppHeader
        title="成果"
        subtitle="每一条都能回源到任务或对话"
        onBack={onBack}
      />
      <div className={styles.screen}>
        <section className={styles.statRow}>
          <span>
            <b>{evidenceRecords.length}</b>项成果
          </span>
          <span>
            <b>{days.length}</b>天
          </span>
          <span>
            <b>{cards.size}</b>张卡因此变化
          </span>
        </section>

        {days.map((day) => {
          const items = evidenceRecords.filter((record) => record.day === day);
          return (
            <section className={styles.block} key={day}>
              <h3>
                {day}
                <small>{items.length} 条</small>
              </h3>
              <div className={styles.timeline}>
                {items.map((record) => (
                  <button
                    type="button"
                    key={record.id}
                    className={styles.evidenceRow}
                    onClick={() => go({ name: "evidence-detail", id: record.id })}
                  >
                    <span className={styles.evidenceTime}>{record.time}</span>
                    <b>{displayTitle(record.title,'')}</b>
                    <small>
                      {record.kindLabel} ·{" "}
                      {record.impacts
                        .map((impact) => impact.card)
                        .join(" / ") || "未影响卡片"}
                    </small>
                    <ChevronRight size={16} />
                  </button>
                ))}
              </div>
            </section>
          );
        })}

        <p className={styles.footNote}>
          <ShieldCheck size={14} />
          看过、点赞、收藏不算成果；只有做过并确认过的事才算。
        </p>
      </div>
    </main>
  );
}
