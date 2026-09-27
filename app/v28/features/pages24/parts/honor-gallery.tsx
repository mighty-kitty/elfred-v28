"use client";
import {displayTitle} from "../../../core/display-labels";

import { useEffect, useState } from "react";
import { BadgeCheck, Star, Trophy } from "lucide-react";
import { fetchBadges, type LiveBadge } from "../api/page2-api";
import styles from "../styles/knowledge.module.css";

// 荣誉勋章图鉴：**第二页（理解度弹层里那一栏）和第四页（我的 → 勋章）用同一份数据、同一个长相。**
//
// 以前两边各写一套：第二页那套是写死的 12 枚（洞察先锋 / 可靠交付 / 能力觉醒 / 共创之星…），
// 第四页那套读 `/page2/badges`（第一次成果 / 五连成果 / 到过 Lv.3）。
// 同一个用户在两处看到两套不同的勋章，等于两处都不可信 —— 现在统一到后端这一份。
//
// 后端的勋章是按"卡片等级 + 成果数"实时算出来的，所以没有"图鉴里那 12 枚"这种固定名单，
// 分类筛选（能力/协作/里程碑）也就没有依据，一并去掉了。
function iconFor(id: string) {
  if (/level/i.test(id)) return Trophy;
  if (/evidence|outcome/i.test(id)) return BadgeCheck;
  return Star;
}

export function HonorGallery({ compact = false }: { compact?: boolean } = {}) {
  const [badges, setBadges] = useState<LiveBadge[] | null>(null);
  useEffect(() => {
    let alive = true;
    void fetchBadges().then((result) => {
      if (alive && result?.badges) setBadges(result.badges);
    });
    return () => {
      alive = false;
    };
  }, []);
  // 后端没给（离线/接口挂了）就先不画：宁可少一块，也不摆一套假的名单
  if (!badges) return null;
  const earned = badges.filter((badge) => badge.earned);
  const locked = badges.filter((badge) => !badge.earned);
  const cell = (badge: LiveBadge) => {
    const Icon = iconFor(badge.id);
    return (
      <div
        className={`${styles.medal}${badge.earned ? "" : ` ${styles.medalLocked}`}`}
        key={badge.id}
      >
        <span>
          <Icon size={badge.earned ? 28 : 26} />
        </span>
        <b>{displayTitle(badge.title,'')}</b>
        <small>{badge.progress}</small>
      </div>
    );
  };
  return (
    <div className={compact ? styles.honorCompact : undefined}>
      <section className={styles.honorTop}>
        <div>
          <b>勋章图鉴</b>
          <small>
            已点亮 {earned.length} / {badges.length} 枚
          </small>
        </div>
        <strong>
          {earned.length} / {badges.length}
        </strong>
      </section>
      {earned.length > 0 && (
        <section>
          <header className={styles.pathHead}>
            <h4>已获得（{earned.length} 枚）</h4>
          </header>
          <div className={styles.medalGrid}>{earned.map(cell)}</div>
        </section>
      )}
      {locked.length > 0 && (
        <section>
          <header className={styles.pathHead}>
            <h4>未获得（{locked.length} 枚）</h4>
          </header>
          <div className={styles.medalGrid}>{locked.map(cell)}</div>
        </section>
      )}
    </div>
  );
}
