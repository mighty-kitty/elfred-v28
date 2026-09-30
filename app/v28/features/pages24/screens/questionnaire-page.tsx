"use client";

// 「轻量测试」：新用户填一份短问卷，得到**五维的起点**。
//
// 两条口径写在最前面，改这个文件之前先看：
//  1. 答完就有一张起始的五维图（数值低），之后按真实表现慢慢更新、也会回落 ——
//     它不是"不计入综合分"的自评，也不是成绩；界面只如实说"这是起点"；
//  2. 题目与选项**都由后端给**（改题不用发前端），选项顺序就是分值顺序（低 → 高）；
//     题面里有反向计分的题，所以"一路点同意"不会被算成"全都强"。
//
// 交互照人格测试那种感觉：一次一题、进度可见、可回退；最后给一眼"你的起点"。

import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { Screen } from "../../../core/screen";
import { fetchQuestionnaire, submitQuestionnaire, type Questionnaire } from "../api/page2-api";
import styles from "../styles/questionnaire.module.css";

export function QuestionnairePage({
  go,
  onBack,
}: {
  go: (screen: Screen) => void;
  onBack: () => void;
}) {
  const [paper, setPaper] = useState<Questionnaire | null>(null);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState("");
  const [result, setResult] = useState<Record<string, number> | null>(null);

  useEffect(() => {
    let alive = true;
    void fetchQuestionnaire().then((data) => {
      if (!alive) return;
      if (!data?.items?.length) setFailed("题目没取到 —— 后端没起来或这版没配问卷");
      else setPaper(data);
    });
    return () => {
      alive = false;
    };
  }, []);

  // ── 完成页：给起点，并说清它会怎么变 ────────────────────────────────
  if (result) {
    const dims = Object.entries(result);
    return (
      <main className={styles.wrap}>
        <header className={styles.head}>
          <button type="button" className={styles.back} onClick={onBack} aria-label="返回">
            <ChevronLeft size={20} />
          </button>
          <h1>你的起点</h1>
          <span />
        </header>
        <section className={styles.card}>
          <b>
            这是你的起点
            <span className={styles.tag}>起跑线</span>
          </b>
          <div className={styles.result}>
            {dims.map(([name, value]) => (
              <div key={name}>
                <span>{name}</span>
                <span className={styles.track}>
                  <i style={{ width: `${Math.max(4, Math.min(100, value))}%` }} />
                </span>
                <b>{Math.round(value)}</b>
              </div>
            ))}
          </div>
          <p className={styles.hint}>
            数值偏低是正常的：它只是坐标系的起点。接下来你跟它做事情、确认结果，
            这几维就按真实表现往上走；做得不好、或者很久不碰，也会回落。
          </p>
        </section>
        <div className={`${styles.foot} ${styles.footSingle}`}>
          <button type="button" data-primary="true" onClick={() => go({ name: "knowledge" })}>
            去看看我的能力洞察
          </button>
        </div>
      </main>
    );
  }

  if (failed) {
    return (
      <main className={styles.wrap}>
        <header className={styles.head}>
          <button type="button" className={styles.back} onClick={onBack} aria-label="返回">
            <ChevronLeft size={20} />
          </button>
          <h1>轻量测试</h1>
          <span />
        </header>
        <section className={styles.card}>
          <b>现在做不了这份测试</b>
          <p className={styles.hint}>{failed}</p>
        </section>
        <div className={`${styles.foot} ${styles.footSingle}`}>
          <button type="button" data-primary="true" onClick={onBack}>
            先回去
          </button>
        </div>
      </main>
    );
  }

  const item = paper?.items[index];
  const total = paper?.items.length ?? 0;
  const picked = item ? answers[item.id] : undefined;
  const last = index === total - 1;

  const finish = async () => {
    if (!paper) return;
    setBusy(true);
    const payload = paper.items.map((row) => ({ id: row.id, choice: answers[row.id] ?? 0 }));
    const outcome = await submitQuestionnaire(payload);
    setBusy(false);
    if (outcome?.ok && outcome.axes) setResult(outcome.axes);
    else setFailed(outcome?.note || "提交没成功，稍后再试");
  };

  return (
    <main className={styles.wrap}>
      <header className={styles.head}>
        <button type="button" className={styles.back} onClick={onBack} aria-label="返回">
          <ChevronLeft size={20} />
        </button>
        <h1>轻量测试</h1>
        <span />
      </header>

      <div className={styles.progress}>
        <span>
          <em>{`第 ${Math.min(index + 1, total || 1)} / ${total || 22} 题`}</em>
          <em>{paper ? `${Object.keys(answers).length} 题已答` : "正在取题…"}</em>
        </span>
        <span className={styles.bar}>
          <i style={{ width: `${total ? ((index + 1) / total) * 100 : 0}%` }} />
        </span>
      </div>

      {item ? (
        <section className={styles.card}>
          <b>{item.text}</b>
          <div className={styles.options}>
            {item.options.map((option, choice) => (
              <button
                key={option}
                type="button"
                className={styles.option}
                aria-pressed={picked === choice}
                onClick={() => setAnswers((prev) => ({ ...prev, [item.id]: choice }))}
              >
                {option}
              </button>
            ))}
          </div>
        </section>
      ) : (
        <section className={styles.card}>
          <b>正在取题…</b>
        </section>
      )}

      <div className={styles.foot}>
        <button type="button" onClick={() => setIndex((i) => Math.max(0, i - 1))} disabled={index === 0}>
          上一步
        </button>
        <button
          type="button"
          data-primary="true"
          disabled={picked === undefined || busy}
          onClick={() => (last ? void finish() : setIndex((i) => i + 1))}
        >
          {busy ? "提交中…" : last ? "完成" : "下一步"}
          {last ? null : <ChevronRight size={16} />}
        </button>
      </div>
      <p className={styles.hint}>大约 1–2 分钟。答完就有起点，之后按真实结果更新。</p>
    </main>
  );
}
