"use client";
// 第四页「动态」：**人发的**（社区里真人发的帖子）按时间排的时间轴。
// 版式照最初的设计稿：左边一列日期（08 / 9月），右边正文 + 配图 + 互动行。
//
//   · 数据就是社区那份 —— runtime 里的 `post` 对象（`author_type:'human'`、公开、
//     已发布 / 招募中 / 已结束），不另存一份，所以和社区永远一致；
//   · 点正文/配图 → 那条帖子详情（正文、评论都在它自己的地方，这里不复制）；
//   · 互动行是真操作：点赞（`post.interact: like`）、收藏（`: save`）、评论数（读真实评论），
//     不是装饰；
//   · 一条都没有就是空态，不拿演示数据顶。
//
// ⚠️ 这个文件不 import runtime 的类型：第二页/第四页在我自己那份单独跑的版本里没有 runtime，
// 用结构化类型两边都能编过（和 api/skill-launch.ts 一个做法）。
import {displayTitle} from "../../../core/display-labels";
import {Bookmark, Heart, MessageCircle, PenLine} from "lucide-react";
import type {Screen} from "../../../core/screen";
import styles from "../styles/profile.module.css";

type Ent = { id: string; owner?: string; visibility?: string; created?: string; data?: Record<string, unknown> };
type Runtimeish = {
  snapshot?: { objects?: Record<string, Ent[]> };
  command?: (action: string, input: Record<string, unknown>) => Promise<unknown>;
};
type Attachment = { id: string; name?: string; mime?: string };

/** 页面上最多摆这么多条，再多去社区看全部（不然第四页这一个页签能拉到天荒地老）。 */
const LIMIT = 10;
/** 还在人眼前的三态：已发布 / 招募中 / 已结束。撤回、草稿不算动态。 */
const LIVE_STATUS = ["published", "recruiting", "closed"];

const excerpt = (text: string, max: number) => (text.length > max ? `${text.slice(0, max)}…` : text);

function rowsOf(runtime: Runtimeish | undefined, hidden: string[]) {
  const snapshot = runtime?.snapshot;
  const objects = snapshot?.objects ?? {};
  const comments = objects.comment ?? [];
  const interactions = objects.interaction ?? [];
  const mine = (postId: string, kind: string) =>
    interactions.some((item) => item.data?.object_id === postId && item.data?.kind === kind && item.data?.active);
  return (objects.post ?? [])
    .filter(
      (item) =>
        item.visibility === "public" &&
        item.data?.author_type === "human" &&
        LIVE_STATUS.includes(String(item.data?.status ?? "")) &&
        !hidden.includes(item.id) &&
        !item.data?.hidden,
    )
    .sort((a, b) => String(b.created ?? "").localeCompare(String(a.created ?? "")))
    .map((item) => {
      const data = item.data ?? {};
      const title = String(data.title ?? "").trim();
      const body = String(data.content ?? "").trim();
      const image = ((data.attachments ?? []) as Attachment[]).find((file) => String(file.mime ?? "").startsWith("image/"));
      const liked = mine(item.id, "like");
      return {
        id: item.id,
        author: String(data.author_name ?? "").trim() || "社区成员",
        title: title || excerpt(body, 60) || "（这条动态没有正文）",
        body: title && body && body !== title ? excerpt(body, 80) : "",
        imageId: image?.id ?? "",
        at: String(item.created ?? ""),
        liked,
        saved: mine(item.id, "save"),
        likes: Number(data.likes ?? 0) + (liked ? 1 : 0),
        comments: comments.filter((comment) => comment.data?.post_id === item.id).length || Number(data.comments ?? 0),
      };
    });
}

function dateOf(at: string) {
  const when = new Date(at);
  if (Number.isNaN(when.getTime())) return { day: "--", month: "" };
  return {
    day: String(when.getDate()).padStart(2, "0"),
    month: `${when.getMonth() + 1}月`,
  };
}

export function PostTimeline({
  runtime,
  hidden,
  go,
}: {
  runtime?: unknown;
  /** 被用户隐藏过的动态（和社区同一份判断，别在这里又漏出来） */
  hidden: string[];
  go: (screen: Screen) => void;
}) {
  const live = runtime as Runtimeish | undefined;
  const rows = rowsOf(live, hidden);
  const command = live?.command;

  /** 点赞 / 收藏：走真实命令，状态由服务端回执刷新（本地不自己记一份） */
  const toggle = (id: string, kind: "like" | "save") => {
    if (!command) return;
    void command("post.interact", { id, kind }).catch(() => {});
  };

  if (rows.length === 0) {
    return (
      <div className={styles.timelineEmpty}>
        <i>
          <PenLine size={22} />
        </i>
        <b>还没有动态</b>
        <p>别人在社区发的东西，会出现在这里</p>
        <button type="button" onClick={() => go({ name: "community" })}>
          去社区看看
        </button>
      </div>
    );
  }

  return (
    <div className={styles.timeline}>
      {rows.slice(0, LIMIT).map((row) => {
        const { day, month } = dateOf(row.at);
        return (
          <article key={row.id} className={styles.timelineRow}>
            <div className={styles.timelineDate} aria-hidden="true">
              <b>{day}</b>
              <small>{month}</small>
            </div>
            <div className={styles.timelineBody}>
              <button
                type="button"
                className={styles.timelineText}
                onClick={() => go({ name: "community-post", id: row.id })}
                aria-label={`${row.title} · ${row.author}`}
              >
                <b>{displayTitle(row.title, "（这条动态没有正文）")}</b>
                {row.body ? <span>{row.body}</span> : null}
              </button>
              {row.imageId ? (
                <button
                  type="button"
                  className={styles.timelineImage}
                  onClick={() => go({ name: "community-post", id: row.id })}
                  aria-label="查看这条动态的配图"
                >
                  <img src={`/api/elfred/attachments/${row.imageId}`} alt="动态配图" loading="lazy" />
                </button>
              ) : null}
              {/* 互动行照设计稿：三格均分、各自靠左对齐（点赞 / 评论 / 收藏），
                  不在这一行里塞作者名 —— 这是"我的动态"，作者就是本人，写了反而是杂音 */}
              <footer className={styles.timelineActions}>
                <button
                  type="button"
                  className={row.liked ? styles.actionOn : undefined}
                  onClick={() => toggle(row.id, "like")}
                  aria-pressed={row.liked}
                  aria-label={`点赞：${row.likes}`}
                >
                  <Heart size={17} fill={row.liked ? "currentColor" : "none"} />
                  {row.likes > 0 ? <em>{row.likes}</em> : null}
                </button>
                <button
                  type="button"
                  onClick={() => go({ name: "community-post", id: row.id })}
                  aria-label={`查看评论：${row.comments}`}
                >
                  <MessageCircle size={17} />
                  {row.comments > 0 ? <em>{row.comments}</em> : null}
                </button>
                <button
                  type="button"
                  className={row.saved ? styles.actionOn : undefined}
                  onClick={() => toggle(row.id, "save")}
                  aria-pressed={row.saved}
                  aria-label={row.saved ? "取消收藏" : "收藏"}
                >
                  <Bookmark size={17} fill={row.saved ? "currentColor" : "none"} />
                  <em>收藏</em>
                </button>
              </footer>
            </div>
          </article>
        );
      })}
      {rows.length > LIMIT ? (
        <button type="button" className={styles.timelineMore} onClick={() => go({ name: "community" })}>
          去社区看全部 {rows.length} 条
        </button>
      ) : null}
    </div>
  );
}
