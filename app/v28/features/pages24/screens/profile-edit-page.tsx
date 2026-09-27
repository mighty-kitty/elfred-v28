"use client";
import {displayTitle} from "../../../core/display-labels";

// 编辑资料（第四页 →「编辑资料」）。
//
// 为什么自己写一份：这一屏原来在 legacy 里，字段全挤在一页、每个字段就是一行输入框，
// 顶部还有一个"总共保存一次"的按钮 —— 改一个字段要记得点保存，改完忘了就白改。
//
// 调研出来的做法（小红书/抖音/微信/Instagram 都一样）：
//   · 主页面只放**形象（封面+头像）**和**字段行**；
//   · **点一个字段 → 单独编辑**（小红书那边是整屏「编辑简介」，有字数上限和自己的保存）；
//   · 账号（小红书号/微信号）只读、灰显，不给改；
//   · 可见性开关（我们这里是「展示等级与能力」）必须**真的生效**。
//
// 所以这一版：每个字段点开是一个底部弹层，弹层里点保存 → **立刻落库**（不再有"总保存"这种坑）。
// 头像/封面选完即存。

import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { Camera, Check, ChevronRight, Eye, EyeOff, UserRound } from "lucide-react";
import type { V277State } from "../../../../v27-7-state";
import type { Screen } from "../../../core/screen";
import { AppHeader, RootPortal } from "../../../legacy/legacy-ui";
import { fetchProfile, saveProfile } from "../api/page2-api";
import { DEFAULT_NAME, isAutoName, shownNameOf } from "../data/identity";
import styles from "../styles/profile-edit.module.css";

type Sheet = "name" | "bio" | "tags" | null;

// ⚠️ 图片限制和 legacy 那版保持一致（250KB，走 data URL 存进 profile）：
//    不是为了省流量，是因为它跟着 profile.save 一起走，太大对方那边也存不下。
const MAX_IMAGE_BYTES = 250_000;
const BIO_LIMIT = 64;
const TAG_LIMIT = 4;
// 领域标签**是选出来的，不是手打的**（小红书/抖音/标签选择器都是这个做法：预设一堆 chips，
// 点了变选中，右上角写清"最多可选几个"，下面列已选）。
// 分组只是为了扫得快，先给"我在做什么"，再给"我在哪一行"。
const TAG_GROUPS: { title: string; tags: string[] }[] = [
  { title: "我在做什么", tags: ["产品", "设计", "研发", "数据", "运营", "市场", "写作", "研究", "项目管理", "学生"] },
  { title: "我在哪一行", tags: ["AI", "教育", "金融", "医疗", "法律", "咨询", "内容创作", "硬件", "创业"] },
];

export function ProfileEditPage({
  state,
  setState,
  go,
  onBack,
  notify,
  runtime,
}: {
  state: V277State;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
  go: (screen: Screen) => void;
  onBack: () => void;
  notify: (text: string) => void;
  runtime?: unknown;
}) {
  const [profile, setProfile] = useState(state.profile);
  const [sheet, setSheet] = useState<Sheet>(null);
  const [draft, setDraft] = useState("");
  const [draftTags, setDraftTags] = useState<string[]>([]);
  const [cover, setCover] = useState("");
  const [avatar, setAvatar] = useState("");
  const [busy, setBusy] = useState(false);
  const coverInput = useRef<HTMLInputElement>(null);
  const avatarInput = useRef<HTMLInputElement>(null);
  useEffect(() => { setProfile(state.profile); }, [state.profile]);

  // 媒体和等级偏好读取同一登录会话；未完成读取时沿用当前资料值。
  const [levelPref, setLevelPref] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    void fetchProfile().then((data) => {
      if (alive && data?.available) {
        setLevelPref(data.showLevel ?? state.profile.showLevel);
        setCover(data.background);
        setAvatar(data.avatar);
      }
    });
    return () => {
      alive = false;
    };
  }, []);

  const account = (profile.username || "").replace(/^@/, "");
  /** 昵称没起过、或者就是登录账号（手机号/邮箱前缀，注册时自动填的）→ 显示默认名「路人」 */
  const nameIsAccount = isAutoName(profile.name || "", profile.username || "");
  const shownName = shownNameOf(profile.name || "", profile.username || "");
  const showLevel = levelPref ?? profile.showLevel;

  /** 等待一次 profile.save 成功，再合并本次修改的字段。 */
  const persist = async (patch: Partial<V277State["profile"]>, extra: { cover?: string; avatar?: string } = {}) => {
    if (busy) return false;
    setBusy(true);
    try {
      if (runtime) await saveProfile({
        ...patch,
        ...(patch.name !== undefined ? { name: patch.name || DEFAULT_NAME } : {}),
        ...(extra.cover !== undefined ? { background: extra.cover } : {}),
        ...(extra.avatar !== undefined ? { avatar: extra.avatar } : {}),
      });
      if (Object.keys(patch).length) {
        setProfile((current) => ({ ...current, ...patch }));
        setState((current) => ({ ...current, profile: { ...current.profile, ...patch } }));
      }
      if (typeof patch.showLevel === "boolean") setLevelPref(patch.showLevel);
      if (extra.cover !== undefined) setCover(extra.cover);
      if (extra.avatar !== undefined) setAvatar(extra.avatar);
      return true;
    } catch (error) {
      notify(error instanceof Error ? error.message : "保存失败，请重试");
      return false;
    } finally {
      setBusy(false);
    }
  };

  const takeImage = (event: ChangeEvent<HTMLInputElement>, kind: "cover" | "avatar") => {
    const file = event.target.files?.[0];
    event.target.value = "";                      // 同一个文件再选一次也要能触发
    if (!file) return;
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
      notify("请选择 PNG / JPEG / WebP 图片");
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      notify("图片要小于 250 KB，支持 PNG / JPEG / WebP");
      return;
    }
    const reader = new FileReader();
    reader.onload = async () => {
      const data = String(reader.result);
      if (await persist({}, kind === "cover" ? { cover: data } : { avatar: data }))
        notify(kind === "cover" ? "封面已更新" : "头像已更新");
    };
    reader.onerror = () => notify("图片读取失败，请重新选择");
    reader.readAsDataURL(file);
  };

  const openSheet = (which: Exclude<Sheet, null>) => {
    // 昵称弹层：没起过名字就留空（占位是「路人」），别把手机号塞进输入框让人以为那是名字
    if (which === "name") setDraft(nameIsAccount ? "" : profile.name || "");
    if (which === "bio") setDraft(profile.bio || "");
    if (which === "tags") setDraftTags(profile.tags.slice(0, TAG_LIMIT));
    setSheet(which);
  };

  const toggleTag = (tag: string) => {
    setDraftTags((current) => {
      if (current.includes(tag)) return current.filter((item) => item !== tag);
      if (current.length >= TAG_LIMIT) return current;      // 到上限就只提示不硬塞
      return [...current, tag];
    });
  };

  const coverImage = cover || "";
  const avatarImage = avatar || "";

  return (
    <main className="v277-page v279-profile-edit-page">
      <AppHeader title="编辑资料" onBack={onBack} />

      {/* ── 主页形象：封面 + 头像，点哪块改哪块 ───────────────────────── */}
      <section className={styles.section}>
        <h2>主页形象</h2>
        <button
          type="button"
          className={styles.cover}
          onClick={() => coverInput.current?.click()}
          aria-label="更换封面"
          style={coverImage ? { backgroundImage: `url(${coverImage})` } : undefined}
          data-has-image={coverImage ? "true" : undefined}
        >
          <span className={styles.coverAction}>
            <Camera size={15} />
            {coverImage ? "更换封面" : "上传封面"}
          </span>
        </button>
        <div className={styles.avatarRow}>
          <button
            type="button"
            className={styles.avatar}
            onClick={() => avatarInput.current?.click()}
            aria-label="更换头像"
            style={avatarImage ? { backgroundImage: `url(${avatarImage})` } : undefined}
            data-has-image={avatarImage ? "true" : undefined}
          >
            {avatarImage ? null : shownName ? (
              <b>{shownName.slice(0, 1).toUpperCase()}</b>
            ) : (
              <UserRound size={26} />
            )}
            <i className={styles.avatarBadge}>
              <Camera size={12} />
            </i>
          </button>
          <button type="button" className={styles.avatarHint} onClick={() => avatarInput.current?.click()}>
            更换头像
          </button>
        </div>
        <input ref={coverInput} type="file" accept="image/*" hidden onChange={(event) => takeImage(event, "cover")} />
        <input ref={avatarInput} type="file" accept="image/*" hidden onChange={(event) => takeImage(event, "avatar")} />
      </section>

      {/* ── 个人信息：一行一个字段，点开单独编辑 ─────────────────────── */}
      <section className={styles.section}>
        <h2>个人信息</h2>
        <button type="button" className={styles.row} onClick={() => openSheet("name")}>
          <span>昵称</span>
          <b className={nameIsAccount ? styles.rowEmpty : ""}>{shownName}</b>
          <ChevronRight size={16} />
        </button>
        <div className={`${styles.row} ${styles.rowReadOnly}`}>
          <span>用户名</span>
          <b>@{account || "还没有"}</b>
          <em>登录账号，不可修改</em>
        </div>
        <button type="button" className={styles.row} onClick={() => openSheet("bio")}>
          <span>个人简介</span>
          <b className={profile.bio ? "" : styles.rowEmpty}>
            {profile.bio || "你是谁、擅长什么、正在做什么"}
          </b>
          <ChevronRight size={16} />
        </button>
        <button type="button" className={styles.row} onClick={() => openSheet("tags")}>
          <span>领域标签</span>
          <b className={profile.tags.length ? "" : styles.rowEmpty}>
            {profile.tags.length ? profile.tags.join("、") : `最多 ${TAG_LIMIT} 个`}
          </b>
          <ChevronRight size={16} />
        </button>
      </section>

      {/* ── 主页展示：开关是真的生效（关掉之后主页不显示等级/理解度）───── */}
      <section className={styles.section}>
        <h2>主页展示</h2>
        <button
          type="button"
          className={`${styles.row} ${styles.rowToggle}`}
          aria-pressed={showLevel}
          disabled={busy}
          onClick={async () => {
            if (await persist({ showLevel: !showLevel })) notify(
              showLevel
                ? "主页不再显示等级与理解度"
                : "主页会显示你的等级与理解度",
            );
          }}
        >
          <span>
            展示等级与能力
            <small>
              {showLevel
                ? "主页上会显示「Lv.x · 阶段」和理解度"
                : "主页上不显示等级与理解度（只看得到你自己）"}
            </small>
          </span>
          <i className={`${styles.switch} ${showLevel ? styles.switchOn : ""}`}>
            {showLevel ? <Eye size={14} /> : <EyeOff size={14} />}
          </i>
        </button>
      </section>

      <p className={styles.footNote}>
        这里改的只有「别人能不能看到你」的那部分。私人记忆、任务和对话，任何情况下都不会公开。
        <button type="button" onClick={() => go({ name: "memory" })}>
          去看它记住了什么
        </button>
      </p>

      {/* ── 单字段编辑（小红书那种"点一个字段，单独改一个"）────────────── */}
      {sheet && (
        <RootPortal>
          <button
            type="button"
            className="v278-sheet-backdrop"
            aria-label="关闭编辑"
            onClick={() => setSheet(null)}
          />
          <section className={styles.sheet} role="dialog" aria-modal="true">
            <i className="v278-sheet-handle" />
            <header className={styles.sheetHead}>
              <h2>
                {sheet === "name" ? "改个称呼" : sheet === "bio" ? "个人简介" : "领域标签"}
              </h2>
              <button
                type="button"
                className={styles.sheetSave}
                disabled={busy}
                onClick={async () => {
                  const patch = sheet === "name" ? { name: draft.trim() || DEFAULT_NAME }
                    : sheet === "bio" ? { bio: draft.trim().slice(0, BIO_LIMIT) }
                    : { tags: draftTags.slice(0, TAG_LIMIT) };
                  if (await persist(patch)) {
                    setSheet(null);
                    notify("已保存");
                  }
                }}
              >
                保存
              </button>
            </header>

            {sheet === "name" ? (
              <>
                <input
                  className={styles.sheetInput}
                  value={draft}
                  autoFocus
                  maxLength={24}
                  placeholder={DEFAULT_NAME}
                  onChange={(event) => setDraft(event.target.value)}
                />
                <p className={styles.sheetNote}>留空就显示「{DEFAULT_NAME}」；主页上的账号是遮蔽过的。</p>
              </>
            ) : sheet === "bio" ? (
              <>
                <textarea
                  className={styles.sheetArea}
                  value={draft}
                  autoFocus
                  maxLength={BIO_LIMIT}
                  placeholder="你是谁、擅长什么、正在做什么"
                  onChange={(event) => setDraft(event.target.value)}
                />
                <p className={styles.sheetCount}>
                  {draft.length}/{BIO_LIMIT}
                </p>
              </>
            ) : (
              <>
                <p className={styles.tagCount}>
                  已选 {draftTags.length}/{TAG_LIMIT}
                </p>
                {TAG_GROUPS.map((group) => (
                  <div key={group.title} className={styles.tagGroup}>
                    <h3>{displayTitle(group.title,'')}</h3>
                    <div className={styles.tagOptions}>
                      {group.tags.map((tag) => {
                        const picked = draftTags.includes(tag);
                        return (
                          <button
                            key={tag}
                            type="button"
                            className={`${styles.tagOption} ${picked ? styles.tagOptionOn : ""}`}
                            aria-pressed={picked}
                            onClick={() => toggleTag(tag)}
                          >
                            {picked ? <Check size={13} /> : null}
                            {tag}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
                {/* 以前手打过的标签不在预设里 —— 也列出来，别让用户以为它丢了 */}
                {draftTags.some((tag) => !TAG_GROUPS.some((group) => group.tags.includes(tag))) ? (
                  <div className={styles.tagGroup}>
                    <h3>你已经有的</h3>
                    <div className={styles.tagOptions}>
                      {draftTags
                        .filter((tag) => !TAG_GROUPS.some((group) => group.tags.includes(tag)))
                        .map((tag) => (
                          <button
                            key={tag}
                            type="button"
                            className={`${styles.tagOption} ${styles.tagOptionOn}`}
                            aria-pressed
                            onClick={() => toggleTag(tag)}
                          >
                            <Check size={13} />
                            {tag}
                          </button>
                        ))}
                    </div>
                  </div>
                ) : null}
                <p className={styles.sheetNote}>
                  点一下选中、再点一下取消；到 {TAG_LIMIT} 个之后要先取消一个才能换。
                </p>
              </>
            )}
          </section>
        </RootPortal>
      )}

    </main>
  );
}
