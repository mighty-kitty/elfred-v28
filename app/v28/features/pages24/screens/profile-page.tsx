"use client";
import {useRuntime} from '../../../core/runtime-context';
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
import {
  alignmentView,
  abilityCardSamples,
  readAlignmentStage,
  readStage,
} from "../data/knowledge-data";
import { CapabilitySheet, type SheetCard } from "../parts/capability-sheet";
import { PostTimeline } from "../parts/post-timeline";
import { HonorGallery } from "../parts/honor-gallery";
import { UnderstandingSheet } from "../parts/understanding-sheet";
import { maskHandle, shownNameOf } from "../data/identity";
import { launchWithSkill } from "../api/skill-launch";
import {
  fetchFeed,
  fetchProfile,
  usePage2Live,
  type LiveFeedItem,
  type LiveProfile,
} from "../api/page2-api";
import styles from "../styles/profile.module.css";

// 昵称 / 账号怎么显示：规则都在 `data/identity.ts`（和编辑资料、设置共用一份，别各写一套）
//
// 版式口径（2026-09-28，老板定的）：**照最初那版设计稿的骨架**做——
// 封面照片 → 头像压在下沿 → 名字 + 理解度胶囊 → @账号 → 简介 → 标签 →
// 数字条 + 编辑资料 → 白色圆角面板（动态 / 能力 / 勋章）。
// 空态不是另换一套"空块"：骨架一模一样，没设过的位置是可点的占位句，
// 数字条照实显示 0，动态那一栏给一段引导。老板说的"用最初版的布局做空态"就是这个意思。

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
  /** 整合版由 app-shell 传入；用来发社区帖子、把「用它做一件事」的契约写进对话草稿。 */
  runtime?: unknown;
  initialShareOpen?: boolean;
}) {
  const profile = state.profile;
  // ⚠️ 必须订阅/启动第二页的数据：不然"先打开『我的』"时后端根本不会被调用，
  // 能力栏会一直显示本地演示卡（实测踩到）。usePage2Live 既启动加载又订阅变更。
  usePage2Live();
  // 名字旁边那个胶囊跟"理解度"那条线（不是卡片等级）。
  // 后端没给理解度时按第一档显示——**不能拿演示兜底值当用户真等级**（新用户不是 Lv.4）。
  const memoryRuntime=useRuntime();
  // 最左边那栏：**动态**（人发的，社区那份数据；用户 2026-09-28 定的口径，
  // 之前误做成了「Agent 动态」= 朋友圈）。
  const [tab, setTab] = useState("动态");
  const [shareOpen, setShareOpen] = useState(initialShareOpen);
  // 理解度那格点开的面板（和页头那个胶囊同一个组件，口径一致）
  const [understandingOpen, setUnderstandingOpen] = useState(false);

  // ── 身份区要显示的四件事 ────────────────────────────────────────────
  // 名字/账号：昵称空（或就是账号）→ 说"点击设置称呼"，账号一律遮蔽。
  const handle = maskHandle(profile.username || "");
  const realName = shownNameOf(profile.name, profile.username || "");
  // 能力 tab 里点开的那张卡（详情弹层和第二页那个是同一个组件）
  const [selectedCard, setSelectedCard] = useState<SheetCard | null>(null);
  const myCards = abilityCardSamples.map((card) => ({ ...card }));
  // ── 后端接线（第四页原来是纯本地状态：资料、动态、勋章都不落库）──
  // 读：进页面拉一次真资料/动态/勋章；写：本地改过的资料回到这一页时同步给后端。
  const [feed, setFeed] = useState<LiveFeedItem[] | null>(null);
  const [liveProfile, setLiveProfile] = useState<LiveProfile | null>(null);
  const hasRuntime = Boolean((runtime as { snapshot?: unknown } | undefined)?.snapshot);
  // 「展示等级与理解度」：没设过 = 默认展示（设计稿里名字旁边就有这一颗）；
  // 用户明确关掉才不显示 —— 不然新账号第一眼是光头名字，和设计稿不一样。
  const rawShowLevel = memoryRuntime?.snapshot?.objects.profile?.[0]?.data.showLevel;
  const showLevel = hasRuntime ? (rawShowLevel === undefined ? true : rawShowLevel === true) : profile.showLevel;
  // 名字旁边那颗胶囊：**理解度那条线**（初见 → 可托付）。和页头胶囊、理解度弹层
  // 读的是同一个 `alignmentView()`；后端没给数时它就是第一档（Lv.1），
  // 不会拿演示兜底值当用户真等级（新用户不是 Lv.4）。
  const trustLevel = alignmentView().level;
  useEffect(() => {
    let alive = true;
    void Promise.all([fetchProfile(), hasRuntime ? Promise.resolve(null) : fetchFeed()])
      .then(([live, liveFeed]) => {
        if (!alive) return;
        setLiveProfile(live);
        if (liveFeed?.items) setFeed(liveFeed.items);
      });
    return () => { alive = false; };
  }, [profile, hasRuntime]);

  // 数字条：**关注 / 粉丝 / 获赞**（照设计稿那一套）。
  //   三个数都由服务端聚合（粉丝和获赞是别人对我的动作，前端看不到别人的互动记录）：
  //   bootstrap 里的 `social`，全部来自真实对象，没有就是 0，不编数。
  //   关注 → 社区（那一栏就是"你关注的人"）· 粉丝 → 关系 · 获赞没有对应的一屏，就不假装能点。
  const social = memoryRuntime?.snapshot?.social;
  const stats: { label: string; value: number; open?: () => void }[] = [
    { label: "关注", value: social?.following ?? 0, open: () => go({ name: "community" }) },
    { label: "粉丝", value: social?.followers ?? 0, open: () => go({ name: "utility", kind: "relationships" }) },
    { label: "获赞", value: social?.likes ?? 0 },
  ];
  // 新账号三个数都是 0：照实显示（不摆假数据），但用弱一档的颜色，不装成成绩。
  const statsAllZero = stats.every((item) => !item.value);
  const cover = liveProfile?.background || "";
  const avatar = liveProfile?.avatar || "";

  return (
    <main className={`v277-page v277-profile-page ${styles.page}`}>
      <section
        className={styles.hero}
        data-cover={cover ? "photo" : "none"}
        aria-label="我的个人主页"
      >
        {/* 封面：设过就贴用户自己的图；没设过是淡蓝渐变（不拿网图顶）。
            用 <img> 不用 background-image —— 公共样式里有一条
            `.phone-stage *{background-image:none!important}`，背景图会被整条干掉。 */}
        {cover ? <img className={styles.coverImg} src={cover} alt="" /> : null}
        {cover ? <span className={styles.coverScrim} aria-hidden="true" /> : null}

        <div className={styles.coverActions}>
          <button
            type="button"
            className={styles.iconBtn}
            aria-label="分享个人主页"
            onClick={() => setShareOpen(true)}
          >
            <Share2 size={18} />
          </button>
          <button
            type="button"
            className={styles.iconBtn}
            aria-label="个人设置"
            onClick={() => go({ name: "settings" })}
          >
            <GearIcon size={18} />
          </button>
        </div>

        {/* 头像在左、信息在右 —— 照设计稿：名字 + 理解度胶囊同一行，下面依次是
            @账号 / 简介 / 标签。头像和这块信息竖直居中（左边那张脸对着一整块字）。 */}
        <div className={styles.identity}>
          <button
            type="button"
            className={styles.avatar}
            style={avatar ? { backgroundImage: `url(${avatar})`, backgroundSize: "cover", backgroundPosition: "center" } : undefined}
            aria-label="编辑资料 · 换头像"
            onClick={() => go({ name: "profile-edit" })}
          >
            {avatar ? null : realName ? (
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

          <div className={styles.info}>
            <div className={styles.headline}>
              <h1 className={styles.name}>
                {/* 没起过名字就是默认名「路人」（`realNameOf` 里定的），不再摆"点击设置称呼"那句提示 */}
                {realName}
              </h1>
              {/* 关掉「展示等级与能力」之后，这一颗就不显示（开关真的生效） */}
              {showLevel ? (
                <button
                  type="button"
                  className={styles.levelChip}
                  onClick={() => setUnderstandingOpen(true)}
                  aria-label={`理解度：Lv.${trustLevel} ${readAlignmentStage(trustLevel)}`}
                >
                  Lv.{trustLevel} · {readAlignmentStage(trustLevel)}
                </button>
              ) : null}
            </div>
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
              {profile.tags.map((tag) => (
                <span key={tag}>{tag}</span>
              ))}
              <button
                type="button"
                className={styles.tagAdd}
                onClick={() => go({ name: "profile-edit" })}
              >
                + 标签
              </button>
            </div>
          </div>
        </div>

        {/* 数字条：成果 / 能力卡 / 勋章 / 理解度 —— 每一格都真的能点进去，
            没有任何一个数是写死的：成果来自 /insight/abilities 的 outcomeCount、
            卡来自能力卡组、勋章来自 /page2/badges、理解度来自 /alignment。
            四个数全是 0 时照实显示 0（弱一档的颜色），不摆假数据撑着。 */}
        <div className={styles.heroFoot}>
          <ul className={`${styles.stats} ${statsAllZero ? styles.statsZero : ""}`}>
            {stats.map((item) => (
              <li key={item.label}>
                {/* 有落点的（关注 / 粉丝）才做成按钮；"获赞"没有对应的一屏，就给个纯数字，
                    不做假按钮 */}
                {item.open ? (
                  <button type="button" onClick={item.open} aria-label={`${item.label}：${item.value}`}>
                    <b>{item.value}</b>
                    <span>{item.label}</span>
                  </button>
                ) : (
                  <div className={styles.statPlain}>
                    <b>{item.value}</b>
                    <span>{item.label}</span>
                  </div>
                )}
              </li>
            ))}
          </ul>
          <button
            type="button"
            className={styles.editBtn}
            onClick={() => go({ name: "profile-edit" })}
          >
            编辑资料
          </button>
        </div>
      </section>

      <section className={styles.sheet}>
        <nav className={styles.tabs} aria-label="个人主页分类">
          {["动态", "能力", "勋章"].map((name) => (
            <button
              type="button"
              key={name}
              data-on={tab === name}
              onClick={() => setTab(name)}
            >
              {name}
            </button>
          ))}
        </nav>
        {tab === "动态" ? (
          /* 动态 = **社区里人发的帖子**，按最初设计稿的时间轴排（左日期 / 右正文+配图+互动）。
             有 runtime 就一律走这条，哪怕一条都没有 —— 那才是"社区确实还没人发"的空态，
             不能拿 Agent 朋友圈或别的流顶上。 */
          hasRuntime ? (
            <PostTimeline runtime={runtime} hidden={state.hiddenPostIds} go={go} />
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
            <div className={styles.timelineEmpty}>
              <i>
                <Sparkles size={22} />
              </i>
              <b>还没有动态</b>
              <p>你做过的事被验收之后，会在这里留下一条</p>
            </div>
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
            <div className={styles.tabEmpty}>
              <i>
                <Layers3 size={22} />
              </i>
              <b>还没有能力卡</b>
              <p>你让 Agent 干成的事，会沉淀成一张张能力卡</p>
            </div>
          )
        ) : (
          /* 勋章这一栏：和第二页理解度弹层里那一栏是**同一个 HonorGallery**、
             同一份 /page2/badges —— 同一个用户在两处看到同一套勋章。 */
          <div className={styles.honors}>
            <HonorGallery />
          </div>
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
            // 同第二页：说明书挂成输入框上方的附件卡，输入框留给用户自己写话。
            const result = await launchWithSkill(runtime, card.id||card.title, goal);
            if (result.ok && result.system && result.attach) {
              setSelectedCard(null);
              go({ name: "chat", id: result.system, attach: result.attach });
              return { ok: true };
            }
            return { ok: false, note: result.note };
          }}
          tasks={state.tasks}
        />
      )}
      {/* 理解度那格点开的面板：和页头那个胶囊是同一个组件，说法一致（档位 / 差多少 / 怎么涨） */}
      {understandingOpen && (
        <UnderstandingSheet
          state={state}
          onClose={() => setUnderstandingOpen(false)}
        />
      )}
    </main>
  );
}
