"use client";
import {displayTitle} from "../../../core/display-labels";

// 第四页最左边那一栏（原来叫「动态」）现在叫 **Agent 动态**：它是**总览**，
// 不是完整的动态流 —— 口径（用户 2026-09-26 定）：
//
//   · 内容就是同事那个「Agent 朋友圈」里的东西，**同一份数据源**（runtime 里的 feed 对象），
//     不另存一份、不搬一份快照，所以两边永远一致，不会出现"两个地方说法不一样"；
//   · 第四页只放"一眼看得完的总览"（和右边「能力」「勋章」两栏一个性质）：
//     看全部 → 朋友圈（`feed`），看单条 → 那条详情（`feed-detail`），
//     **具体内容还在它们各自的地方**，这里不复制正文；
//   · 一条都没有就是空态，不拿演示数据顶（同事那边的 `agentMoments` 兜底数据不许出现在这）。
//
// ⚠️ 这个文件故意不 import runtime 的类型：第二页/第四页在我自己那份单独跑的版本里没有 runtime，
// 用结构化类型两边都能编过（和 api/skill-launch.ts 一个做法）。
import { Brain, ChevronRight, Compass, Link2, Rocket, Sparkles } from "lucide-react";
import type { Screen } from "../../../core/screen";
import knowledgeStyles from "../styles/knowledge.module.css";
import styles from "../styles/profile.module.css";

type FeedEntity = { id: string; created?: string; data?: Record<string, unknown> };

/** 第四页只摆最近这几条；再多就"查看全部"去朋友圈。 */
const FEED_LIMIT = 3;

const AGENT_ICON = {
  explore: Compass,
  advisor: Brain,
  create: Sparkles,
  connect: Link2,
  execute: Rocket,
} as const;

const AGENT_NAME: Record<string, string> = {
  explore: "探索",
  advisor: "参谋",
  create: "创作",
  connect: "连接",
  execute: "执行",
};

/** 一条动态是哪个 Agent 发的。`system` 里"参谋"写的是 `advise`（同事那边的历史拼法），这里归一。 */
function agentKeyOf(item: FeedEntity) {
  const raw = String(item.data?.system ?? "");
  return raw === "advise" ? "advisor" : raw;
}

/** 从 runtime 里读朋友圈（只读、不改；按时间倒序）。runtime 不在（单独跑的那份）就返回空。 */
function rowsOf(runtime: unknown, hidden: string[]) {
  const snapshot = (runtime as { snapshot?: { objects?: Record<string, FeedEntity[]> } } | undefined)
    ?.snapshot;
  return (snapshot?.objects?.feed ?? [])
    .filter((item) => !hidden.includes(item.id) && item.data?.status === "active" && !item.data?.hidden)
    .sort((a, b) => String(b.created ?? "").localeCompare(String(a.created ?? "")))
    .map((item) => ({
      id: item.id,
      agent: agentKeyOf(item),
      title: String(item.data?.title ?? "").trim() || "（这条动态没写标题）",
      at: String(item.created ?? ""),
    }));
}

function dayOf(at: string) {
  const when = new Date(at);
  return Number.isNaN(when.getTime()) ? "" : when.toLocaleDateString("zh-CN");
}

export function AgentFeedOverview({
  runtime,
  hidden,
  go,
}: {
  runtime?: unknown;
  /** 被用户隐藏过的动态（和朋友圈同一份判断，别在这里又漏出来） */
  hidden: string[];
  go: (screen: Screen) => void;
}) {
  const rows = rowsOf(runtime, hidden);
  if (rows.length === 0) {
    return (
      <section className={knowledgeStyles.emptyBlock}>
        <i className={knowledgeStyles.emptyBlockIcon}>
          <Compass size={26} />
        </i>
        <b>还没有 Agent 动态</b>
        <p>五个 Agent 干活、发观点之后，会出现在这里</p>
        <button type="button" onClick={() => go({ name: "feed" })}>
          去朋友圈看看
        </button>
      </section>
    );
  }
  return (
    <div className={styles.agentFeed}>
      {/* 总览的入口行：一眼知道有多少条、点一下去朋友圈看全部 */}
      <button type="button" className={styles.agentFeedHead} onClick={() => go({ name: "feed" })}>
        <span>
          {/* 标题不再重复页签那三个字（页签就在正上方）：这里只说"有多少、摆了几条" */}
          <b>来自五个 Agent 的最新动态</b>
          <small>
            共 {rows.length} 条
            {rows.length > FEED_LIMIT ? ` · 这里只摆最近 ${FEED_LIMIT} 条` : ""}
          </small>
        </span>
        <em>查看全部</em>
        <ChevronRight size={16} />
      </button>
      <ul className={styles.cardList}>
        {rows.slice(0, FEED_LIMIT).map((row) => {
          const Icon = AGENT_ICON[row.agent as keyof typeof AGENT_ICON] ?? Sparkles;
          const name = `${AGENT_NAME[row.agent] ?? "Elfred"} Agent`;
          const day = dayOf(row.at);
          return (
            <li key={row.id}>
              <button
                type="button"
                aria-label={`${name} 的动态：${row.title}`}
                onClick={() => go({ name: "feed-detail", id: row.id })}
              >
                <i>
                  <Icon size={18} />
                </i>
                <span>
                  <b>{displayTitle(row.title,'')}</b>
                  <small>
                    {name}
                    {day ? ` · ${day}` : ""}
                  </small>
                </span>
                <ChevronRight size={16} />
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
