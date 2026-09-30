"use client";

import type { Screen } from "../../../core/screen";
import { libraryHeader } from "../data/knowledge-data";
import styles from "../styles/knowledge.module.css";

// 这一页两个面共用的页头：**能力 ／ 记忆**。
// 改名原因：原来叫「知识库」，但"知识"已经不在前台展示（后台的东西不上界面），
// 这一页真正装的是资产（能力）+ 它凭什么懂我（记忆）。见《第二页-结构重排》。
// 这一格是**用户等级**（信任/对齐那条线）：只写"理解度 + 百分比"。
// **不出现 Lv、也不出现档名**——Lv 与档名都留给卡片和等级中心；
// 这样页头只有一个百分比的"程度"，不会和卡片的 Lv.1–5 撞符号（《能力卡组设计》§6.3）。
export function LibraryHeader({
  active,
  go,
  onContext,
  alignment = libraryHeader.alignment,
}: {
  active: "knowledge" | "memory";
  go: (screen: Screen) => void;
  onContext: () => void;
  alignment?: number;
}) {
  return (
    <header className="v277-library-head">
      <nav aria-label="能力与记忆切换">
        <button
          type="button"
          className={active === "knowledge" ? "active" : ""}
          onClick={() => go({ name: "knowledge" })}
        >
          能力库
        </button>
        <button
          type="button"
          className={active === "memory" ? "active" : ""}
          onClick={() => go({ name: "memory" })}
        >
          记忆库
        </button>
      </nav>
      <button
        type="button"
        className="v277-context-chip"
        aria-label={`理解度 ${alignment}%，点开查看等级与荣誉勋章`}
        onClick={onContext}
      >
        {/* 原来这里带 .v277-sprite-home —— 那是从 reference-home.png 雪碧图里
            裁出来的**示例人像**（公共样式 v27-7.css:236）。给用户用不能拿示例照片当头像，
            所以去掉雪碧图类，改由本页样式画一个中性底（见 knowledge.module.css
            的 .headerAvatar 规则），并且只显示"理解度"三个字，不摆人。 */}
        <i className={`v277-context-avatar ${styles.headerAvatar}`} />
        <span>
          <b>理解度</b>
          <small>
            {/* 进度条的宽度直接由理解度决定，不写死 */}
            <em style={{ width: `${alignment}%` }} />
            <i />
          </small>
        </span>
        <strong>{alignment}%</strong>
      </button>
    </header>
  );
}
