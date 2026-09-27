"use client";
import {displayTitle} from "../../../core/display-labels";

import {
  useEffect,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import {
  ChevronRight,
  Layers3,
  Settings as GearIcon,
  Share2,
  Sparkles,
} from "lucide-react";
import type { V277State } from "../../../../v27-7-state";
import type { Screen } from "../../../core/screen";
import { ProfileShareSheet } from "../../../legacy/legacy-ui";
import knowledgeStyles from "../styles/knowledge.module.css";
import {
  abilityInsight,
  hasLiveAlignment,
  libraryHeader,
  abilityCardSamples,
  readAlignmentStage,
  readStage,
} from "../data/knowledge-data";
import { CapabilitySheet, type SheetCard } from "../parts/capability-sheet";
import { AgentFeedOverview } from "../parts/agent-feed-overview";
import { UnderstandingSheet } from "../parts/understanding-sheet";
import { maskHandle, shownNameOf } from "../data/identity";
import { readPage2, setCardLevel, setPendingSkill } from "../api/page2-store";
import { launchWithSkill } from "../api/skill-launch";
import {
  fetchBadges,
  fetchFeed,
  fetchProfile,
  usePage2Live,
  type LiveBadge,
  type LiveFeedItem,
  type LiveProfile,
} from "../api/page2-api";
import styles from "../styles/profile.module.css";

// 昵称 / 账号怎么显示：规则都在 `data/identity.ts`（和编辑资料、设置共用一份，别各写一套）

export function ProfilePage({
  state,
  setState,
  go,
  notify,
  initialShareOpen = false,
  runtime,
}: {
  state: V277State;
  setState: Dispatch<SetStateAction<V277State>>;
  go: (screen: Screen) => void;
  notify: (text: string) => void;
  /** 整合版由 app-shell 传入；只用来把「用它做一件事」的契约写进对话草稿。 */
  runtime?: unknown;
  initialShareOpen?: boolean;
}) {
  const profile = state.profile;
  // ⚠️ 必须订阅/启动第二页的数据：不然"先打开『我的』"时后端根本不会被调用，
  // 能力栏会一直显示本地演示卡（实测踩到）。usePage2Live 既启动加载又订阅变更。
  usePage2Live();
  // 名字旁边那个胶囊跟"理解度"那条线（不是卡片等级）。
  // 后端没给理解度时按第一档显示——**不能拿演示兜底值当用户真等级**（新用户不是 Lv.4）。
  const level = hasLiveAlignment ? libraryHeader.level : 1;
  const stageName = readAlignmentStage(level);
  // 最左边那栏：原来叫「动态」，现在是 **Agent 动态 的总览**（用户 2026-09-26 定的）。
  const [tab, setTab] = useState("Agent 动态");
  const [shareOpen, setShareOpen] = useState(initialShareOpen);
  // 理解度那格点开的面板（和页头那个胶囊同一个组件，口径一致）
  const [understandingOpen, setUnderstandingOpen] = useState(false);

  // ── 身份区要显示的四件事 ────────────────────────────────────────────
  // 名字/账号：昵称空（或就是账号）→ 说"点击设置称呼"，账号一律遮蔽。
  const handle = maskHandle(profile.username || "");
  const realName = shownNameOf(profile.name, profile.username || "");
  // 能力 tab 里点开的那张卡（详情弹层和第二页那个是同一个组件）
  const [selectedCard, setSelectedCard] = useState<SheetCard | null>(null);
  // 改过等级之后要重画（等级存在 page2 的本地 store 里，不是 React state）
  const [cardVersion, setCardVersion] = useState(0);
  const cardStore = readPage2();
  const myCards = abilityCardSamples.map((card) => ({
    ...card,
    level: cardStore.levelOverride[card.title] ?? card.level,
  }));
  // ── 后端接线（第四页原来是纯本地状态：资料、动态、勋章都不落库）──
  // 读：进页面拉一次真资料/动态/勋章；写：本地改过的资料回到这一页时同步给后端。
  const [feed, setFeed] = useState<LiveFeedItem[] | null>(null);
  const [badges, setBadges] = useState<LiveBadge[] | null>(null);
  const [liveProfile, setLiveProfile] = useState<LiveProfile | null>(null);
  const showLevel = profile.showLevel;
  const hasRuntime = Boolean((runtime as { snapshot?: unknown } | undefined)?.snapshot);
  useEffect(() => {
    let alive = true;
    void Promise.all([fetchProfile(), hasRuntime ? Promise.resolve(null) : fetchFeed(), fetchBadges()])
      .then(([live, liveFeed, liveBadges]) => {
        if (!alive) return;
        setLiveProfile(live);
        if (liveFeed?.items) setFeed(liveFeed.items);
        if (liveBadges?.badges) setBadges(liveBadges.badges);
      });
    return () => { alive = false; };
  }, [profile, hasRuntime]);

  // 数字条四格 —— 每一格都**真有落点**，没有装饰性按钮：
  //   成果 → 成果列表（第二页那条二级屏）· 能力卡 → 本页"能力"页签
  //   勋章 → 荣誉勋章页 · 理解度 → 理解度弹层（档位/差多少/解释）
  const stats = [
    { label: "成果", value: abilityInsight.outcomeCount, suffix: "", open: () => go({ name: "evidence" }) },
    { label: "能力卡", value: myCards.length, suffix: "", open: () => setTab("能力") },
    {
      label: "勋章",
      value: badges ? badges.filter((badge) => badge.earned).length : 0,
      suffix: badges && badges.length ? `/${badges.length}` : "",
      open: () => go({ name: "utility", kind: "honors" }),
    },
    ...(showLevel
      ? [{
          label: "理解度",
          value: hasLiveAlignment ? libraryHeader.alignment : 0,
          suffix: "%",
          open: () => setUnderstandingOpen(true),
        }]
      : []),
  ];

  return (
    <main className="v277-page v277-profile-page">
      <section
        className={`v277-profile-hero ${styles.hero}`}
        aria-label="我的个人主页"
      >
        {/* 封面：没设过就是淡蓝渐变（不拿网图顶）。右上角是**设置**入口 ——
            原来这里是"设置背景"的提示胶囊，它和「编辑资料 → 主页形象 → 更换封面」重复，
            而且点了没用（不是按钮）。现在换成真能打开设置页的按钮。 */}
        <div className={styles.cover} style={liveProfile?.background ? { backgroundImage: `url(${liveProfile.background})`, backgroundSize: "cover", backgroundPosition: "center" } : undefined}>
          <button
            type="button"
            className={styles.settingsBtn}
            aria-label="个人设置"
            onClick={() => go({ name: "settings" })}
          >
            <GearIcon size={15} />
            设置
          </button>
        </div>

        {/* 头像压在封面下沿（行业通用做法），名字/账号/简介/标签跟着它走 */}
        <div className={styles.identity}>
          <button
            type="button"
            className={styles.avatar}
            style={liveProfile?.avatar ? { backgroundImage: `url(${liveProfile.avatar})`, backgroundSize: "cover", backgroundPosition: "center" } : undefined}
            aria-label="编辑资料 · 换头像"
            onClick={() => go({ name: "profile-edit" })}
          >
            {liveProfile?.avatar ? null : realName ? (
              realName.slice(0, 1).toUpperCase()
            ) : (
              // 没有名字时的人形默认头像（不用网图：不依赖网络、无版权问题）
              <svg viewBox="0 0 24 24" width="34" height="34" aria-hidden="true">
                <path
                  fill="currentColor"
                  d="M12 12a4.2 4.2 0 1 0 0-8.4 4.2 4.2 0 0 0 0 8.4Zm0 2.1c-3.3 0-6.3 1.8-6.3 4v1.5h12.6v-1.5c0-2.2-3-4-6.3-4Z"
                />
              </svg>
            )}
          </button>

          <h1 className={styles.name}>
            {/* 没起过名字就是默认名「路人」（`realNameOf` 里定的），不再摆"点击设置称呼"那句提示 */}
            {realName}
            {/* 关掉「展示等级与能力」之后，这一颗就不显示（开关真的生效） */}
            {showLevel ? (
              <span className={styles.levelChip}>
                Lv.{level} · {stageName}
              </span>
            ) : null}
          </h1>
          {handle ? <p className={styles.handle}>@{handle}</p> : null}

          {/* 简介：就是小红书那种"点击这里，填写简介"的可点占位句 */}
          <button
            type="button"
            className={`${styles.bio} ${profile.bio ? "" : styles.bioEmpty}`}
            onClick={() => go({ name: "profile-edit" })}
          >
            {profile.bio || "点击这里，填写简介"}
          </button>

          <div className={styles.tags}>
            {profile.tags.length > 0 ? (
              profile.tags.map((tag) => <span key={tag}>{tag}</span>)
            ) : null}
            <button
              type="button"
              className={styles.tagAdd}
              onClick={() => go({ name: "profile-edit" })}
            >
              + 标签
            </button>
          </div>

          {/* 数字条：成果 / 能力卡 / 勋章 / 理解度 —— 每一格都真的能点进去，
              没有任何一个数是写死的：成果来自 /insight/abilities 的 outcomeCount、
              卡来自能力卡组、勋章来自 /page2/badges、理解度来自 /alignment。
              四个数全是 0 时整条不显示（不摆 0 0 0 0 撑着好看）。 */}
          {stats.some((item) => item.value > 0) ? (
            <ul className={styles.stats}>
              {stats.map((item) => (
                <li key={item.label}>
                  <button type="button" onClick={item.open} aria-label={`${item.label}：${item.value}${item.suffix}`}>
                    <b>
                      {item.value}
                      {item.suffix}
                    </b>
                    <span>{item.label}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}

          <div className={styles.actions}>
            <button
              type="button"
              className={styles.editBtn}
              onClick={() => go({ name: "profile-edit" })}
            >
              编辑资料
            </button>
            <button
              type="button"
              className={styles.shareBtn}
              aria-label="分享个人主页"
              onClick={() => setShareOpen(true)}
            >
              <Share2 size={18} />
            </button>
          </div>
        </div>
      </section>
      <section className="v277-profile-body">
        <nav className="v277-profile-tabs">
          {["Agent 动态", "能力", "勋章"].map((name) => (
            <button
              type="button"
              key={name}
              className={tab === name ? "active" : ""}
              onClick={() => setTab(name)}
            >
              {name}
            </button>
          ))}
        </nav>
        {tab === "Agent 动态" ? (
          /* 整合版：Agent 动态 = 朋友圈那份数据的**总览**（看全部去朋友圈、看单条去详情，
             具体内容仍在它们各自的地方）。有 runtime 就一律走这条，哪怕它一条都没有 ——
             那才是"朋友圈确实没动态"的空态，不能拿别的流顶上。 */
          hasRuntime ? (
            <AgentFeedOverview runtime={runtime} hidden={state.hiddenPostIds} go={go} />
          ) : feed && feed.length > 0 ? (
            // 没有 runtime（我们自己单独跑的那份）时的退路：还是后端把"成果 + 记忆"
            // 按时间合并的流。整合版走不到这里。
            <ul className={styles.feed}>
              {feed.map((item) => (
                <li key={`${item.kind}-${item.id}`} className={styles.feedItem}>
                  <b>{displayTitle(item.title,'')}</b>
                  {item.detail ? <p>{item.detail}</p> : null}
                  <span className={styles.feedMeta}>
                    {item.kind === "evidence" ? "成果" : "记忆"}
                    {item.count && item.count > 1 ? ` · 共 ${item.count} 次` : ""}
                    {item.at ? ` · ${item.at.replace("T", " ").slice(0, 16)}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            // 空态：后端确实没有动态时才这么显示（原来这里硬编码过一条假动态）
            <section className={knowledgeStyles.emptyBlock}>
              <i className={knowledgeStyles.emptyBlockIcon}>
                <Sparkles size={26} />
              </i>
              <b>还没有动态</b>
              <p>你做过的事被验收之后，会在这里留下一条</p>
            </section>
          )
        ) : tab === "能力" ? (
          /* 第四页的"能力"这一栏以前只是一张"去知识库看看"的跳转卡 ——
             那等于第四页什么都看不见。现在直接把用户的能力卡摆在这里，
             点开就是第二页那张详情（同一个 CapabilitySheet，同一份数据）。 */
          myCards.length > 0 ? (
            <ul className={styles.cardList}>
              {myCards.map((card) => {
                const Icon = card.icon;
                return (
                  <li key={card.title}>
                    <button
                      type="button"
                      onClick={() => setSelectedCard(card)}
                      aria-label={`${card.title}：${card.type}，Lv.${card.level} ${readStage(card.level)}`}
                    >
                      <i>
                        <Icon size={18} />
                      </i>
                      <span>
                        <b>{displayTitle(card.title,'')}</b>
                        <small>
                          {card.type} · Lv.{card.level} {readStage(card.level)}
                        </small>
                      </span>
                      <em>{card.notRunYet ? (card.evidence ? "待评估" : "证据不足") : card.score}</em>
                      <ChevronRight size={16} />
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : (
            <section className={knowledgeStyles.emptyBlock}>
              <i className={knowledgeStyles.emptyBlockIcon}>
                <Layers3 size={26} />
              </i>
              <b>还没有能力卡</b>
              <p>你让 Agent 干成的事，会沉淀成一张张能力卡</p>
            </section>
          )
        ) : (
          <button
            type="button"
            className="v277-profile-tab-card"
            onClick={() => go({ name: "utility", kind: "honors" })}
          >
            <span>
              <Sparkles size={24} />
            </span>
            <h2>成长勋章</h2>
            <p>
              {badges
                ? `已获得 ${badges.filter((badge) => badge.earned).length}/${badges.length} 枚，点击查看荣誉。`
                : "记录每一次被验证的成长，点击查看荣誉。"}
            </p>
            <ChevronRight size={18} />
          </button>
        )}
      </section>
      {shareOpen && (
        <ProfileShareSheet
          state={state}
          setState={setState}
          onClose={() => setShareOpen(false)}
          notify={notify}
        />
      )}
      {selectedCard && (
        <CapabilitySheet
          key={cardVersion}
          card={selectedCard}
          go={go}
          onClose={() => setSelectedCard(null)}
          onOpenEvidence={(evidenceId) => {
            setSelectedCard(null);
            go({ name: "evidence-detail", id: evidenceId });
          }}
          onOpenEvidenceList={() => {
            setSelectedCard(null);
            go({ name: "evidence" });
          }}
          onCreateTask={async (card, goal) => {
            // ⚠️ 2026-09-26 对齐你们的新契约：`launchWithSkill` 现在返回 system + prompt，
            //    直接带着可编辑的 prefill 进那个 Agent 的会话（我们原来那版是 conversationId）。
            const result = await launchWithSkill(runtime, card.id||card.title, goal);
            if (result.ok && result.system && result.prompt) {
              setPendingSkill(card.title);
              setSelectedCard(null);
              go({ name: "chat", id: result.system, prefill: result.prompt });
              return { ok: true };
            }
            return { ok: false, note: result.note };
          }}
          tasks={state.tasks}
          onUpgrade={(card) => {
            setCardLevel(card.title, card.level + 1);
            setCardVersion((version) => version + 1);
            setSelectedCard({ ...card, level: card.level + 1 });
          }}
        />
      )}
      {/* 理解度那格点开的面板：和页头那个胶囊是同一个组件，说法一致（档位 / 差多少 / 怎么涨） */}
      {understandingOpen && (
        <UnderstandingSheet
          state={state}
          go={go}
          empty={!hasLiveAlignment}
          onClose={() => setUnderstandingOpen(false)}
        />
      )}
    </main>
  );
}
