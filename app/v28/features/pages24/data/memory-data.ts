"use client";

// 第二页 · 记忆库的数据层。
//
// 【哪些是真数据】记忆条目本身来自 state.memories（引导流程会写入"称呼 / 当前角色 / 当前重点"，
// 记忆详情页可以改、可以删），所以这一层的条数、分组、状态都是活的。
// 【哪些还是演示】"可信度""持续更新天数""当前身份"的说明文案、关键关系这几项还没有后端，
// 现在从这里出；接上后端后只改本文件，视图不用动。

import type { V277Memory } from "../../../../v27-7-state";

import { registerProjector, type LiveMemory } from "../api/page2-api";

export type MemoryGroup = "基础" | "社交" | "习惯" | "偏好";

// 分组的唯一来源：筛选按钮、区块、条数统计都从这里来，不再在页面里另写一套（之前"近况/习惯"点了没反应就是两套对不上）。
export const MEMORY_GROUPS: MemoryGroup[] = ["基础", "社交", "习惯", "偏好"];

export type MemoryRowView = {
  id: string;
  group: MemoryGroup;
  label: string;
  value: string;
  source: string;
  status: string;
};

export type RelationshipView = {
  id: string;
  name: string;
  role: string;
  photo: string;
  chatId: string;
};

export type MemoryPageView = {
  /** 理解卡：一句话说清"这些记忆拿去干什么" */
  headline: string;
  totalCount: number;
  daysTracked: number;
  credibility: number;
  identity: {
    headline: string;
    describe: string;
    photoLabel: string;
    rule: string;
  };
  relationships: RelationshipView[];
  relationshipStats: { longTerm: number; pending: number };
  memories: MemoryRowView[];
};

const RELATIONSHIPS: RelationshipView[] = [];

const IDENTITY = {
  headline: "当前身份",
  describe: "还没有确认的身份信息",
  photoLabel: "",
  rule: "用于机会推荐，可随时纠正",
};

const UNDERSTANDING = {
  headline: "Elfred 对你的当前理解",
  daysTracked: 0,
  credibility: 0,
};

// 真数据一到就换上（页头理解度、当前身份、关系链都跟着后端走）；
// 没接上就继续用上面这份演示兜底。
let LIVE: LiveMemory | null = null;
/** 后端那份记忆条目（有后端就用它——记忆库以后端为准，后端空就是真空态） */
let LIVE_ROWS: MemoryRowView[] | null = null;
registerProjector({
  data: (data) => {
    if (!data.memory) return;
    LIVE = data.memory;
    LIVE_ROWS = Object.values(data.memory.groups ?? {})
      .flat()
      .map((row) => ({
        id: row.id,
        group: (MEMORY_GROUPS as string[]).includes(row.group) ? (row.group as MemoryGroup) : "基础",
        label: row.label,
        value: row.value,
        source: row.source,
        status: row.status,
      }));
  },
});

// 记忆条目：后端在跑就用后端的（后端空 = 真空态）；够不着才退回本地 state 里那几条。
// 其余几项（理解卡、当前身份、关系链）同理，见上面 LIVE。
export function buildMemoryView(memories: V277Memory[]): MemoryPageView {
  const rows: MemoryRowView[] =
    LIVE_ROWS ??
    memories.map((memory) => ({
      id: memory.id,
      group: (MEMORY_GROUPS as string[]).includes(memory.group)
        ? (memory.group as MemoryGroup)
        : "基础",
      label: memory.label,
      value: memory.value,
      source: memory.source,
      status: memory.status,
    }));
  return {
    headline: LIVE?.headline ?? UNDERSTANDING.headline,
    totalCount: rows.filter(row=>row.status==="已确认").length,
    daysTracked: LIVE?.daysTracked ?? UNDERSTANDING.daysTracked,
    credibility: LIVE?.credibility ?? UNDERSTANDING.credibility,
    identity: LIVE ? LIVE.identity : IDENTITY,
    // 注意：这里不能写 `LIVE?.relationships.length ? … : 演示`。
    // 后端返回"空关系链"是一个真结果，不是"没数据"——写成前者会让空库又冒出三个人来。
    relationships: LIVE ? LIVE.relationships : RELATIONSHIPS,
    relationshipStats: LIVE ? LIVE.relationshipStats : { longTerm: 0, pending: 0 },
    memories: rows,
  };
}

export function memoriesOf(view: MemoryPageView, group: MemoryGroup) {
  return view.memories.filter((memory) => memory.group === group);
}
