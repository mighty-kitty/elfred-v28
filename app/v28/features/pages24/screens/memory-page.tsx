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
import {
  SHOW_RESERVED_ACTIONS,
  archiveMemory,
  fetchHygiene,
  type LiveHygiene,
} from "../api/page2-api";
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
  // 记忆体检：后端有接口（`/page2/memory/hygiene`）但界面原来没有入口，这里补一个真入口。
  // 只读一遍候选，点"归档"才真的动数据（走 `/page2/memory/{id}/archive`，可 restore 回滚）。
  const [hygiene, setHygiene] = useState<LiveHygiene | null>(null);
  const [hygieneBusy, setHygieneBusy] = useState(false);
  const [hygieneNote, setHygieneNote] = useState("");

  const runHygiene = async () => {
    setHygieneBusy(true);
    const result = await fetchHygiene();
    setHygiene(result);
    setHygieneNote(
      result?.available
        ? `体检过一遍：长期未用 ${result.stale.length} · 低置信 ${result.lowConfidence.length} · 没标签 ${result.untagged.length}`
        : "记忆体检暂时不可用（后端没连上或 EMOS 没起）",
    );
    setHygieneBusy(false);
  };

  const archive = async (memoryId: string) => {
    const result = await archiveMemory(memoryId, "记忆体检：用户手动归档");
    setHygieneNote(result?.ok ? "已归档（可在记忆历史里恢复）" : "归档没成功，稍后再试");
    if (result?.ok) await runHygiene();
  };
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
              <b>{view.totalCount}</b> 已确认的记忆
            </span>
            <span>
              {/* 这一格以前是"7 天有确认记录"，中间换过一版叫"覆盖类别"（四类记忆有着落几类）。
                  "覆盖类别"这个词不是一眼能懂的，评审时被问了两遍，所以按原样回到"持续更新"。 */}
              <b>{view.daysTracked > 0 ? view.daysTracked : "—"}</b> 天持续更新
            </span>
            <span>
              <b className="elfred-stat-label">{view.memories.filter(m=>m.status!=="已确认").length}</b> 条待核对
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
            <em className={knowledgeStyles.emptyNote}>只记你确认过的，随时可以改</em>
          </section>
        )}

        {/* 记忆体检：**预留功能，默认不展示**（产品说现阶段只做闭环、不加新入口）。
            代码留着，把 SHOW_RESERVED_ACTIONS 打开就会出来。 */}
        {SHOW_RESERVED_ACTIONS && !isEmpty && (
          <section className={styles.hygiene}>
            <div className={styles.hygieneHead}>
              <h2>记忆体检</h2>
              <button
                type="button"
                className={styles.hygieneRun}
                onClick={() => void runHygiene()}
                disabled={hygieneBusy}
              >
                {hygieneBusy ? "正在体检…" : "体检一遍"}
              </button>
            </div>
            {hygieneNote ? <p className={styles.hygieneNote}>{hygieneNote}</p> : null}
            {hygiene?.available &&
              ([
                ["长期未用", hygiene.stale],
                ["低置信", hygiene.lowConfidence],
                ["没标签", hygiene.untagged],
              ] as const).map(([label, items]) =>
                items.length ? (
                  <div key={label} className={styles.hygieneGroup}>
                    <b>
                      {label} · {items.length} 条
                    </b>
                    {items.map((item) => (
                      <div key={item.id} className={styles.hygieneItem}>
                        <span>{(item.text || "").slice(0, 60)}</span>
                        <button type="button" onClick={() => void archive(item.id)}>
                          归档
                        </button>
                      </div>
                    ))}
                  </div>
                ) : null,
              )}
            {hygiene?.available &&
              hygiene.stale.length + hygiene.lowConfidence.length + hygiene.untagged.length === 0 && (
                <p className={styles.hygieneNote}>这次没有需要过问的记忆。</p>
              )}
            {/* 冲突这一类后端一直是空的：EMOS 的 active_conflict_scan 还没接。
                不写清的话，用户会把"没列出来"当成"没有冲突"。 */}
            {hygiene?.available ? (
              <p className={styles.hygieneNote}>
                冲突检测还没接（EMOS 的 active_conflict_scan 未开），所以这里只列长期未用 / 低置信 / 没标签。
              </p>
            ) : null}
          </section>
        )}

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
                        {memory.status === "已确认" ? (
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
          go={go}
          onClose={() => setAlignmentOpen(false)}
        />
      )}
    </main>
  );
}
