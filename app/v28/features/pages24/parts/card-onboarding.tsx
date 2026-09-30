"use client";

// 第一张能力卡的初始化：**分支选择树**。
//
// 每页 3 个选项，选完决定下一页问什么；路径上的每个选项除了指向某张卡，
// 还往这张卡的说明书里写"内容片段"，所以**同一张卡走不同路径 = 两份不同的 skill**。
// 题目 / 选项 / 片段都在 `core/card-onboarding.mjs`（服务端用同一份还原内容，不会两套真相）。
//
// 界面只有三层：**答题 → 确认（复述这一次的选择 + 它将是什么）→ 生成**。
// 2026-09-29 按反馈再收一遍：去掉「再细一点」与「看完整说明书」（确认页只留"是什么"），
// 去掉答题页的"自己说一句"出口（一页只有三个选项）。要按自己一句话生成，走接口的 `custom_text`。

import { useMemo, useState } from "react";
import { ArrowLeft, Loader2, RefreshCw, Sparkles, X } from "lucide-react";
import {
  CARD_QUESTIONS, SYSTEM_LABELS, composeSkillMarkdown, resolvePath,
} from "../../../core/card-onboarding.mjs";
import { onboardCards, type OnboardResult } from "../api/page2-api";
import { RootPortal } from "../../../legacy/legacy-ui";
import styles from "../styles/knowledge-library.module.css";

type QuestionOption = { id: string; label: string; next?: string; preset?: string; fragments?: string[] };
type Question = { id: string; title: string; options: QuestionOption[] };
type Preset = { id: string; system: string; title: string; canDo: string; deliver: string; custom?: boolean };

// 共用目录是 .mjs（前后端同一份），TS 在这里拿不到类型：只在这一层做一次断言，别处用到就是有类型的
const QUESTIONS = CARD_QUESTIONS as unknown as Record<string, Question>;

const systemLabel = (system: string) => (SYSTEM_LABELS as Record<string, string>)[system] || system;

/** 共用目录是 .mjs，TS 拿不到参数类型；在这里收一次口，别处调用就是有类型的 */
const composeMarkdown = composeSkillMarkdown as unknown as (
  preset: Preset,
  options: { fragments: { id: string }[] },
) => string;

/** 从根一路走下去，返回"现在该问哪一题"；node 为 null = 已经答完（或路径断了） */
function walk(ids: string[]) {
  let current: Question | null = QUESTIONS.root;
  for (const id of ids) {
    const option: QuestionOption | undefined = current?.options.find((item) => item.id === id);
    if (!option || !option.next) return { node: null };
    current = QUESTIONS[option.next] ?? null;
    if (!current) return { node: null };
  }
  return { node: current };
}

export function CardOnboarding({
  onClose,
  onOpenCard,
}: {
  onClose: () => void;
  /** 生成完成后想直接看某张卡（页面用它打开卡片详情） */
  onOpenCard?: (title: string) => void;
}) {
  const [answers, setAnswers] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<OnboardResult | null>(null);

  const { node } = walk(answers);
  const resolved = useMemo(() => resolvePath(answers) as unknown as {
    ok: boolean; reason?: string; preset: Preset | null;
    fragments: { id: string }[]; trail: { question: string; label: string }[];
  }, [answers]);

  /** 确认页显示的那句"交付什么"：由路径片段算出来，不是卡片模板里的默认值 */
  const preview = useMemo(() => {
    if (!resolved.ok || !resolved.preset) return null;
    const markdown = composeMarkdown(resolved.preset, { fragments: resolved.fragments });
    const deliver = markdown.split("## 交付什么\n")[1]?.split("\n## ")[0]?.trim() || resolved.preset.deliver;
    return { preset: resolved.preset, deliver, trail: resolved.trail };
  }, [resolved]);

  const generate = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      setResult(await onboardCards({ path: answers }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "生成没成功，稍后再试");
    } finally {
      setBusy(false);
    }
  };

  const restart = () => {
    setResult(null);
    setAnswers([]);
    setError("");
  };

  const stepLabel = result ? "完成" : node ? `第 ${answers.length + 1} 步` : "确认";
  const heading = result ? "已经生成好了" : node?.title || "即将生成";

  return (
    <RootSheet onClose={onClose}>
      <header className={styles.onboardHead}>
        <span className={styles.onboardStepTag}>{stepLabel}</span>
        <h2>{heading}</h2>
        <button type="button" aria-label="关闭" className={styles.onboardClose} onClick={onClose}>
          <X size={20} />
        </button>
      </header>

      <div className={styles.onboardBody}>
        {/* ① 答题：每页 3 个选项，选完决定下一页 */}
        {!result && node && (
          <>
            <section className={styles.onboardGroup}>
              <div className={styles.onboardCards}>
                {node.options.map((option) => (
                  <button
                    type="button"
                    key={option.id}
                    aria-pressed={false}
                    className={styles.onboardCard}
                    onClick={() => {
                      setError("");
                      setAnswers((current) => [...current, option.id]);
                    }}
                  >
                    <b>{option.label}</b>
                  </button>
                ))}
              </div>
            </section>
            {answers.length > 0 && (
              <div className={styles.onboardFooter}>
                <button
                  type="button"
                  className={styles.onboardGhost}
                  onClick={() => setAnswers((current) => current.slice(0, -1))}
                >
                  <ArrowLeft size={15} />
                  上一步
                </button>
              </div>
            )}
          </>
        )}

        {/* ② 确认：复述这次的选择 + 它是什么、交付什么 */}
        {!result && !node && preview && (
          <>
            <p className={styles.onboardTrail}>
              你要的是：{preview.trail.map((item) => item.label).join(" → ")}
            </p>
            <div className={styles.onboardPreview}>
              <article className={styles.onboardPreviewCard}>
                <span className={styles.onboardPreviewSystem}>{systemLabel(preview.preset.system)}</span>
                <b>{preview.preset.title}</b>
                <p>{preview.preset.canDo}</p>
                <small>交付：{preview.deliver}</small>
              </article>
            </div>
            <p className={styles.onboardNote}>
              生成后是 <b>Lv.1、0 项成果</b>；分数只由你<strong>验收过</strong>的结果往上走。
            </p>
            {error && <p className={styles.onboardError}>{error}</p>}
            <div className={styles.onboardFooter}>
              <button
                type="button"
                className={styles.onboardGhost}
                disabled={busy}
                onClick={() => setAnswers((current) => current.slice(0, -1))}
              >
                <ArrowLeft size={15} />
                上一步
              </button>
              <button type="button" className={styles.onboardPrimary} onClick={() => void generate()} disabled={busy}>
                {busy ? <Loader2 size={16} className={styles.onboardSpin} /> : <Sparkles size={16} />}
                {busy ? "正在生成…" : "生成这张卡"}
              </button>
            </div>
          </>
        )}

        {/* ③ 完成 */}
        {result && (
          <>
            <p className={styles.onboardNote}>
              已经放进能力卡组（Lv.1、0 项成果）。点开它就能用它做一件事。
            </p>
            <div className={styles.onboardPreview}>
              {result.created.map((item) => (
                <button
                  type="button"
                  key={item.skill_id}
                  className={styles.onboardPreviewCard}
                  onClick={() => onOpenCard?.(item.title)}
                >
                  <span className={styles.onboardPreviewSystem}>{systemLabel(item.system)}</span>
                  <b>{item.title}</b>
                  <small>点开看它的说明与用法</small>
                </button>
              ))}
            </div>
            {result.skipped.length > 0 && (
              <p className={styles.onboardNote}>
                已经有的是这些，没有重复生成：{result.skipped.map((item) => item.title).join("、")}
              </p>
            )}
            {result.notes.map((note) => (
              <p key={note} className={styles.onboardNote}>{note}</p>
            ))}
            <div className={styles.onboardFooter}>
              <button type="button" className={styles.onboardGhost} onClick={restart}>
                <RefreshCw size={15} />
                再来一张
              </button>
              <button type="button" className={styles.onboardPrimary} onClick={onClose}>
                看我的能力卡组
              </button>
            </div>
          </>
        )}
      </div>
    </RootSheet>
  );
}

/**
 * 用项目里那套"共用底部弹层"（RootPortal + `v278-sheet-backdrop` + `v279-setting-sheet`）：
 * 卡片详情、设置面板都是这套，它挂到设备层、层级稳；自己写 fixed + z-index 会被底部导航盖住
 * （第一版就是这么翻的车：按钮在，但点不到）。
 */
function RootSheet({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <RootPortal>
      <button type="button" className="v278-sheet-backdrop" aria-label="关闭能力卡初始化" onClick={onClose} />
      <section className={`v279-setting-sheet ${styles.onboardSheet}`} role="dialog" aria-modal="true" aria-label="做一张能力卡">
        <i className="v278-sheet-handle" />
        {children}
      </section>
    </RootPortal>
  );
}
