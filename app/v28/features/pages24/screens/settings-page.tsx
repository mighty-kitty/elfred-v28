"use client";

// 设置页（第四页进）。
//
// 为什么自己写一份：原来这个屏在 legacy 里，**入口是 hero 上一块隐形热区**（opacity:0），
// 所以用户根本不知道有设置；而且弹出的分组自己也说不清"哪些是真的、哪些是占位"。
// 这版按调研（docs/调研-个人页与设置-20260926.md §6）重排，规矩就三条：
//
//   1. **每一行都有真落点**：要么跳一个真页面（编辑资料 / 记忆库），要么开一个能改东西的面板
//      （面板内容是同事那套真命令 `ConnectedSettings`，我们只是把它按人话分组），
//      要么就是**说明文字**（说明行右侧不带箭头、也不做成按钮的样子）。
//   2. **不摆假开关**：没做出来的能力只写状态（比如"外观：当前浅色"），不给可点的假选项。
//   3. **破坏性动作单独一组**：退出登录在最下面、要二次确认。
//
// 没有 runtime（我们那份单独跑的版本）时：行还是在，面板里如实说"要连上 Elfred 主服务才能改"，
// 不糊一份假界面给他点。

import { useEffect, useState, type ReactNode } from "react";
import {
  ChevronRight,
  Database,
  HelpCircle,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  UserRound,
} from "lucide-react";
import type { V277State } from "../../../../v27-7-state";
import type { Screen } from "../../../core/screen";
import { AppHeader, RootPortal } from "../../../legacy/legacy-ui";
import { SettingsPanel } from "../parts/settings-panels";
import {
  fetchProfile,
  type LiveProfile,
} from "../api/page2-api";
import {
  hasLiveAlignment,
  libraryHeader,
} from "../data/knowledge-data";
import {useRuntime} from '../../../core/runtime-context';
import {memoryOverview} from '../../../core/agent-alignment.mjs';
import { buildMemoryView } from "../data/memory-data";
import { shownNameOf } from "../data/identity";
import { UnderstandingSheet } from "../parts/understanding-sheet";
import styles from "../styles/settings.module.css";

// ⚠️ 没有 "appearance"：外观还没做切换，那一行是**只读**的（不摆假开关，见调研文档 §6.2）
type PanelKey = "account" | "notifications" | "privacy" | "data" | "help";

const PANEL_TITLE: Record<PanelKey, string> = {
  account: "账号与身份",
  notifications: "通知",
  privacy: "隐私与授权",
  data: "数据与额度",
  help: "帮助与反馈",
};

export function SettingsPage({
  state,
  go,
  logout,
  runtime,
  notify,
}: {
  state: V277State;
  go: (screen: Screen) => void;
  logout: () => void;
  /** 整合版由 app-shell 传；没有它（我们那份单独跑的版本）时，面板里如实说明，不糊假界面 */
  runtime?: unknown;
  notify: (text: string) => void;
}) {
  const [panel, setPanel] = useState<PanelKey | null>(null);
  const [understandingOpen, setUnderstandingOpen] = useState(false);
  const [logoutOpen, setLogoutOpen] = useState(false);
  const [live, setLive] = useState<LiveProfile | null>(null);

  // 后端那份真数据：个人资料（昵称/简介）。拿不到就保持 null —— 行里显示本地那份，不编数字。
  //
  // 上游服务状态（EMOS / Skill Foundry / 网关 / Jev 探活与"有没有真用上"）**只留在后端**：
  // `GET /api/elfred/health/deps` 还在，排查时直接打这个接口；设置页不再摆那一栏 ——
  // 普通用户看不懂那几个服务名，看到了也没法处理。
  useEffect(() => {
    let alive = true;
    void (async () => {
      const profile = await fetchProfile();
      if (!alive) return;
      if (profile?.available) setLive(profile);
    })();
    return () => {
      alive = false;
    };
  }, []);

  const rawName = (live?.name || state.profile.name || "").trim();
  // ⚠️ LiveProfile 里**没有** handle 字段（只有 name/bio/tags/…）：账号仍需从本地 state 取
  const account = (state.profile.username || "").replace(/^@/, "").trim();
  const name = shownNameOf(rawName, state.profile.username || "");
  const handle = account ? `@${account}` : "";
  const memoryCount = buildMemoryView(state.memories).totalCount;
  const memoryRuntime=useRuntime();
  // 这一行叫「理解度」，就得显示理解度。以前它显示的是 `memoryOverview().label`——
  // 那是"记忆领域覆盖"（N/5 个领域有记录），和页头那个百分比根本不是一回事，
  // 同一个设置页里两条口径并列，用户会以为是两套数。领域覆盖挪到下面"记忆与理解"那一行去说。
  const memoryCoverage = memoryOverview(memoryRuntime?.snapshot?.objects.memory || []).label;
  const alignmentValue = hasLiveAlignment ? `${libraryHeader.alignment}% · Lv.${libraryHeader.level}` : "还没有数据";

  return (
    <main className="v277-page v279-settings-page">
      <AppHeader title="设置" onBack={() => go({ name: "profile" })} />

      {/* 顶部本人卡片 → 编辑资料（小红书那种"设置里也能改资料"的做法） */}
      <button type="button" className={styles.me} onClick={() => go({ name: "profile-edit" })}>
        <span className={styles.avatar}>{name.slice(0, 1).toUpperCase()}</span>
        <span>
          <b>{name}</b>
          {handle ? <small>{handle}</small> : null}
        </span>
        <em>编辑资料</em>
        <ChevronRight size={18} />
      </button>

      <section className={styles.group}>
        <h2>账号与身份</h2>
        <Row
          icon={<UserRound size={19} />}
          title="昵称、简介与标签"
          value={name || "待设置"}
          onClick={() => go({ name: "profile-edit" })}
        />
        <Row
          icon={<ShieldCheck size={19} />}
          title="登录方式"
          value={handle ? `${handle} · 会话最长 7 天` : "账号密码登录"}
          readOnly
        />
        <Row
          icon={<SlidersHorizontal size={19} />}
          title="时区"
          value="保存后，日报与提醒按它算"
          onClick={() => setPanel("account")}
        />
      </section>

      <section className={styles.group}>
        <h2>Elfred 对我的理解</h2>
        <Row
          icon={<Sparkles size={19} />}
          title="理解度"
          value={alignmentValue}
          onClick={() => setUnderstandingOpen(true)}
        />
        <Row
          icon={<Database size={19} />}
          title="记忆与理解"
          value={memoryCount ? `已确认 ${memoryCount} 条 · ${memoryCoverage}` : "还没有记忆"}
          onClick={() => go({ name: "memory" })}
        />
      </section>

      <section className={styles.group}>
        <h2>隐私与授权</h2>
        <Row
          icon={<ShieldCheck size={19} />}
          title="主页公开范围与授权"
          value="默认只有你自己能看到"
          onClick={() => setPanel("privacy")}
        />
      </section>

      <section className={styles.group}>
        <h2>数据与额度</h2>
        <Row
          icon={<Database size={19} />}
          title="模型、额度与数据导出"
          value="本地调用配额，不代表人民币"
          onClick={() => setPanel("data")}
        />
      </section>

      <section className={styles.group}>
        <h2>使用偏好</h2>
        <Row
          icon={<SlidersHorizontal size={19} />}
          title="通知与免打扰"
          value={state.notifications ? "站内提醒已开启" : "站内提醒已关闭"}
          onClick={() => setPanel("notifications")}
        />
        {/* 外观还没做切换 —— 按"不摆假开关"的规矩，这里只写状态、不做成按钮 */}
        <Row icon={<Sparkles size={19} />} title="外观" value="当前：浅色" readOnly />
      </section>

      <section className={styles.group}>
        <h2>帮助与反馈</h2>
        <Row
          icon={<HelpCircle size={19} />}
          title="帮助、反馈与数据说明"
          value=""
          onClick={() => setPanel("help")}
        />
      </section>

      <p className={styles.version}>Elfred V28 · 本机数据保存在你自己的机器上</p>
      <button type="button" className={styles.logout} onClick={() => setLogoutOpen(true)}>
        退出登录
      </button>

      {/* ── 面板（底部升起，和能力卡详情同一个形式）────────────────────── */}
      {panel && (
        <RootPortal>
          <button
            type="button"
            className="v278-sheet-backdrop"
            aria-label="关闭设置选项"
            onClick={() => setPanel(null)}
          />
          <section className="v279-setting-sheet" role="dialog" aria-modal="true">
            <i className="v278-sheet-handle" />
            <header className="v279-sheet-title">
              <h2>{PANEL_TITLE[panel]}</h2>
              <button type="button" className={styles.close} aria-label="关闭" onClick={() => setPanel(null)}>
                ✕
              </button>
            </header>
            <SettingsPanel panel={panel} runtime={runtime} go={go} notify={notify} />
          </section>
        </RootPortal>
      )}

      {understandingOpen && (
        <UnderstandingSheet
          state={state}
          go={go}
          empty={!hasLiveAlignment}
          onClose={() => setUnderstandingOpen(false)}
        />
      )}

      {logoutOpen && (
        <RootPortal>
          <button
            type="button"
            className="v278-sheet-backdrop"
            aria-label="关闭退出确认"
            onClick={() => setLogoutOpen(false)}
          />
          <section className="v279-setting-sheet" role="dialog" aria-modal="true">
            <i className="v278-sheet-handle" />
            <header className="v279-sheet-title">
              <h2>退出登录？</h2>
              <button type="button" className={styles.close} aria-label="关闭" onClick={() => setLogoutOpen(false)}>
                ✕
              </button>
            </header>
            <p className={styles.confirmNote}>
              退出后已保存的数据仍在，重新登录能看到原来的能力卡、成果与记忆。
            </p>
            <button type="button" className={styles.danger} onClick={logout}>
              退出登录
            </button>
            <button type="button" className={styles.cancel} onClick={() => setLogoutOpen(false)}>
              再想想
            </button>
          </section>
        </RootPortal>
      )}
    </main>
  );
}

/** 一行：有 onClick 才画箭头、才做成按钮；只读行就是个静态行（免得看起来能点）。 */
function Row({
  icon,
  title,
  value,
  onClick,
  readOnly = false,
}: {
  icon: ReactNode;
  title: string;
  value: string;
  onClick?: () => void;
  readOnly?: boolean;
}) {
  if (readOnly || !onClick) {
    return (
      <div className={`${styles.row} ${styles.rowReadOnly}`}>
        <i className={styles.rowIcon}>{icon}</i>
        <b>{title}</b>
        {value ? <small>{value}</small> : <span />}
      </div>
    );
  }
  return (
    <button type="button" className={styles.row} onClick={onClick}>
      <i className={styles.rowIcon}>{icon}</i>
      <b>{title}</b>
      {value ? <small>{value}</small> : <span />}
      <ChevronRight size={16} className={styles.rowArrow} />
    </button>
  );
}
