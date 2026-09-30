"use client";

// 页头那个胶囊点开之后的面板。
//   · 说法：信任线（初见→可托付），不借用卡片的 Lv / Evidence 那套词
//   · 形式：从底部升起的面板（和能力卡详情同一个形式），按内容撑高，一屏放得下
//   · 内容：当前档 + 到下一档还差多少 + 三个记忆口径的数 + 成长路径（点开铺全六档）
//   · 荣誉勋章那一栏原样保留，功能一个不少

import { useEffect, useState } from "react";
import {
  ChevronRight,
  Star,
  Trophy,
  X,
} from "lucide-react";
import type { V277State } from "../../../../v27-7-state";
import { RootPortal } from "../../../legacy/legacy-ui";
import { buildMemoryView } from "../data/memory-data";
import { HonorGallery } from "./honor-gallery";
import {
  ALIGNMENT_GATE,
  ALIGNMENT_STAGE,
  ALIGNMENT_UNLOCK,
  alignmentView,
  readAlignmentStage,
} from "../data/knowledge-data";
import styles from "../styles/knowledge.module.css";
import sheetStyles from "../styles/knowledge-sheet.module.css";

export function UnderstandingSheet({
  state,
  onClose,
}: {
  state: V277State;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<"level" | "honors">("level");
  const [pathOpen, setPathOpen] = useState(false);
  // 打开面板时用一个钟同时驱动三件事：两条进度条从 0 长到位、大数字从 0 滚上来。
  // 这一页要"看得爽"，数字和进度都得会动；系统开了"减少动态效果"就直接给终值。
  const [clock, setClock] = useState(0);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setClock(1);
      return;
    }
    let frame = 0;
    let started = 0;
    const step = (now: number) => {
      if (!started) started = now;
      const passed = Math.min(1, (now - started) / 700);
      setClock(passed);
      if (passed < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, []);
  // 这一块**不再有自己的"空态口径"**：页头那个胶囊、第四页那颗胶囊、设置页那一行
  // 和这里读的是同一个 `alignmentView()`。以前这里有 `empty ? 0 : …`，于是新用户
  // 在同一屏看到"页头 10%、弹层 0%"（用户截图里那个）。
  const alignment = alignmentView();
  const live = alignment.live;
  const level = alignment.level;
  const percent = alignment.percent;
  const nextLevel = Math.min(level + 1, ALIGNMENT_STAGE.length - 1);
  const gateFrom = ALIGNMENT_GATE[level] ?? 0;
  const gateTo = ALIGNMENT_GATE[nextLevel] ?? 100;
  const toNext = live ? Math.max(0, gateTo - percent) : 0;
  const progress = Math.min(
    100,
    Math.max(0, Math.round(((percent - gateFrom) / Math.max(1, gateTo - gateFrom)) * 100)),
  );
  const memory = buildMemoryView(state.memories);
  // 缓动后的进度（0–1）：两条进度条的长度和那个大数字都用它
  const eased = 1 - (1 - clock) ** 3;
  const shownPercent = Math.round(percent * eased);

  return (
    <RootPortal>
      <button
        type="button"
        className={styles.sheetBackdrop}
        aria-label="关闭理解度详情"
        onClick={onClose}
      />
      <section
        className={styles.sheet}
        role="dialog"
        aria-modal="true"
        aria-label="理解度详情"
      >
        <i className={styles.sheetHandle} />
        <header className={styles.sheetHead}>
          <h2 className={styles.sheetTitle}>理解与成长</h2>
          <button
            type="button"
            className={styles.sheetClose}
            aria-label="关闭"
            onClick={onClose}
          >
            <X size={21} />
          </button>
        </header>
        <nav className={sheetStyles.segTabs}>
          <button
            type="button"
            className={`${sheetStyles.segTab}${tab === "level" ? ` ${sheetStyles.segTabOn}` : ""}`}
            onClick={() => setTab("level")}
          >
            <Trophy size={17} />
            等级
          </button>
          <button
            type="button"
            className={`${sheetStyles.segTab}${tab === "honors" ? ` ${sheetStyles.segTabOn}` : ""}`}
            onClick={() => setTab("honors")}
          >
            <Star size={17} />
            荣誉勋章
          </button>
        </nav>
        {tab === "level" ? (
          <div>
            <section className={sheetStyles.stage}>
              <div className={sheetStyles.stageTop}>
                <i className={sheetStyles.orb} />
                <div>
                  <h3 className={sheetStyles.stageName}>
                    Lv.{level}
                    <em>{readAlignmentStage(level)}</em>
                  </h3>
                  <p className={sheetStyles.stageSub}>{ALIGNMENT_UNLOCK[level]}</p>
                </div>
                <span className={sheetStyles.stagePct}>
                  <b>{live ? `${shownPercent}%` : "—"}</b>
                  <small>当前理解度</small>
                </span>
              </div>
              <em className={sheetStyles.bar}>
                <i
                  className={sheetStyles.barFill}
                  style={{ width: `${percent * eased}%` }}
                >
                  <i className={sheetStyles.barKnob} />
                </i>
              </em>
            </section>
            <section className={sheetStyles.next}>
              <header className={sheetStyles.nextHead}>
                {/* 一句话说完：离下一档差多少（百分数）。上面那行已经有大号当前值，
                    这里不再重复写「10% →」；也不再拆成左右两截。 */}
                <span>
                  {live ? (
                    <>
                      距离 Lv.{nextLevel} 还差 <b>{toNext}%</b>
                    </>
                  ) : (
                    <>距离 Lv.{nextLevel} 还差多少</>
                  )}
                </span>
              </header>
              <em className={sheetStyles.bar}>
                <i
                  className={sheetStyles.barFill}
                  style={{ width: `${(live ? progress : 0) * eased}%` }}
                >
                  <i className={sheetStyles.barKnob} />
                </i>
                <i className={sheetStyles.barGoal} />
              </em>
            </section>
            <section className={styles.statRow}>
              <span className={sheetStyles.stat}>
                <b>{memory.totalCount}</b>
                <small>已确认的记忆</small>
              </span>
              <span className={sheetStyles.stat}>
                <b>{memory.daysTracked}</b>
                <small>天持续更新</small>
              </span>
              <span className={sheetStyles.stat}>
                {/* 记忆可信度 = 已确认的记忆里档位到"场景已验证/跨时间稳定"的占比。
                    一条都没确认时没有基数 → 写"—"（0% 会被读成"它确认过但都不可信"，是另一件事）。 */}
                <b>{memory.credibility === null ? "—" : `${memory.credibility}%`}</b>
                <small>记忆可信度</small>
              </span>
            </section>
            <section>
              <header className={sheetStyles.pathHead}>
                <h4>成长路径</h4>
                <button type="button" onClick={() => setPathOpen((open) => !open)}>
                  {pathOpen ? "收起" : "查看全部"}
                  <ChevronRight size={15} />
                </button>
              </header>
              {pathOpen ? (
                <div className={sheetStyles.pathGrid}>
                  {ALIGNMENT_STAGE.slice(1).map((stage, index) => {
                    const item = index + 1;
                    return (
                      <div
                        key={item}
                        className={`${sheetStyles.pathCell}${
                          item === level ? ` ${sheetStyles.pathCellCurrent}` : ""
                        }`}
                      >
                        <b>
                          Lv.{item} · {stage}
                        </b>
                        <small>{ALIGNMENT_UNLOCK[item]}</small>
                      </div>
                    );
                  })}
                </div>
              ) : (
                // 这一行原来是个点不动的 div（写着「下一阶段」却点不了）；
                // 现在它跟右上角「查看全部」是同一件事：点开就是六档整条路径。
                <button
                  type="button"
                  className={sheetStyles.pathRow}
                  aria-label="查看完整的成长路径"
                  onClick={() => setPathOpen(true)}
                >
                  <b>Lv.{nextLevel}</b>
                  <span className={sheetStyles.pathInfo}>
                    <strong>{ALIGNMENT_STAGE[nextLevel]}</strong>
                  </span>
                  <em className={sheetStyles.pathTag}>下一阶段</em>
                  <ChevronRight size={15} className={sheetStyles.pathArrow} />
                </button>
              )}
            </section>
          </div>
        ) : (
          <div>
            {/* 原来这里是写死的 12 枚（洞察先锋 / 可靠交付 /…），和第四页那套完全不同。
                现在两边都用 HonorGallery：同一份 /page2/badges、同一个长相。 */}
            <HonorGallery />
          </div>
        )}
      </section>
    </RootPortal>
  );
}
