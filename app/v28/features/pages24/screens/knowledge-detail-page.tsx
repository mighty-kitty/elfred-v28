"use client";

import {MarkdownContent} from '../../../core/markdown-content';
import { useState, type Dispatch, type SetStateAction } from "react";
import { ArrowRight, BookOpen, ListChecks, Plus, Sparkles } from "lucide-react";
import type { V277State } from "../../../../v27-7-state";
import type { Screen } from "../../../core/screen";
import { AppHeader, type KnowledgeItem } from "../../../legacy/legacy-ui";
import { draftTask } from "../api/task-draft";
import { createCapability, getPage2State } from "../api/page2-api";
import styles from "../styles/knowledge.module.css";

// 知识详情（第二页自带，替代 legacy 那份）。
// 改动点只有一个：**原来底部那个灰按钮"当前没有可推进任务"变成了两个真动作**——
//   ① 用它做个任务：把资料作为来源创建持久任务草稿
//   ② 固化成能力卡：保存并启用本人可使用的工具
export function KnowledgeDetailPage({
  item,
  go,
  onBack,
  setState,
}: {
  item: KnowledgeItem;
  go: (screen: Screen) => void;
  onBack: () => void;
  setState: Dispatch<SetStateAction<V277State>>;
}) {
  const [confirming, setConfirming] = useState(false);
  const [drafted, setDrafted] = useState(false);
  const [error, setError] = useState("");
  const fixedTitle = getPage2State().data.skills?.find(skill => skill.title === item.title)?.title;

  const useIt = async () => {
    setError("");
    try {
    const id = await draftTask(setState, {
      title: `用「${item.title}」做一件事`,
      brief: item.purpose,
      source: `知识 · ${item.title}`,
      agent: "advisor",
      knowledgeIds: [item.id],
    });
    setDrafted(true);
    go({ name: "task", id });
    } catch (cause) { setDrafted(false); setError(cause instanceof Error ? cause.message : "任务暂时无法创建"); }
  };

  const fixIt = async () => {
    setError("");
    try {
      const created = await createCapability({ title: item.title, copyText: (item.example || item.purpose).slice(0, 12000), type: "Skill", owner: "探索" });
      if (!created) return;
      setConfirming(false);
      go({ name: "knowledge" });
    } catch (cause) { setConfirming(false); setError(cause instanceof Error ? cause.message : "能力暂时无法保存"); }
  };

  return (
    <main className="v277-page">
      <AppHeader title="知识详情" subtitle={item.source} onBack={onBack} />
      <div className={styles.screen}>
        <section className={styles.block}>
          <h3>
            <span className={styles.titleInline}>
              <BookOpen size={16} />
              {item.title}
            </span>
          </h3>
          <p className={styles.quote}>{item.purpose}</p>
          <div className={styles.chips}>
            <span>{item.source}</span>
            <span>{item.status}</span>
          </div>
        </section>

        <section className={styles.block}>
          <h3>使用示例</h3>
          <MarkdownContent text={item.example}/>
        </section>

        {/* 这两个动作是这次补上的闭环 */}
        <section className={styles.block}>
          <h3>
            用它
            <small>看完就能动手，不用再去别处</small>
          </h3>
          <div className={styles.actions}>
            <button type="button" className={styles.actionPrimary} onClick={useIt}>
              <ListChecks size={17} />
              用它做个任务
            </button>
            <button type="button" onClick={() => setConfirming(true)}>
              <Sparkles size={17} />
              固化成能力卡
            </button>
          </div>
          {error && <p className={styles.note} role="alert">{error}</p>}
          {drafted && (
            <p className={styles.note}>
              已生成任务草稿，并带上这张知识 ·{" "}
              <button
                type="button"
                className={styles.linkBtn}
                onClick={() => go({ name: "tasks" })}
              >
                去任务里看
              </button>
            </p>
          )}
          {fixedTitle && (
            <p className={styles.note}>
              已固化为能力卡：{fixedTitle} ·{" "}
              <button
                type="button"
                className={styles.linkBtn}
                onClick={() => go({ name: "knowledge" })}
              >
                去能力货架看
              </button>
            </p>
          )}
        </section>

        {confirming && (
          <section className={styles.actionBox}>
            <Plus size={16} />
            <span>
              <b>保存为可用工具</b>
              名称：{item.title} · 归属探索 Agent · 来源「{item.source}」。能力评分须以真实任务和本人验收的成果核对。
              <span className={styles.actions}>
                <button type="button" className={styles.actionPrimary} onClick={fixIt}>
                  确认生成
                </button>
                <button type="button" onClick={() => setConfirming(false)}>
                  先不要
                </button>
              </span>
            </span>
          </section>
        )}

        <p className={styles.trace}>
          <ArrowRight size={14} />
          知识是「能查阅、能套用」，能力是「能替你干」；反复套用并有结果之后，它就该固化成能力卡。
        </p>
      </div>
    </main>
  );
}
