"use client";

import {InactiveMemories} from '../../home/memory-governance';
import { useState } from "react";
import {
  Bookmark,
  CheckCircle2,
  ChevronRight,
  CircleDashed,
} from "lucide-react";
import type { V277State } from "../../../../v27-7-state";
import type { Screen } from "../../../core/screen";
import { UnderstandingSheet } from "../parts/understanding-sheet";
import { LibraryHeader } from "../parts/library-header";
import {
  MEMORY_GROUPS,
  buildMemoryView,
  memoriesOf,
  type MemoryGroup,
} from "../data/memory-data";
import knowledgeStyles from "../styles/knowledge.module.css";
import styles from "../styles/memory.module.css";

// 记忆库：从 legacy-ui 搬出来的第二页组件。
// 两处与旧版不同：① 记忆条目改成真的（来自 state，能点进去改/删）；② 筛选按钮和分组共用一份定义。
export function MemoryPage({
  state,
  go,
}: {
  state: V277State;
  go: (screen: Screen) => void;
}) {
  const [filter, setFilter] = useState<"全部" | MemoryGroup>("全部");
  const [alignmentOpen, setAlignmentOpen] = useState(false);
  const view = buildMemoryView(state.memories);
  const visibleGroups =
    filter === "全部" ? MEMORY_GROUPS : MEMORY_GROUPS.filter((group) => group === filter);
  const basicCount = memoriesOf(view, "基础").length;
  // 空态：记忆库也以后端为准 —— 后端没有记忆、也没有关系链，就是还没认识你。
  // （四个分组、身份卡、关系卡都不画，换成和卡组/洞察同一款式的空块。）
  const isEmpty = view.memories.length === 0 && view.relationships.length === 0;

  return (
    <main className="v277-page v277-library-page v277-memory-overview">
      <LibraryHeader
        active="memory"
        go={go}
        onContext={() => setAlignmentOpen(true)}
      />
      <div className="v277-memory-filter" aria-label="记忆分类">
        {(["全部", ...MEMORY_GROUPS] as const).map((name) => (
          <button
            type="button"
            className={filter === name ? "active" : ""}
            key={name}
            onClick={() => setFilter(name)}
          >
            {name}
          </button>
        ))}
      </div>
      <div className="v277-library-scroll memory-scroll"><InactiveMemories/>
        <section className="v277-understanding">
          <header>
            <span>
              <Bookmark size={19} />
              {view.headline}
            </span>
            <button type="button" onClick={() => go({ name: "profile" })}>
              展开
              <ChevronRight size={17} />
            </button>
          </header>
          <div className="v277-understanding-stats">
            <span>
              <b>{view.totalCount}</b> 有效的记忆
            </span>
            <span>
              {/* 这一格以前是"7 天有确认记录"，中间换过一版叫"覆盖类别"（四类记忆有着落几类）。
                  "覆盖类别"这个词不是一眼能懂的，评审时被问了两遍，所以按原样回到"持续更新"。 */}
              <b>{view.daysTracked > 0 ? view.daysTracked : "—"}</b> 天持续更新
            </span>
            <span>
              <b className="elfred-stat-label">{view.memories.filter(m=>!["已确认","自动记录"].includes(m.status)).length}</b> 条待核对
            </span>
          </div>
        </section>

        {/* 空态：圆图标 + 标题 + 一行说明 + 黑色胶囊按钮，和「还没有能力卡片/洞察」同款同尺寸 */}
        {isEmpty && (
          <section className={knowledgeStyles.emptyBlock}>
            <i className={knowledgeStyles.emptyBlockIcon}>
              <Bookmark size={26} />
            </i>
            <b>还没有记忆</b>
            <p>在聊天和任务里说过、确认过的事，它会记在这里</p>
            <button type="button" onClick={() => go({ name: "chat", id: "elfred" })}>
              去聊两句
            </button>
            <em className={knowledgeStyles.emptyNote}>偏好自动学习，敏感理解由你确认，随时可以改</em>
          </section>
        )}

        {/* 「记忆体检 / 归档」这块原来挂在一个默认关掉的开关后面，而它依赖的两个函数是
            永远返回"未接通"的空壳（旧独立后端那几条 /page2 路径已经不存在）。
            产品口径是"先留存但不展示"，所以这里去掉假入口，将来要做得接 EMOS 侧的体检接口。 */}
        {!isEmpty && visibleGroups.map((group) => {
          const items = memoriesOf(view, group);
          return (
            <section
              key={group}
              className={`v277-memory-showcase${group === "社交" ? " social" : ""}`}
            >
              <div className="v277-section-title">
                <h2>{group}</h2>
                {/* 社交这一类装的是"人"，所以条数按关系条目算，和别的类同一套算法 */}
                <span className={styles.count}>
                  {group === "社交" ? view.relationships.length : items.length} 条
                </span>
              </div>

              {/* 身份卡要有内容才画：后端还没有"当前身份"的时候就别摆一张空卡 */}
              {group === "基础" && view.identity.describe.trim() !== "" && (
                <button
                  type="button"
                  className="v277-identity-card"
                  onClick={() => go({ name: "profile" })}
                >
                  <span>
                    <b>{view.identity.headline}</b>
                    <strong>{state.profile.role || view.identity.photoLabel}</strong>
                    <p>{view.identity.describe}</p>
                    <small>
                      {basicCount} 条基础信息 · 来自个人资料
                    </small>
                  </span>
                  <i className="v277-memory-photo person-owner v277-sprite-community">
                    <em>{view.identity.photoLabel}</em>
                  </i>
                  <footer>
                    <CheckCircle2 size={18} />
                    {view.identity.rule}
                    <ChevronRight size={18} />
                  </footer>
                </button>
              )}

              {group === "社交" && (
                <article className="v277-relationship-card">
                  <h3>关键关系</h3>
                  <div>
                    {view.relationships.map((person) => (
                      <button
                        type="button"
                        key={person.id}
                        onClick={() => go({ name: "chat", id: person.chatId })}
                      >
                        <i
                          className={`v277-relation-photo ${person.photo} v277-sprite-community`}
                        >
                          <em>{person.name}</em>
                        </i>
                        <span>{person.role}</span>
                        {/* 和基础那两条同一套格式：状态 + 来源 */}
                        <small className={styles.rowSource}>已确认 · 来源：合作记录</small>
                      </button>
                    ))}
                  </div>
                  <footer>
                    {/* 这是"关系链的规模"，不是记忆条目数 —— 两者本来就不一样 */}
                    <span>
                      关系链规模：{view.relationshipStats.longTerm} 位长期合作者 ·{" "}
                      {view.relationshipStats.pending} 位待连接
                    </span>
                    <button
                      type="button"
                      onClick={() => go({ name: "utility", kind: "relationships" })}
                    >
                      查看关系图
                      <ChevronRight size={16} />
                    </button>
                  </footer>
                </article>
              )}

              <div className={styles.list}>
                {items.map((memory) => (
                  <button
                    type="button"
                    key={memory.id}
                    className={styles.row}
                    onClick={() => go({ name: "memory-detail", id: memory.id })}
                  >
                    <span className={styles.rowHead}>
                      <em className={styles.rowLabel}>{memory.label}</em>
                      <small className={styles.rowStatus}>
                        {["已确认","自动记录"].includes(memory.status) ? (
                          <CheckCircle2 size={12} />
                        ) : (
                          <CircleDashed size={12} />
                        )}
                        {memory.status}
                      </small>
                    </span>
                    <b className={styles.rowValue}>{memory.value || "待补充"}</b>
                    <small className={styles.rowSource}>来源：{memory.source}</small>
                  </button>
                ))}
                {items.length === 0 && (
                  <p className={styles.empty}>
                    <CircleDashed size={14} />
                    {/* 四个类统一一句，不再给社交单独写一套 */}
                    这一类还没有记忆，Elfred 会在任务里慢慢攒
                  </p>
                )}
              </div>
            </section>
          );
        })}
      </div>
      {alignmentOpen && (
        <UnderstandingSheet
          state={state}
          onClose={() => setAlignmentOpen(false)}
        />
      )}
    </main>
  );
}
