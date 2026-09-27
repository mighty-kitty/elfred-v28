"use client";
import {displayTitle,displayError} from "../core/display-labels";
import {MarkdownContent} from '../core/markdown-content';
import {PlayerRunLog} from '../features/home/player-run-log';
import {PlayerModelSettings} from '../features/home/player-model-settings';
import {FollowAuthor,RecruitmentSummary} from '../features/home/community-author';
import {Observations} from '../features/home/observations';
import {ContextRecovery} from '../features/home/context-recovery';
import {TaskContext} from '../features/home/task-context';
import {ConnectedSearch} from '../features/home/connected-search';
import {KnowledgeEditor} from '../features/home/knowledge-editor';
import {MentionPicker} from '../features/messages/mention-picker';
import {PersonalAgentPanel,type PersonalAgentHandle} from '../features/messages/personal-agent';
import {VoiceInput} from '../features/messages/voice-input';
import {BuiltinCapabilities,TaskCapability} from '../features/home/builtin-capabilities';
import {objectScreen} from '../core/object-screen';
import {CommunityWorkCard} from '../features/home/community-works';
import {GroupRecords} from '../features/messages/group-records';
import {GroupAgentPanel} from '../features/messages/group-agent';
import {OriginLinks,CalendarDraft,ConversationHandoffs,SharedRecordCard} from '../features/messages/result-handoffs';
import {AttachmentPicker,AttachmentList,type FileRef} from '../features/live/attachments';
import {CommunityEntry} from '../features/home/community-entry';
import {useConversationDraft} from "../core/use-conversation-draft";
import {usePageState} from '../core/page-memory';
import {BriefActions,type BriefFact} from '../features/home/brief-actions';
import {agentAlignment} from '../core/agent-alignment.mjs';
import {MemoryGovernance,InactiveMemories} from '../features/home/memory-governance';
import {MemoryEvidence} from "../core/memory-evidence";
import {ConnectedUtility,ConnectedSettings,PrivateAssist,AssetEditor,MethodsPanel,ConversationMembers} from "../core/runtime-panels";
import {text as entityText,statuses as runtimeStatuses} from "../features/live/types";
// ── 第二页 / 第四页以我方为准（负责人 B）──────────────────────────
// 这几处是接入点：勋章与关系读我方后端、头像/占位不再用示例素材。
// 第二页/第四页的东西一律从它们自己的入口进（见 features/pages24/index.ts）
import {fetchRelationships,hasLiveAlignment,HonorGallery,libraryHeader,type LiveRelationship} from '../features/pages24';

import {
  Fragment,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type CSSProperties,
  type DragEvent as ReactDragEvent,
  type FormEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { useRuntime, entityRef } from '../core/runtime-context';
import {
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Apple,
  BadgeCheck,
  Bell,
  BookOpen,
  Bookmark,
  Bot,
  Briefcase,
  Camera,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleUserRound,
  Clock3,
  Circle,
  Compass,
  Copy,
  Database,
  FileText,
  Folder,
  Gauge,
  Heart,
  HelpCircle,
  History,
  Home,
  Layers3,
  Lightbulb,
  Link2,
  List,
  ListChecks,
  LogOut,
  MemoryStick,
  MessageCircle,
  Mic,
  MoreHorizontal,
  Paperclip,
  Palette,
  Pause,
  PenLine,
  Play,
  Plus,
  QrCode,
  Search,
  Send,
  Settings2,
  Share2,
  ShieldCheck,
  SkipBack,
  SkipForward,
  SlidersHorizontal,
  Sparkles,
  Sun,
  Trash2,
  Trophy,
  Star,
  Medal,
  UserPlus,
  UserCog,
  UserRound,
  Users,
  Video,
  Wrench,
  X,
} from "lucide-react";
import { DeviceFrame } from "../../device-frame";
import { agentList, initialMessages } from "../../v27-7-data";

// State layer lives in v27-7-state.ts. These are imported for local use and
// re-exported so existing importers (app/v28, app/page, tests) keep working.
import type {
  V277AgentId,
  V277TaskStatus,
  V277Phase,
  V277Task,
  V277Message,
  V277Memory,
  V277State,
  Post,
  KnowledgeItem,
} from "../../v27-7-state";
export type {
  V277AgentId,
  V277TaskStatus,
  V277Phase,
  V277Task,
  V277Message,
  V277Memory,
  V277State,
  Post,
  KnowledgeItem,
} from "../../v27-7-state";
import {
  V277_STORAGE_KEY,
  createDefaultAgentSetup,
  createInitialV277State,
  restoreV277State,
  taskFromPost,
  updateTaskStatus,
} from "../../v27-7-state";
export {
  V277_STORAGE_KEY,
  createDefaultAgentSetup,
  createInitialV277State,
  restoreV277State,
  taskFromPost,
  updateTaskStatus,
};
import type { Screen } from "../core/screen";

export type CapabilityCard = {
  item: KnowledgeItem;
  type: "Skill" | "Mini App" | "Agent" | "资料";
  title: string;
  copy: string;
  score: number;
  evidence: number;
  icon: typeof Compass;
};

type SocialPost = {
  id: string;
  name: string;
  date: string;
  text: string;
  likes: number;
  comments: number;
  avatar: "lin" | "chen" | "bei";
  preview?: string;
  gallery?: boolean;
};

type AgentMoment = {
  id: string;
  agent: V277AgentId;
  variant: "topic" | "social" | "brief";
  type: "专题汇总" | "图文帖子" | "观点动态";
  period: "今天" | "本周" | "本月";
  time: string;
  title: string;
  summary: string;
  target: Screen;
  lines?: string[];
  gallery?: boolean;
  likes?: number;
  comments?: number;
};







export type DailyBriefKind = "morning" | "noon" | "evening";

const agentExperience: Record<
  V277AgentId,
  {
    level: string;
    duty: string;
    question: string;
    intro: string;
    actions: [string, string, string];
    questions: [string, string, string];
    focus: string;
    sources: string;
    tools: string;
  }
> = {
  explore: {
    level: "L6",
    duty: "信息发现",
    question: "想探索什么？",
    intro: "我会持续查找、整理，并把有价值的发现带回来。",
    actions: ["发现案例", "追踪话题", "生成简报"],
    questions: [
      "最近有哪些值得关注的 AI 产品？",
      "持续追踪 Personal Agent 赛道",
      "找出与我当前目标相关的新机会",
    ],
    focus: "3 个主题",
    sources: "已连接 6 项",
    tools: "4 个",
  },
  advisor: {
    level: "L5",
    duty: "分析判断",
    question: "今天要判断什么？",
    intro: "我会理解问题、比较选择，并给出清晰的行动建议。",
    actions: ["梳理问题", "比较方案", "给出建议"],
    questions: [
      "这三个首页方案应该优先选哪一个？",
      "帮我比较两种内测邀请方式",
      "下一版最值得先解决的问题是什么？",
    ],
    focus: "4 个议题",
    sources: "已连接 5 项",
    tools: "3 个",
  },
  create: {
    level: "L5",
    duty: "内容创作",
    question: "想创作什么？",
    intro: "我会把你的意图转化为清楚、自然、可交付的内容。",
    actions: ["起草内容", "改写表达", "输出方案"],
    questions: [
      "起草一份首批内测邀请文案",
      "把这段说明改得更像消费产品",
      "输出一版移动端首页方案",
    ],
    focus: "3 类内容",
    sources: "已连接 4 项",
    tools: "5 个",
  },
  connect: {
    level: "L4",
    duty: "关系连接",
    question: "想连接谁？",
    intro: "我会寻找合适的人、判断匹配度，并先完成前置对齐。",
    actions: ["寻找对象", "判断匹配", "发起对齐"],
    questions: [
      "寻找两位 Personal Agent 产品共创者",
      "判断这些候选人与当前阶段是否匹配",
      "为一次技术合作准备前置对齐",
    ],
    focus: "3 类关系",
    sources: "已连接 7 项",
    tools: "3 个",
  },
  execute: {
    level: "L6",
    duty: "任务执行",
    question: "想完成什么？",
    intro: "我会把已确认的目标拆成步骤，执行并汇报结果。",
    actions: ["拆解任务", "开始执行", "查看结果"],
    questions: [
      "把首页优化拆成今天能完成的步骤",
      "开始整理第一批内测名单",
      "汇总正在执行的任务结果",
    ],
    focus: "4 类任务",
    sources: "已连接 5 项",
    tools: "6 个",
  },
};

export const dailyBriefs: Record<
  DailyBriefKind,
  {
    label: string;
    title: string;
    summary: string;
    stats: string;
    cta: string;
  }
> = {
  morning: {
    label: "今天的重点",
    title: "先确认首页结构，再推进二级功能",
    summary: "这是今天最值得投入的一件事。",
    stats: "3 项计划 · 2 项待确认 · 5 个 Agent 已就绪",
    cta: "查看今天的计划",
  },
  noon: {
    label: "上午进展",
    title: "完成了 2 项，有 1 项需要调整",
    summary: "首页方案仍在等待确认，影响下午推进。",
    stats: "2 已完成 · 1 进行中 · 1 项阻塞",
    cta: "处理需要调整的事项",
  },
  evening: {
    label: "待你核对的今日总结",
    title: "今日任务状态与一条新理解待核对",
    summary: "Person Agent 将依据当前任务状态整理事实、解释与候选理解。",
    stats: "不自动沉淀 · 不自动分发 · 不自动创建任务",
    cta: "查看今日回顾",
  },
};

type BriefPreferences = {
  morning: string;
  noon: string;
  evening: string;
  morningModule: string;
  noonModule: string;
  eveningModule: string;
  style: string;
};

export const defaultBriefPreferences: BriefPreferences = {
  morning: "08:00",
  noon: "12:30",
  evening: "20:30",
  morningModule: "重点与计划",
  noonModule: "进展与阻塞",
  eveningModule: "成果与沉淀",
  style: "标准",
};

export function readBriefPreferences(): BriefPreferences {
  if (typeof window === "undefined") return defaultBriefPreferences;
  try {
    const saved = JSON.parse(
      window.localStorage.getItem("elfred-v278-brief-settings") || "null",
    ) as Partial<BriefPreferences> | null;
    return { ...defaultBriefPreferences, ...(saved || {}) };
  } catch {
    return defaultBriefPreferences;
  }
}

export function timeToMinutes(value: string) {
  const [hour, minute] = value.split(":").map(Number);
  return hour * 60 + minute;
}

export function getCurrentBriefIndex(preferences = readBriefPreferences()) {
  if (typeof window === "undefined") return 0;
  const now = new Date();
  const minutes = now.getHours() * 60 + now.getMinutes();
  if (minutes >= timeToMinutes(preferences.evening)) return 2;
  if (minutes >= timeToMinutes(preferences.noon)) return 1;
  return 0;
}

export function getBriefDayId() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

type AgentMomentPost = {
  id: string;
  date: string;
  title: string;
  summary: string;
  tag: "产品观察" | "专题" | "机会";
};

export function getAgentMomentPosts(id: V277AgentId): AgentMomentPost[] {
  const experience = agentExperience[id];
  const exploreTitles = [
    "首页正在从固定看板走向时段化内容",
    "3 个值得关注的 Personal Agent 产品",
    "任务播放器应该如何展示 Agent 过程",
  ];
  return experience.questions.map((question, index) => ({
    id: `agent-moment-${id}-${index}`,
    date: index === 0 ? "今天" : index === 1 ? "9月10日" : "9月8日",
    title: id === "explore" ? exploreTitles[index] : question,
    summary:
      index === 0
        ? experience.intro
        : index === 1
          ? `围绕“${experience.duty}”，我整理了三个最值得继续验证的判断。`
          : `这条发现已经被整理成下一步，可交给${id === "execute" ? "执行" : "对应"} Agent 继续推进。`,
    tag: index === 1 ? "专题" : index === 2 ? "机会" : "产品观察",
  }));
}

export function formatToday() {
  const now = new Date();
  const weekdays = ["日", "一", "二", "三", "四", "五", "六"];
  return `${now.getMonth() + 1}月${now.getDate()}日 · 星期${weekdays[now.getDay()]}`;
}

export const v277Posts: Post[] = [
  {
    id: "entry-design",
    agent: "explore",
    label: "与当前目标相关",
    title: "三种首页入口，哪一种更适合首次使用？",
    summary:
      "我把任务入口、信息流入口和对话入口放在同一标准下比较，结论已经可以直接用于下一版首页。",
    detail: [
      "任务入口：目标明确，但第一次打开时容易显得空。",
      "信息流入口：容易浏览，需要把内容自然接到任务上。",
      "对话入口：表达自由，但用户可能不知道第一句话说什么。",
    ],
    taskTitle: "比较三种首页入口并给出推荐",
    taskBrief:
      "结合首次使用目标，比较任务、信息流和对话三种入口，产出一个可执行建议。",
    result: [
      "推荐以信息流作为主入口，首屏保留一个明确的当前任务。",
      "每条内容只保留一个主动作：查看、保存或转为任务。",
      "全局 Elfred 作为随时可用的辅助入口，不抢占首屏。",
    ],
    category: "推荐",
  },
  {
    id: "first-value",
    agent: "advisor",
    label: "产品方法",
    title: "新用户第一天，先交付一个小结果",
    summary:
      "注册之后直接生成一份与目标有关的任务草稿，比继续填写偏好更容易让用户理解产品价值。",
    detail: [
      "只问当前要推进的事情。",
      "在进入主页前生成一份三步草稿。",
      "允许保存为任务，也允许跳过示例。",
    ],
    taskTitle: "设计首次使用的结果交付",
    taskBrief: "把新手流程缩成目标输入、结果预览和保存任务三个步骤。",
    result: [
      "保留一个必填问题：现在最想推进什么？",
      "姓名和角色改为选填。",
      "主页承接刚刚生成的同一个任务。",
    ],
    category: "方法",
  },
  {
    id: "weekly-review",
    agent: "execute",
    label: "可直接开始",
    title: "把本周目标缩成三个可以完成的动作",
    summary:
      "先明确本周唯一结果，再安排一次验证和一次复盘，避免同时推进太多方向。",
    detail: [
      "写下一项本周必须完成的结果。",
      "安排一次真实用户验证。",
      "周五记录结论和下一步。",
    ],
    taskTitle: "制定本周三步任务计划",
    taskBrief: "围绕当前目标创建一个结果、一次验证和一次复盘。",
    result: [
      "结果：完成一版可点击产品流程。",
      "验证：邀请一位目标用户完整走通。",
      "复盘：记录卡点，只保留下一版最重要的修正。",
    ],
    category: "协作",
  },
];

export const v277Knowledge: KnowledgeItem[] = [
  {
    id: "interview",
    title: "用户访谈提纲",
    purpose: "验证用户是否能独立完成主任务",
    source: "Elfred 内置方法",
    status: "可直接使用",
    example:
      "请用户在不提示的情况下完成一次注册、创建任务和查看结果，并记录停顿位置。",
  },
  {
    id: "decision",
    title: "方案比较框架",
    purpose: "按目标、成本与风险比较多个方案",
    source: "来自首页入口任务",
    status: "已用于 1 个任务",
    example:
      "先写共同目标，再分别列出收益、使用成本、失败风险，最后只给出一个推荐。",
  },
  {
    id: "brief",
    title: "一页任务简报",
    purpose: "把模糊需求变成清晰的交付范围",
    source: "Elfred 内置模板",
    status: "可直接使用",
    example: "目标、背景、交付物、边界、确认点五项即可，不添加无法验证的指标。",
  },
  {
    id: "copy",
    title: "简洁产品文案",
    purpose: "减少抽象词，让按钮与说明更易理解",
    source: "创作 Agent",
    status: "可直接使用",
    example: "把“开启智能协同”改成“生成第一版任务草稿”，让动作和结果都可预期。",
  },
];

export const communityPosts: SocialPost[] = [
  {
    id: "social-entry-design",
    name: "林野",
    date: "09/07",
    text: "真正好的连接，应该发生在彼此都准备好的时候。",
    likes: 18,
    comments: 3,
    avatar: "lin",
    preview: "Mia：为什么？",
  },
  {
    id: "social-first-value",
    name: "陈默",
    date: "09/06",
    text: "把复杂任务交给 Agent，自己只保留真正重要的选择。",
    likes: 24,
    comments: 6,
    avatar: "chen",
    gallery: true,
  },
  {
    id: "social-weekly-review",
    name: "北辰",
    date: "09/05",
    text: "正在寻找两位一起测试长期记忆系统的伙伴。",
    likes: 12,
    comments: 2,
    avatar: "bei",
  },
];

export const agentMoments: AgentMoment[] = [
  {
    id: "moment-agent-network",
    agent: "explore",
    variant: "topic",
    type: "专题汇总",
    period: "今天",
    time: "15 分钟前",
    title: "Personal Agent 正在从工具走向关系网络",
    summary: "围绕同一个话题，为你汇总了 6 篇高相关内容",
    target: { name: "post", id: "entry-design" },
    lines: [
      "入口正在从对话框转向持续信息流",
      "记忆如何参与下一次判断",
      "A2A 的核心是解释为什么值得连接",
    ],
  },
  {
    id: "moment-home-value",
    agent: "create",
    variant: "social",
    type: "图文帖子",
    period: "今天",
    time: "1 小时前",
    title: "好的主页不是展示更多能力，而是让用户一眼知道下一步",
    summary:
      "好的主页不是展示更多能力，而是让用户一眼知道：现在发生了什么，下一步可以做什么。",
    target: { name: "community-post", id: "social-first-value" },
    gallery: true,
    likes: 24,
    comments: 6,
  },
  {
    id: "moment-first-result",
    agent: "advisor",
    variant: "brief",
    type: "观点动态",
    period: "今天",
    time: "2 小时前",
    title: "新用户第一天，先交付一个小结果",
    summary:
      "注册之后直接生成一份与目标有关的任务草稿，比继续填写偏好更容易让用户理解产品价值。",
    target: { name: "post", id: "first-value" },
  },
  {
    id: "moment-week-plan",
    agent: "execute",
    variant: "brief",
    type: "观点动态",
    period: "今天",
    time: "3 小时前",
    title: "把本周目标缩成三个可以完成的动作",
    summary:
      "先明确本周唯一结果，再安排一次验证和一次复盘，避免同时推进太多方向。",
    target: { name: "post", id: "weekly-review" },
  },
  {
    id: "moment-collaborators",
    agent: "connect",
    variant: "topic",
    type: "专题汇总",
    period: "本周",
    time: "昨天",
    title: "本周值得认识的三类协作者",
    summary: "从 18 位候选人中整理了 3 类与你当前阶段更匹配的人",
    target: { name: "agent", id: "connect" },
    lines: [
      "有 Agent 产品经验的共同创造者",
      "能持续参与验证的首批用户",
      "理解消费产品的增长伙伴",
    ],
  },
  {
    id: "moment-community",
    agent: "explore",
    variant: "social",
    type: "图文帖子",
    period: "本周",
    time: "2 天前",
    title: "真正好的连接发生在彼此都准备好的时候",
    summary: "真正好的连接，应该发生在彼此都准备好的时候。",
    target: { name: "community-post", id: "social-entry-design" },
    likes: 18,
    comments: 3,
  },
  {
    id: "moment-expression",
    agent: "create",
    variant: "brief",
    type: "观点动态",
    period: "本周",
    time: "3 天前",
    title: "减少解释，让每个页面只表达一件事",
    summary:
      "把标题、说明和主按钮收拢到同一个结果，用户会更容易理解系统此刻希望他做什么。",
    target: { name: "agent", id: "create" },
  },
  {
    id: "moment-decision",
    agent: "advisor",
    variant: "topic",
    type: "专题汇总",
    period: "本月",
    time: "上周",
    title: "从七次产品判断中提炼出的三个共同标准",
    summary: "目标是否清晰、结果是否可验证、用户是否能自然完成",
    target: { name: "knowledge-detail", id: "decision" },
    lines: [
      "先判断真实目标，再比较方案",
      "只保留能被验证的结果",
      "每个页面只给一个主动作",
    ],
  },
];

export const demoTasks: V277Task[] = [
  {
    id: "schedule-client",
    title: "客户沟通",
    brief: "同步产品进展，确认本周目标、分工与下一步。",
    source: "今日安排 · 09:00",
    agent: "connect",
    status: "待确认",
    nextStep: "确认参会人与会议目标",
    result: [
      "确认本周唯一交付结果。",
      "记录需要对方决定的两个问题。",
      "会后同步结论与负责人。",
    ],
    knowledgeIds: [],
    updatedAt: "今天 09:00",
  },
  {
    id: "schedule-design",
    title: "下月视觉设计排期",
    brief: "统一首页、任务与二级页面的版式规范并确定迭代顺序。",
    source: "今日安排 · 11:00",
    agent: "execute",
    status: "进行中",
    nextStep: "核对页面优先级与交付日期",
    result: [
      "先完成一级页面视觉规范。",
      "随后统一详情页与表单。",
      "最后完成逐页截图验收。",
    ],
    knowledgeIds: ["brief"],
    updatedAt: "今天 11:00",
  },
  {
    id: "schedule-interview",
    title: "首批用户访谈",
    brief: "邀请目标用户完整走通注册、主页、任务与结果查看流程。",
    source: "今日安排 · 14:00",
    agent: "explore",
    status: "待确认",
    nextStep: "确认访谈对象和观察问题",
    result: [
      "不提示地完成一次注册。",
      "从首页进入任务并完成状态变更。",
      "记录第一个犹豫或误解的位置。",
    ],
    knowledgeIds: ["interview"],
    updatedAt: "今天 14:00",
  },
  {
    id: "project-brand",
    title: "品牌官网首屏改版",
    brief: "与开发确认布局、交互与关键表达，完成首屏方案定稿。",
    source: "项目任务",
    agent: "create",
    status: "已暂停",
    nextStep: "确认主标题与首屏唯一动作",
    result: [
      "统一首屏信息层级。",
      "只保留一个主要行动入口。",
      "通过真实用户测试首屏理解度。",
    ],
    knowledgeIds: ["copy"],
    updatedAt: "昨天",
  },
  {
    id: "project-mobile",
    title: "移动端玻璃效果优化",
    brief: "统一模糊层级、圆角、边框与底部导航的视觉质感。",
    source: "项目任务",
    agent: "create",
    status: "进行中",
    nextStep: "完成全页面视觉走查",
    result: [
      "统一 24px 主卡片圆角。",
      "统一 1px 浅灰边框。",
      "减少模糊与阴影的层级数量。",
    ],
    knowledgeIds: ["decision"],
    updatedAt: "今天",
  },
];



const chatDirectory: Record<
  string,
  { name: string; subtitle: string; greeting: string }
> = {
  "group-danbasa": {
    name: "丹巴萨餐厅",
    subtitle: "群聊 · 6 位成员",
    greeting: "欢迎来到丹巴萨餐厅群聊。这里会保留与这次讨论相关的上下文。",
  },
  "person-linjia": {
    name: "林嘉",
    subtitle: "在线",
    greeting: "你好，我是林嘉。我们可以继续刚才的讨论。",
  },
  "partner-agent-linjia": {
    name: "林嘉的 Personal Agent",
    subtitle: "由林嘉授权",
    greeting: "你好，我会先确认双方目标与边界；任何真人联系都需要双方确认。",
  },
  "person-chenkai": {
    name: "陈凯",
    subtitle: "3 分钟前在线",
    greeting: "回头见。如果有新的进展，直接在这里告诉我。",
  },
  "person-aya": {
    name: "阿雅",
    subtitle: "5 分钟前在线",
    greeting: "哈哈，确实。还有什么想继续聊的吗？",
  },
  "person-duming": {
    name: "杜明",
    subtitle: "在线",
    greeting: "那就晚上 8 点开始，可以吗？",
  },
  "person-zhaoya": {
    name: "赵雅",
    subtitle: "12 分钟前在线",
    greeting: "好的，晚点联系。",
  },
  "person-linye": {
    name: "林野",
    subtitle: "在线",
    greeting: "真正好的连接，应该发生在彼此都准备好的时候。",
  },
  "person-chenmo": {
    name: "陈默",
    subtitle: "最近活跃",
    greeting: "把复杂任务交给 Agent，自己只保留真正重要的选择。",
  },
  "person-suning": {
    name: "苏宁",
    subtitle: "最近活跃",
    greeting: "很高兴在这里继续交流。",
  },
  "person-yiming": {
    name: "一鸣",
    subtitle: "最近活跃",
    greeting: "有新的想法可以直接发给我。",
  },
  "person-xiaxia": {
    name: "小夏",
    subtitle: "最近活跃",
    greeting: "我们可以从你最关心的一件事开始。",
  },
  "person-mia": {
    name: "Mia",
    subtitle: "产品共创",
    greeting: "关于产品共创，有新进展可以随时同步给我。",
  },
  "person-kevin": {
    name: "Kevin",
    subtitle: "技术合作",
    greeting: "关于技术合作，我们可以继续确认下一步。",
  },
  "person-lena": {
    name: "Lena",
    subtitle: "市场增长",
    greeting: "关于市场增长，我可以继续补充资源与反馈。",
  },
};



export function makeId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}


export function StatusBar() {
  return (
    <div className="v277-status" aria-hidden="true">
      <b>9:41</b>
      <span>
        <i />
        <i />
        <em />
      </span>
    </div>
  );
}

export function IconButton({
  label,
  onClick,
  children,
  className = "",
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      className={`v277-icon-button ${className}`}
      aria-label={label}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

export function RootPortal({ children }: { children: ReactNode }) {
  if (typeof document === "undefined") return null;
  const host = document.querySelector(".v277-root");
  return host ? createPortal(children, host) : null;
}

export function AppHeader({
  title,
  subtitle,
  onBack,
  right,
}: {
  title: string;
  subtitle?: string;
  onBack?: () => void;
  right?: ReactNode;
}) {
  return (
    <header className="v277-page-head">
      {onBack ? (
        <IconButton label="返回" onClick={onBack}>
          <ArrowLeft size={21} />
        </IconButton>
      ) : (
        <span className="v277-head-spacer" />
      )}
      <div>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      <span className="v277-head-right">{right}</span>
    </header>
  );
}

export function LibraryHeader({
  active,
  go,
  onContext,
}: {
  active: "knowledge" | "memory";
  go: (screen: Screen) => void;
  onContext: () => void;
}) {
  const runtime=useRuntime();
  const confirmed=runtime?.snapshot?.objects.memory.filter(item=>item.data.status==='validated').length||0;
  return (
    <header className="v277-library-head">
      <nav aria-label="知识与记忆切换">
        <button
          type="button"
          className={active === "knowledge" ? "active" : ""}
          onClick={() => go({ name: "knowledge" })}
        >
          知识库
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
        aria-label="查看理解依据与成长记录"
        onClick={onContext}
      >
        <i className="v277-context-avatar v277-sprite-home" />
        <span>
          <b>{runtime?`确认 ${confirmed}`:'理解度 86%'}</b>
          <small>
            <em />
            <i />
          </small>
        </span>
        <strong>{runtime?'依据':'Lv.4'}</strong>
      </button>
    </header>
  );
}

export function BottomNav({
  screen,
  go,
  openElfred,
}: {
  screen: Screen;
  go: (screen: Screen) => void;
  openElfred: () => void;
}) {
  const current = screen.name;
  const items = [
    ["home", "首页", Home],
    ["knowledge", "知识", Layers3],
    ["messages", "消息", MessageCircle],
    ["profile", "我的", CircleUserRound],
  ] as const;
  return (
    <div className="v277-bottom-wrap">
      <nav className="v277-bottom" aria-label="主导航">
        {items.map(([name, label, Icon]) => (
          <button
            type="button"
            key={name}
            aria-label={label}
            title={label}
            className={
              current === name ||
              (name === "home" &&
                (current === "tasks" || current === "community")) ||
              (name === "knowledge" && current === "memory")
                ? "active"
                : ""
            }
            onClick={() => go({ name })}
          >
            <Icon size={25} strokeWidth={1.85} />
          </button>
        ))}
      </nav>
      <button
        type="button"
        aria-label="打开蜂群协作"
        className="v277-elfred-orbit"
        onClick={openElfred}
      >
        <span />
        <i />
        <em />
      </button>
    </div>
  );
}

export function PullDownPill({ onOpen }: { onOpen: () => void }) {
  return (
    <div className="v278-tool-pull">
      <button
        type="button"
        className="v277-pull-pill"
        aria-label="打开我的工具"
        onClick={onOpen}
      >
        <ChevronDown size={18} strokeWidth={2.2} />
        打开我的工具
      </button>
    </div>
  );
}

export function SettingDropdown({
  icon: Icon,
  label,
  value,
  options,
  onSelect,
}: {
  icon: typeof Clock3;
  label: string;
  value: string;
  options: string[];
  onSelect: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`v278-setting-dropdown ${open ? "is-open" : ""}`}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <Icon size={22} />
        <span>
          <b>{label}</b>
          <em>{value}</em>
        </span>
        <ChevronDown size={18} />
      </button>
      {open && (
        <div className="v278-setting-menu" role="listbox" aria-label={label}>
          {options.map((option) => (
            <button
              type="button"
              role="option"
              aria-selected={option === value}
              key={option}
              onClick={() => {
                onSelect(option);
                setOpen(false);
              }}
            >
              <span>{option}</span>
              {option === value && <Check size={17} />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function HomeChannelTabs({
  active,
  onChange,
  taskCount,
  go,
}: {
  active: "home" | "community";
  onChange: (tab: "home" | "community") => void;
  taskCount: number;
  go: (screen: Screen) => void;
}) {
  return (
    <header
      className={`v277-reference-head ${active === "community" ? "community" : ""}`}
    >
      <nav aria-label="首页频道">
        <button
          type="button"
          className={active === "home" ? "active" : ""}
          onClick={() => onChange("home")}
        >
          动态
        </button>
        <button
          type="button"
          className={active === "community" ? "active" : ""}
          onClick={() => onChange("community")}
        >
          社区
        </button>
      </nav>
      {active === "home" && (
        <button
          type="button"
          className="v277-task-entry"
          onClick={() => go({ name: "tasks" })}
        >
          <ListChecks size={19} />
          任务{taskCount > 0 && <b>{taskCount}</b>}
        </button>
      )}
    </header>
  );
}

export function TaskPlayer({
  state,
  go,
  collapsed = false,
  onTaskDrop,
}: {
  state: V277State;
  go: (screen: Screen) => void;
  collapsed?: boolean;
  onTaskDrop?: (taskId: string) => void;
}) {
  const [dropActive, setDropActive] = useState(false);
  const runtime=useRuntime();
  const eligible=runtime?state.tasks.filter(t=>runtime.snapshot?.objects.task.some(o=>o.id===t.id&&o.data.status!=='draft')):state.tasks;
  const current =
    eligible.find((task) => task.status === "进行中") ||
    eligible.find((task) => task.status === "待确认") ||
    eligible.find((task) => task.status === "已暂停");
  const queueCount = state.tasks.filter(
    (task) => task.status === "待确认" || task.status === "已暂停",
  ).length;
  return (
    <aside
      className={`v277-task-player${collapsed ? " is-collapsed" : ""}${dropActive ? " is-drop-target" : ""}`}
      aria-label="任务播放器"
      aria-hidden={collapsed}
      onDragEnter={(event) => {
        if (!onTaskDrop) return;
        event.preventDefault();
        setDropActive(true);
      }}
      onDragOver={(event) => {
        if (!onTaskDrop) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        setDropActive(true);
      }}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null))
          setDropActive(false);
      }}
      onDrop={(event) => {
        if (!onTaskDrop) return;
        event.preventDefault();
        const taskId =
          event.dataTransfer.getData("application/x-elfred-task") ||
          event.dataTransfer.getData("text/plain");
        setDropActive(false);
        if (taskId) onTaskDrop(taskId);
      }}
    >
      <button
        type="button"
        className="v277-player-main"
        onClick={() => go({ name: "player" })}
      >
        <span className="v277-player-wave">
          <i />
          <i />
          <i />
          <i />
          <i />
        </span>
        <span>
          <small>{current ? `Agent ${current.runtimeStatus?runtimeStatuses[current.runtimeStatus]||current.status:current.status}` : "Agent 空闲"}</small>
          <b>{displayTitle(current?.title,'') || "点击查看任务播放器"}</b>
        </span>
      </button>
      <i className="v277-player-progress">
        <em />
      </i>
      <button
        type="button"
        aria-label="打开任务播放器"
        onClick={() => go({ name: "player" })}
      >
        <Play size={21} fill="currentColor" />
      </button>
      <button
        type="button"
        className="v280-player-queue"
        aria-label={`查看任务列表，${queueCount} 项待办`}
        onClick={() => go({ name: "tasks", view: "projects" })}
      >
        <List size={23} />
        {queueCount > 0 && <b>{queueCount}</b>}
      </button>
      {dropActive && (
        <span className="v280-player-drop-copy">
          <Play size={19} fill="currentColor" />
          <b>松开以执行或加入待办</b>
        </span>
      )}
    </aside>
  );
}

export function AgentMomentCard({
  moment,
  go,
}: {
  moment: AgentMoment;
  go: (screen: Screen) => void;
}) {
  const agent = agentList.find((item) => item.id === moment.agent)!;
  const Icon = agent.icon;
  const replies: Partial<Record<V277AgentId, [V277AgentId, string]>> = {
    explore: ["advisor", "我补了一条判断依据，已放进专题。"],
    create: ["execute", "这版可以直接拆成下一步任务。"],
    connect: ["explore", "候选关系里有两位值得优先了解。"],
  };
  const runtime=useRuntime();
  const reply = runtime?undefined:replies[moment.agent];
  if (moment.variant === "topic")
    return (
      <button
        type="button"
        className="v278-topic-post"
        onClick={() => go(moment.target)}
      >
        <header>
          <span className="v278-moment-agent-icon">
            <Icon size={20} />
          </span>
          <div>
            <b>
              {agent.name} <em>Agent</em>
            </b>
            <small>
              {moment.time} · {moment.type}
            </small>
          </div>
          <MoreHorizontal size={20} />
        </header>
        <h3>{displayTitle(moment.title,'')}</h3>
        <p>{moment.summary}</p>
        <ol>
          {moment.lines?.map((line, index) => (
            <li key={line}>
              <span>0{index + 1}</span>
              {line}
            </li>
          ))}
        </ol>
        <footer>
          <span>{moment.lines?.length || 3} 个重点</span>
          <strong>
            查看专题
            <ChevronRight size={15} />
          </strong>
        </footer>
        {reply && (
          <div className="v281-agent-reply">
            <b>{agentList.find((item) => item.id === reply[0])?.name} Agent</b>
            <span>{reply[1]}</span>
          </div>
        )}
      </button>
    );
  if (moment.variant === "social")
    return (
      <button
        type="button"
        className="v278-community-moment"
        onClick={() => go(moment.target)}
      >
        <header>
          <span className="v278-moment-agent-icon">
            <Icon size={20} />
          </span>
          <span>
            <b>{agent.name} Agent</b>
            <small>
              {moment.time} · {moment.type}
            </small>
          </span>
          <MoreHorizontal size={20} />
        </header>
        <p>{moment.summary}</p>
        {moment.gallery && (
          <span className="v278-home-gallery">
            <i className="gallery-one v277-sprite-community" />
            <i className="gallery-two v277-sprite-community" />
            <i className="gallery-three v277-sprite-community" />
          </span>
        )}
        <footer>
          <span>
            <Heart size={17} />
            {moment.likes || 18}
          </span>
          <span>
            <MessageCircle size={17} />
            {moment.comments || 3}
          </span>
          <strong>
            查看讨论
            <ChevronRight size={15} />
          </strong>
        </footer>
        {reply && (
          <div className="v281-agent-reply">
            <b>{agentList.find((item) => item.id === reply[0])?.name} Agent</b>
            <span>{reply[1]}</span>
          </div>
        )}
      </button>
    );
  return (
    <button
      type="button"
      className="v278-compact-moment"
      onClick={() => go(moment.target)}
    >
      <span>
        <Icon size={19} />
      </span>
      <div>
        <header>
          <b>{agent.name} Agent</b>
          <small>{moment.time}</small>
        </header>
        <h3>{displayTitle(moment.title,'')}</h3>
        <p>{moment.summary}</p>
      </div>
      <ChevronRight size={18} />
    </button>
  );
}

export function TaskPlayerPage({
  state,
  go,
  onBack,
  setState,
  notify,
}: {
  state: V277State;
  go: (screen: Screen) => void;
  onBack: () => void;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
  notify: (text: string) => void;
}) {
  const runtime=useRuntime();
  const playable = state.tasks.filter((task) => task.status !== "已完成");
  const first =
    playable.find((task) => task.status === "进行中") ||
    playable.find((task) => task.status === "待确认") ||
    playable[0];
  const [activeId, setActiveId] = usePageState("player-active-task",first?.id || "");
  const [tab, setTab] = usePageState<"SOP" | "实时日志">("player-process-tab","SOP");
  const [speed, setSpeed] = useState(1);
  const [model, setModel] = useState("GPT-5.6");
  const [saved, setSaved] = useState(false);
  const [question, setQuestion] = useState("");
  const [queueOpen, setQueueOpen] = useState(false);
  const [speedOpen, setSpeedOpen] = useState(false);
  const [modelOpen, setModelOpen] = useState(false);
  const current = playable.find((task) => task.id === activeId) || first;
  const index = Math.max(
    0,
    playable.findIndex((task) => task.id === current?.id),
  );
  const liveTask=runtime?.snapshot?.objects.task.find(item=>item.id===current?.id),liveRun=runtime?.snapshot?.objects.run.find(item=>item.id===liveTask?.data.run_id);
  const steps=(liveRun?.data.plan as {steps:{id:string;tool:string;phase?:string}[]}|undefined)?.steps||[];
  const receipts=(liveRun?.data.receipts||[]) as {id:string;step_id:string;at:string;status:string;output_hash:string;provider?:string}[];
  const progress=steps.length?Math.floor(steps.filter(step=>receipts.some(receipt=>receipt.step_id===step.id)).length/steps.length*100):0;
  const status=liveTask?runtimeStatuses[entityText(liveTask,'status')]||'待处理':current?.status||'等待执行';
  const phaseNames:Record<string,string>={work:'生成成果',review:'核对结果',repair:'按反馈修订',collaboration:'协作准备',context:'读取资料'};
  const toolNames:Record<string,string>={'text.compose':'生成内容','document.read':'读取资料','search.local':'查找资料','owner.report':'记录本人完成结果'};
  const title = current?.title || (runtime?"当前没有任务":"生成今日重点简报");
  const agent = current
    ? agentList.find((item) => item.id === current.agent)?.name
    : "探索";
  const playing = liveRun?entityText(liveRun,'status')==='running':current?.status === '进行中';
  const selectOffset = (offset: number) => {
    if (!playable.length) return;
    setActiveId(
      playable[(index + offset + playable.length) % playable.length].id,
    );
  };
  const togglePlayback = () => {
    if (!current) {
      notify("当前没有可执行任务");
      return;
    }
    if(runtime){if(liveRun&&liveRun.data.status==='running')void runtime.command('run.command',{...entityRef(liveRun),command:'pause'}).catch(()=>{});else go({name:'task',id:current.id});return;}
    const next = current.status === "进行中" ? "已暂停" : "进行中";
    setState((value) => ({
      ...value,
      tasks: value.tasks.map((task) =>
        task.id === current.id ? updateTaskStatus(task, next) : task,
      ),
    }));
    notify(next === "进行中" ? "任务已继续" : "任务已暂停");
  };
  const ask = (event: FormEvent) => {
    event.preventDefault();
    if (!question.trim()) return;
    if(runtime){void runtime.command('task.create',{goal:question,mode:'compose',system:'execute'}).then(result=>go({name:'task',id:result.id})).catch(()=>{});return;}
    notify("问题已发送给当前任务");
    setQuestion("");
  };
  return (
    <main className="v277-page v278-player-page">
      <header className="v278-player-header">
        <button type="button" aria-label="返回" onClick={onBack}>
          <ArrowLeft size={27} />
        </button>
        <span>
          <h1>任务播放器</h1>
        </span>
        <button
          type="button"
          aria-label="分享任务"
          onClick={() => notify(runtime?"任务为本人私有，可验收后在社区单独发布成果":"任务分享链接已复制")}
        >
          <Share2 size={24} />
        </button>
        <button
          type="button"
          aria-label={saved ? "取消收藏任务" : "收藏任务"}
          className={saved ? "active" : ""}
          onClick={() => {
            if(runtime&&current){void runtime.command('inbox.create',{object_id:current.id}).then(()=>notify('已保存到待办收件箱')).catch(()=>{});return;}
            setSaved((value) => !value);
            notify(saved ? "已取消收藏" : "任务已收藏");
          }}
        >
          <Bookmark size={24} fill={saved ? "currentColor" : "none"} />
        </button>
      </header>
      <button
        type="button"
        className="v278-player-list"
        onClick={() => setQueueOpen(true)}
      >
        <List size={19} />
        任务列表 {playable.length}
        <ChevronRight size={17} />
      </button>
      <section className="v278-player-card">
        <i className="v278-player-cover" />
        <div className="v278-player-summary">
          <span>
            <i /> {playing ? "正在执行" : status}
          </span>
          <h2>{title}</h2>
          <p>{agent} Agent · {runtime?"累计运行 "+Math.round(Number(liveTask?.data.elapsed_ms||0)/1000)+" 秒":"已运行 12 分钟"}</p>
          {current?.brief!==title&&<strong>{current?.brief || "正在汇总与你相关的动态与待确认事项"}</strong>}
          <div>
            <span>步骤完成度</span>
            <b>{runtime?progress:64}%</b>
            <i>
              <em style={runtime?{width:progress+"%"}:undefined}/>
            </i>
          </div>
        </div>
        <div className="v278-player-process">
          <header>
            <h3>执行过程</h3>
            <nav>
              <button
                type="button"
                className={tab === "SOP" ? "active" : ""}
                onClick={() => setTab("SOP")}
              >
                SOP
              </button>
              <button
                type="button"
                className={tab === "实时日志" ? "active" : ""}
                onClick={() => setTab("实时日志")}
              >
                实时日志
              </button>
            </nav>
          </header>
          {runtime?(tab==="实时日志"?<PlayerRunLog run={liveRun}/>:<ol>{steps.map((step,index)=>{const receipt=receipts.find(r=>r.step_id===step.id),started=playing&&!receipt&&steps.slice(0,index).every(previous=>receipts.some(r=>r.step_id===previous.id));return <li key={step.id} className={receipt?'done':started?'current':''}><i>{receipt&&<Check size={14}/>}</i><div><span>{phaseNames[step.phase||step.id]||toolNames[step.tool]||'执行步骤'}</span><small>{receipt?(receipt.provider==='conditional-skip'||receipt.status==='skipped'?'无需修订，已跳过':'已完成'):started?'正在处理':'等待执行'}</small></div></li>})}{!steps.length&&<li><span>确认并启动任务后，执行过程会出现在这里。</span></li>}{Boolean(liveRun?.data.error)&&<li><span>{displayError((liveRun!.data.error as {message:string}).message)}</span></li>}</ol>):tab === "SOP" ? (
            <ol>
              <li className="done">
                <i>
                  <Check size={17} />
                </i>
                <span>收集今日动态</span>
              </li>
              <li className="current">
                <i />
                <span>汇总待确认事项</span>
                <strong>
                  <em />
                  当前：判断优先级与关联性
                </strong>
              </li>
              <li>
                <i />
                <span>生成简报</span>
              </li>
            </ol>
          ) : (
            <div className="v278-live-log">
              <span>12:08</span>
              <p>已完成动态去重，正在判断优先级与当前目标的关联性。</p>
            </div>
          )}
        </div>
        <footer className="v278-player-controls">
          <div className="v279-control-menu">
            <button
              type="button"
              className="v278-speed"
              aria-expanded={speedOpen}
              onClick={() => {
                if(runtime){notify("执行速度由工具决定，任务进度实时读取");return;}
                setSpeedOpen((value) => !value);
                setModelOpen(false);
              }}
            >
              {runtime?"实时":speed.toFixed(1)+"×"}{!runtime&&<ChevronDown size={17} />}
            </button>
            {speedOpen && (
              <div className="v279-control-popover speed-options">
                {[0.5, 1, 1.5, 2].map((value) => (
                  <button
                    type="button"
                    key={value}
                    className={speed === value ? "active" : ""}
                    onClick={() => {
                      setSpeed(value);
                      setSpeedOpen(false);
                    }}
                  >
                    {value.toFixed(1)}×
                  </button>
                ))}
              </div>
            )}
          </div>
          <button
            type="button"
            aria-label="上一个任务"
            onClick={() => selectOffset(-1)}
          >
            <SkipBack size={27} fill="currentColor" />
          </button>
          <button
            type="button"
            className="v278-pause"
            aria-label={playing ? "暂停任务" : runtime?"查看任务":"继续任务"}
            onClick={togglePlayback}
          >
            {playing ? (
              <Pause size={30} fill="currentColor" />
            ) : (
              <Play size={29} fill="currentColor" />
            )}
          </button>
          <button
            type="button"
            aria-label="下一个任务"
            onClick={() => selectOffset(1)}
          >
            <SkipForward size={27} fill="currentColor" />
          </button>
          <div className="v279-control-menu">
            <button
              type="button"
              className="v278-model"
              aria-expanded={modelOpen}
              onClick={() => {
                setModelOpen((value) => !value);
                setSpeedOpen(false);
              }}
            >
              {runtime?"模型设置":model}
              <ChevronDown size={17} />
            </button>
            {modelOpen && !runtime && (
              <div className="v279-control-popover model-options">
                {["GPT-5.6", "GPT-5.6 深度", "GPT-5.6 快速"].map((value) => (
                  <button
                    type="button"
                    key={value}
                    className={model === value ? "active" : ""}
                    onClick={() => {
                      setModel(value);
                      setModelOpen(false);
                    }}
                  >
                    {value}
                  </button>
                ))}
              </div>
            )}
          </div>
        </footer>
      </section>
      {runtime&&modelOpen&&<RootPortal><button className="v278-sheet-backdrop" aria-label="关闭任务模型设置" onClick={()=>setModelOpen(false)}/><PlayerModelSettings key={activeId} task={liveTask} onClose={()=>setModelOpen(false)}/></RootPortal>}
      <form className="v278-player-composer" onSubmit={ask}>
        <button
          type="button"
          aria-label="添加内容"
          onClick={() => notify("可添加文件、链接或任务资料")}
        >
          <Plus size={25} />
        </button>
        <label>
          <input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="询问当前任务…"
          />
          <Mic size={22} />
        </label>
        <button type="submit" aria-label="发送问题" disabled={!question.trim()}>
          <ArrowUp size={23} />
        </button>
      </form>
      {queueOpen && (
        <PlayerQueueSheet
          tasks={playable}
          currentId={current?.id || ""}
          onSelect={(id) => {
            setActiveId(id);
            setQueueOpen(false);
          }}
          onClose={() => setQueueOpen(false)}
        />
      )}
    </main>
  );
}

export function PlayerQueueSheet({
  tasks,
  currentId,
  onSelect,
  onClose,
}: {
  tasks: V277Task[];
  currentId: string;
  onSelect: (id: string) => void;
  onClose: () => void;
}) {
  const dragStart = useRef(0);
  const [dragY, setDragY] = useState(0);
  const finishDrag = () => {
    if (dragY > 82) onClose();
    else setDragY(0);
  };
  return (
    <RootPortal>
      <button
        type="button"
        className="v278-sheet-backdrop"
        aria-label="关闭任务列表"
        onClick={onClose}
      />
      <section
        className="v278-half-sheet v279-player-queue-sheet"
        style={{ "--queue-drag": `${dragY}px` } as CSSProperties}
        role="dialog"
        aria-modal="true"
        aria-label="任务列表"
        onPointerDown={(event) => {
          dragStart.current = event.clientY;
        }}
        onPointerMove={(event) => {
          if (!dragStart.current) return;
          setDragY(
            Math.max(0, Math.min(190, event.clientY - dragStart.current)),
          );
        }}
        onPointerUp={finishDrag}
        onPointerCancel={finishDrag}
      >
        <i className="v278-sheet-handle" />
        <header className="v278-sheet-header">
          <span>
            <h2>任务列表</h2>
            <p>选择任务继续查看执行过程</p>
          </span>
          <button type="button" aria-label="关闭" onClick={onClose}>
            <X size={21} />
          </button>
        </header>
        <div className="v279-player-queue-list">
          {tasks.length ? (
            tasks.map((task) => (
              <button
                type="button"
                key={task.id}
                className={task.id === currentId ? "active" : ""}
                onClick={() => onSelect(task.id)}
              >
                <i />
                <span>
                  <b>{displayTitle(task.title,'')}</b>
                  <small>
                    {agentList.find((agent) => agent.id === task.agent)?.name}{" "}
                    Agent · {task.runtimeStatus?runtimeStatuses[task.runtimeStatus]||task.status:task.status}
                  </small>
                </span>
                {task.id === currentId ? (
                  <Play size={18} fill="currentColor" />
                ) : (
                  <ChevronRight size={18} />
                )}
              </button>
            ))
          ) : (
            <div className="v277-empty">
              <ListChecks size={22} />
              <b>暂无可播放任务</b>
              <p>回到首页创建一个任务。</p>
            </div>
          )}
        </div>
      </section>
    </RootPortal>
  );
}

export function TodayHighlights({
  state,
  go,
  onBack,
}: {
  state: V277State;
  go: (screen: Screen) => void;
  onBack: () => void;
}) {
  const openTasks = state.tasks.filter((task) => task.status !== "已完成");
  return (
    <main className="v277-page v278-highlights-page">
      <AppHeader
        title="今日重点"
        subtitle="只保留今天需要注意的内容"
        onBack={onBack}
      />
      <section className="v278-highlight-summary">
        <small>今日建议</small>
        <h1>
          {openTasks.length
            ? "先确认一项任务，再继续获取新信息"
            : "先从一项明确目标开始"}
        </h1>
        <p>
          首页简报中的动态、待确认和执行状态，都在这里对应到可点击的具体内容。
        </p>
      </section>
      <section className="v278-highlight-list">
        <h2>需要你处理</h2>
        {openTasks.length ? (
          openTasks.slice(0, 3).map((task, index) => (
            <button
              type="button"
              key={task.id}
              onClick={() => go({ name: "task", id: task.id })}
            >
              <em>0{index + 1}</em>
              <span>
                <b>{displayTitle(task.title,'')}</b>
                <small>
                  {task.status} · {task.nextStep}
                </small>
              </span>
              <ChevronRight size={19} />
            </button>
          ))
        ) : (
          <button
            type="button"
            onClick={() => go({ name: "chat", id: "elfred" })}
          >
            <em>01</em>
            <span>
              <b>告诉 Elfred 一个当前目标</b>
              <small>生成第一份可以确认的任务草稿</small>
            </span>
            <ChevronRight size={19} />
          </button>
        )}
      </section>
      <section className="v278-highlight-list">
        <h2>值得查看</h2>
        <button
          type="button"
          onClick={() => go({ name: "post", id: v277Posts[0].id })}
        >
          <em>01</em>
          <span>
            <b>{displayTitle(v277Posts[0].title,'')}</b>
            <small>探索 Agent · 与当前目标相关</small>
          </span>
          <ChevronRight size={19} />
        </button>
      </section>
    </main>
  );
}

export function Toast({ text }: { text: string }) {
  return (
    <div className="v277-toast" role="status">
      <Check size={16} />
      {text}
    </div>
  );
}

export function LegalSheet({
  kind,
  onClose,
}: {
  kind: "terms" | "privacy";
  onClose: () => void;
}) {
  const title = kind === "terms" ? "用户协议" : "隐私政策";
  return (
    <RootPortal>
      <button
        type="button"
        className="v278-sheet-backdrop"
        aria-label={`关闭${title}`}
        onClick={onClose}
      />
      <section className="v280-legal-sheet" role="dialog" aria-modal="true">
        <i className="v278-sheet-handle" />
        <header className="v279-sheet-title">
          <h2>{title}</h2>
          <IconButton label="关闭" onClick={onClose}>
            <X size={20} />
          </IconButton>
        </header>
        <div>
          <p>
            {kind === "terms"
              ? "继续使用即表示你同意 Elfred 在当前设备中保存登录状态、个人设置与使用记录，以提供连续的 Personal Agent 体验。"
              : "Elfred 只在你明确操作时使用相关信息。私人记忆、任务与对话不会出现在公开主页或分享内容中。"}
          </p>
          <p>涉及发送、发布、删除、付费或联系人邀请时，始终需要再次确认。</p>
        </div>
      </section>
    </RootPortal>
  );
}

export function LoginPage({
  state,
  setState,
}: {
  state: V277State;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
}) {
  const runtime=useRuntime();
  const [identifier, setIdentifier] = useState(state.account.identifier);
  const [legal, setLegal] = useState<"terms" | "privacy" | null>(null);
  const normalized = identifier.trim();
  const valid =
    (runtime && /^[a-zA-Z0-9_.@-]{3,80}$/.test(normalized)) || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized) ||
    /^1\d{10}$/.test(normalized.replace(/\s/g, ""));
  const quickLogin = (provider: "wechat" | "apple") => {
    if(runtime){runtime.report('该登录服务尚未配置，请使用本地账号登录');return;}
    setState((current) => ({
      ...current,
      account: {
        ...current.account,
        identifier: provider === "wechat" ? "微信账号" : "Apple ID",
        provider,
        verified: true,
      },
      phase: current.account.onboardingComplete ? "ready" : "welcome",
    }));
  };
  return (
    <main className="v280-auth-page">
      <div className="v280-auth-brand" aria-label="Elfred">
        <span>
          <Sparkles size={25} strokeWidth={1.9} />
        </span>
        <b>Elfred</b>
      </div>
      <section className="v280-auth-copy">
        <h1>欢迎使用 Elfred</h1>
        <p>一个持续理解你、帮助你行动的 Personal Agent。</p>
      </section>
      <form
        className="v280-login-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!valid) return;
          setState((current) => ({
            ...current,
            account: {
              ...current.account,
              identifier: normalized,
              provider: "contact",
              verified: false,
            },
            phase: "verify",
          }));
        }}
      >
        <label>
          <span>手机号或邮箱</span>
          <input
            value={identifier}
            onChange={(event) => setIdentifier(event.target.value)}
            placeholder="输入手机号或邮箱"
            inputMode="email"
            autoComplete="username"
          />
        </label>
        <button className="v277-primary" type="submit" disabled={!valid}>
          继续
        </button>
      </form>
      <div className="v280-auth-divider"><span>或</span></div>
      <div className="v280-quick-login">
        <button type="button" onClick={() => quickLogin("wechat")}>
          <MessageCircle size={21} />
          微信登录
        </button>
        <button type="button" onClick={() => quickLogin("apple")}>
          <Apple size={21} />
          Apple 登录
        </button>
      </div>
      <p className="v280-auth-legal">
        继续即表示你同意
        <button type="button" onClick={() => setLegal("terms")}>用户协议</button>
        和
        <button type="button" onClick={() => setLegal("privacy")}>隐私政策</button>
      </p>
      {legal && <LegalSheet kind={legal} onClose={() => setLegal(null)} />}
    </main>
  );
}

export function VerifyPage({
  state,
  setState,
}: {
  state: V277State;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
}) {
  const runtime=useRuntime();
  const [password,setPassword]=useState('');
  const [register,setRegister]=useState(false);
  const [busy,setBusy]=useState(false);
  const [code, setCode] = useState(["", "", "", "", "", ""]);
  const [cooldown, setCooldown] = useState(0);
  const codeRefs = useRef<Array<HTMLInputElement | null>>([]);
  useEffect(() => {
    if (!cooldown) return;
    const timer = window.setInterval(
      () => setCooldown((value) => Math.max(0, value - 1)),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [cooldown]);
  const complete = code.every(Boolean);
  if(runtime)return <main className="v280-onboarding-page"><AppHeader title={register?'创建本地账号':'登录本地账号'} onBack={()=>setState(current=>({...current,phase:'auth'}))}/><section className="v280-step-copy"><h1>确认这是你的账号</h1><p>{state.account.identifier}</p><p>本地模式使用密码。短信、微信与 Apple 登录尚未接通。</p></section><form className="v280-login-form" onSubmit={async event=>{event.preventDefault();setBusy(true);try{await runtime.login(state.account.identifier,password,register)}catch{}finally{setBusy(false)}}}><label><span>密码（10—128 位）</span><input type="password" aria-label="账号密码" minLength={10} maxLength={128} required value={password} autoComplete={register?'new-password':'current-password'} onChange={event=>setPassword(event.target.value)}/></label><button className="v277-primary" disabled={busy||password.length<10}>{busy?'正在处理…':register?'创建账号并继续':'登录并继续'}</button><button type="button" className="v277-secondary" onClick={()=>setRegister(!register)}>{register?'已有账号，去登录':'首次使用，创建账号'}</button></form></main>;
  return (
    <main className="v280-onboarding-page">
      <AppHeader
        title="输入验证码"
        onBack={() => setState((current) => ({ ...current, phase: "auth" }))}
      />
      <section className="v280-step-copy">
        <h1>确认这是你的账号</h1>
        <p>验证码已发送到</p>
        <strong>{state.account.identifier}</strong>
      </section>
      <div className="v280-code-input" aria-label="六位验证码">
        {code.map((value, index) => (
          <input
            key={index}
            ref={(element) => { codeRefs.current[index] = element; }}
            aria-label={`验证码第 ${index + 1} 位`}
            value={value}
            inputMode="numeric"
            autoComplete={index === 0 ? "one-time-code" : "off"}
            maxLength={1}
            onChange={(event) => {
              const nextValue = event.target.value.replace(/\D/g, "").slice(-1);
              const next = [...code];
              next[index] = nextValue;
              setCode(next);
              if (nextValue) codeRefs.current[index + 1]?.focus();
            }}
            onKeyDown={(event) => {
              if (event.key === "Backspace" && !value)
                codeRefs.current[index - 1]?.focus();
            }}
          />
        ))}
      </div>
      <button
        type="button"
        className="v280-resend"
        disabled={cooldown > 0}
        onClick={() => {
          setCode(["", "", "", "", "", ""]);
          setCooldown(60);
          codeRefs.current[0]?.focus();
        }}
      >
        {cooldown ? `${cooldown} 秒后可重新发送` : "重新发送验证码"}
      </button>
      <div className="v280-onboarding-action">
        <button
          type="button"
          className="v277-primary"
          disabled={!complete}
          onClick={() =>
            setState((current) => ({
              ...current,
              account: { ...current.account, verified: true },
              phase: current.account.onboardingComplete ? "ready" : "welcome",
            }))
          }
        >
          继续
        </button>
      </div>
    </main>
  );
}

export function OnboardingWelcome({
  setState,
}: {
  setState: React.Dispatch<React.SetStateAction<V277State>>;
}) {
  return (
    <main className="v280-welcome-page">
      <IconButton
        label="返回"
        onClick={() => setState((current) => ({ ...current, phase: "auth" }))}
      >
        <ArrowLeft size={21} />
      </IconButton>
      <section>
        <span className="v280-welcome-mark">
          <Sparkles size={32} strokeWidth={1.7} />
        </span>
        <h1>让 Elfred 开始理解你</h1>
        <p>
          Elfred 会通过你的目标、选择和日常使用逐渐形成属于你的 Personal Agent。
        </p>
      </section>
      <div className="v280-onboarding-action">
        <button
          type="button"
          className="v277-primary"
          onClick={() => setState((current) => ({ ...current, phase: "profile-init" }))}
        >
          开始设置
        </button>
      </div>
    </main>
  );
}

export function ProfileInitPage({
  state,
  setState,
}: {
  state: V277State;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
}) {
  const runtime=useRuntime();
  const [name, setName] = useState(state.profile.name);
  const [role, setRole] = useState(state.profile.role);
  const [focus, setFocus] = useState(state.profile.focus);
  const [avatar, setAvatar] = useState("");
  const valid = Boolean(name.trim() && focus.trim());
  return (
    <main className="v280-onboarding-page v280-profile-init">
      <AppHeader
        title="个人信息"
        subtitle="1 / 2"
        onBack={() => setState((current) => ({ ...current, phase: "welcome" }))}
      />
      <section className="v280-step-copy compact">
        <h1>先认识一下你</h1>
        <p>只填写最必要的信息，之后都可以在设置中修改。</p>
      </section>
      <label className="v280-init-avatar">
        <span>
          {avatar ? <img src={avatar} alt="已选择的头像" /> : <UserRound size={28} />}
        </span>
        <b>添加头像</b>
        <small>选填</small>
        <input
          type="file"
          accept="image/*"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if(file&&runtime){if(file.size>250000){runtime.report('头像需小于 250 KB');return;}const reader=new FileReader();reader.onload=()=>setAvatar(String(reader.result));reader.readAsDataURL(file);}else if (file) setAvatar(URL.createObjectURL(file));
          }}
        />
      </label>
      <section className="v280-init-fields">
        <label>
          <span>怎么称呼你 <b>必填</b></span>
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder="你的名字" />
        </label>
        <label>
          <span>你现在主要在做什么 <em>选填</em></span>
          <input value={role} onChange={(event) => setRole(event.target.value)} placeholder="例如：产品经理与创业者" />
        </label>
        <label>
          <span>最近最重要的一件事 <b>必填</b></span>
          <textarea value={focus} onChange={(event) => setFocus(event.target.value)} maxLength={100} placeholder="例如：完成产品首批用户测试" />
        </label>
      </section>
      <div className="v280-onboarding-action">
        <button
          type="button"
          className="v277-primary"
          disabled={!valid}
          onClick={() => {if(runtime?.snapshot){void runtime.command('profile.save',{...entityRef(runtime.snapshot.objects.profile[0]),...state.profile,name:name.trim(),role:role.trim(),...(avatar?{avatar}:{})}).then(()=>runtime.command('onboarding.save',{...entityRef(runtime.snapshot!.objects.onboarding[0]),intent:focus.trim()})).then(()=>setState(current=>({...current,phase:'agents-init'}))).catch(()=>{});return;}
            setState((current) => ({
              ...current,
              profile: {
                ...current.profile,
                name: name.trim(),
                role: role.trim(),
                focus: focus.trim(),
              },
              phase: "agents-init",
            }));}
          }
        >
          继续
        </button>
      </div>
    </main>
  );
}

export function AgentAdjustSheet({
  id,
  state,
  setState,
  onClose,
}: {
  id: V277AgentId;
  state: V277State;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState(state.agentSetup[id]);
  return (
    <RootPortal>
      <button type="button" className="v278-sheet-backdrop" aria-label="关闭 Agent 调整" onClick={onClose} />
      <section className="v280-agent-adjust-sheet" role="dialog" aria-modal="true">
        <i className="v278-sheet-handle" />
        <header className="v279-sheet-title">
          <h2>调整 {agentList.find((agent) => agent.id === id)?.name} Agent</h2>
          <IconButton label="关闭" onClick={onClose}><X size={20} /></IconButton>
        </header>
        <div className="v280-adjust-fields">
          <label>
            <span>名称</span>
            <input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
          </label>
          <label>
            <span>关注方向</span>
            <textarea value={draft.focus} onChange={(event) => setDraft({ ...draft, focus: event.target.value })} />
          </label>
          <button type="button" className="v280-adjust-toggle" onClick={() => setDraft({ ...draft, enabled: !draft.enabled })}>
            <span><b>启用 Agent</b><small>关闭后不会主动工作</small></span>
            <i className={draft.enabled ? "active" : ""}><em /></i>
          </button>
        </div>
        <button
          type="button"
          className="v277-primary v280-sheet-primary"
          onClick={() => {
            setState((current) => ({
              ...current,
              agentSetup: { ...current.agentSetup, [id]: draft },
            }));
            onClose();
          }}
        >
          保存调整
        </button>
      </section>
    </RootPortal>
  );
}

export function AgentInitPage({
  state,
  setState,
}: {
  state: V277State;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
}) {
  const [adjusting, setAdjusting] = useState<V277AgentId | null>(null);
  return (
    <main className="v280-onboarding-page v280-agent-init">
      <AppHeader
        title="你的 Agent 团队"
        subtitle="2 / 2"
        onBack={() => setState((current) => ({ ...current, phase: "profile-init" }))}
      />
      <section className="v280-agent-intro">
        <p>我们根据你的目标准备了五个基础 Agent，之后可以随时调整。</p>
      </section>
      <section className="v280-agent-setup-list">
        {agentList.map((agent) => {
          const config = state.agentSetup[agent.id];
          const Icon = agent.icon;
          return (
            <article key={agent.id}>
              <span><Icon size={21} /></span>
              <div><b>{config.name}</b><p>{config.focus}</p></div>
              <button type="button" onClick={() => setAdjusting(agent.id)}>调整</button>
              <em className={config.enabled ? "active" : ""}>{config.enabled ? "已启用" : "已关闭"}</em>
            </article>
          );
        })}
      </section>
      <div className="v280-onboarding-action">
        <button type="button" className="v277-primary" onClick={() => setState((current) => ({ ...current, phase: "complete" }))}>
          使用默认设置并继续
        </button>
      </div>
      {adjusting && <AgentAdjustSheet id={adjusting} state={state} setState={setState} onClose={() => setAdjusting(null)} />}
    </main>
  );
}

export function OnboardingComplete({
  state,
  finish,
  onBack,
}: {
  state: V277State;
  finish: () => void;
  onBack: () => void;
}) {
  return (
    <main className="v280-complete-page">
      <IconButton label="返回" onClick={onBack}><ArrowLeft size={21} /></IconButton>
      <section className="v280-complete-copy">
        <span className="v280-welcome-mark"><Sparkles size={31} strokeWidth={1.7} /></span>
        <h1>Elfred 已准备好</h1>
        <p>它会从今天开始持续理解你，并在重要节点帮助你做出选择。</p>
      </section>
      <section className="v280-complete-agents">
        {agentList.map((agent) => {
          const config = state.agentSetup[agent.id];
          return <div key={agent.id}><span><i className={config.enabled ? "active" : ""} />{config.name}</span><em>{config.enabled ? "已启用" : "已关闭"}</em></div>;
        })}
      </section>
      <div className="v280-onboarding-action">
        <button type="button" className="v277-primary" onClick={finish}>进入首页</button>
      </div>
    </main>
  );
}


export function BriefSettingsSheet({
  initial = readBriefPreferences(),
  onSave,
  onClose,
}: {
  initial?: BriefPreferences;
  onSave?: (next: BriefPreferences) => void;
  onClose: () => void;
}) {
  const runtime=useRuntime();
  initial={...initial,...runtime?.snapshot?.objects.settings[0].data.brief_preferences as Partial<BriefPreferences>};
  const [morning, setMorning] = useState(initial.morning);
  const [noon, setNoon] = useState(initial.noon);
  const [evening, setEvening] = useState(initial.evening);
  const [morningModule, setMorningModule] = useState(initial.morningModule);
  const [noonModule, setNoonModule] = useState(initial.noonModule);
  const [eveningModule, setEveningModule] = useState(initial.eveningModule);
  const [style, setStyle] = useState(initial.style);
  const saveSettings = () => {
    const next = {
      morning,
      noon,
      evening,
      morningModule,
      noonModule,
      eveningModule,
      style,
    };
    if(runtime?.snapshot){void runtime.command('brief.preferences',{...entityRef(runtime.snapshot.objects.settings[0]),preferences:next}).then(()=>{onSave?.(next);onClose()}).catch(()=>{});return;}
    window.localStorage.setItem(
      "elfred-v278-brief-settings",
      JSON.stringify(next),
    );
    onSave?.(next);
    if (!onSave) onClose();
  };
  return (
    <RootPortal>
      <button
        type="button"
        className="v278-sheet-backdrop"
        aria-label="关闭简报设置"
        onClick={onClose}
      />
      <section className="v283-brief-settings" role="dialog" aria-modal="true">
        <i className="v283-sheet-handle" />
        <header>
          <span>
            <h2>三时简报设置</h2>
            <p>调整出现时间、内容重点与卡片风格</p>
          </span>
          <button type="button" onClick={onClose} aria-label="关闭">
            <X size={20} />
          </button>
        </header>
        <div className="v283-brief-setting-list">
          {[
            ["开始今天", morning, setMorning, ["07:30", "08:00", "09:00"], morningModule, setMorningModule, ["重点与计划", "仅关键事项", "事项与 Agent"]],
            ["中场校准", noon, setNoon, ["12:00", "12:30", "13:00"], noonModule, setNoonModule, ["进展与阻塞", "仅阻塞事项", "进展与下午安排"]],
            ["今日回顾", evening, setEvening, ["19:30", "20:30", "21:30"], eveningModule, setEveningModule, ["成果与沉淀", "仅今日成果", "成果与未完成"]],
          ].map(([label, value, setter, options, module, moduleSetter, moduleOptions]) => (
            <label key={label as string}>
              <span>
                <b>{label as string}</b>
                <small>{module as string}</small>
              </span>
              <span className="v283-brief-setting-controls">
                <select
                  aria-label={`${label as string}出现时间`}
                  value={value as string}
                  onChange={(event) =>
                    (setter as React.Dispatch<React.SetStateAction<string>>)(
                      event.target.value,
                    )
                  }
                >
                  {(options as string[]).map((option) => (
                    <option key={option}>{option}</option>
                  ))}
                </select>
                <select
                  aria-label={`${label as string}内容模块`}
                  value={module as string}
                  onChange={(event) =>
                    (moduleSetter as React.Dispatch<React.SetStateAction<string>>)(
                      event.target.value,
                    )
                  }
                >
                  {(moduleOptions as string[]).map((option) => (
                    <option key={option}>{option}</option>
                  ))}
                </select>
              </span>
            </label>
          ))}
          <label>
            <span>
              <b>卡片风格</b>
              <small>只影响卡组的内容密度</small>
            </span>
            <select value={style} onChange={(event) => setStyle(event.target.value)}>
              <option>标准</option>
              <option>简洁</option>
              <option>紧凑</option>
            </select>
          </label>
        </div>
        <button type="button" className="v283-sheet-primary" onClick={saveSettings}>
          保存设置
        </button>
      </section>
    </RootPortal>
  );
}

const morningPlan = [
  ["确认首页信息层级", "advisor"],
  ["完善三时卡片交互", "create"],
  ["整理第一批内测名单", "execute"],
] as const;

export function DailyBriefPage({
  kind,
  state,
  setState,
  go,
  onBack,
  notify,
}: {
  kind: Exclude<DailyBriefKind, "evening">;
  state: V277State;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
  go: (screen: Screen) => void;
  onBack: () => void;
  notify: (text: string) => void;
}) {
  const runtime=useRuntime();
  const localDate=new Intl.DateTimeFormat('en-CA',{timeZone:String(runtime?.snapshot?.objects.settings[0].data.timezone||'Asia/Shanghai'),year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const brief=runtime?.snapshot?.objects.brief.find(item=>item.data.kind===kind&&item.data.local_date===localDate&&item.data.timezone===runtime.snapshot?.objects.settings[0].data.timezone);
  const briefCommand=runtime?.command,briefId=brief?.id,briefTimezone=runtime?.snapshot?.objects.settings[0].data.timezone;
  useEffect(()=>{if(briefCommand&&!briefId)void briefCommand('brief.create',{kind}).catch(()=>{});},[briefCommand,briefId,kind,localDate,briefTimezone]);
  const [moreOpen, setMoreOpen] = useState(false);
  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const dayId = getBriefDayId();
  const [confirmed, setConfirmed] = useState(
    state.tasks.some((task) => task.sourceId === `daily-morning-${getBriefDayId()}`),
  );
  const [afternoonAdopted, setAfternoonAdopted] = useState(
    state.tasks.some((task) => task.sourceId === `daily-noon-${getBriefDayId()}`),
  );
  const [question, setQuestion] = useState("");
  const title =
    kind === "morning"
      ? "开始今天"
      : "中场校准";

  const createBriefTask = (
    id: string,
    taskTitle: string,
    agent: V277AgentId,
    status: V277TaskStatus = "待确认",
  ): V277Task => ({
    id,
    title: taskTitle,
    brief: "来自三时简报，围绕今天的目标继续推进。",
    source: title + " · " + formatToday(),
    sourceId: `daily-${kind}-${dayId}`,
    agent,
    status,
    nextStep:
      status === "进行中" ? "Agent 正在准备第一版结果" : "确认目标与执行顺序",
    result: ["确认完成标准", "完成第一版交付", "把结论同步回简报"],
    knowledgeIds: [],
    updatedAt: "刚刚",
  });

  const openPlanTask = (
    index: number,
    taskTitle: string,
    agent: V277AgentId,
  ) => {
    const id = `brief-${kind}-${dayId}-${index}`;
    if (!state.tasks.some((task) => task.id === id)) {
      setState((current) => ({
        ...current,
        tasks: [createBriefTask(id, taskTitle, agent), ...current.tasks],
      }));
    }
    go({ name: "task", id });
  };

  const confirmMorning = () => {
    setState((current) => {
      const ids = new Set(current.tasks.map((task) => task.id));
      const added = morningPlan
        .map(([taskTitle, agent], index) =>
          createBriefTask(
            `brief-morning-${dayId}-${index}`,
            taskTitle,
            agent,
            index === 0 ? "进行中" : "待确认",
          ),
        )
        .filter((task) => !ids.has(task.id));
      return { ...current, tasks: [...added, ...current.tasks] };
    });
    setConfirmed(true);
    notify("今日计划已确认，任务与 Agent 已同步");
  };

  const updateBlockedTask = (mode: "delay" | "confirm") => {
    const id = `brief-noon-blocked-${dayId}`;
    setState((current) => {
      const existing = current.tasks.find((task) => task.id === id);
      const status: V277TaskStatus = mode === "confirm" ? "进行中" : "已暂停";
      const next = existing
        ? current.tasks.map((task) =>
            task.id === id
              ? {
                  ...task,
                  status,
                  nextStep:
                    mode === "confirm"
                      ? "等待你确认首页方案"
                      : "已顺延到下午计划末尾",
                  updatedAt: "刚刚",
                }
              : task,
          )
        : [
            createBriefTask(id, "确认首页方案", "advisor", status),
            ...current.tasks,
          ];
      return { ...current, tasks: next };
    });
    notify(mode === "confirm" ? "已置顶确认事项" : "已延后到下午处理");
  };

  const adoptAfternoonPlan = () => {
    const plan = [
      ["14:00 确认首页方案", "advisor"],
      ["15:00 完成 UI 更新", "create"],
      ["17:00 整理内测名单", "execute"],
    ] as const;
    setState((current) => {
      const planIds = new Set(plan.map((_, index) => `brief-afternoon-${dayId}-${index}`));
      const rest = current.tasks.filter((task) => !planIds.has(task.id));
      const tasks = plan.map(([taskTitle, agent], index) =>
        createBriefTask(
          `brief-afternoon-${dayId}-${index}`,
          taskTitle,
          agent,
          index === 0 ? "进行中" : "待确认",
        ),
      );
      return { ...current, tasks: [...tasks, ...rest] };
    });
    setAfternoonAdopted(true);
    notify("下午任务顺序已同步到任务页");
  };

  const shareBrief = async () => {
    if(runtime){try{await navigator.clipboard.writeText(title+'\n'+state.tasks.map(task=>task.title+' · '+task.nextStep).join('\n'));notify('简报摘要已复制')}catch{notify('复制失败')}setMoreOpen(false);return;}
    const shareText = `${title}｜${dailyBriefs[kind].title}\n${dailyBriefs[kind].stats}`;
    try {
      if (navigator.share) {
        await navigator.share({ title, text: shareText });
        notify("简报摘要已分享");
      } else {
        await navigator.clipboard.writeText(shareText);
        notify("简报摘要已复制");
      }
    } catch {}
    setMoreOpen(false);
  };

  const submitQuestion = (event: FormEvent) => {
    event.preventDefault();
    if (!question.trim()) return;
    if(runtime){void runtime.command('task.create',{goal:question,mode:'compose',system:'execute'}).then(result=>go({name:'task',id:result.id})).catch(()=>{});return;}
    const message: V277Message = {
      id: makeId("brief-question"),
      role: "user",
      text: question.trim(),
      time: "刚刚",
    };
    setState((current) => ({
      ...current,
      messages: {
        ...current.messages,
        elfred: [...(current.messages.elfred || []), message],
      },
    }));
    go({ name: "chat", id: "elfred" });
  };

  return (
    <main className="v277-page v283-brief-page">
      <header className="v283-brief-head">
        <IconButton label="返回" onClick={onBack}>
          <ArrowLeft size={22} />
        </IconButton>
        <span>
          <h1>{title}</h1>
          <small>{formatToday()}</small>
        </span>
        <IconButton
          label="更多操作"
          onClick={() => setMoreOpen((current) => !current)}
        >
          <MoreHorizontal size={22} />
        </IconButton>
        {moreOpen && (
          <div className="v283-brief-more">
            <button type="button" onClick={shareBrief}>
              <Share2 size={17} />
              分享摘要
            </button>
            <button
              type="button"
              onClick={() => {
                setMoreOpen(false);
                setPreferencesOpen(true);
              }}
            >
              <Settings2 size={17} />
              简报偏好
            </button>
          </div>
        )}
      </header>

      <div className="v283-brief-scroll">
        <section className="v283-brief-conclusion">
          <small>{dailyBriefs[kind].label}</small>
          <h2>{runtime?({morning:"从今天的重点开始",noon:"核对进展与待处理事项",evening:"核对今日成果与理解"}[kind]):displayTitle(dailyBriefs[kind].title,'')}</h2>
          <p>{runtime?"依据当前真实任务记录，请核对今天的重点与进展。":dailyBriefs[kind].summary}</p>
          <strong>{runtime?((brief?.data.facts||[]) as BriefFact[]).length+" 项今日任务 · "+((brief?.data.facts||[]) as BriefFact[]).filter(task=>task.status==="completed").length+" 项已验收":dailyBriefs[kind].stats}</strong>
        </section>

        {runtime&&<BriefActions key={brief?.id||kind} brief={brief} kind={kind} go={go}/>}
        {!runtime&&kind === "morning" && (
          <>
            <section className="v283-brief-section">
              <h3>今日安排</h3>
              <div className="v283-number-list">
                {morningPlan.map(([taskTitle, agent], index) => (
                  <button
                    type="button"
                    key={taskTitle}
                    onClick={() => openPlanTask(index, taskTitle, agent)}
                  >
                    <em>0{index + 1}</em>
                    <span>{taskTitle}</span>
                    <ChevronRight size={19} />
                  </button>
                ))}
              </div>
            </section>
            <section className="v283-brief-section">
              <h3>Agent 今日计划</h3>
              <div className="v283-agent-plan-card">
                {[
                  ["explore", "收集产品案例"],
                  ["create", "输出界面方案"],
                  ["execute", "整理内测资料"],
                ].map(([agentId, task]) => {
                  const agent = agentList.find((item) => item.id === agentId)!;
                  const AgentIcon = agent.icon;
                  return (
                    <button
                      type="button"
                      key={agentId}
                      onClick={() =>
                        go({ name: "agent", id: agentId as V277AgentId })
                      }
                    >
                      <i>
                        <AgentIcon size={18} />
                      </i>
                      <b>{agent.name} Agent</b>
                      <span>{task}</span>
                      <ChevronRight size={18} />
                    </button>
                  );
                })}
                <button
                  type="button"
                  className="v283-brief-primary"
                  onClick={confirmMorning}
                >
                  {confirmed ? (
                    <>
                      <Check size={19} />
                      今日计划已确认
                    </>
                  ) : (
                    "确认今天的计划"
                  )}
                </button>
              </div>
            </section>
          </>
        )}

        {!runtime&&kind === "noon" && (
          <>
            <section className="v283-brief-section">
              <h3>当前进度</h3>
              <div className="v283-status-list">
                {[
                  ["竞品案例检索", "已完成", true],
                  ["首页结构分析", "已完成", true],
                  ["UI 方案生成", "进行中", false],
                ].map(([task, status, done], index) => (
                  <button
                    type="button"
                    key={task as string}
                    onClick={() =>
                      openPlanTask(
                        index,
                        task as string,
                        index === 0 ? "explore" : index === 1 ? "advisor" : "create",
                      )
                    }
                  >
                    {done ? <CheckCircle2 size={22} /> : <Circle size={22} />}
                    <b>{task as string}</b>
                    <span>{status as string}</span>
                    <ChevronRight size={18} />
                  </button>
                ))}
              </div>
            </section>
            <section className="v283-brief-section">
              <h3>需要调整</h3>
              <div className="v283-decision-card">
                <span>
                  <Circle size={22} />
                  <b>首页方案等待确认</b>
                  <small>比原计划晚 1 小时</small>
                </span>
                <footer>
                  <button type="button" onClick={() => updateBlockedTask("delay")}>
                    延后处理
                  </button>
                  <button type="button" onClick={() => updateBlockedTask("confirm")}>
                    立即确认
                  </button>
                </footer>
              </div>
            </section>
            <section className="v283-brief-section">
              <h3>下午安排</h3>
              <div className="v283-time-card">
                {[
                  ["14:00", "确认首页方案"],
                  ["15:00", "完成 UI 更新"],
                  ["17:00", "整理内测名单"],
                ].map(([time, task]) => (
                  <button
                    type="button"
                    key={time}
                    onClick={() =>
                      openPlanTask(
                        Number(time.slice(0, 2)),
                        `${time} ${task}`,
                        time === "14:00" ? "advisor" : time === "15:00" ? "create" : "execute",
                      )
                    }
                  >
                    <time>{time}</time>
                    <span>{task}</span>
                    <ChevronRight size={18} />
                  </button>
                ))}
                <button
                  type="button"
                  className="v283-card-action"
                  onClick={adoptAfternoonPlan}
                >
                  {afternoonAdopted ? "下午安排已采用" : "采用下午安排"}
                  <ChevronRight size={18} />
                </button>
              </div>
            </section>
          </>
        )}

      </div>

      <form className="v283-brief-composer" onSubmit={submitQuestion}>
        <input
          aria-label={"询问" + title}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={
            kind === "morning" ? "问问今天的安排…" : "问问下午的安排…"
          }
        />
        <VoiceInput onText={value=>setQuestion(previous=>previous+value)}/>
        <button type="submit" aria-label="发送">
          <Send size={21} />
        </button>
      </form>
      {preferencesOpen && (
        <BriefSettingsSheet onClose={() => setPreferencesOpen(false)} />
      )}
    </main>
  );
}

export function GlobalSearchSheet({
  state,
  go,
  onClose,
}: {
  state: V277State;
  go: (screen: Screen) => void;
  onClose: () => void;
}) {
  const runtime=useRuntime();
  const [hits,setHits]=useState<{id:string;type:string;title:string;excerpt:string;anchor:string}[]>([]);
  const [query, setQuery] = useState("");
  const normalized = query.trim().toLowerCase();
  useEffect(()=>{if(!runtime)return;if(!normalized){setHits([]);return;}let active=true;const timer=setTimeout(()=>{void runtime.request<{hits:typeof hits}>('/search',{query:normalized}).then(result=>{if(active)setHits(result.hits)}).catch(()=>{if(active)setHits([])})},250);return()=>{active=false;clearTimeout(timer)}},[normalized]);
  const results = runtime?hits.map(item=>({key:item.id,type:item.type,title:item.title,copy:item.excerpt+' · '+item.anchor,action:()=>{const object=Object.values(runtime.snapshot?.objects||{}).flat().find(o=>o.id===item.id);if(object)go(objectScreen(object));else runtime.report('内容已变化，请刷新搜索。')}})):normalized
    ? [
        ...v277Posts
          .filter((item) =>
            `${item.title}${item.summary}${item.label}`
              .toLowerCase()
              .includes(normalized),
          )
          .map((item) => ({
            key: `post-${item.id}`,
            type: "内容",
            title: item.title,
            copy: `${agentList.find((agent) => agent.id === item.agent)?.name} Agent · ${item.summary}`,
            action: () => go({ name: "post", id: item.id }),
          })),
        ...state.tasks
          .filter((item) =>
            `${item.title}${item.brief}${item.nextStep}`
              .toLowerCase()
              .includes(normalized),
          )
          .map((item) => ({
            key: `task-${item.id}`,
            type: "任务",
            title: item.title,
            copy: `${item.status} · ${item.nextStep}`,
            action: () => go({ name: "task", id: item.id }),
          })),
        ...v277Knowledge
          .filter((item) =>
            `${item.title}${item.purpose}${item.source}`
              .toLowerCase()
              .includes(normalized),
          )
          .map((item) => ({
            key: `knowledge-${item.id}`,
            type: "知识",
            title: item.title,
            copy: item.purpose,
            action: () => go({ name: "knowledge-detail", id: item.id }),
          })),
        ...state.memories
          .filter((item) =>
            `${item.label}${item.value}${item.source}`
              .toLowerCase()
              .includes(normalized),
          )
          .map((item) => ({
            key: `memory-${item.id}`,
            type: "记忆",
            title: item.label,
            copy: item.value,
            action: () => go({ name: "memory-detail", id: item.id }),
          })),
        ...Object.entries(chatDirectory)
          .filter(([, item]) =>
            `${item.name}${item.subtitle}`.toLowerCase().includes(normalized),
          )
          .map(([id, item]) => ({
            key: `person-${id}`,
            type: "人物",
            title: item.name,
            copy: item.subtitle,
            action: () => go({ name: "chat", id }),
          })),
      ].slice(0, 12)
    : [];
  if(runtime)return <ConnectedSearch go={go} onClose={onClose}/>;
  return (
    <RootPortal>
      <button
        type="button"
        className="v278-sheet-backdrop"
        aria-label="关闭全局搜索"
        onClick={onClose}
      />
      <section
        className="v278-half-sheet v278-global-search-page"
        role="dialog"
        aria-modal="true"
        aria-label="全局搜索"
      >
        <header className="v278-sheet-header">
          <span>
            <h2>全局搜索</h2>
            <p>跨内容、任务、知识、记忆与联系人检索</p>
          </span>
          <button type="button" aria-label="关闭" onClick={onClose}>
            <X size={21} />
          </button>
        </header>
        <label className="v278-global-search-box">
          <Search size={22} />
          <input
            autoFocus
            aria-label="全局搜索"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索人、内容、任务、机会…"
          />
          {query && (
            <button
              type="button"
              aria-label="清空搜索"
              onClick={() => setQuery("")}
            >
              <X size={17} />
            </button>
          )}
        </label>
        {!normalized ? (
          <section className="v278-search-guide">
            <small>搜索范围</small>
            <h2>一次检索整个 Elfred</h2>
            <p>
              这里的搜索与今日简报和 Agent 朋友圈相互独立，不会改变主页内容。
            </p>
            <div>
              {[
                [FileText, "内容"],
                [ListChecks, "任务"],
                [BookOpen, "知识"],
                [MemoryStick, "记忆"],
                [Users, "人物"],
              ].map(([Icon, label]) => {
                const ResultIcon = Icon as typeof FileText;
                return (
                  <button
                    type="button"
                    key={label as string}
                    onClick={() => setQuery(label as string)}
                  >
                    <ResultIcon size={20} />
                    <span>{label as string}</span>
                  </button>
                );
              })}
            </div>
          </section>
        ) : (
          <section className="v278-global-results">
            <header>
              <h2>搜索结果</h2>
              <small>{results.length} 条</small>
            </header>
            {results.length ? (
              results.map((item) => (
                <button type="button" key={item.key} onClick={item.action}>
                  <span>{item.type}</span>
                  <div>
                    <b>{displayTitle(item.title,'')}</b>
                    <p>{item.copy}</p>
                  </div>
                  <ChevronRight size={18} />
                </button>
              ))
            ) : (
              <div className="v277-empty">
                <Search size={22} />
                <b>没有找到相关结果</b>
                <p>试试更短的关键词。</p>
              </div>
            )}
          </section>
        )}
      </section>
    </RootPortal>
  );
}

export function AlignmentModal({
  go: _go,
  onClose,
}: {
  go: (screen: Screen) => void;
  onClose: () => void;
}) {
  const runtime=useRuntime();
  const [tab, setTab] = useState<"level" | "honors">("level");
  const [honorFilter, setHonorFilter] = useState("全部");
  return (
    <RootPortal>
      <button
        type="button"
        className="v278-sheet-backdrop"
        aria-label="关闭理解度详情"
        onClick={onClose}
      />
      <section
        className="v278-alignment-modal"
        role="dialog"
        aria-modal="true"
        aria-label="理解度详情"
      >
        <header className="v278-sheet-header">
          <span>
            <h2>理解与成长</h2>
            <p>由已确认的记忆、反馈与任务结果持续更新</p>
          </span>
          <button type="button" aria-label="关闭" onClick={onClose}>
            <X size={21} />
          </button>
        </header>
        <nav className="v279-growth-tabs">
          <button
            type="button"
            className={tab === "level" ? "active" : ""}
            onClick={() => setTab("level")}
          >
            <Trophy size={22} />
            等级
          </button>
          <button
            type="button"
            className={tab === "honors" ? "active" : ""}
            onClick={() => setTab("honors")}
          >
            <Star size={22} />
            荣誉勋章
          </button>
        </nav>
        {runtime?<div className="v279-level-panel"><section className="v279-stage-card"><div><small>当前理解</small><h3>有待验证</h3><p>本人确认 {runtime.snapshot?.objects.memory.filter(item=>item.data.status==='validated').length||0} 条理解。尚无跨情境、跨时间验证，不生成百分比与等级。</p></div></section><button className="v277-secondary" onClick={()=>_go({name:'memory'})}>查看理解依据</button><button className="v277-secondary" onClick={()=>_go({name:'tasks'})}>查看真实成果</button></div>:tab === "level" ? (
          <div className="v279-level-panel">
            <section className="v279-stage-card">
              <i className="v279-level-orb" />
              <div>
                <small>当前阶段</small>
                <h3>
                  Lv.4 <span>可靠复用</span>
                </h3>
                <p>已能在熟悉场景中稳定复用能力</p>
              </div>
              <strong>
                86%<small>当前理解度</small>
              </strong>
              <em>
                <i style={{ width: "86%" }} />
              </em>
            </section>
            <section className="v279-upgrade-card">
              <header>
                <h3>升级进度</h3>
                <b>8 / 10</b>
              </header>
              <em>
                <i style={{ width: "80%" }} />
              </em>
              <p>再完成 2 次真实 Outcome 验证，即可进入「稳定交付」</p>
            </section>
            <section className="v279-level-stats">
              <span>
                <b>18</b>
                <small>有效 Evidence</small>
              </span>
              <span>
                <b>12</b>
                <small>真实交付</small>
              </span>
              <span>
                <b>4</b>
                <small>长期协作</small>
              </span>
            </section>
            <section className="v279-growth-path">
              <header>
                <h3>成长路径</h3>
                <button type="button">
                  查看全部
                  <ChevronRight size={17} />
                </button>
              </header>
              <div>
                <b>Lv.5</b>
                <span>
                  <strong>稳定交付</strong>
                  <small>完成 2 次 Outcome</small>
                </span>
                <em>下一阶段</em>
              </div>
            </section>
          </div>
        ) : (
          <div className="v279-honors-panel">
            <section className="v279-honors-progress">
              <span>
                <b>勋章图鉴</b>
                <small>已点亮 4 / 12 枚</small>
              </span>
              <em>
                <i />
              </em>
              <strong>4 / 12</strong>
            </section>
            <nav className="v279-honor-filter">
              {["全部", "能力", "协作", "里程碑"].map((item) => (
                <button
                  type="button"
                  key={item}
                  className={honorFilter === item ? "active" : ""}
                  onClick={() => setHonorFilter(item)}
                >
                  {item}
                </button>
              ))}
            </nav>
            <section className="v279-honor-section">
              <header>
                <h3>已获得</h3>
                <span>
                  4 枚<ChevronRight size={16} />
                </span>
              </header>
              <div className="v279-medal-list">
                {[
                  [Lightbulb, "洞察先锋"],
                  [Check, "可靠交付"],
                  [Layers3, "能力觉醒"],
                  [Star, "共创之星"],
                ].map(([Icon, title]) => {
                  const MedalIcon = Icon as typeof Trophy;
                  return (
                    <button
                      type="button"
                      key={title as string}
                      onClick={() => {}}
                    >
                      <span>
                        <MedalIcon size={30} />
                      </span>
                      <b>{title as string}</b>
                    </button>
                  );
                })}
              </div>
            </section>
            <section className="v279-honor-section">
              <header>
                <h3>未获得</h3>
                <span>
                  8 枚<ChevronRight size={16} />
                </span>
              </header>
              <div className="v279-medal-list">
                {[
                  [Share2, "跨场景实践者"],
                  [Users, "长期协作者"],
                  [Settings2, "稳定交付者"],
                ].map(([Icon, title]) => {
                  const MedalIcon = Icon as typeof Trophy;
                  return (
                    <button
                      type="button"
                      className="locked"
                      key={title as string}
                      onClick={() => {}}
                    >
                      <span>
                        <MedalIcon size={28} />
                      </span>
                      <b>{title as string}</b>
                      <small>尚未解锁</small>
                    </button>
                  );
                })}
              </div>
            </section>
          </div>
        )}
      </section>
    </RootPortal>
  );
}

export function FeedPage({
  state,
  go,
  onBack,
}: {
  state: V277State;
  go: (screen: Screen) => void;
  onBack: () => void;
}) {
  const runtime=useRuntime();
  const moments:AgentMoment[]=runtime?(runtime.snapshot?.objects.feed||[]).filter(item=>!state.hiddenPostIds.includes(item.id)).map(item=>({id:item.id,agent:(item.data.system==='advise'?'advisor':item.data.system) as V277AgentId,variant:'brief',type:'观点动态',period:new Date(item.created).toDateString()===new Date().toDateString()?'今天':'本月',time:new Date(item.created).toLocaleDateString('zh-CN'),title:entityText(item,'title'),summary:entityText(item,'summary'),target:{name:'feed-detail',id:item.id}})):agentMoments;
  const [agentFilter, setAgentFilter] = useState<"all" | V277AgentId>("all");
  const [period, setPeriod] = useState("全部时间");
  const [postType, setPostType] = useState("全部类型");
  const [filterOpen, setFilterOpen] = useState(false);
  const visible = moments.filter(
    (moment) =>
      (agentFilter === "all" || moment.agent === agentFilter) &&
      (period === "全部时间" ||
        period === moment.period ||
        (period === "24 小时内" && moment.period === "今天")) &&
      (postType === "全部类型" || postType === moment.type),
  );
  return (
    <main className="v277-page v278-feed-page">
      <AppHeader
        title="Agent 朋友圈"
        subtitle="来自五个 Agent 的最新动态"
        onBack={onBack}
        right={
          <IconButton
            label="筛选朋友圈"
            onClick={() => setFilterOpen(true)}
            className={
              period !== "全部时间" || postType !== "全部类型" ? "active" : ""
            }
          >
            <SlidersHorizontal size={20} />
          </IconButton>
        }
      />
      <nav
        className="v278-chip-row v278-agent-chip-row"
        aria-label="按 Agent 筛选"
      >
        <button
          type="button"
          className={agentFilter === "all" ? "active" : ""}
          onClick={() => setAgentFilter("all")}
        >
          全部
        </button>
        {agentList.map((agent) => (
          <button
            type="button"
            key={agent.id}
            className={agentFilter === agent.id ? "active" : ""}
            onClick={() => setAgentFilter(agent.id)}
          >
            {agent.name}
          </button>
        ))}
      </nav>
      <section className="v278-feed-list v278-moment-feed">
        {visible.map((moment) => (
          <AgentMomentCard key={moment.id} moment={moment} go={go} />
        ))}
      </section>
      {!visible.length && (
        <div className="v277-empty">
          <SlidersHorizontal size={22} />
          <b>没有匹配的动态</b>
          <p>调整 Agent、发布时间或帖子类型。</p>
        </div>
      )}
      {filterOpen && (
        <FeedFilterSheet
          period={period}
          postType={postType}
          setPeriod={setPeriod}
          setPostType={setPostType}
          onClose={() => setFilterOpen(false)}
        />
      )}
    </main>
  );
}

export function FeedFilterSheet({
  period,
  postType,
  setPeriod,
  setPostType,
  onClose,
}: {
  period: string;
  postType: string;
  setPeriod: (value: string) => void;
  setPostType: (value: string) => void;
  onClose: () => void;
}) {
  return (
    <RootPortal>
      <button
        type="button"
        className="v278-sheet-backdrop"
        aria-label="关闭筛选"
        onClick={onClose}
      />
      <section
        className="v278-half-sheet v278-filter-sheet"
        role="dialog"
        aria-modal="true"
        aria-label="朋友圈筛选"
      >
        <i className="v278-sheet-handle" />
        <header className="v278-sheet-header">
          <span>
            <h2>筛选朋友圈</h2>
            <p>按发布时间和帖子类型缩小范围</p>
          </span>
          <button type="button" aria-label="关闭" onClick={onClose}>
            <X size={21} />
          </button>
        </header>
        <div className="v278-filter-group">
          <h3>发布时间</h3>
          <div>
            {["全部时间", "24 小时内", "本周", "本月"].map((item) => (
              <button
                type="button"
                key={item}
                className={period === item ? "active" : ""}
                onClick={() => setPeriod(item)}
              >
                {item}
              </button>
            ))}
          </div>
        </div>
        <div className="v278-filter-group">
          <h3>帖子类型</h3>
          <div>
            {["全部类型", "专题汇总", "图文帖子", "观点动态"].map((item) => (
              <button
                type="button"
                key={item}
                className={postType === item ? "active" : ""}
                onClick={() => setPostType(item)}
              >
                {item}
              </button>
            ))}
          </div>
        </div>
        <footer>
          <button
            type="button"
            onClick={() => {
              setPeriod("全部时间");
              setPostType("全部类型");
            }}
          >
            重置
          </button>
          <button type="button" onClick={onClose}>
            查看结果
          </button>
        </footer>
      </section>
    </RootPortal>
  );
}

export function TasksPage({
  state,
  go,
  setState,
  notify,
  initialView = "today",
}: {
  state: V277State;
  go: (screen: Screen) => void;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
  notify: (text: string) => void;
  initialView?: "today" | "projects";
}) {
  const runtime=useRuntime();
  const todayDate=runtime?String(new Date().getDate()):"14";
  const [view, setView] = useState<"today" | "projects">(initialView);
  const [category, setCategory] = useState("全部");
  const [selectedDate, setSelectedDate] = useState(todayDate);
  const [draggingId, setDraggingId] = useState("");
  const openTask = (taskId: string) => {
    const task =
      state.tasks.find((item) => item.id === taskId) ||
      demoTasks.find((item) => item.id === taskId);
    if (!task) return;
    if (!state.tasks.some((item) => item.id === task.id))
      setState((current) => ({ ...current, tasks: [task, ...current.tasks] }));
    go({ name: "task", id: task.id });
  };
  const handoffTask = (taskId: string) => {
    if(runtime){go({name:"task",id:taskId});notify("请核对范围后确认运行");return;}
    const source =
      state.tasks.find((item) => item.id === taskId) ||
      demoTasks.find((item) => item.id === taskId);
    if (!source) return;
    const hasRunningTask = state.tasks.some(
      (item) => item.status === "进行中" && item.id !== source.id,
    );
    const nextStatus: V277TaskStatus = hasRunningTask ? "待确认" : "进行中";
    setState((current) => {
      const exists = current.tasks.some((item) => item.id === source.id);
      const nextTask = { ...source, status: nextStatus, updatedAt: "刚刚" };
      return {
        ...current,
        tasks: exists
          ? current.tasks.map((item) =>
              item.id === source.id ? nextTask : item,
            )
          : [nextTask, ...current.tasks],
      };
    });
    setDraggingId("");
    notify(
      nextStatus === "进行中"
        ? `已开始执行“${source.title}”`
        : `已将“${source.title}”加入待办`,
    );
  };
  const dragProps = (taskId: string) => ({
    draggable: true,
    onDragStart: (event: ReactDragEvent<HTMLButtonElement>) => {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("application/x-elfred-task", taskId);
      event.dataTransfer.setData("text/plain", taskId);
      setDraggingId(taskId);
    },
    onDragEnd: () => setDraggingId(""),
  });
  const people = ["avatar-lin", "avatar-kevin", "avatar-aya"];
  const schedule = runtime?state.tasks.filter(task=>task.status!=="已完成"&&String(new Date(Number(runtime.snapshot?.objects.task.find(item=>item.id===task.id)?.data.not_before)||runtime.snapshot?.server_time||0).getDate())===selectedDate).map(task=>({taskId:task.id,category:"工作",time:new Date(Number(runtime.snapshot?.objects.task.find(item=>item.id===task.id)?.data.not_before)||runtime.snapshot?.objects.task.find(item=>item.id===task.id)?.updated||runtime.snapshot?.server_time||0).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'}),title:task.title,meta:task.nextStep,action:task.nextStep,actionClass:task.status==="进行中"?"running":"waiting",icon:Clock3})):[
    {
      taskId: "schedule-client",
      category: "协作",
      time: "9:00",
      title: "客户沟通",
      meta: "同步项目进展，确认目标与待办",
      action: "视频会议",
      actionClass: "meeting",
      icon: Video,
    },
    {
      taskId: "schedule-design",
      category: "工作",
      time: "11:00",
      title: "下月视觉设计排期",
      meta: "11:00 – 12:30",
      action: "进行中",
      actionClass: "running",
      icon: Clock3,
    },
    {
      taskId: "schedule-interview",
      category: "个人",
      time: "14:00",
      title: "首批用户访谈",
      meta: "14:00 – 15:00 · 腾讯会议",
      action: "待开始",
      actionClass: "waiting",
      icon: Clock3,
    },
  ];
  const projects = runtime?state.tasks.filter(task=>task.status==="已完成").map(task=>({taskId:task.id,title:task.title,copy:task.brief,progress:100,comments:0,links:task.knowledgeIds.length})):[
    {
      taskId: "project-brand",
      title: "品牌官网首屏改版",
      copy: "与开发确认布局与交互，完成首屏方案定稿。",
      progress: 64,
      comments: 0,
      links: 1,
    },
    {
      taskId: "project-mobile",
      title: "移动端玻璃效果优化",
      copy: "统一模糊层级、圆角与底部导航的视觉质感。",
      progress: 66,
      comments: 8,
      links: 14,
    },
  ];
  const visibleSchedule =
    category === "全部"
      ? schedule
      : schedule.filter((item) => item.category === category);
  return (
    <main className="v277-page v277-actions-page">
      <div className="v282-actions-fixed-head">
        <header className="v277-actions-head">
          <button
            type="button"
            aria-label="返回首页"
            onClick={() => go({ name: "home" })}
          >
            <ArrowLeft size={25} />
          </button>
          <h1>任务</h1>
          <button
            type="button"
            aria-label="新建任务"
            onClick={() => go({ name: "new-task" })}
          >
            <Plus size={27} />
          </button>
        </header>
        <nav className="v277-action-switch" aria-label="任务视图">
          <button
            type="button"
            className={view === "today" ? "active" : ""}
            onClick={() => setView("today")}
          >
            <ListChecks size={20} />
            今天
          </button>
          <button
            type="button"
            className={view === "projects" ? "active" : ""}
            onClick={() => setView("projects")}
          >
            <Folder size={20} />
            项目任务
          </button>
        </nav>
      </div>
      <ContextRecovery go={go}/><Observations go={go}/>
      {view === "today" ? (
        <>
          <section className="v277-date-strip">
            {(runtime?Array.from({length:6},(_,index)=>{const day=new Date();day.setDate(day.getDate()+index-2);return [["日","一","二","三","四","五","六"][day.getDay()],String(day.getDate())]}):[
              ["一", "12"],
              ["二", "13"],
              ["三", "14"],
              ["四", "15"],
              ["五", "16"],
              ["六", "17"],
            ]).map(([day, date]) => (
              <button
                type="button"
                className={date === selectedDate ? "active" : ""}
                key={date}
                onClick={() => setSelectedDate(date)}
              >
                <span>{day}</span>
                <b>{date}</b>
              </button>
            ))}
          </section>
          <nav className="v277-action-filters">
            {(
              [
                { name: "全部", icon: ListChecks },
                { name: "工作", icon: Briefcase },
                { name: "个人", icon: UserRound },
                { name: "协作", icon: Users },
              ] as const
            ).map(({ name, icon: Icon }) => (
              <button
                type="button"
                key={name}
                className={category === name ? "active" : ""}
                onClick={() => setCategory(name)}
              >
                <Icon size={19} /> {name}
              </button>
            ))}
          </nav>
          <div className="v277-day-title">
            <h2>
              <Sun size={23} />
              {selectedDate === todayDate ? "今天" : `${new Date().getMonth()+1} 月 ${selectedDate} 日`}
            </h2>
            <span>{visibleSchedule.length} 项</span>
          </div>
          {(runtime||selectedDate === todayDate) && visibleSchedule.length ? (
            <section className="v277-schedule-list">
              {visibleSchedule.map((item) => {
                const ActionIcon = item.icon;
                return (
                  <button
                    type="button"
                    key={item.time}
                    {...dragProps(item.taskId)}
                    className={draggingId === item.taskId ? "is-dragging" : ""}
                    onClick={() => openTask(item.taskId)}
                  >
                    <time>
                      <small>{item.time === "14:00" ? "下午" : "上午"}</small>
                      <b>{item.time}</b>
                      <i />
                      <em>↓</em>
                    </time>
                    <article>
                      <h3>{displayTitle(item.title,'')}</h3>
                      <p>{item.meta}</p>
                      <div>
                        {people.map((photo) => (
                          <i
                            className={`${photo} v277-sprite-community`}
                            key={photo}
                          />
                        ))}
                        {!runtime&&<strong>+4</strong>}
                      </div>
                    </article>
                    <span className={item.actionClass}>
                      <ActionIcon size={17} />
                      {item.action}
                    </span>
                  </button>
                );
              })}
            </section>
          ) : (
            <div className="v277-empty v278-task-empty">
              <CalendarDays size={24} />
              <b>当天没有安排</b>
              <p>切换日期或点击右上角添加新的任务。</p>
            </div>
          )}
        </>
      ) : (
        <>
          <section className="v277-project-stats">
            <span>
              <small>进行中</small>
              <b>{runtime?runtime.snapshot?.objects.project.length||0:3}</b>
            </span>
            <span>
              <small>本周任务</small>
              <b>{runtime?state.tasks.length:8}</b>
            </span>
            <span>
              <small>整体进度</small>
              <b className={runtime?"elfred-stat-label":undefined}>{runtime?"待逐项验收":"56%"}</b>
            </span>
          </section>
          <section className="v277-project-list">
            {(runtime?runtime.snapshot?.objects.project.map(item=>({title:entityText(item,'title'),copy:entityText(item,'goal'),taskId:item.id,progress:item.data.release_id?100:0,comments:runtime.snapshot!.objects.feedback.filter(feedback=>feedback.space===item.id).length,links:runtime.snapshot!.objects.release.filter(release=>release.data.project_id===item.id).length}))||[]:projects).map((item) => (
              <button
                type="button"
                key={item.title}
                {...dragProps(item.taskId)}
                className={draggingId === item.taskId ? "is-dragging" : ""}
                onClick={() => runtime?go({name:"community-post",id:item.taskId}):openTask(item.taskId)}
              >
                <em>
                  <i />
                  {runtime?"项目":"受阻"}
                </em>
                <h2>{displayTitle(item.title,'')}</h2>
                <p>{item.copy}</p>
                <div className="v277-project-progress">
                  <span>完成进度</span>
                  <b>{item.progress}%</b>
                  <i
                    style={
                      { "--progress": `${item.progress}%` } as CSSProperties
                    }
                  />
                </div>
                <footer>
                  <span>
                    <MessageCircle size={18} />
                    {item.comments} 条评论
                  </span>
                  <span>
                    <Link2 size={18} />
                    {item.links} 个链接
                  </span>
                  <strong>
                    {people.slice(0, 2).map((photo) => (
                      <i
                        className={`${photo} v277-sprite-community`}
                        key={photo}
                      />
                    ))}
                  </strong>
                </footer>
              </button>
            ))}
          </section>
        </>
      )}
      <TaskPlayer state={state} go={go} onTaskDrop={handoffTask} />
    </main>
  );
}

export function NewTaskPage({
  onBack,
  setState,
  go,
  notify,
}: {
  onBack: () => void;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
  go: (screen: Screen) => void;
  notify: (text: string) => void;
}) {
  const runtime=useRuntime();
  const [sourceRefs,setSourceRefs]=useState<{id:string;version:number}[]>([]);
  const uploadRef=useRef<HTMLInputElement|null>(null);
  const [goal, setGoal] = useState("");
  const [mode, setMode] = useState<"快速待办" | "Agent 执行" | "项目任务">(
    "Agent 执行",
  );
  const [time, setTime] = useState(runtime?"确认后立即":"今天 14:00");
  const [type, setType] = useState(runtime?"模型生成":"工作");
  const [project, setProject] = useState("未选择");
  const [people, setPeople] = useState("暂不添加");
  const create = () => {
    if (!goal.trim()) return;
    if(runtime){const notBefore=time==='明天 09:00'?new Date(new Date().getFullYear(),new Date().getMonth(),new Date().getDate()+1,9).getTime():time==='一小时后'?Date.now()+3600000:0;const projectEntity=runtime.snapshot?.objects.project.find(item=>item.data.title===project);void runtime.command('task.create',{goal:goal.trim().replace(/^(搜索|检索|查找)[：:\s]*/,''),mode:mode==='快速待办'?'manual':type==='资料检索'||/^(搜索|检索|查找)/.test(goal.trim())?'search':type==='文件读取'?'read':'compose',system:mode==='Agent 执行'?'execute':'create',source_refs:sourceRefs,project_id:projectEntity?.id,not_before:notBefore}).then(result=>{notify('任务草稿已保存，确认后才运行');go({name:'task',id:result.id})}).catch(()=>{});return;}
    const task: V277Task = {
      id: `custom-${Date.now()}`,
      title: goal.trim().slice(0, 22),
      brief: goal.trim(),
      source: mode,
      agent: mode === "Agent 执行" ? "execute" : "create",
      status: mode === "Agent 执行" ? "待确认" : "已暂停",
      nextStep: "确认完成标准与执行范围",
      result: [
        "确认目标与完成标准。",
        "拆分可执行步骤。",
        "在任务播放器中跟踪进展。",
      ],
      knowledgeIds: [],
      updatedAt: "刚刚",
    };
    setState((current) => ({ ...current, tasks: [task, ...current.tasks] }));
    notify("新任务已创建");
    go({ name: "task", id: task.id });
  };
  return (
    <main className="v277-page v281-new-task">
      <header>
        <button type="button" aria-label="返回任务" onClick={onBack}>
          <ArrowLeft size={27} />
        </button>
        <span>
          <h1>新建任务</h1>
        </span>
      </header>
      <section className="v281-task-prompt">
        <h2>你想完成什么？</h2>
        <textarea
          autoFocus
          value={goal}
          onChange={(event) => setGoal(event.target.value)}
          placeholder="例如：整理今天的用户访谈，提炼关键结论并生成后续任务"
        />
        <footer>
          <button
            type="button"
            onClick={() => runtime?uploadRef.current?.click():notify("可添加文件、图片或链接")}
          >
            <Paperclip size={24} />
          </button>
          <VoiceInput onText={value=>setGoal(previous=>previous+value)}/>
          <button
            type="button"
            disabled={!goal.trim()}
            onClick={() => runtime?create():notify("已生成任务计划草稿")}
          >
            <Sparkles size={19} />
            生成任务计划
          </button>
        </footer>
        {runtime&&<><input ref={uploadRef} type="file" accept=".txt,.md,.csv,.json,.pdf,.docx,.pptx,.xlsx" hidden onChange={async event=>{const file=event.target.files?.[0];if(!file)return;if(file.size>8*1024*1024){runtime.report('文件不能超过 8 MB');return;}try{const base64=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file)});const attachment=await runtime.command('attachment.upload',{name:file.name,base64});const result=await runtime.request<{id:string}>('/attachment-parse',{id:attachment.id});await runtime.refresh();setSourceRefs(current=>[...current,{id:result.id,version:1}]);notify('已添加本次任务资料')}catch{}}}/>{sourceRefs.length>0&&<small>已选择 {sourceRefs.length} 份资料</small>}</>}
      </section>
      <section className="v281-task-mode">
        <h2>创建方式</h2>
        <nav>
          {(["快速待办", "Agent 执行", "项目任务"] as const).map((item) => (
            <button
              type="button"
              key={item}
              className={mode === item ? "active" : ""}
              onClick={() => setMode(item)}
            >
              {item === "Agent 执行" && <i />}
              {item}
            </button>
          ))}
        </nav>
      </section>
      {runtime&&<section className="v277-edit-card"><h3>选择已有资料（最多 20 项）</h3>{[...(runtime.snapshot?.objects.document||[]),...(runtime.snapshot?.objects.knowledge||[])].filter(item=>item.data.status!=='archived').map(item=><label key={item.id}><input type="checkbox" checked={sourceRefs.some(ref=>ref.id===item.id)} onChange={()=>setSourceRefs(prev=>prev.some(ref=>ref.id===item.id)?prev.filter(ref=>ref.id!==item.id):[...prev,entityRef(item)])}/>{displayTitle(entityText(item,'title'),'')}</label>)}</section>}
      <section className="v281-task-settings">
        <h2>任务设置</h2>
        <div>
          <SettingDropdown
            icon={Clock3}
            label="执行时间"
            value={time}
            options={runtime?["确认后立即","一小时后","明天 09:00"]:["今天 14:00", "明天 09:00", "本周五 18:00"]}
            onSelect={setTime}
          />
          <SettingDropdown
            icon={Layers3}
            label="任务类型"
            value={type}
            options={runtime?["模型生成","资料检索","文件读取"]:["工作", "个人", "协作"]}
            onSelect={setType}
          />
          <SettingDropdown
            icon={Folder}
            label="加入项目"
            value={project}
            options={runtime?["未选择",...(runtime.snapshot?.objects.project.map(item=>entityText(item,"title"))||[])]:["未选择", "品牌官网", "V27.8 优化"]}
            onSelect={setProject}
          />
          <SettingDropdown
            icon={Users}
            label="添加协作者"
            value={people}
            options={runtime?["暂不添加"]:["暂不添加", "Mia", "Kevin"]}
            onSelect={setPeople}
          />
        </div>
      </section>
      <footer className="v281-create-task">
        <button type="button" disabled={!goal.trim()} onClick={create}>
          创建任务
        </button>
      </footer>
    </main>
  );
}

export function TaskDetail({
  task,
  go,
  onBack,
  setState,
  notify,
}: {
  task: V277Task;
  go: (screen: Screen) => void;
  onBack: () => void;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
  notify: (text: string) => void;
}) {
  const runtime=useRuntime();
  const actual=runtime?.snapshot?.objects.task.find(item=>item.id===task.id);
  const run=runtime?.snapshot?.objects.run.find(item=>item.id===actual?.data.run_id);
  const [consent,setConsent]=useState(false);
  const [feedback,setFeedback]=useState('');
  const [acceptance,setAcceptance]=useState(false);
  const setStatus = (status: V277TaskStatus) =>
    setState((s) => ({
      ...s,
      tasks: s.tasks.map((item) =>
        item.id === task.id ? updateTaskStatus(item, status) : item,
      ),
    }));
  const remove = () => {
    if(runtime&&actual){void runtime.command('task.archive',entityRef(actual)).then(()=>{notify('任务已归档，可在数据设置恢复');onBack()}).catch(()=>{});return;}
    setState((s) => ({
      ...s,
      tasks: s.tasks.filter((item) => item.id !== task.id),
    }));
    go({ name: "tasks" });
    notify("任务已删除");
  };
  return (
    <main className="v277-page">
      <AppHeader
        title="任务详情"
        subtitle={task.updatedAt}
        onBack={onBack}
        right={
          <IconButton label={runtime?"归档任务":"删除任务"} onClick={remove}>
            <Trash2 size={19} />
          </IconButton>
        }
      />
      <section className="v277-task-hero">
        <span className={`v277-status-pill status-${task.status}`}>
          {actual?runtimeStatuses[entityText(actual,'status')]||entityText(actual,'status'):task.status}
        </span>
        <h1>{displayTitle(task.title,'')}</h1>
        <p>{task.brief}</p>
        <dl>
          <div>
            <dt>来源</dt>
            <dd>{task.source}</dd>
          </div>
          <div>
            <dt>下一步</dt>
            <dd>{task.nextStep}</dd>
          </div>
          <div>
            <dt>负责 Agent</dt>
            <dd>{agentList.find((agent) => agent.id === task.agent)?.name}</dd>
          </div>
        </dl>
      </section>
      <section className="v277-result-section">
        <div className="v277-section-row">
          <h2>{task.status === "已完成" ? "最终结果" : "当前草稿"}</h2>
          <small>{task.result.length} 条</small>
        </div>
        <ol>
          {task.result.map((line, index) => (
            <li key={line}>
              <span>{index + 1}</span>
              <MarkdownContent text={line}/>
            </li>
          ))}
        </ol>
      </section>
      {task.knowledgeIds.length > 0 && (
        <section className="v277-task-knowledge">
          <h2>已使用的知识</h2>
          {task.knowledgeIds.map((id) => {
            const entity=runtime?.snapshot?.objects.knowledge.find(entry=>entry.id===id);const item = runtime?entity?{title:entityText(entity,'title'),source:entity.type}:undefined:v277Knowledge.find((entry) => entry.id === id);
            return item ? (
              <button
                type="button"
                key={id}
                onClick={() => go({ name: "knowledge-detail", id })}
              >
                <BookOpen size={18} />
                <span>
                  <b>{displayTitle(item.title,'')}</b>
                  <small>{item.source}</small>
                </span>
                <ChevronRight size={18} />
              </button>
            ) : null;
          })}
        </section>
      )}
      {actual&&<><TaskContext task={actual}/><TaskCapability task={actual} run={run}/></>}
      <section className="v277-task-actions">
        {runtime&&actual?<><p>验收标准：{entityText(actual,'criteria')}</p><p>权限边界：{entityText(actual,'constraints')}</p><p>有限停止条件：最多 {String((actual.data.stop as {maxAttempts:number}).maxAttempts)} 次尝试，{String((actual.data.stop as {maxCalls:number}).maxCalls)} 次工具调用。已调用 {String(actual.data.calls)} 次。</p><p>本次累计额度上限：{String((actual.data.stop as {maxUnits:number}).maxUnits)}；已用 {String(actual.data.units||0)}。这是本地调用额度，实际费用以服务商账单为准。</p><details><summary>用量与运行时限</summary><p>最多 {String((actual.data.stop as {maxTokens:number}).maxTokens)} tokens、累计运行 {String((actual.data.stop as {maxSeconds:number}).maxSeconds)} 秒；已用 {String(actual.data.tokens||0)} tokens。暂停或恢复不会清空累计用量。</p></details>{Boolean(actual.data.not_before)&&<p>排期：{new Date(Number(actual.data.not_before)).toLocaleString('zh-CN')}（需本人启动后进入队列）</p>}
          {actual.data.status==='draft'&&<><label><input type="checkbox" checked={consent} onChange={event=>setConsent(event.target.checked)}/>确认目标与有限额度{actual.data.mode==='compose'?'，允许将目标和所选资料发送给已配置模型':''}</label><button className="v277-primary" disabled={!consent} onClick={()=>void runtime.command('task.confirm',{...entityRef(actual),confirm:true,model_consent:consent}).catch(()=>{})}>确认任务</button></>}
          {actual.data.mode!=='manual'&&['ready','blocked','failed','partial','paused','cancelled'].includes(String(actual.data.status))&&<button className="v277-primary" onClick={()=>void runtime.command('run.start',entityRef(actual)).catch(()=>{})}><Play size={18}/>启动 / 恢复任务</button>}
          {actual.data.mode==='manual'&&actual.data.status==='ready'&&<><label className="v277-field"><span>本人实际完成的结果</span><textarea value={feedback} onChange={event=>setFeedback(event.target.value)}/></label><button className="v277-primary" disabled={!feedback.trim()} onClick={()=>void runtime.command('task.complete_manual',{...entityRef(actual),confirm:true,result:feedback}).catch(()=>{})}>确认本人已完成并保存成果</button></>}
          {['blocked','failed','partial','paused','cancelled','ready'].includes(String(actual.data.status))&&<><label><input type="checkbox" checked={consent} onChange={event=>setConsent(event.target.checked)}/>重新确认原目标、资料与模型发送范围</label><button className="v277-secondary" disabled={!consent} onClick={()=>void runtime.command('task.renew_approval',{...entityRef(actual),confirm:true,model_consent:consent}).catch(()=>{})}>更新已撤销或过期的授权</button></>}
          {actual.data.status==='partial'&&<button className="v277-secondary" onClick={()=>void runtime.command('run.replan',entityRef(actual)).catch(()=>{})}>按本人反馈进行有限修订</button>}
          {run&&['queued','running'].includes(String(run.data.status))&&<><button className="v277-secondary" onClick={()=>void runtime.command('run.command',{...entityRef(run),command:'pause'}).catch(()=>{})}>暂停</button><button className="v277-secondary" onClick={()=>void runtime.command('run.command',{...entityRef(run),command:'cancel'}).catch(()=>{})}>取消</button></>}
          {run?.data.error?<p role="status">{String((run.data.error as {message:string}).message)}</p>:null}
          {['awaiting_acceptance','awaiting_review'].includes(String(actual.data.status))&&<><label className="v277-field"><span>需要修订的具体缺口</span><textarea value={feedback} onChange={event=>setFeedback(event.target.value)}/></label><label><input type="checkbox" checked={acceptance} onChange={event=>setAcceptance(event.target.checked)}/>已阅读实际成果与来源，符合本次目标</label><button className="v277-primary" disabled={!acceptance||!task.result.length} onClick={()=>void runtime.command('task.accept',{...entityRef(actual),accept:true}).catch(()=>{})}>验收并保存成果</button><button className="v277-secondary" onClick={()=>void runtime.command('task.accept',{...entityRef(actual),accept:false,feedback:feedback||'本人认为仍有缺口，需要修改'}).catch(()=>{})}>仍有缺口</button></>}
          {actual.data.status==='completed'&&<button className="v277-primary" onClick={()=>go({name:'knowledge-detail',id:String(actual.data.artifact_id)})}>查看已验收成果</button>}
        </>:<>
        {task.status === "待确认" && (
          <button
            type="button"
            className="v277-primary"
            onClick={() => {
              setStatus("进行中");
              notify("任务已开始，当前草稿已保留");
            }}
          >
            <Play size={18} />
            开始任务
          </button>
        )}
        {task.status === "进行中" && (
          <>
            <button
              type="button"
              className="v277-secondary"
              onClick={() => {
                setStatus("已暂停");
                notify("任务已暂停，当前结果不会丢失");
              }}
            >
              <Pause size={18} />
              暂停
            </button>
            <button
              type="button"
              className="v277-primary"
              onClick={() => {
                setStatus("已完成");
                notify("任务已完成，结果已保存");
              }}
            >
              <Check size={18} />
              完成任务
            </button>
          </>
        )}
        {task.status === "已暂停" && (
          <>
            <button
              type="button"
              className="v277-secondary"
              onClick={() => go({ name: "agent", id: task.agent })}
            >
              查看负责 Agent
            </button>
            <button
              type="button"
              className="v277-primary"
              onClick={() => {
                setStatus("进行中");
                notify("已从原进度继续");
              }}
            >
              <Play size={18} />
              继续任务
            </button>
          </>
        )}
        {task.status === "已完成" && (
          <>
            <button
              type="button"
              className="v277-secondary"
              onClick={() => go({ name: "knowledge" })}
            >
              查看相关知识
            </button>
            <button
              type="button"
              className="v277-primary"
              onClick={() => go({ name: "home" })}
            >
              返回今天
            </button>
          </>
        )}
        </>}
      </section>
    </main>
  );
}

export function AgentsPage({
  state,
  go,
}: {
  state: V277State;
  go: (screen: Screen) => void;
}) {
  return (
    <main className="v277-page">
      <AppHeader
        title="你的 Agent"
        subtitle="每个 Agent 都围绕同一份任务与记忆工作"
        onBack={() => go({ name: "home" })}
      />
      <section className="v277-agent-list">
        {agentList.map(({ id, name, role, icon: Icon }) => {
          const count = state.tasks.filter(
            (task) => task.agent === id && task.status !== "已完成",
          ).length;
          return (
            <button
              type="button"
              key={id}
              onClick={() => go({ name: "agent", id })}
            >
              <span>
                <Icon size={21} />
              </span>
              <div>
                <b>{name}</b>
                <p>{role}</p>
                <small>
                  {count ? `${count} 个待推进任务` : "现在没有待办"}
                </small>
              </div>
              <ChevronRight size={19} />
            </button>
          );
        })}
      </section>
    </main>
  );
}

export function AgentPage({
  id,
  state,
  go,
  onBack,
}: {
  id: V277AgentId;
  state: V277State;
  go: (screen: Screen) => void;
  onBack: () => void;
}) {
  const [tab, setTab] = useState<"工作" | "对话" | "记忆" | "设置">("工作");
  const agent = agentList.find((item) => item.id === id)!;
  const Icon = agent.icon;
  const tasks = state.tasks.filter((task) => task.agent === id);
  const memories = state.memories.filter(
    (memory) => memory.status === "已确认",
  );
  return (
    <main className="v277-page">
      <AppHeader
        title={`${agent.name} Agent`}
        subtitle={agent.role}
        onBack={onBack}
        right={
          <span className="v277-agent-mark">
            <Icon size={20} />
          </span>
        }
      />
      <div className="v277-filter-row v277-agent-tabs">
        {(["工作", "对话", "记忆", "设置"] as const).map((item) => (
          <button
            type="button"
            className={tab === item ? "active" : ""}
            key={item}
            onClick={() => setTab(item)}
          >
            {item}
          </button>
        ))}
      </div>
      {tab === "工作" && (
        <section className="v277-list-section">
          <div className="v277-agent-intro">
            <span>
              <Icon size={19} />
            </span>
            <p>{agent.prompt}</p>
          </div>
          {tasks.length ? (
            tasks.map((task) => (
              <button
                type="button"
                className="v277-task-card"
                key={task.id}
                onClick={() => go({ name: "task", id: task.id })}
              >
                <span className={`v277-status-dot status-${task.status}`} />
                <div>
                  <span>
                    <b>{displayTitle(task.title,'')}</b>
                    <em className={`v277-status-pill status-${task.status}`}>
                      {task.status}
                    </em>
                  </span>
                  <p>{task.nextStep}</p>
                </div>
                <ChevronRight size={18} />
              </button>
            ))
          ) : (
            <div className="v277-empty">
              <CheckCircle2 size={22} />
              <b>当前没有任务</b>
              <p>你可以直接和 {agent.name} Agent 说一件要推进的事。</p>
              <button type="button" onClick={() => go({ name: "chat", id })}>
                开始对话
              </button>
            </div>
          )}
        </section>
      )}
      {tab === "对话" && (
        <section className="v277-panel-action">
          <MessageCircle size={23} />
          <h2>继续和 {agent.name} 对话</h2>
          <p>对话会保存在消息页；创建的任务也会同步到这里。</p>
          <button
            type="button"
            className="v277-primary"
            onClick={() => go({ name: "chat", id })}
          >
            打开对话
          </button>
        </section>
      )}
      {tab === "记忆" && (
        <section className="v277-memory-mini">
          <p>以下信息来自你已确认的全局记忆。Agent 不会使用待确认内容。</p>
          {memories.length ? (
            memories.slice(0, 4).map((memory) => (
              <button
                type="button"
                key={memory.id}
                onClick={() => go({ name: "memory-detail", id: memory.id })}
              >
                <span>
                  <b>{memory.label}</b>
                  <small>{memory.value}</small>
                </span>
                <ChevronRight size={17} />
              </button>
            ))
          ) : (
            <div className="v277-empty">
              <MemoryStick size={22} />
              <b>还没有已确认记忆</b>
              <p>完善个人资料后会在这里同步显示。</p>
            </div>
          )}
        </section>
      )}
      {tab === "设置" && (
        <section className="v277-panel-action">
          <Settings2 size={23} />
          <h2>{agent.name} 的工作边界</h2>
          <p>
            {id === "connect"
              ? "只整理候选人与机会，不会自动发送消息或邀请。"
              : "先生成草稿；发送、发布、删除和付款等外部动作始终需要你确认。"}
          </p>
        </section>
      )}
    </main>
  );
}

export function PhonePortal({ children }: { children: ReactNode }) {
  if (typeof document === "undefined") return null;
  const host = document.querySelector(".phone-stage");
  return host ? createPortal(children, host) : null;
}

export function AgentHistoryDrawer({
  id,
  onClose,
  onSelect,
}: {
  id: V277AgentId;
  onClose: () => void;
  onSelect: (taskId?:string) => void;
}) {
  const runtime=useRuntime();
  const agent = agentList.find((item) => item.id === id)!;
  const experience = agentExperience[id];
  const Icon = agent.icon;
  const [query, setQuery] = useState("");
  const startX = useRef(0);
  const tasks=runtime?.snapshot?.objects.task.filter(item=>item.data.system===(id==='advisor'?'advise':id))||[];
  const conversations = (runtime?tasks.map(item=>entityText(item,'title')):[
    "AI 工作流首页结构",
    "Personal Agent 赛道跟踪",
    "任务播放器参考案例",
    "寻找技术合伙人",
    "首页信息结构讨论",
  ]).filter((item) => item.toLowerCase().includes(query.trim().toLowerCase()));
  return (
    <PhonePortal>
      <button
        type="button"
        className="v283-drawer-mask"
        aria-label="关闭过往对话"
        onClick={onClose}
      />
      <aside
        className="v283-agent-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="过往对话"
        onTouchStart={(event) => {
          startX.current = event.touches[0]?.clientX || 0;
        }}
        onTouchEnd={(event) => {
          if ((event.changedTouches[0]?.clientX || 0) - startX.current < -42)
            onClose();
        }}
      >
        <label>
          <Search size={22} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索对话"
            aria-label="搜索对话"
          />
        </label>
        <header>
          <span>30 天内</span>
          <SlidersHorizontal size={19} />
        </header>
        <nav>
          {conversations.map((conversation, index) => (
            <button
              type="button"
              className={index === 0 ? "active" : ""}
              key={conversation}
              onClick={()=>onSelect(runtime?tasks.find(item=>item.data.title===conversation)?.id:undefined)}
            >
              <i className={index === 0 ? "current" : ""} />
              <span>{conversation}</span>
            </button>
          ))}
        </nav>
        <footer>
          <i className={"v283-agent-avatar small agent-" + id}>
            <Icon size={18} />
            <em />
          </i>
          <span>
            <b>{agent.name} Agent</b>
            <small>
              {runtime?"本人任务记录":experience.level} · {experience.duty}
            </small>
          </span>
          <MoreHorizontal size={21} />
        </footer>
      </aside>
    </PhonePortal>
  );
}

export function AgentExperiencePage({
  id,
  state,
  setState,
  go,
  onBack,
}: {
  id: V277AgentId;
  state: V277State;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
  go: (screen: Screen) => void;
  onBack: () => void;
}) {
  const runtime=useRuntime();
  const agent = agentList.find((item) => item.id === id)!;
  const experience = agentExperience[id];
  const Icon = agent.icon;
  const [historyOpen, setHistoryOpen] = useState(false);
  const [input, setInput] = useState("");
  const backGesture = useRef(0);
  const quickIcons =
    id === "explore"
      ? [Compass, Search, FileText]
      : id === "advisor"
        ? [ListChecks, Gauge, Lightbulb]
        : id === "create"
          ? [PenLine, Sparkles, FileText]
          : id === "connect"
            ? [Users, BadgeCheck, Link2]
            : [ListChecks, Play, CheckCircle2];

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!input.trim()) return;
    if(runtime){void runtime.command("task.create",{goal:input.trim().replace(/^(搜索|检索|查找)[：:\s]*/,""),system:id==="advisor"?"advise":id,mode:/^(搜索|检索|查找)/.test(input)?"search":"compose"}).then(result=>go({name:"task",id:result.id})).catch(()=>{});return;}
    const message: V277Message = {
      id: makeId("agent-message"),
      role: "user",
      text: input.trim(),
      time: "刚刚",
    };
    setState((current) => ({
      ...current,
      messages: {
        ...current.messages,
        [id]: [...(current.messages[id] || []), message],
      },
    }));
    go({ name: "chat", id });
  };

  return (
    <main
      className="v277-page v283-agent-page"
      onTouchStart={(event) => {
        backGesture.current = event.touches[0]?.clientX || 0;
      }}
      onTouchEnd={(event) => {
        const distance = (event.changedTouches[0]?.clientX || 0) - backGesture.current;
        if (!historyOpen && backGesture.current < 36 && distance > 72) onBack();
      }}
    >
      <header className="v283-agent-head">
        <span className="v279-agent-head-left">
          <IconButton label="返回上一页" onClick={onBack}>
            <ArrowLeft size={21} />
          </IconButton>
          <IconButton label="过往对话" onClick={() => setHistoryOpen(true)}>
            <History size={20} />
          </IconButton>
        </span>
        <button
          type="button"
          className="v283-agent-title"
          onClick={() => runtime?go({name:"agent-level",id}):setInput(experience.question)}
        >
          <i className={"v283-agent-avatar small agent-" + id}>
            <Icon size={18} />
            <em />
          </i>
          <span>
            <b>{agent.name} Agent</b>
            <small>
              {runtime?agentAlignment(runtime.snapshot?.objects.memory||[],id==='advisor'?'advise':id).label:experience.level} · {experience.duty}
            </small>
          </span>
        </button>
        <span>
          <IconButton
            label={agent.name + " Agent 朋友圈"}
            onClick={() => go({ name: "agent-moments", id })}
          >
            <Users size={21} />
          </IconButton>
          <IconButton
            label={agent.name + " Agent 设置"}
            onClick={() => go({ name: "agent-settings", id })}
          >
            <Settings2 size={21} />
          </IconButton>
        </span>
      </header>
      <section className="v283-agent-identity">
        <i className={"v283-agent-avatar hero agent-" + id}>
          <Icon size={38} />
          <em />
        </i>
        <h1>{experience.question}</h1>
        <p>{runtime?({explore:'我会从你选择的资料中整理发现、比较变化，并核对依据。',advisor:'我会分析问题、比较选择，并说明取舍与风险。',create:'我会按你的意图创作、修改内容，保留原有设计要求。',connect:'我会根据你提供的背景匹配人选、准备沟通和协作草稿。',execute:'我会拆解步骤、核对执行条件，并根据实际回执整理进展。'}[id]):experience.intro}</p>
      </section>
      <section className="v283-agent-shortcuts" aria-label="快捷能力">
        {experience.actions.map((action, index) => {
          const ActionIcon = quickIcons[index];
          return (
            <button type="button" key={action} onClick={() => setInput(action)}>
              <ActionIcon size={22} />
              <span>{action}</span>
            </button>
          );
        })}
      </section>
      {runtime?.snapshot&&<BuiltinCapabilities system={id==='advisor'?'advise':id} go={go}/>}
      <section className="v283-agent-examples">
        <h2>可以这样问</h2>
        <div>
          {experience.questions.map((question) => (
            <button type="button" key={question} onClick={() => setInput(question)}>
              <span>{question}</span>
              <ArrowUp size={18} />
            </button>
          ))}
        </div>
      </section>
      <form className="v283-agent-composer" onSubmit={submit}>
        <button type="button" aria-label="添加附件" onClick={()=>go({name:"new-task"})}>
          <Plus size={23} />
        </button>
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={"问" + agent.name + " Agent…"}
          aria-label={"问" + agent.name + " Agent"}
        />
        <VoiceInput onText={value=>setInput(previous=>previous+value)}/>
        <button type="submit" aria-label="发送">
          <ArrowUp size={22} />
        </button>
      </form>
      {historyOpen && (
        <AgentHistoryDrawer
          id={id}
          onClose={() => setHistoryOpen(false)}
          onSelect={(taskId) => {
            setHistoryOpen(false);
            go(taskId?{name:"task",id:taskId}:{ name: "chat", id });
          }}
        />
      )}
      <button type="button" className="v283-agent-back" onClick={onBack}>
        返回
      </button>
    </main>
  );
}

type AgentPublishPreferences = {
  topic: string;
  length: string;
  format: string;
  frequency: string;
};

const defaultPublishPreferences: AgentPublishPreferences = {
  topic: "产品观察",
  length: "简洁摘要",
  format: "图文",
  frequency: "每日 2 次",
};

export function readAgentPublishPreferences(id: V277AgentId) {
  if (typeof window === "undefined") return defaultPublishPreferences;
  try {
    const value = JSON.parse(
      window.localStorage.getItem(`elfred-v278-agent-publish-${id}`) || "null",
    ) as Partial<AgentPublishPreferences> | null;
    return { ...defaultPublishPreferences, ...(value || {}) };
  } catch {
    return defaultPublishPreferences;
  }
}

export function AgentPreferenceSheet({
  id,
  initial,
  onSave,
  onClose,
}: {
  id: V277AgentId;
  initial: AgentPublishPreferences;
  onSave: (next: AgentPublishPreferences) => void;
  onClose: () => void;
}) {
  const runtime=useRuntime();
  const saved=runtime?.snapshot?.objects.settings[0].data.agent_publish as Record<string,AgentPublishPreferences&{format_version?:number}>|undefined;
  const stored=saved?.[id==='advisor'?'advise':id];
  initial=runtime?{...initial,...stored,format:stored?.format_version===2?stored.format:'图文',frequency:'事件触发'}:initial;
  const [topic, setTopic] = useState(initial.topic);
  const [length, setLength] = useState(initial.length);
  const [format, setFormat] = useState(initial.format);
  const [frequency, setFrequency] = useState(initial.frequency);
  const save = () => {
    const next = { topic, length, format, frequency };
    if(runtime?.snapshot){void runtime.command('agent.publish_preferences',{...entityRef(runtime.snapshot.objects.settings[0]),system:id==='advisor'?'advise':id,...next}).then(()=>onSave(next)).catch(()=>{});return;}
    window.localStorage.setItem(
      `elfred-v278-agent-publish-${id}`,
      JSON.stringify(next),
    );
    onSave(next);
  };
  return (
    <RootPortal>
      <button
        type="button"
        className="v278-sheet-backdrop"
        aria-label="关闭发布偏好"
        onClick={onClose}
      />
      <section className="v283-preference-sheet" role="dialog" aria-modal="true">
        <i className="v283-sheet-handle" />
        <header>
          <h2>发布偏好</h2>
          <button type="button" onClick={onClose} aria-label="关闭">
            <X size={20} />
          </button>
        </header>
        {[
          ["发布主题", topic, setTopic, ["产品观察", "行业案例", "新机会"]],
          ["内容长度", length, setLength, ["简洁摘要", "标准摘要", "详细说明"]],
          ["内容形式", format, setFormat, ["图文", "纯文字"]],
          ["发布频率", frequency, setFrequency, runtime?["事件触发"]:["每日 2 次", "每日 1 次", "每周 3 次"]],
        ].map(([label, value, setter, options]) => (
          <label key={label as string}>
            <span>{label as string}</span>
            <select
              value={value as string}
              onChange={(event) =>
                (setter as React.Dispatch<React.SetStateAction<string>>)(
                  event.target.value,
                )
              }
            >
              {(options as string[]).map((option) => (
                <option key={option}>{option}</option>
              ))}
            </select>
          </label>
        ))}
        <button type="button" className="v283-sheet-primary" onClick={save}>
          保存偏好
        </button>
      </section>
    </RootPortal>
  );
}

export function AgentMomentActionSheet({
  post,
  saved,
  onSave,
  onSkill,
  onClose,
}: {
  post: AgentMomentPost;
  saved: boolean;
  onSave: () => void;
  onSkill: () => void;
  onClose: () => void;
}) {
  return (
    <RootPortal>
      <button
        type="button"
        className="v278-sheet-backdrop"
        aria-label="关闭内容操作"
        onClick={onClose}
      />
      <section className="v283-moment-actions" role="dialog" aria-modal="true">
        <i className="v283-sheet-handle" />
        <header>
          <span>
            <small>内容操作</small>
            <h2>{displayTitle(post.title,'')}</h2>
          </span>
          <button type="button" onClick={onClose} aria-label="关闭">
            <X size={20} />
          </button>
        </header>
        <button type="button" onClick={onSave}>
          <Bookmark size={20} fill={saved ? "currentColor" : "none"} />
          <span>{saved ? "取消专题收藏" : "收藏为专题"}</span>
          <ChevronRight size={18} />
        </button>
        <button type="button" className="primary" onClick={onSkill}>
          <Sparkles size={20} />
          <span>转为 Skill 草稿</span>
          <ChevronRight size={18} />
        </button>
      </section>
    </RootPortal>
  );
}

export function AgentMomentsPage({
  id,
  state,
  setState,
  go,
  onBack,
  notify,
}: {
  id: V277AgentId;
  state: V277State;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
  go: (screen: Screen) => void;
  onBack: () => void;
  notify: (text: string) => void;
}) {
  const runtime=useRuntime();
  const agent = agentList.find((item) => item.id === id)!;
  const experience = agentExperience[id];
  const Icon = agent.icon;
  const [filter, setFilter] = useState<"全部" | "专题" | "机会">("全部");
  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const [preferences, setPreferences] = useState(() =>
    readAgentPublishPreferences(id),
  );
  const holdTimer = useRef<number | null>(null);
  const held = useRef(false);
  const [actionPost, setActionPost] = useState<AgentMomentPost | null>(null);
  const feeds=runtime?.snapshot?.objects.feed.filter(item=>item.data.system===(id==='advisor'?'advise':id))||[];
  const posts:AgentMomentPost[] = runtime?feeds.map(item=>({id:item.id,date:new Date(item.created).toLocaleDateString('zh-CN'),title:entityText(item,'title'),summary:entityText(item,'summary'),tag:'专题',detail:[entityText(item,'summary')]})):getAgentMomentPosts(id);
  const visible =
    filter === "全部" ? posts : posts.filter((post) => post.tag === filter);
  const toggleSave = (postId: string) => {
    if(runtime){void runtime.command('feed.interact',{id:postId,kind:'save'}).catch(()=>{});return;}
    const wasSaved = state.savedPostIds.includes(postId);
    setState((current) => ({
      ...current,
      savedPostIds: current.savedPostIds.includes(postId)
        ? current.savedPostIds.filter((item) => item !== postId)
        : [...current.savedPostIds, postId],
    }));
    notify(
      wasSaved
        ? "已取消专题收藏"
        : "已收藏为专题，可继续转为 Skill 草稿",
    );
  };
  return (
    <main className="v277-page v283-agent-moments-page">
      <header className="v283-secondary-head">
        <IconButton label="返回" onClick={onBack}>
          <ArrowLeft size={22} />
        </IconButton>
        <span>
          <h1>{agent.name}朋友圈</h1>
          <small>{posts.length * (runtime?1:4)} 条动态</small>
        </span>
        <IconButton label="筛选与偏好" onClick={() => setPreferencesOpen(true)}>
          <SlidersHorizontal size={21} />
        </IconButton>
      </header>
      <section className="v283-moments-agent">
        <i className={"v283-agent-avatar medium agent-" + id}>
          <Icon size={25} />
          <em />
        </i>
        <span>
          <h2>{agent.name} Agent</h2>
          <p>{runtime?({explore:'我会从你选择的资料中整理发现、比较变化，并核对依据。',advisor:'我会分析问题、比较选择，并说明取舍与风险。',create:'我会按你的意图创作、修改内容，保留原有设计要求。',connect:'我会根据你提供的背景匹配人选、准备沟通和协作草稿。',execute:'我会拆解步骤、核对执行条件，并根据实际回执整理进展。'}[id]):experience.intro}</p>
        </span>
      </section>
      <button
        type="button"
        className="v283-preference-entry"
        onClick={() => setPreferencesOpen(true)}
      >
        <Settings2 size={20} />
        <b>发布偏好</b>
        <span>{preferences.length} · {preferences.format}</span>
        <ChevronRight size={18} />
      </button>
      <nav className="v283-moments-tabs" aria-label="内容分类">
        {(["全部", "专题", "机会"] as const).map((item) => (
          <button
            type="button"
            className={filter === item ? "active" : ""}
            key={item}
            onClick={() => setFilter(item)}
          >
            {item}
          </button>
        ))}
      </nav>
      <section className="v283-moment-timeline">
        {visible.map((post, index) => (
          <article key={post.id}>
            <time>{post.date}</time>
            <i />
            <button
              type="button"
              className={state.savedPostIds.includes(post.id) ? "saved" : ""}
              onPointerDown={() => {
                held.current = false;
                holdTimer.current = window.setTimeout(() => {
                  held.current = true;
                  setActionPost(post);
                }, 620);
              }}
              onPointerUp={() => {
                if (holdTimer.current) window.clearTimeout(holdTimer.current);
              }}
              onPointerLeave={() => {
                if (holdTimer.current) window.clearTimeout(holdTimer.current);
              }}
              onContextMenu={(event) => {
                event.preventDefault();
                setActionPost(post);
              }}
              onClick={() => {
                if (held.current) {
                  held.current = false;
                  return;
                }
                go(runtime?{name:'feed-detail',id:post.id}:{ name: "agent-moment-detail", id, postId: post.id });
              }}
            >
              <h3>{displayTitle(post.title,'')}</h3>
              <p>{post.summary}</p>
              <span>{post.tag}</span>
              {index === 0 && <i className="v283-moment-thumb" aria-hidden="true" />}
              {state.savedPostIds.includes(post.id) && (
                <Bookmark size={16} fill="currentColor" />
              )}
            </button>
          </article>
        ))}
      </section>
      {preferencesOpen && (
        <AgentPreferenceSheet
          id={id}
          initial={preferences}
          onClose={() => setPreferencesOpen(false)}
          onSave={(next) => {
            setPreferences(next);
            setPreferencesOpen(false);
            notify("发布偏好已保存");
          }}
        />
      )}
      {actionPost && (
        <AgentMomentActionSheet
          post={actionPost}
          saved={state.savedPostIds.includes(actionPost.id)}
          onClose={() => setActionPost(null)}
          onSave={() => {
            toggleSave(actionPost.id);
            setActionPost(null);
          }}
          onSkill={() => {
            if(runtime){setActionPost(null);go({name:'my-tools'});return;}
            const memory: V277Memory = {
              id: `skill-draft-${actionPost.id}`,
              group: "偏好",
              label: "Skill 草稿",
              value: actionPost.title,
              source: `${agent.name} Agent 朋友圈`,
              status: "待确认",
            };
            setState((current) => ({
              ...current,
              memories: current.memories.some((item) => item.id === memory.id)
                ? current.memories
                : [memory, ...current.memories],
            }));
            setActionPost(null);
            notify("已转为 Skill 草稿并写入记忆库");
          }}
        />
      )}
    </main>
  );
}

export function AgentMomentDetailPage({
  id,
  postId,
  state,
  setState,
  onBack,
  notify,
}: {
  id: V277AgentId;
  postId: string;
  state: V277State;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
  onBack: () => void;
  notify: (text: string) => void;
}) {
  const agent = agentList.find((item) => item.id === id)!;
  const experience = agentExperience[id];
  const Icon = agent.icon;
  const post = getAgentMomentPosts(id).find((item) => item.id === postId) ||
    getAgentMomentPosts(id)[0];
  const saved = state.savedPostIds.includes(post.id);
  const saveTopic = () => {
    setState((current) => ({
      ...current,
      savedPostIds: saved
        ? current.savedPostIds.filter((item) => item !== post.id)
        : [...current.savedPostIds, post.id],
    }));
    notify(saved ? "已取消专题收藏" : "已收藏为专题");
  };
  const createSkillDraft = () => {
    const memory: V277Memory = {
      id: `skill-draft-${post.id}`,
      group: "偏好",
      label: "Skill 草稿",
      value: post.title,
      source: `${agent.name} Agent 朋友圈`,
      status: "待确认",
    };
    setState((current) => ({
      ...current,
      memories: current.memories.some((item) => item.id === memory.id)
        ? current.memories
        : [memory, ...current.memories],
    }));
    notify("Skill 草稿已写入记忆库");
  };
  return (
    <main className="v277-page v283-agent-moment-detail-page">
      <header className="v283-secondary-head">
        <IconButton label="返回" onClick={onBack}>
          <ArrowLeft size={22} />
        </IconButton>
        <span>
          <h1>内容详情</h1>
          <small>{agent.name}朋友圈</small>
        </span>
        <IconButton label="更多内容操作" onClick={saveTopic}>
          <Bookmark size={20} fill={saved ? "currentColor" : "none"} />
        </IconButton>
      </header>
      <section className="v283-moment-detail-author">
        <i className={`v283-agent-avatar small agent-${id}`}>
          <Icon size={18} />
          <em />
        </i>
        <span>
          <b>{agent.name} Agent</b>
          <small>{post.date} · {post.tag}</small>
        </span>
      </section>
      <article className="v283-moment-detail-card">
        <span>{post.tag}</span>
        <h2>{displayTitle(post.title,'')}</h2>
        <p>{post.summary}</p>
        <div className="v283-moment-detail-visual" aria-hidden="true">
          <i />
          <i />
          <i />
        </div>
        <h3>关键判断</h3>
        <p>
          这条内容与“{experience.duty}”直接相关。当前最重要的不是继续增加信息，
          而是保留可以验证的结论，并把它接到下一步行动上。
        </p>
        <h3>建议下一步</h3>
        <p>将这条发现保存为专题继续跟踪，或转成 Skill 草稿沉淀为可复用能力。</p>
      </article>
      <footer className="v283-moment-detail-actions">
        <button type="button" onClick={saveTopic}>
          <Bookmark size={19} fill={saved ? "currentColor" : "none"} />
          {saved ? "已收藏" : "收藏为专题"}
        </button>
        <button type="button" onClick={createSkillDraft}>
          <Sparkles size={19} />
          转为 Skill 草稿
        </button>
      </footer>
    </main>
  );
}

type AgentSettingEditor = {
  label: string;
  value: string;
  options: string[];
};

type PersistedAgentSettings = {
  enabled: boolean;
  values: Record<string, string>;
};

export function readAgentSettings(id: V277AgentId): PersistedAgentSettings | null {
  if (typeof window === "undefined") return null;
  try {
    return JSON.parse(
      window.localStorage.getItem(`elfred-v278-agent-settings-${id}`) || "null",
    ) as PersistedAgentSettings | null;
  } catch {
    return null;
  }
}

export function AgentSettingSheet({
  editor,
  onSelect,
  onClose,
}: {
  editor: AgentSettingEditor;
  onSelect: (value: string) => void;
  onClose: () => void;
}) {
  return (
    <RootPortal>
      <button
        type="button"
        className="v278-sheet-backdrop"
        aria-label={"关闭" + editor.label}
        onClick={onClose}
      />
      <section className="v283-setting-sheet" role="dialog" aria-modal="true">
        <i className="v283-sheet-handle" />
        <header>
          <h2>{editor.label}</h2>
          <button type="button" onClick={onClose} aria-label="关闭">
            <X size={20} />
          </button>
        </header>
        <div>
          {editor.options.map((option) => (
            <button
              type="button"
              key={option}
              className={option === editor.value ? "active" : ""}
              onClick={() => onSelect(option)}
            >
              <span>{option}</span>
              {option === editor.value && <Check size={18} />}
            </button>
          ))}
        </div>
      </section>
    </RootPortal>
  );
}

export function AgentSettingsPage({
  id,
  onBack,
  notify,
}: {
  id: V277AgentId;
  onBack: () => void;
  notify: (text: string) => void;
}) {
  const runtime=useRuntime();
  const runtimeSetting=runtime?.snapshot?.objects.settings[0];
  const prefs=(runtimeSetting?.data.agents as Record<string,{enabled:boolean;duty:string;focus:string}>|undefined)?.[id==='advisor'?'advise':id];
  const agent = agentList.find((item) => item.id === id)!;
  const experience = agentExperience[id];
  const Icon = agent.icon;
  const savedSettings = useMemo(() => runtime?{enabled:prefs?.enabled!==false,values:{名称与职责:prefs?.duty||experience.duty,关注范围:prefs?.focus||"仅当前目标",知识来源:"仅任务中明确选择的资料",使用模型:runtime.snapshot?.provider.model||"未配置",主动频率:"本人发起",可用工具:"本地检索、文档读取、模型生成",外部操作确认:"始终询问"}}:readAgentSettings(id), [id]);
  const [enabled, setEnabled] = useState(savedSettings?.enabled ?? true);
  const [editor, setEditor] = useState<AgentSettingEditor | null>(null);
  const [values, setValues] = useState<Record<string, string>>(
    savedSettings?.values || {
      名称与职责: experience.duty,
      关注范围: experience.focus,
      知识来源: experience.sources,
      使用模型: "GPT-5.6",
      主动频率: "每日 2 次",
      可用工具: experience.tools,
      外部操作确认: "始终询问",
    },
  );
  useEffect(() => {
    if(runtime)return;
    window.localStorage.setItem(
      `elfred-v278-agent-settings-${id}`,
      JSON.stringify({ enabled, values }),
    );
  }, [enabled, id, values]);
  const rows: {
    icon: typeof FileText;
    label: string;
    options: string[];
  }[] = [
    { icon: FileText, label: "名称与职责", options: [experience.duty, "自定义职责"] },
    { icon: Compass, label: "关注范围", options: [experience.focus, "5 个主题", "仅当前目标"] },
    { icon: Database, label: "知识来源", options: [experience.sources, "仅知识库", "知识库与记忆库"] },
    { icon: Gauge, label: "使用模型", options: ["GPT-5.6", "自动选择", "高效模式"] },
    { icon: Clock3, label: "主动频率", options: ["每日 2 次", "每日 1 次", "每周 3 次"] },
    { icon: Wrench, label: "可用工具", options: [experience.tools, "仅内置工具", "全部已授权工具"] },
    { icon: ShieldCheck, label: "外部操作确认", options: ["始终询问"] },
  ];
  const savePreferences=(nextEnabled:boolean,nextValues:Record<string,string>)=>{if(runtime&&runtimeSetting)void runtime.command('agent.preferences',{...entityRef(runtimeSetting),system:id==='advisor'?'advise':id,enabled:nextEnabled,duty:nextValues.名称与职责,focus:nextValues.关注范围}).then(()=>{setEnabled(nextEnabled);setValues(nextValues)}).catch(()=>{});else {setEnabled(nextEnabled);setValues(nextValues)}};
  const openEditor = (label: string, options: string[]) => {
    if(runtime&&!['名称与职责','关注范围'].includes(label)){notify(label+'：'+values[label]);return;}
    setEditor({ label, value: values[label], options });
  };
  return (
    <main className="v277-page v283-agent-settings-page">
      <header className="v283-secondary-head">
        <IconButton label="返回" onClick={onBack}>
          <ArrowLeft size={22} />
        </IconButton>
        <span>
          <h1>Agent 设置</h1>
          <small>{agent.name} Agent</small>
        </span>
        <button type="button" className="v283-done-button" onClick={onBack}>
          完成
        </button>
      </header>
      <section className="v283-settings-identity">
        <i className={"v283-agent-avatar medium agent-" + id}>
          <Icon size={25} />
          <em />
        </i>
        <span>
          <h2>{agent.name} Agent</h2>
          <p>{runtime?({explore:'我会从你选择的资料中整理发现、比较变化，并核对依据。',advisor:'我会分析问题、比较选择，并说明取舍与风险。',create:'我会按你的意图创作、修改内容，保留原有设计要求。',connect:'我会根据你提供的背景匹配人选、准备沟通和协作草稿。',execute:'我会拆解步骤、核对执行条件，并根据实际回执整理进展。'}[id]):experience.intro}</p>
        </span>
      </section>
      <section className="v283-settings-group">
        <h3>基础设置</h3>
        <div>
          {rows.slice(0, 3).map(({ icon: RowIcon, label, options }) => (
            <button type="button" key={label} onClick={() => openEditor(label, options)}>
              <RowIcon size={21} />
              <b>{label}</b>
              <span>{values[label]}</span>
              <ChevronRight size={18} />
            </button>
          ))}
        </div>
      </section>
      <section className="v283-settings-group">
        <h3>运行设置</h3>
        <div>
          {rows.slice(3, 6).map(({ icon: RowIcon, label, options }) => (
            <button type="button" key={label} onClick={() => openEditor(label, options)}>
              <RowIcon size={21} />
              <b>{label}</b>
              <span>{values[label]}</span>
              <ChevronRight size={18} />
            </button>
          ))}
        </div>
      </section>
      <section className="v283-settings-group">
        <h3>权限</h3>
        <div>
          <button type="button" onClick={() => openEditor("外部操作确认", ["始终询问"])}>
            <ShieldCheck size={21} />
            <b>外部操作确认</b>
            <span>{values.外部操作确认}</span>
            <ChevronRight size={18} />
          </button>
          <button type="button" onClick={() => savePreferences(!enabled,values)}>
            <Bot size={21} />
            <b>启用 Agent</b>
            <span
              className={"v283-switch" + (enabled ? " is-on" : "")}
              role="switch"
              aria-checked={enabled}
            >
              <i />
            </span>
          </button>
        </div>
      </section>
      <button
        type="button"
        className="v283-disable-agent"
        onClick={() => {
          savePreferences(false,values);
          notify(agent.name + " Agent 已停用，可从 Agent 列表选择替换");
        }}
      >
        停用并替换 Agent
      </button>
      {editor && (
        <AgentSettingSheet
          editor={editor}
          onClose={() => setEditor(null)}
          onSelect={(value) => {
            savePreferences(enabled,{ ...values, [editor.label]: value });
            setEditor(null);
          }}
        />
      )}
    </main>
  );
}

export function PostDetail({
  post,
  state,
  onBack,
  setState,
  openTaskFromPost,
  notify,
}: {
  post: Post;
  state: V277State;
  onBack: () => void;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
  openTaskFromPost: (post: Post) => void;
  notify: (text: string) => void;
}) {
  const saved = state.savedPostIds.includes(post.id);
  return (
    <main className="v277-page">
      <AppHeader
        title="内容详情"
        subtitle={`${agentList.find((agent) => agent.id === post.agent)?.name} Agent`}
        onBack={onBack}
        right={
          <IconButton
            label={saved ? "取消保存" : "保存内容"}
            onClick={() => {
              setState((s) => ({
                ...s,
                savedPostIds: saved
                  ? s.savedPostIds.filter((id) => id !== post.id)
                  : [...s.savedPostIds, post.id],
              }));
              notify(saved ? "已取消保存" : "内容已保存");
            }}
          >
            <Bookmark size={19} fill={saved ? "currentColor" : "none"} />
          </IconButton>
        }
      />
      <article className="v277-article">
        <span>{post.label}</span>
        <h1>{displayTitle(post.title,'')}</h1>
        <p className="lead">{post.summary}</p>
        <div>
          {post.detail.map((line, index) => (
            <section key={line}>
              <b>0{index + 1}</b>
              <p>{line}</p>
            </section>
          ))}
        </div>
        <aside>
          <Sparkles size={18} />
          <p>
            {state.profile.focus
              ? `推荐原因：这与当前目标“${state.profile.focus}”有关。`
              : "这是示例内容。完成首次目标后，Elfred 会说明真实的推荐原因。"}
          </p>
        </aside>
      </article>
      <div className="v277-sticky-actions">
        <button
          type="button"
          className="v277-primary"
          onClick={() => openTaskFromPost(post)}
        >
          {state.tasks.some((task) => task.sourceId === post.id)
            ? "打开已有任务"
            : "转为任务"}
          <ArrowRight size={18} />
        </button>
      </div>
    </main>
  );
}

export function CapabilityDetailSheet({
  card,
  go,
  onClose,
}: {
  card: CapabilityCard;
  go: (screen: Screen) => void;
  onClose: () => void;
}) {
  const [showRecords, setShowRecords] = useState(false);
  const startY = useRef(0);
  const Icon = card.icon;
  const structure =
    card.type === "Skill"
      ? {
          complete: ["寻找潜在合作人", "发现相关项目", "解释匹配理由"],
          input: ["你的目标", "个人记忆"],
          process: ["扫描来源", "条件筛选", "匹配判断"],
          output: ["候选人", "相关机会", "匹配理由"],
        }
      : card.type === "Mini App"
        ? {
            complete: ["提取核心观点", "整理内容结构", "生成复用摘要"],
            input: ["收藏内容", "目标主题"],
            process: ["内容拆分", "信息归类", "观点提炼"],
            output: ["结构摘要", "观点卡片", "行动建议"],
          }
        : {
            complete: ["筛选合适对象", "判断双方匹配", "准备前置对齐"],
            input: ["连接目标", "双方资料"],
            process: ["候选检索", "匹配判断", "风险检查"],
            output: ["候选名单", "匹配理由", "沟通草稿"],
          };
  const useCapability = () => {
    onClose();
    go({
      name: "agent",
      id:
        card.type === "Skill"
          ? "explore"
          : card.type === "Mini App"
            ? "create"
            : "connect",
    });
  };
  return (
    <RootPortal>
      <button
        type="button"
        className="v278-sheet-backdrop v279-capability-backdrop"
        aria-label="关闭能力详情"
        onClick={onClose}
      />
      <section
        className="v279-capability-sheet"
        role="dialog"
        aria-modal="true"
        aria-label={`${card.title}能力详情`}
        onTouchStart={(event) => {
          startY.current = event.touches[0]?.clientY || 0;
        }}
        onTouchEnd={(event) => {
          if ((event.changedTouches[0]?.clientY || 0) - startY.current > 72)
            onClose();
        }}
      >
        <i className="v278-sheet-handle" />
        <header className="v279-capability-head">
          <span>
            <Icon size={26} />
          </span>
          <div>
            <span>
              <h2>{displayTitle(card.title,'')}</h2>
              <em>{card.type}</em>
            </span>
            <p>{card.copy}</p>
          </div>
          <IconButton label="关闭" onClick={onClose}>
            <X size={20} />
          </IconButton>
        </header>
        {showRecords ? (
          <section className="v279-capability-records">
            <div className="v279-sheet-section-title">
              <h3>使用记录</h3>
              <button type="button" onClick={() => setShowRecords(false)}>
                返回结构
              </button>
            </div>
            {["整理技术合伙人候选", "扫描深圳产品共创项目", "解释 3 位候选人的匹配理由"].map(
              (record, index) => (
                <article key={record}>
                  <CheckCircle2 size={18} />
                  <span>
                    <b>{record}</b>
                    <small>{index === 0 ? "今天 16:40" : `${index + 1} 天前`}</small>
                  </span>
                </article>
              ),
            )}
          </section>
        ) : (
          <>
            <section className="v279-capability-complete">
              <h3>可以完成</h3>
              <div>
                {structure.complete.map((item) => (
                  <span key={item}>
                    <Check size={16} />
                    {item}
                  </span>
                ))}
              </div>
            </section>
            <section className="v279-capability-structure">
              <h3>内部结构</h3>
              <div className="v279-flow-labels" aria-label="输入到处理再到输出">
                {[
                  ["输入", structure.input],
                  ["处理", structure.process],
                  ["输出", structure.output],
                ].map(([label, values], index) => (
                  <div key={label as string}>
                    <b>{label as string}</b>
                    {(values as string[]).map((value) => (
                      <span key={value}>{value}</span>
                    ))}
                    {index < 2 && <ArrowRight size={17} />}
                  </div>
                ))}
              </div>
            </section>
          </>
        )}
        <footer className="v279-capability-actions">
          <button type="button" onClick={() => setShowRecords(true)}>
            <History size={19} />
            使用记录
          </button>
          <button type="button" onClick={useCapability}>
            开始使用
          </button>
        </footer>
      </section>
    </RootPortal>
  );
}


function formatAssetBody(content:string) {
  // Older local search artifacts were stored as JSON. Render their evidence as prose.
  if(content.trim().startsWith('['))try{const hits=JSON.parse(content);if(Array.isArray(hits)&&hits.every(hit=>typeof hit.title==='string'&&typeof hit.excerpt==='string'))return hits.map(hit=>hit.title+'\n'+hit.excerpt+'\n定位：'+(hit.anchor||'')).join('\n\n')}catch{}
  return content;
}
export function KnowledgeDetail({
  item,
  anchor,
  state,
  go,
  onBack,
  setState,
  notify,
}: {
  item: KnowledgeItem;
  anchor?:string;
  state: V277State;
  go: (screen: Screen) => void;
  onBack: () => void;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
  notify: (text: string) => void;
}) {
  const runtime=useRuntime();
  const sourceBody=formatAssetBody(item.example),sourceLines=sourceBody.split("\n"),matchLine=anchor?sourceLines.findIndex(line=>line.includes(anchor)):-1;
  useEffect(()=>{if(anchor)document.getElementById("knowledge-source-anchor")?.scrollIntoView({block:"center"})},[anchor,item.id,sourceBody]);
  const entity=runtime?.snapshot&&Object.values(runtime.snapshot.objects).flat().find(entry=>entry.id===item.id);
  const current = state.tasks.find((task) =>
    ["待确认", "进行中", "已暂停"].includes(task.status),
  );
  const used = current?.knowledgeIds.includes(item.id);
  const attach = () => {
    if(runtime&&entity){void runtime.command('task.create',{goal:'阅读并核对资料：'+item.title,mode:entity.type==='document'?'read':'compose',source_refs:[entityRef(entity)],system:'explore'}).then(result=>go({name:'task',id:result.id})).catch(()=>{});return;}
    if (!current || used) return;
    setState((s) => ({
      ...s,
      tasks: s.tasks.map((task) =>
        task.id === current.id
          ? {
              ...task,
              knowledgeIds: [...task.knowledgeIds, item.id],
              updatedAt: "刚刚",
            }
          : task,
      ),
    }));
    notify(`已添加到任务“${current.title}”`);
  };
  return (
    <main className="v277-page">
      <AppHeader title="知识详情" subtitle={item.source} onBack={onBack} />
      <article className="v277-knowledge-detail">
        <span>
          <BookOpen size={22} />
        </span>
        <h1 id={anchor&&matchLine<0?"knowledge-source-anchor":undefined}>{displayTitle(item.title,'')}</h1>
        {runtime&&entity&&<><OriginLinks targetId={entity.id} go={go}/><CalendarDraft item={entity}/><AttachmentList items={(entity.data.attachments||[]) as FileRef[]}/></>}
        {runtime&&entity?.type==='knowledge'&&entity.owner===runtime.snapshot?.user.id&&<KnowledgeEditor item={entity} onArchived={onBack}/>}
        <p>{item.purpose}</p>
        <dl>
          <div>
            <dt>来源</dt>
            <dd>{item.source}</dd>
          </div>
          <div>
            <dt>状态</dt>
            <dd>{item.status}</dd>
          </div>
        </dl>
        <section>
          <b>{runtime?"正文":"使用示例"}</b>
          <div style={{whiteSpace:"pre-wrap"}}>{sourceLines.map((line,index)=><div key={index} id={index===matchLine?"knowledge-source-anchor":undefined} style={index===matchLine?{background:"#fff0b8",borderRadius:6}:undefined}>{line||"\u00a0"}</div>)}</div>
          {runtime&&Array.isArray(entity?.data.source_refs)&&(entity.data.source_refs as {id:string}[]).map(ref=><button className="v277-secondary" key={ref.id} onClick={()=>{const source=Object.values(runtime.snapshot!.objects).flat().find(value=>value.id===ref.id);if(source)go({name:source.type==='task'?'task':'knowledge-detail',id:source.id});else notify('此来源已不可访问')}}>查看来源</button>)}
        </section>
      </article>
      <div className="v277-sticky-actions">
        <button
          type="button"
          className="v277-primary"
          disabled={runtime?!entity:!current || used}
          onClick={attach}
        >
          {runtime?"以此资料创建任务草稿":!current
            ? "当前没有可推进任务"
            : used
              ? "已用于当前任务"
              : "用于当前任务"}
        </button>
      </div>
    </main>
  );
}

export function MemoryPage({
  state,
  go,
}: {
  state: V277State;
  go: (screen: Screen) => void;
}) {
  const runtime=useRuntime();
  const [filter, setFilter] = useState("全部");
  const [alignmentOpen, setAlignmentOpen] = useState(false);
  const showBasic =
    filter === "全部" ||
    filter === "基础" ||
    filter === "近况" ||
    filter === "习惯";
  const showSocial = filter === "全部" || filter === "社交";
  return (
    <main className="v277-page v277-library-page v277-memory-overview">
      <LibraryHeader
        active="memory"
        go={go}
        onContext={() => setAlignmentOpen(true)}
      />
      <div className="v277-memory-filter" aria-label="记忆分类">
        {["全部", "基础", "社交", "近况", "习惯"].map((name) => (
          <button
            type="button"
            className={filter === name ? "active" : ""}
            key={name}
            onClick={() => setFilter(name)}
          >
            {name}
          </button>
        ))}
      </div>
      <div className="v277-library-scroll memory-scroll">{runtime&&<InactiveMemories/>}
        <section className="v277-understanding">
          <header>
            <span>
              <Bookmark size={19} />
              Elfred 对你的当前理解
            </span>
            <button type="button" onClick={() => go({ name: "profile" })}>
              展开
              <ChevronRight size={17} />
            </button>
          </header>
          <div className="v277-understanding-stats">
            <span>
              <b>{runtime?state.memories.length:128}</b>有效记忆
            </span>
            <span>
              <b>{runtime?state.memories.filter(item=>item.status==='待确认').length:7}</b>{runtime?"待确认":"天持续更新"}
            </span>
            <span>
              <b>{runtime?"待验证":"94%"}</b>{runtime?"跨情境理解":"可信度"}
            </span>
          </div>
        </section>
        {showBasic && (
          <section className="v277-memory-showcase">
            <div className="v277-section-title">
              <h2>基础</h2>
            </div>
            <button
              type="button"
              className="v277-identity-card"
              onClick={() => go({ name: "profile" })}
            >
              <span>
                <b>当前身份</b>
                <strong>{state.profile.role || (runtime?"尚未填写":"Elfred 产品负责人")}</strong>
                <p>{runtime?state.profile.bio:"正在打造帮助用户发现机会并完成价值交付的 Personal Agent。"}</p>
                <small>{runtime?"由本人维护的个人资料":"9 条基础信息 · 今天更新"}</small>
              </span>
              <i className="v277-memory-photo person-owner v277-sprite-community">
                <em>{runtime?state.profile.role:"产品负责人"}</em>
              </i>
              <footer>
                <CheckCircle2 size={18} />
                用于机会推荐，可随时纠正
                <ChevronRight size={18} />
              </footer>
            </button>
          </section>
        )}
        {showSocial && !runtime && (
          <section className="v277-memory-showcase social">
            <div className="v277-section-title">
              <h2>社交</h2>
              <button type="button" onClick={() => setFilter("社交")}>
                查看全部
                <ChevronRight size={16} />
              </button>
            </div>
            <article className="v277-relationship-card">
              <h3>关键关系</h3>
              <div>
                {[
                  ["Mia", "产品共创", "person-mia", "person-mia"],
                  ["Kevin", "技术合作", "person-kevin", "person-kevin"],
                  ["Lena", "市场增长", "person-lena", "person-lena"],
                ].map(([name, role, photo, chatId]) => (
                  <button
                    type="button"
                    key={name}
                    onClick={() => go({ name: "chat", id: chatId })}
                  >
                    <i
                      className={`v277-relation-photo ${photo} v277-sprite-community`}
                    >
                      <em>{name}</em>
                    </i>
                    <span>{role}</span>
                  </button>
                ))}
              </div>
              <footer>
                <span>8 位长期合作者 · 12 位待连接对象</span>
                <button
                  type="button"
                  onClick={() => go({ name: "utility", kind: "relationships" })}
                >
                  查看关系图
                  <ChevronRight size={16} />
                </button>
              </footer>
            </article>
          </section>
        )}
        {runtime&&<><section className="v277-memory-showcase"><h2>理解与来源</h2>{state.memories.filter(item=>filter==='全部'||item.group===filter).map(item=><button className="v277-identity-card" key={item.id} onClick={()=>go({name:'memory-detail',id:item.id})}><span><b>{item.label} · {item.status}</b><p>{item.value}</p></span><ChevronRight size={18}/></button>)}</section><AssetEditor onSaved={()=>{}}/></>}
      </div>
      {alignmentOpen && (
        <AlignmentModal go={go} onClose={() => setAlignmentOpen(false)} />
      )}
    </main>
  );
}

export function MemoryDetail({
  item,
  go,
  onBack,
  setState,
  notify,
}: {
  item: V277Memory;
  go: (screen: Screen) => void;
  onBack: () => void;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
  notify: (text: string) => void;
}) {
  const runtime=useRuntime();
  const entity=runtime?.snapshot?.objects.memory.find(entry=>entry.id===item.id);
  const [value, setValue] = useState(item.value);
  const save = () => {
    if(runtime&&entity){void runtime.command('memory.decide',{...entityRef(entity),decision:value===item.value?'confirm':'correct',content:value}).then(()=>{notify('理解已保存');go({name:'memory'})}).catch(()=>{});return;}
    setState((s) => ({
      ...s,
      profile:
        item.id === "profile-name"
          ? { ...s.profile, name: value }
          : item.id === "profile-role"
            ? { ...s.profile, role: value }
            : item.id === "profile-focus"
              ? { ...s.profile, focus: value }
              : s.profile,
      memories: s.memories.map((memory) =>
        memory.id === item.id ? { ...memory, value, status: "已确认" } : memory,
      ),
    }));
    notify("记忆已更新");
  };
  const remove = () => {
    if(runtime&&entity){void runtime.command('memory.decide',{...entityRef(entity),decision:'delete'}).then(()=>go({name:'memory'})).catch(()=>{});return;}
    setState((s) => ({
      ...s,
      profile:
        item.id === "profile-name"
          ? { ...s.profile, name: "" }
          : item.id === "profile-role"
            ? { ...s.profile, role: "" }
            : item.id === "profile-focus"
              ? { ...s.profile, focus: "" }
              : s.profile,
      memories: s.memories.filter((memory) => memory.id !== item.id),
    }));
    go({ name: "memory" });
    notify("记忆已移除");
  };
  return (
    <main className="v277-page">
      <AppHeader
        title="记忆详情"
        subtitle={`${item.group} · ${item.status}`}
        onBack={onBack}
        right={
          <IconButton label="移除记忆" onClick={remove}>
            <Trash2 size={19} />
          </IconButton>
        }
      />
      <section className="v277-edit-card">
        <label className="v277-field">
          <span>{item.label}</span>
          <textarea
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
        </label>
        <dl>
          <div>
            <dt>来源</dt>
            <dd>{item.source}</dd>
          </div>
          <div>
            <dt>使用规则</dt>
            <dd>仅已确认信息会用于任务与 Agent 对话</dd>
          </div>
        </dl>
        <button
          type="button"
          className="v277-primary"
          disabled={!value.trim() || (!runtime&&value === item.value)}
          onClick={save}
        >
          {runtime&&value===item.value?"确认这条理解":"保存修改"}
        </button>
        {runtime&&entity&&<div>{['defer','reject'].map(decision=><button className="v277-secondary" key={decision} onClick={()=>void runtime.command('memory.decide',{...entityRef(entity),decision}).then(()=>go({name:'memory'})).catch(()=>{})}>{decision==='defer'?'搁置':'否认'}</button>)}</div>}
      </section>
      {runtime&&entity&&<><MemoryEvidence item={entity}/><MemoryGovernance item={entity}/></>}
    </main>
  );
}


export function MessageSearchSheet({
  contacts,
  go,
  onClose,
}: {
  contacts: {
    id: string;
    name: string;
    text: string;
    time: string;
    badge?: number;
    kind: string;
    avatar: string;
  }[];
  go: (screen: Screen) => void;
  onClose: () => void;
}) {
  const runtime=useRuntime();
  const [query, setQuery] = useState("");
  const results = runtime&&query.trim()?[
    ...contacts.filter(item=>item.name.toLowerCase().includes(query.trim().toLowerCase())).map(item=>({...item,key:item.id,messageId:undefined as string|undefined})),
    ...(runtime.snapshot?.objects.message||[]).filter(item=>entityText(item,'text').toLowerCase().includes(query.trim().toLowerCase())).slice(0,50).flatMap(message=>{const contact=contacts.find(item=>item.id===message.space);return contact?[{...contact,key:message.id,text:entityText(message,'text'),messageId:message.id}]:[]})
  ]:(query.trim()?contacts.filter(item=>`${item.name}${item.text}`.includes(query.trim())):contacts.slice(0,3)).map(item=>({...item,key:item.id,messageId:undefined as string|undefined}));
  return (
    <RootPortal>
      <button
        type="button"
        className="v278-sheet-backdrop"
        aria-label="关闭消息搜索"
        onClick={onClose}
      />
      <section
        className="v278-half-sheet v281-message-search-sheet"
        role="dialog"
        aria-modal="true"
        aria-label="搜索消息"
      >
        <header className="v278-sheet-header">
          <span>
            <h2>搜索消息</h2>
            <p>查找联系人、群聊和聊天内容</p>
          </span>
          <button type="button" aria-label="关闭" onClick={onClose}>
            <X size={21} />
          </button>
        </header>
        <label className="v281-message-search-box">
          <Search size={21} />
          <input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索联系人和消息…"
          />
          {query && (
            <button
              type="button"
              aria-label="清空"
              onClick={() => setQuery("")}
            >
              <X size={17} />
            </button>
          )}
        </label>
        <section className="v281-message-search-results">
          <small>
            {query ? `搜索结果 · ${results.length} 条` : "最近联系"}
          </small>
          {!results.length&&<p className="v277-empty">没有匹配的会话或消息。</p>}
          {results.map((item) => (
            <button
              type="button"
              key={item.key}
              onClick={() => {
                onClose();
                go({ name: "chat", id: item.id, messageId:item.messageId });
              }}
            >
              <i className={`${item.avatar} v277-sprite-community`} />
              <span>
                <b>{item.name}</b>
                <p>{item.text}</p>
              </span>
              <ChevronRight size={18} />
            </button>
          ))}
        </section>
      </section>
    </RootPortal>
  );
}

export function ChatPage({
  id,
  messageId,
  state,
  go,
  onBack,
  setState,
  notify,
}: {
  id: string;
  messageId?:string;
  state: V277State;
  go: (screen: Screen) => void;
  onBack: () => void;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
  notify: (text: string) => void;
}) {
  const runtime=useRuntime();
  const conversation=runtime?.snapshot?.objects.conversation.find(item=>item.id===id);
  const [unreadEntry,setUnreadEntry]=useState<{id:string;after:number}|null>(null);
  useEffect(()=>{if(conversation)setUnreadEntry(current=>current?.id===id?current:{id,after:Number(conversation.data.seq)-(conversation.unread||0)})},[conversation,id]);
  const [attachments,setAttachments]=useState<FileRef[]>([]),[mediaBusy,setMediaBusy]=useState(false),[messageLimit,setMessageLimit]=useState(50);
  useEffect(()=>{setMessageLimit(50)},[id]);
  const [assistOpen,setAssistOpen]=useState(false),[chatQuery,setChatQuery]=useState(''),[sending,setSending]=useState(false);
  const [agentMode,setAgentMode]=useState<false|'personal'|'icebreaker'>(false),[agentInput,setAgentInput]=useState(''),[iceDismissed,setIceDismissed]=useState(false);
  const agentPanel=useRef<PersonalAgentHandle>(null),agentAnchor=useRef<HTMLDivElement>(null),composerInput=useRef<HTMLTextAreaElement>(null);
  const [mention,setMention]=useState<{prefix:string;query:string}|null>(null);
  const [mentionBusy,setMentionBusy]=useState(false);
  const isGroup=conversation?.data.kind==='group';
  const groupAgentReady=Boolean(isGroup&&conversation?.data.agent_enabled&&conversation?.members?.every(member=>(conversation.data.agent_consents as Record<string,boolean>|undefined)?.[member.id]));
  const latestGroupAgentTask=isGroup?runtime?.snapshot?.objects.task.filter(task=>(task.data.group_agent as {conversation_id?:string}|undefined)?.conversation_id===id).sort((a,b)=>b.created.localeCompare(a.created))[0]:undefined;
  const groupMembers=(conversation?.members||[]).filter(member=>member.id!==runtime?.snapshot?.user.id&&(!mention?.query||(member.name+' '+member.handle).toLowerCase().includes(mention.query.toLowerCase())));
  const chooseMember=(member:{id:string;name:string;handle:string})=>{if(!mention)return;setText(mention.prefix+'@'+member.name+'（'+member.handle+'） ');setMention(null);composerInput.current?.focus()};
  const chooseGroupAgent=()=>{if(!mention)return;setText(mention.prefix+'@Elfred ');setMention(null);composerInput.current?.focus()};
  const [composerHeight,setComposerHeight]=useState(64);
  const mentionGeneration=useRef(0);
  useEffect(()=>{mentionGeneration.current++;return()=>{mentionGeneration.current++}},[id]);
  useEffect(()=>{if(agentMode)agentAnchor.current?.scrollIntoView({block:'start'})},[agentMode]);
  useEffect(()=>{if(!mentionBusy&&!mention)composerInput.current?.focus()},[agentMode,mentionBusy,Boolean(mention)]);
  const [searchHits,setSearchHits]=useState<{id:string;type:string;title:string;excerpt:string}[]|null>(null);
  const lastHumanMessage=runtime?.snapshot?.objects.message.filter(item=>item.space===id).sort((a,b)=>Number(b.data.seq)-Number(a.data.seq))[0];
  const cold=conversation?.data.kind==='direct'&&(!lastHumanMessage||Date.parse(runtime?.snapshot?.server_time||lastHumanMessage.created)-Date.parse(lastHumanMessage.created)>=7*86400000);
  const agentDraftKey=runtime?.snapshot?`elfred-personal-draft:${runtime.snapshot.user.id}:${id}`:'';
  useEffect(()=>{setAgentMode(false);setMention(null);setMentionBusy(false);setIceDismissed(false);setSearchHits(null);try{setAgentInput(sessionStorage.getItem(agentDraftKey)||'')}catch{setAgentInput('')}},[agentDraftKey]);
  const updateAgentInput=(value:string)=>{setAgentInput(value);try{sessionStorage.setItem(agentDraftKey,value)}catch{}};
  const {text,setText,save:flushDraft,saving:draftSaving,reload:reloadDraft}=useConversationDraft(id,Boolean(conversation));
  const composerValue=agentMode?agentInput:mention?mention.prefix+'@'+mention.query:text;
  useLayoutEffect(()=>{
    const field=composerInput.current;if(!field)return;
    field.style.height='0px';const height=Math.max(48,Math.min(144,field.scrollHeight));
    field.style.height=height+'px';field.style.overflowY=field.scrollHeight>144?'auto':'hidden';setComposerHeight(height+16);
  },[composerValue,id]);
  useEffect(()=>{if(!runtime||!conversation)return;void runtime.command('conversation.read',{id,seq:conversation.data.seq}).catch(()=>{});},[id,conversation?.data.seq]);
  useEffect(()=>{if(messageId)document.getElementById('message-'+messageId)?.scrollIntoView({block:'center'});},[id,messageId]);
  const openMentionPersonal=()=>{
    if(!mention||mentionBusy)return;setMentionBusy(true);
    const query=mention.query,generation=mentionGeneration.current;
    void flushDraft().then(()=>{if(generation!==mentionGeneration.current)return;if(query.trim())updateAgentInput(query);setMention(null);setAgentMode('personal');composerInput.current?.focus()}).catch(()=>{}).finally(()=>{if(generation===mentionGeneration.current)setMentionBusy(false)});
  };
  const closeMention=()=>{mentionGeneration.current++;setMentionBusy(false);setMention(null);composerInput.current?.focus()};
  const changeComposer=(value:string)=>{
    if(agentMode){updateAgentInput(value);return;}
    if(mention){
      const marker=mention.prefix+'@';
      if(value.startsWith(marker)){setMention({...mention,query:value.slice(marker.length)});return;}
      mentionGeneration.current++;setMentionBusy(false);setMention(null);setText(value);return;
    }
    if(runtime&&conversation&&value.endsWith('@')&&(value.length===1||/[^a-zA-Z0-9_.+-]/.test(value[value.length-2]))){setText(value.slice(0,-1));setMention({prefix:value.slice(0,-1),query:''});return;}
    setText(value);
  };
  const saveDraft=()=>{void flushDraft().catch(()=>{});};
  const [searchOpen, setSearchOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const agent = agentList.find((item) => item.id === id);
  const contact = conversation?{name:displayTitle(entityText(conversation,'title'),'会话'),subtitle:conversation.data.kind==='group'?'群聊 · '+conversation.members?.length+' 人':'真人会话',greeting:''}:runtime?undefined:chatDirectory[id];
  const isHuman = Boolean(conversation || (contact && id.startsWith("person-")));
  const humanPreview: V277Message[] =
    id === "person-linjia"
      ? [
          {
            id: "linjia-1",
            role: "assistant",
            text: "我刚看完你发的 Elfred 首页方案，早中晚三张卡片这个思路挺清楚。",
            time: "今天 14:20",
          },
          {
            id: "linjia-2",
            role: "user",
            text: "对，我想让首页根据用户每天打开的时机变化。",
            time: "",
          },
          {
            id: "linjia-3",
            role: "assistant",
            text: "中午那张卡片能直接调整下午的任务吗？",
            time: "",
          },
          {
            id: "linjia-4",
            role: "user",
            text: "可以，确认后会同步到任务页。",
            time: "",
          },
          {
            id: "linjia-5",
            role: "assistant",
            text: "那这套逻辑就顺了。",
            time: "",
          },
        ]
      : [];
  const defaultMessages =
    humanPreview.length > 0
      ? humanPreview
      : contact
        ? [
            {
              id: `welcome-${id}`,
              role: "assistant" as const,
              text: contact.greeting,
              time: "刚刚",
            },
          ]
        : [];
  const messages =
    state.messages[id] ||
    (runtime?[]:defaultMessages);
  const send = (event?: FormEvent) => {
    event?.preventDefault();
    if(mention){if(isGroup){if(groupAgentReady&&/^elfred$/i.test(mention.query.trim()))chooseGroupAgent();else if(mention.query.trim()&&groupMembers.length===1)chooseMember(groupMembers[0])}else openMentionPersonal();return;}
    const input = (agentMode?agentInput:text).trim();
    if ((!input&&!attachments.length)||sending||mediaBusy) return;
    if(runtime&&conversation&&agentMode){
      if(!input)return;setSending(true);
      const keyword=/^(?:搜索|检索|查找)[：:\s]*(.+)$/.exec(input)?.[1]?.trim();
      void (async()=>{try{if(keyword){const result=await runtime.request<{hits:{id:string;type:string;title:string;excerpt:string}[]}>('/search',{query:keyword});setSearchHits(result.hits);updateAgentInput('')}else if(await agentPanel.current?.submit(input))updateAgentInput('')}catch(error){runtime.report(error instanceof Error?error.message:'请求失败')}finally{setSending(false)}})();return;
    }
    if(runtime){setSending(true);void flushDraft().then(()=>conversation?runtime.command('message.send',{id,text:input,attachment_ids:attachments.map(file=>file.id),mentions:isGroup?(conversation.members||[]).filter(member=>input.includes('@'+member.name+'（'+member.handle+'）')).map(member=>member.id):[],agent_mention:Boolean(isGroup&&/(?:^|\s)@Elfred(?:\s|$)/i.test(input))}):runtime.command('task.create',{goal:input,mode:/^(搜索|检索|查找)/.test(input)?'search':'compose',system:agent?.id==='advisor'?'advise':agent?.id||'execute'})).then(async result=>{setText('');setAttachments([]);if(conversation)await flushDraft();else go({name:'task',id:result.id})}).catch(()=>{}).finally(()=>setSending(false));return;}
    const userMessage: V277Message = {
      id: makeId("message"),
      role: "user",
      text: input,
      time: "刚刚",
    };
    const reply: V277Message = {
      id: makeId("reply"),
      role: "assistant",
      text: /任务|计划|推进|完成|做/.test(input)
        ? "我先把它整理成一个任务草稿。你可以直接打开确认，之后会在任务台和负责 Agent 中同步。"
        : "我记下了。为了让下一步更具体，请补充你希望最终得到什么结果。",
      time: "刚刚",
    };
    setState((s) => ({
      ...s,
      messages: {
        ...s.messages,
        [id]: [
          ...(s.messages[id] || messages),
          userMessage,
          ...(isHuman ? [] : [reply]),
        ],
      },
    }));
    setText("");
  };
  const createTask = () => {
    const latest =
      [...messages].reverse().find((message) => message.role === "user")
        ?.text || text.trim();
    if (!latest) {
      notify("先说一件你想推进的事");
      return;
    }
    if(runtime){void runtime.command('task.create',{goal:latest,mode:'compose',system:'execute'}).then(result=>go({name:'task',id:result.id})).catch(()=>{});return;}
    const existing = state.tasks.find(
      (task) => task.sourceId === `chat-${id}-${latest}`,
    );
    if (existing) {
      go({ name: "task", id: existing.id });
      return;
    }
    const task: V277Task = {
      id: makeId("chat-task"),
      title: latest.length > 26 ? `${latest.slice(0, 26)}…` : latest,
      brief: `把对话里的目标整理成可以确认和推进的任务。`,
      source: `${id === "elfred" ? "Elfred" : contact ? contact.name : `${agent?.name} Agent`} 对话`,
      sourceId: `chat-${id}-${latest}`,
      agent: agent?.id || "execute",
      status: "待确认",
      nextStep: "确认目标与交付范围",
      result: [
        "明确完成标准和边界。",
        "完成最小可用的一版结果。",
        "用一次真实反馈决定下一步。",
      ],
      knowledgeIds: [],
      updatedAt: "刚刚",
    };
    setState((s) => ({ ...s, tasks: [task, ...s.tasks] }));
    notify("任务草稿已创建");
    go({ name: "task", id: task.id });
  };
  if (isHuman)
    return (
      <main className="v277-page v277-chat-page v279-human-chat-page" style={{'--elfred-composer-height':composerHeight+'px'} as CSSProperties}>
        <header className="v279-human-chat-head">
          <IconButton label="返回" onClick={onBack}>
            <ArrowLeft size={21} />
          </IconButton>
          <button
            type="button"
            className="v279-chat-person"
            onClick={() => go({ name: "friend-profile", id })}
          >
            <i className="avatar-lin v277-sprite-community">
              <em />
            </i>
            <span>
              <b>{contact?.name}</b>
              <small>{contact?.subtitle}</small>
            </span>
          </button>
          <span>
            <IconButton label="搜索对话" onClick={() => setSearchOpen(true)}>
              <Search size={21} />
            </IconButton>
            <IconButton label="更多" onClick={() => {if(!sending)setMoreOpen(true)}}>
              <MoreHorizontal size={21} />
            </IconButton>
          </span>
        </header>
        {runtime&&isGroup&&!agentMode&&<><button className="v277-secondary" style={{margin:'4px 20px'}} onClick={()=>void flushDraft().then(()=>setAgentMode('personal')).catch(()=>{})}>帮我理解与准备表达 · 仅自己可见</button>{conversation?.data.agent_enabled&&<small style={{margin:'0 20px',display:'block'}}>Elfred 在群内以 AI 身份参与{groupAgentReady?' · 输入 @Elfred 可提问':' · 等待成员授权'}</small>}{latestGroupAgentTask&&['queued','running','blocked','failed','reconciliation_required'].includes(String(latestGroupAgentTask.data.status))&&<button type="button" className="v277-secondary" style={{margin:'4px 20px'}} onClick={()=>go({name:'task',id:latestGroupAgentTask.id})} role="status">Elfred 回复：{runtimeStatuses[String(latestGroupAgentTask.data.status)]||String(latestGroupAgentTask.data.status)} · 查看详情</button>}</>}
        <section className="v277-chat-stream v279-human-chat-stream">
          <time>{runtime?new Date().toLocaleDateString("zh-CN"):"今天 14:20"}</time>
          {runtime&&messages.length>messageLimit&&!chatQuery&&!messageId&&<button type="button" className="v277-secondary" onClick={()=>setMessageLimit(value=>value+50)}>加载更早的消息</button>}
          {messages.filter(message=>!chatQuery||message.text.includes(chatQuery)).slice(chatQuery||messageId?0:-messageLimit).map((message, index) => (
            <Fragment key={message.id}>
              <div id={"message-"+message.id} className={`v277-message ${message.role}`} style={message.id===messageId?{outline:"2px solid #7894a4",borderRadius:12}:undefined}>
                {message.role === "assistant" && (runtime?.snapshot?.objects.message.find(item=>item.id===message.id)?.data.actor_type==='agent'?<span className="elfred-group-agent-avatar" aria-label="AI Agent"><Bot size={19}/></span>:<i className="avatar-lin v277-sprite-community" />)}
                <div>
                  {runtime&&<small>{entityText(runtime.snapshot?.objects.message.find(item=>item.id===message.id),'sender_name')} · {message.time}</small>}
                  <p>{message.text}</p>{runtime&&runtime.snapshot?.objects.message.find(item=>item.id===message.id)?.data.actor_type==='agent'&&<><small>AI 协作建议 · 日程、介绍和承诺待相关成员确认</small><details><summary>查看引用的群消息</summary>{((runtime.snapshot?.objects.message.find(item=>item.id===message.id)?.data.source_refs||[]) as {id:string}[]).map(ref=>{const source=runtime.snapshot?.objects.message.find(item=>item.id===ref.id);return <button type="button" key={ref.id} className="v277-secondary" onClick={()=>document.getElementById('message-'+ref.id)?.scrollIntoView({block:'center'})}>{source?`${entityText(source,'sender_name')}：${entityText(source,'text').slice(0,60)}`:'来源已不可访问'}</button>})}</details></>}{runtime&&<SharedRecordCard message={runtime.snapshot?.objects.message.find(item=>item.id===message.id)} go={go}/>}{runtime&&<AttachmentList items={(runtime.snapshot?.objects.message.find(item=>item.id===message.id)?.data.attachments||[]) as FileRef[]}/>}
                </div>
              </div>
              {id === "person-linjia" && index === 3 && (
                <div className="v279-chat-share-row">
                  <button
                    type="button"
                    className="v279-chat-share-card"
                    onClick={() =>
                      go({ name: "daily-brief", kind: "morning" })
                    }
                  >
                    <span aria-hidden="true">
                      <i />
                      <i />
                      <i />
                    </span>
                    <div>
                      <b>Elfred 首页时段卡片</b>
                      <small>早间 · 午间 · 晚间</small>
                      <em>
                        查看方案 <ChevronRight size={15} />
                      </em>
                    </div>
                  </button>
                </div>
              )}
            </Fragment>
          ))}
          {runtime&&conversation&&cold&&!iceDismissed&&!agentMode&&!mention&&<div className="elfred-icebreaker"><span>想重新聊起来？Elfred 可以帮你找个开场。</span><button type="button" onClick={()=>{void flushDraft().then(()=>setAgentMode('icebreaker')).catch(()=>{})}}>准备开场</button><button type="button" aria-label="关闭破冰提示" onClick={()=>setIceDismissed(true)}>×</button></div>}
          {runtime&&conversation&&agentMode&&<div ref={agentAnchor}><PersonalAgentPanel ref={agentPanel} conversation={conversation} unreadAfter={unreadEntry?.after} entry={agentMode} onClose={()=>{if(!sending){setAgentMode(false);setSearchHits(null)}}} onFill={async(value,version)=>{setSending(true);try{await runtime.command('draft.save',{conversation_id:id,text:value,version});await reloadDraft(value)}finally{setSending(false)}}} go={go}/></div>}
          {agentMode&&searchHits&&<section className="elfred-search-results" aria-label="个人智能体搜索结果"><b>搜索结果 · {searchHits.length} 条</b>{!searchHits.length&&<p>未找到匹配资料，试试更具体的关键词。</p>}{searchHits.map(hit=><button type="button" key={hit.id} onClick={()=>{void runtime!.request<import('../features/live/types').Entity>('/objects/'+hit.id).then(item=>go(objectScreen(item))).catch(error=>runtime!.report(error.message))}}><b>{displayTitle(hit.title,'')}</b><p>{hit.excerpt}</p><small>{hit.type} · 查看来源</small></button>)}</section>}
        </section>
        {runtime&&conversation&&mention&&!agentMode&&isGroup&&<section id="elfred-mention-picker" className="elfred-mention-picker" aria-label="选择群成员"><p className="elfred-mention-title">提及群成员或群协作 Agent</p><div className="elfred-mention-results">{groupAgentReady&&'Elfred'.toLowerCase().includes(mention.query.toLowerCase())&&<button className="elfred-mention-personal" type="button" onClick={chooseGroupAgent}><span><strong>Elfred · 群协作 Agent</strong><small>AI 身份公开回复 · 使用群内授权上下文</small></span></button>}{groupMembers.map(member=><button className="elfred-mention-personal" type="button" key={member.id} onClick={()=>chooseMember(member)}><span><strong>{member.name}</strong><small>@{member.handle}</small></span></button>)}{!groupMembers.length&&!groupAgentReady&&<p>没有匹配的当前群成员</p>}</div><button type="button" onClick={closeMention}>取消</button></section>}
        {runtime&&conversation&&mention&&!agentMode&&!isGroup&&<MentionPicker query={mention.query} busy={mentionBusy} onPersonal={openMentionPersonal} onDismiss={closeMention} onResource={item=>{if(mentionBusy)return;setMentionBusy(true);const generation=mentionGeneration.current;void flushDraft().then(()=>{if(generation!==mentionGeneration.current)return;setMention(null);go(objectScreen(item))}).catch(()=>{}).finally(()=>{if(generation===mentionGeneration.current)setMentionBusy(false)})}}/>}
        {mention&&!mention.prefix&&!mention.query&&<span className="elfred-mention-input-hint" aria-hidden="true">继续输入…</span>}
        <form className={`v279-human-composer ${runtime?'elfred-connected-composer':''} ${agentMode?'elfred-agent-mode':''} ${mention?'elfred-mention-composer':''}`} onSubmit={send}>
          <button type="button" aria-label="添加内容" disabled={sending} onClick={()=>void flushDraft().then(()=>setAssistOpen(true)).catch(()=>{})}>
            <Plus size={22} />
          </button>
          <textarea
            rows={1}
            aria-label={agentMode?'对 Elfred 说':'发消息'}
            ref={composerInput}
            disabled={sending||mentionBusy}
            aria-expanded={Boolean(mention)}
            aria-controls={mention?'elfred-mention-picker':undefined}
            onBlur={()=>{if(!agentMode)saveDraft()}}
            value={composerValue}
            onChange={event=>changeComposer(event.target.value)}
            onKeyDown={event=>{if(event.nativeEvent.isComposing||event.nativeEvent.keyCode===229)return;if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();send();return;}if(event.key==='Escape'&&mention){event.preventDefault();closeMention()}else if(event.key==='ArrowDown'&&mention){event.preventDefault();document.querySelector<HTMLButtonElement>('.elfred-mention-personal')?.focus()}}}
            placeholder={agentMode?'问 Elfred，或输入 搜索 关键词':attachments.length?`已选 ${attachments.length} 个附件，点击箭头发送`:draftSaving?"正在保存草稿…":"发消息…"}
          />
          <VoiceInput waveform={Boolean(mention)} disabled={sending||mentionBusy} onText={value=>changeComposer((agentMode?agentInput:mention?mention.prefix+'@'+mention.query:text)+value)}/>
          <button type="submit" aria-label={mention?(isGroup?'选择群成员':'选择我的 Elfred'):agentMode?'发送给 Elfred':'发送消息'} disabled={(!mention&&(agentMode?!agentInput.trim():!text.trim()&&!attachments.length))||sending||mediaBusy||mentionBusy}>
            <ArrowUp size={21} />
          </button>
        </form>
        {runtime&&conversation&&assistOpen&&<RootPortal><button className="v278-sheet-backdrop" aria-label="关闭辅助" onClick={()=>setAssistOpen(false)}/><section className="v278-half-sheet" role="dialog" aria-modal="true" style={{overflowY:'auto',maxHeight:'80%'}}><button className="v277-secondary" onClick={()=>setAssistOpen(false)}>关闭</button><GroupAgentPanel conversation={conversation}/><AttachmentPicker value={attachments} onChange={setAttachments} conversationId={id} go={go} onBusy={setMediaBusy}/><ConversationMembers conversation={conversation} onLeave={onBack}/><GroupRecords conversation={conversation}/><ConversationHandoffs conversation={conversation} go={go}/></section></RootPortal>}
        {searchOpen && (
          <RootPortal>
            <button
              type="button"
              className="v278-sheet-backdrop"
              aria-label="关闭搜索"
              onClick={() => setSearchOpen(false)}
            />
            <section className="v279-chat-action-sheet" role="dialog" aria-modal="true">
              <i className="v278-sheet-handle" />
              <header className="v279-sheet-title">
                <h2>搜索对话</h2>
                <IconButton label="关闭" onClick={() => setSearchOpen(false)}>
                  <X size={20} />
                </IconButton>
              </header>
              <label className="v279-chat-search-box">
                <Search size={20} />
                <input autoFocus placeholder="搜索当前会话" value={chatQuery} onChange={event=>setChatQuery(event.target.value)}/>
              </label>
            </section>
          </RootPortal>
        )}
        {moreOpen && (
          <RootPortal>
            <button
              type="button"
              className="v278-sheet-backdrop"
              aria-label="关闭更多操作"
              onClick={() => setMoreOpen(false)}
            />
            <section className="v279-chat-action-sheet" role="dialog" aria-modal="true">
              <i className="v278-sheet-handle" />
              <header className="v279-sheet-title">
                <h2>对话设置</h2>
                <IconButton label="关闭" onClick={() => setMoreOpen(false)}>
                  <X size={20} />
                </IconButton>
              </header>
              <div className="v279-chat-menu">
                <button
                  type="button"
                  onClick={() => go({ name: "friend-profile", id })}
                >
                  <UserRound size={21} />
                  <span>查看好友资料</span>
                  <ChevronRight size={18} />
                </button>
                <button
                  type="button"
                  disabled={sending} onClick={() => {if(!sending)void flushDraft().then(()=>{if(!sending){setMoreOpen(false);setAgentMode('personal')}}).catch(()=>{})}}
                >
                  <Bot size={21} />
                  <span>{runtime?"我的 Elfred":"和 Ta 的 Personal Agent 沟通"}</span>
                  <ChevronRight size={18} />
                </button>
              </div>
            </section>
          </RootPortal>
        )}
      </main>
    );
  return (
    <main className="v277-page v277-chat-page">
      <AppHeader
        title={
          id === "elfred"
            ? "我的 Elfred"
            : contact
              ? contact.name
              : `${agent?.name} Agent`
        }
        subtitle={
          id === "elfred"
            ? "目标、任务与结果助手"
            : contact
              ? contact.subtitle
              : agent?.role
        }
        onBack={onBack}
        right={
          <IconButton label="创建任务" onClick={createTask}>
            <ListChecks size={19} />
          </IconButton>
        }
      />
      <section className="v277-chat-stream">
        {messages.map((message) => (
          <div className={`v277-message ${message.role}`} key={message.id}>
            {message.role === "assistant" && (
              <span>
                {id === "elfred" ? <Sparkles size={16} /> : <Bot size={16} />}
              </span>
            )}
            <div>
              <p>{message.text}</p>{runtime&&<SharedRecordCard message={runtime.snapshot?.objects.message.find(item=>item.id===message.id)} go={go}/>}{runtime&&<AttachmentList items={(runtime.snapshot?.objects.message.find(item=>item.id===message.id)?.data.attachments||[]) as FileRef[]}/>}
              <small>{message.time}</small>
            </div>
          </div>
        ))}
      </section>
      <form className="v277-composer" onSubmit={send}>
        <input
          aria-label="输入消息"
          disabled={sending}
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="说一件你想推进的事…"
        />
        <button type="submit" aria-label="发送消息" disabled={(!text.trim()&&!attachments.length)||sending||mediaBusy}>
          <Send size={19} />
        </button>
      </form>
    </main>
  );
}

export function FriendProfilePage({
  id,
  go,
  onBack,
}: {
  id: string;
  go: (screen: Screen) => void;
  onBack: () => void;
}) {
  const runtime=useRuntime();
  const conversation=runtime?.snapshot?.objects.conversation.find(item=>item.id===id);
  const contact = runtime?{name:displayTitle(entityText(conversation,'title'),'会话')||'会话当前不可访问'}:chatDirectory[id] || chatDirectory['person-linjia'];
  return (
    <main className="v277-page v279-friend-profile-page">
      <AppHeader title="好友信息" onBack={onBack} />
      <section className="v279-friend-identity">
        <i className="avatar-lin v277-sprite-community">
          <em />
        </i>
        <h1>{contact.name}</h1>
        <p>{runtime?conversation?.data.kind==='group'?"群聊成员":"已确认站内关系":"产品设计师 · 深圳"}</p>
        <span>
          <i /> {runtime?"不提供在线状态":"在线"}
        </span>
      </section>
      <section className="v279-friend-info-list">
        <div>
          <span>当前关注</span>
          <b>{runtime?"以对方明确表达为准":"Personal Agent 产品体验"}</b>
        </div>
        <div>
          <span>关系</span>
          <b>{runtime?conversation?.members?.map(member=>member.name).join("、"):"产品共创联系人"}</b>
        </div>
      </section>
      <button
        type="button"
        className="v277-primary v279-friend-agent-entry"
        onClick={() => go({ name: "chat", id:runtime?id:"partner-agent-linjia" })}
      >
        {runtime?"返回真人会话":"和 Ta 的 Agent 沟通"}
        <ArrowRight size={18} />
      </button>
      <button
        type="button"
        className="v277-secondary v279-friend-message-entry"
        onClick={() => go({ name: "chat", id })}
      >
        发消息
      </button>
    </main>
  );
}

export function CommunityPage({
  state,
  go,
  setState,
  notify,
}: {
  state: V277State;
  go: (screen: Screen) => void;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
  notify: (text: string) => void;
}) {
  const runtime=useRuntime();
  const [searchOpen, setSearchOpen] = useState(false);
  const [playerCollapsed, setPlayerCollapsed] = useState(false);
  const [liked, setLiked] = useState<string[]>([]);
  const [comment, setComment] = useState("");
  const [communityKind,setCommunityKind]=usePageState('community:kind','all');
  const followed=(author:string)=>Boolean(runtime?.snapshot?.objects.interaction.some(i=>i.data.kind==='follow_author'&&i.data.object_id===author&&i.data.active));
  const visibleWorks=runtime?.snapshot?.objects.release.filter(r=>r.visibility==='public'&&r.data.author_type==='human'&&r.data.status==='published'&&r.data.is_current&&(communityKind!=='following'||followed(r.owner))&&!runtime.snapshot?.objects.interaction.some(i=>i.data.object_id===r.id&&i.data.kind==='hide'&&i.data.active))||[];
  const shownWorks=runtime&&['all','work','following'].includes(communityKind)?visibleWorks:[];
  const visiblePosts:SocialPost[]=runtime?(runtime.snapshot?.objects.post||[]).filter(item=>item.visibility==='public'&&item.data.author_type==='human'&&['published','recruiting','closed'].includes(String(item.data.status))&&!state.hiddenPostIds.includes(item.id)&&(communityKind!=='following'||followed(item.owner))&&(['all','following'].includes(communityKind)||(communityKind==='project'?Boolean(item.data.project_id):communityKind==='post'?!item.data.project_id:false))).map(item=>({id:item.id,name:entityText(item,'author_name')||displayTitle(entityText(item,'title'),'社区动态'),date:new Date(item.created).toLocaleDateString('zh-CN'),text:entityText(item,'content'),likes:Number(item.data.likes||0),comments:Number(item.data.comments||0),avatar:'lin'})):communityPosts;
  const communityDates = new Map([...(runtime?.snapshot?.objects.post || []), ...shownWorks].map(item => [item.id, item.created]));
  const toggleSaved = (id: string) => {
    if(runtime){void runtime.command('post.interact',{id,kind:'save'}).catch(()=>{});return;}
    const saved = state.savedPostIds.includes(id);
    setState((current) => ({
      ...current,
      savedPostIds: saved
        ? current.savedPostIds.filter((item) => item !== id)
        : [...current.savedPostIds, id],
    }));
    notify(saved ? "已取消收藏" : "帖子已收藏");
  };
  return (
    <main
      className={`v277-page v277-community-page v277-reference-page${playerCollapsed ? " player-collapsed" : ""}`}
      onScroll={(event) =>
        setPlayerCollapsed(event.currentTarget.scrollTop > 48)
      }
    >
      <PullDownPill onOpen={() => go({ name: "my-tools" })} />
      <div className="v277-community-head-row v282-community-fixed-head">
        <HomeChannelTabs
          active="community"
          onChange={(next) => next === "home" && go({ name: "home" })}
          taskCount={state.tasks.filter(task=>task.status!=="已完成").length}
          go={go}
        />
        <button
          type="button"
          className="v277-community-search v278-community-search-entry"
          aria-label="搜索社区"
          onClick={() => setSearchOpen(true)}
        >
          <Search size={23} strokeWidth={1.8} />
          <span>搜索社区…</span>
        </button>
        <IconButton
          label="通知"
          onClick={() => go({ name: "utility", kind: "notifications" })}
        >
          <Bell size={22} strokeWidth={1.8} />
        </IconButton>
      </div>
      {runtime?<CommunityEntry go={go}/>:<>
      <button
        type="button"
        className="v277-community-featured"
        onClick={() => go({ name: "community-post", id: runtime?"new":communityPosts[0].id })}
      >
        <i className="v277-feature-image v277-sprite-community" />
        <span>
          <b>{runtime?"分享动态或发起共创":"本周值得参与的 3 个讨论"}</b>
          <small>{runtime?"分享你的发现，或邀请大家一起完成目标":"社区精选 · 刚刚更新"}</small>
        </span>
        <span className="v277-feature-people">
          <i className="v277-feature-face face-one v277-sprite-community" />
          <i className="v277-feature-face face-two v277-sprite-community" />
          <i className="v277-feature-face face-three v277-sprite-community" />
        </span>
        <ChevronRight size={22} />
      </button>
      </>}
      {runtime&&<nav aria-label="社区内容分类" className="community-kind-filters">{[['all','全部'],['post','动态'],['work','作品'],['project','共创'],['following','关注']].map(([v,n])=><button key={v} aria-pressed={communityKind===v} onClick={()=>setCommunityKind(v)}>{n}</button>)}</nav>}
      <section className="v277-social-feed">
        {[...visiblePosts,...shownWorks.map(r=>({id:r.id,name:entityText(r,'author_name'),date:new Date(r.created).toLocaleDateString('zh-CN'),text:entityText(r,'content'),likes:0,comments:0,avatar:'lin'} as SocialPost))].sort((a,b)=>runtime?(communityDates.get(b.id)||'').localeCompare(communityDates.get(a.id)||''):0).map((post) => {
          const work=visibleWorks.find(r=>r.id===post.id);if(work)return <CommunityWorkCard key={work.id} release={work} go={go}/>;
          const originalPost=runtime?.snapshot?.objects.post.find(p=>p.id===post.id);
          const isLiked = runtime?runtime.snapshot?.objects.interaction.some(item=>item.data.object_id===post.id&&item.data.kind==='like'&&item.data.active):liked.includes(post.id);
          const saved = state.savedPostIds.includes(post.id);
          return (
            <article className="v277-social-post" key={post.id}>
              <header>
                {runtime?<i className="community-human-avatar" aria-hidden="true">{post.name.slice(0,1)}</i>:<i className={`v277-social-avatar avatar-${post.avatar} v277-sprite-community`}/>}
                <span>
                  <b>{post.name}</b>
                  <small>{post.date}</small>
                </span>
              </header>
              <button
                type="button"
                className="v277-social-body"
                onClick={() => go({ name: "community-post", id: post.id })}
              >
                {runtime?.snapshot?.objects.post.find(item=>item.id===post.id)?.data.project_id?<span className="community-cocreation-label">共创帖</span>:null}
                {originalPost&&<h3>{displayTitle(entityText(originalPost,'title'),'')}</h3>}
                <p>{post.text}</p>
              </button>
              {originalPost&&<><RecruitmentSummary post={originalPost} onOpen={()=>go({name:"community-post",id:post.id})}/><FollowAuthor post={originalPost}/></>}
              {originalPost&&((originalPost.data.attachments||[]) as FileRef[]).some(file=>file.mime.startsWith('image/'))&&<button type="button" className="community-post-image-preview" onClick={()=>go({name:'community-post',id:post.id})} aria-label="查看动态图片"><img src={`/api/elfred/attachments/${((originalPost.data.attachments||[]) as FileRef[]).find(file=>file.mime.startsWith('image/'))?.id}`} alt="动态配图" loading="lazy"/></button>}
              {post.gallery && (
                <button
                  type="button"
                  className="v277-social-gallery"
                  aria-label="查看帖子图片"
                  onClick={() => go({ name: "community-post", id: post.id })}
                >
                  <i className="gallery-one v277-sprite-community" />
                  <i className="gallery-two v277-sprite-community" />
                  <i className="gallery-three v277-sprite-community" />
                </button>
              )}
              <div className="v277-social-actions">
                <button
                  type="button"
                  className={isLiked ? "liked" : ""}
                  onClick={() =>
                    runtime?void runtime.command('post.interact',{id:post.id,kind:'like'}).catch(()=>{}):setLiked((items) =>
                      isLiked
                        ? items.filter((id) => id !== post.id)
                        : [...items, post.id],
                    )
                  }
                >
                  <Heart size={22} fill={isLiked ? "currentColor" : "none"} />
                  {post.likes + (!runtime&&isLiked ? 1 : 0)}
                </button>
                <button
                  type="button"
                  onClick={() => go({ name: "community-post", id: post.id })}
                >
                  <MessageCircle size={22} />
                  {post.comments}
                </button>
                <button
                  type="button"
                  aria-label="分享"
                  onClick={() => {void navigator.clipboard.writeText(location.origin+location.pathname+'?post='+post.id).then(()=>notify('帖子链接已复制')).catch(()=>notify('复制失败，请重试'))}}
                >
                  <Send size={21} />
                </button>
                <button
                  type="button"
                  aria-label={saved ? "取消收藏" : "收藏"}
                  onClick={() => toggleSaved(post.id)}
                >
                  <Bookmark size={21} fill={saved ? "currentColor" : "none"} />
                </button>
              </div>
              {post.preview && (
                <>
                  <div className="v277-comment-preview">
                    <i className="v277-comment-avatar v277-sprite-community" />
                    <span>{post.preview}</span>
                  </div>
                  <button
                    type="button"
                    className="v277-expand-comments"
                    onClick={() => go({ name: "community-post", id: post.id })}
                  >
                    展开评论
                    <ChevronDown size={17} />
                  </button>
                  <form
                    className="v277-inline-comment"
                    onSubmit={(event) => {
                      event.preventDefault();
                      if (!comment.trim()) return;
                      setComment("");
                      notify("评论已发布");
                    }}
                  >
                    <input
                      value={comment}
                      onChange={(event) => setComment(event.target.value)}
                      placeholder="期待你的评论…"
                      aria-label="发表评论"
                    />
                  </form>
                </>
              )}
            </article>
          );
        })}
        {!visiblePosts.length&&!shownWorks.length && (
        <div className="v277-empty">
          <b>{communityKind==='all'?'社区还没有真人发布的内容':'这个分类暂时没有内容'}</b>
          <p>可以分享动态、作品，或发起一个共创项目。</p>
          <button type="button" onClick={()=>go({name:'community-post',id:'new'})}>发布第一条内容</button>
        </div>
        )}
      </section>
      <TaskPlayer state={state} go={go} collapsed={playerCollapsed} />
      {searchOpen && (
        <CommunitySearchSheet go={go} onClose={() => setSearchOpen(false)} />
      )}
    </main>
  );
}

export function CommunitySearchSheet({
  go,
  onClose,
}: {
  go: (screen: Screen) => void;
  onClose: () => void;
}) {
  const runtime=useRuntime();
  const posts=runtime?(runtime.snapshot?.objects.post||[]).map(item=>({id:item.id,name:displayTitle(entityText(item,'title'),'社区动态'),text:entityText(item,'content'),avatar:'lin'})):communityPosts;
  const [query, setQuery] = useState("");
  const normalized = query.trim();
  const results = normalized
    ? posts.filter((post) =>
        `${post.name}${post.text}`.includes(normalized),
      )
    : posts;
  return (
    <RootPortal>
      <button
        type="button"
        className="v278-sheet-backdrop"
        aria-label="关闭社区搜索"
        onClick={onClose}
      />
      <section
        className="v278-half-sheet v278-community-search-sheet"
        role="dialog"
        aria-modal="true"
        aria-label="社区搜索"
      >
        <header className="v278-sheet-header">
          <span>
            <h2>搜索社区</h2>
            <p>查找社区中的用户、讨论与内容</p>
          </span>
          <button type="button" aria-label="关闭" onClick={onClose}>
            <X size={21} />
          </button>
        </header>
        <label className="v278-global-search-box">
          <Search size={22} />
          <input
            autoFocus
            aria-label="输入社区搜索内容"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索社区…"
          />
          {query && (
            <button
              type="button"
              aria-label="清空搜索"
              onClick={() => setQuery("")}
            >
              <X size={17} />
            </button>
          )}
        </label>
        <section className="v278-community-search-results">
          <header>
            <h3>{normalized ? "搜索结果" : "最近讨论"}</h3>
            <small>{results.length} 条</small>
          </header>
          {results.map((post) => (
            <button
              type="button"
              key={post.id}
              onClick={() => go({ name: "community-post", id: post.id })}
            >
              <i
                className={`v277-social-avatar avatar-${post.avatar} v277-sprite-community`}
              />
              <span>
                <b>{post.name}</b>
                <p>{post.text}</p>
              </span>
              <ChevronRight size={18} />
            </button>
          ))}
        </section>
      </section>
    </RootPortal>
  );
}

export function CommunityPostDetail({
  post,
  state,
  setState,
  notify,
  onBack,
}: {
  post: SocialPost;
  state: V277State;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
  notify: (text: string) => void;
  onBack: () => void;
}) {
  const [liked, setLiked] = useState(false);
  const [comment, setComment] = useState("");
  const [comments, setComments] = useState<string[]>(
    post.preview ? [post.preview] : [],
  );
  const saved = state.savedPostIds.includes(post.id);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const value = comment.trim();
    if (!value) return;
    setComments((items) => [
      ...items,
      `${state.profile.name || "我"}：${value}`,
    ]);
    setComment("");
    notify("评论已发布");
  };
  return (
    <main className="v277-page v278-social-detail">
      <AppHeader
        title="讨论详情"
        subtitle={`社区 · ${post.date}`}
        onBack={onBack}
        right={
          <IconButton label="分享讨论" onClick={() => notify("帖子链接已复制")}>
            <Share2 size={19} />
          </IconButton>
        }
      />
      <article className="v278-social-article">
        <header>
          <i
            className={`v277-social-avatar avatar-${post.avatar} v277-sprite-community`}
          />
          <span>
            <b>{post.name}</b>
            <small>
              <BadgeCheck size={14} />
              社区成员
            </small>
          </span>
        </header>
        <p>{post.text}</p>
        {post.gallery && (
          <div className="v277-social-gallery v278-detail-gallery">
            <i className="gallery-one v277-sprite-community" />
            <i className="gallery-two v277-sprite-community" />
            <i className="gallery-three v277-sprite-community" />
          </div>
        )}
        <div className="v278-social-metrics">
          <button
            type="button"
            className={liked ? "liked" : ""}
            onClick={() => setLiked((value) => !value)}
          >
            <Heart size={21} fill={liked ? "currentColor" : "none"} />
            {post.likes + (liked ? 1 : 0)}
          </button>
          <button
            type="button"
            onClick={() =>
              document.getElementById("community-comment")?.focus()
            }
          >
            <MessageCircle size={21} />
            {comments.length || post.comments}
          </button>
          <button
            type="button"
            aria-label={saved ? "取消收藏" : "收藏讨论"}
            onClick={() => {
              setState((current) => ({
                ...current,
                savedPostIds: saved
                  ? current.savedPostIds.filter((id) => id !== post.id)
                  : [...current.savedPostIds, post.id],
              }));
              notify(saved ? "已取消收藏" : "帖子已收藏");
            }}
          >
            <Bookmark size={21} fill={saved ? "currentColor" : "none"} />
          </button>
        </div>
      </article>
      <section className="v278-comment-list">
        <h2>
          评论 <small>{comments.length || post.comments}</small>
        </h2>
        {comments.length ? (
          comments.map((item, index) => (
            <article key={`${item}-${index}`}>
              <i className="v277-comment-avatar v277-sprite-community" />
              <p>{item}</p>
            </article>
          ))
        ) : (
          <div className="v277-empty">
            <MessageCircle size={22} />
            <b>还没有评论</b>
            <p>说说你对这条讨论的看法。</p>
          </div>
        )}
      </section>
      <form className="v278-comment-composer" onSubmit={submit}>
        <input
          id="community-comment"
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          placeholder="期待你的评论…"
          aria-label="发表评论"
        />
        <button type="submit" disabled={!comment.trim()}>
          <Send size={18} />
        </button>
      </form>
    </main>
  );
}

export function MyToolsPage({
  go,
  onBack,
}: {
  go: (screen: Screen) => void;
  onBack: () => void;
}) {
  const runtime=useRuntime();
  const [tab, setTab] = useState<"Skill" | "Mini App" | "Agent">("Skill");
  const tools = [
    {
      title: "任务简报",
      copy: "把一个目标整理成可执行任务",
      icon: ListChecks,
      action: () => go({ name: "new-task" }),
    },
    {
      title: "知识检索",
      copy: "从已沉淀知识中查找方法",
      icon: BookOpen,
      action: () => go({ name: "knowledge" }),
    },
    {
      title: "机会扫描",
      copy: "由探索 Agent 继续查找信息",
      icon: Compass,
      action: () => go({ name: "agent", id: "explore" }),
    },
    {
      title: "快速对话",
      copy: "把临时想法交给 Elfred",
      icon: MessageCircle,
      action: () => go({ name: "chat", id: "elfred" }),
    },
  ];
  if(runtime)return <main className="v277-page v278-utility-page"><AppHeader title="我的工具" onBack={onBack}/><MethodsPanel go={go}/></main>;
  return (
    <main className="v277-page v281-tools-page">
      <header>
        <button type="button" aria-label="返回" onClick={onBack}>
          <ArrowLeft size={26} />
        </button>
        <h1>我的工具</h1>
      </header>
      <nav className="v281-tools-tabs">
        {(["Skill", "Mini App", "Agent"] as const).map((item) => (
          <button
            type="button"
            key={item}
            className={tab === item ? "active" : ""}
            onClick={() => setTab(item)}
          >
            {item}
          </button>
        ))}
      </nav>
      <section className="v281-recent-tools">
        <header>
          <h2>最近使用</h2>
          <button type="button">
            查看全部
            <ChevronRight size={18} />
          </button>
        </header>
        <button
          type="button"
          className="v281-recent-card"
          onClick={tools[0].action}
        >
          <span>
            <ListChecks size={28} />
          </span>
          <div>
            <h3>任务简报</h3>
            <p>把一个目标整理成可执行任务</p>
            <small>
              <i />
              最近使用
            </small>
          </div>
          <em>
            <i />
            <i />
            <i />
          </em>
        </button>
      </section>
      <section className="v281-all-tools">
        <h2>全部工具</h2>
        <div>
          {tools.map(({ title, copy, icon: Icon, action }) => (
            <button type="button" key={title} onClick={action}>
              <span>
                <Icon size={27} />
              </span>
              <h3>{title}</h3>
              <p>{copy}</p>
              <ChevronRight size={20} />
            </button>
          ))}
        </div>
      </section>
      <div className="v278-tools-home">
        <button
          type="button"
          className="v281-tools-collapse"
          aria-label="收起我的工具"
          onClick={onBack}
        >
          <ChevronDown size={28} />
        </button>
        <span>回到首页</span>
      </div>
    </main>
  );
}

export function CreateToolPage({
  onBack,
  notify,
}: {
  onBack: () => void;
  notify: (text: string) => void;
}) {
  const [tab, setTab] = useState<"Skill" | "Mini App" | "Agent">("Skill");
  const [description, setDescription] = useState("");
  const [toolName, setToolName] = useState("自动生成");
  const [source, setSource] = useState("未选择");
  const [scope, setScope] = useState("仅自己");
  return (
    <main className="v277-page v281-create-tool">
      <header>
        <button type="button" aria-label="返回知识库" onClick={onBack}>
          <ArrowLeft size={27} />
        </button>
        <span>
          <h1>创建工具</h1>
        </span>
      </header>
      <nav className="v281-create-tabs">
        {(["Skill", "Mini App", "Agent"] as const).map((item) => (
          <button
            type="button"
            key={item}
            className={tab === item ? "active" : ""}
            onClick={() => setTab(item)}
          >
            {item}
          </button>
        ))}
      </nav>
      <section className="v281-tool-prompt">
        <h2>描述你的工具</h2>
        <textarea
          autoFocus
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="例如：把用户访谈整理成洞察，并生成后续任务"
        />
        <footer>
          <button type="button" onClick={() => notify("选择要引用的知识")}>
            <Layers3 size={22} />
            引用知识库
          </button>
          <button
            type="button"
            aria-label="语音输入"
            onClick={() => notify("语音输入已准备")}
          >
            <Mic size={24} />
          </button>
        </footer>
      </section>
      <section className="v281-tool-settings">
        <h2>基础设置</h2>
        <div>
          <SettingDropdown
            icon={FileText}
            label="工具名称"
            value={toolName}
            options={["自动生成", "自定义名称", "沿用描述标题"]}
            onSelect={setToolName}
          />
          <SettingDropdown
            icon={Layers3}
            label="知识来源"
            value={source}
            options={["未选择", "访谈知识库", "产品知识库"]}
            onSelect={setSource}
          />
          <SettingDropdown
            icon={Users}
            label="使用范围"
            value={scope}
            options={["仅自己", "团队可用", "公开分享"]}
            onSelect={setScope}
          />
        </div>
      </section>
      <footer className="v281-create-tool-footer">
        <button
          type="button"
          disabled={!description.trim()}
          onClick={() => {
            notify(`${tab} 已创建`);
            onBack();
          }}
        >
          创建 {tab}
        </button>
      </footer>
    </main>
  );
}

export function UtilityPage({
  kind,
  go,
  onBack,
  notify,
}: {
  kind:
    | "tools"
    | "notifications"
    | "add-friend"
    | "ability"
    | "relationships"
    | "level"
    | "honors";
  go: (screen: Screen) => void;
  onBack: () => void;
  notify: (text: string) => void;
}) {
  const runtime=useRuntime();
  const [contact, setContact] = useState("");
  // 关系图读我方 /page2/relationships（后端没有就如实空着，不摆写死的三个人）
  const [relationships, setRelationships] = useState<LiveRelationship[] | null>(null);
  useEffect(() => {
    if (kind !== "relationships") return;
    let alive = true;
    void fetchRelationships().then((result) => {
      if (alive && result?.relationships) setRelationships(result.relationships);
    });
    return () => {
      alive = false;
    };
  }, [kind]);
  const definitions = {
    tools: {
      title: "Skill 与 Mini App",
      subtitle: "已启用的工具",
      items: [
        {
          title: "任务简报",
          copy: "把一个目标整理成可执行任务",
          icon: ListChecks,
          action: () => go({ name: "tasks" }),
        },
        {
          title: "知识检索",
          copy: "从已沉淀知识中查找方法",
          icon: BookOpen,
          action: () => go({ name: "knowledge" }),
        },
        {
          title: "机会扫描",
          copy: "由探索 Agent 继续查找信息",
          icon: Compass,
          action: () => go({ name: "agent", id: "explore" }),
        },
        {
          title: "快速对话",
          copy: "把临时想法交给 Elfred",
          icon: MessageCircle,
          action: () => go({ name: "chat", id: "elfred" }),
        },
      ],
    },
    notifications: {
      title: "通知",
      subtitle: "需要你关注的更新",
      items: [
        {
          title: "有 2 项任务待确认",
          copy: "确认后 Agent 才会继续推进",
          icon: ListChecks,
          action: () => go({ name: "tasks" }),
        },
        {
          title: "社区讨论有新回复",
          copy: "查看林野发起的讨论",
          icon: MessageCircle,
          action: () =>
            go({ name: "community-post", id: "social-entry-design" }),
        },
        {
          title: "能力卡新增 2 条证据",
          copy: "来自今天的用户访谈与产品审阅",
          icon: Sparkles,
          action: () => go({ name: "utility", kind: "ability" }),
        },
      ],
    },
    ability: {
      title: "能力洞察",
      subtitle: "来自真实任务与结果",
      items: [
        {
          title: "策略 · 91",
          copy: "能围绕目标比较方案并给出取舍",
          icon: Lightbulb,
          action: () => go({ name: "knowledge-detail", id: "decision" }),
        },
        {
          title: "洞察 · 88",
          copy: "能从访谈中识别稳定的用户卡点",
          icon: Compass,
          action: () => go({ name: "knowledge-detail", id: "interview" }),
        },
        {
          title: "创作 · 84",
          copy: "已形成简洁、结果导向的表达偏好",
          icon: PenLine,
          action: () => go({ name: "knowledge-detail", id: "copy" }),
        },
        {
          title: "执行 · 76",
          copy: "任务完成后会继续更新能力评分",
          icon: CheckCircle2,
          action: () => go({ name: "tasks" }),
        },
      ],
    },
    relationships: {
      title: "关键关系",
      subtitle: "基于已确认的社交记忆",
      items: [
        {
          title: "Mia · 产品共创",
          copy: "最近一次联系：昨天",
          icon: UserRound,
          action: () => go({ name: "chat", id: "person-mia" }),
        },
        {
          title: "Kevin · 技术合作",
          copy: "最近一次联系：3 天前",
          icon: UserRound,
          action: () => go({ name: "chat", id: "person-kevin" }),
        },
        {
          title: "Lena · 市场增长",
          copy: "最近一次联系：本周",
          icon: UserRound,
          action: () => go({ name: "chat", id: "person-lena" }),
        },
      ],
    },
    level: {
      title: "等级展示",
      subtitle: "当前处于对齐期 · Lv.4",
      items: [
        {
          title: "Lv.4 · 偏好模型形成中",
          copy: "已确认 12 项稳定偏好与 3 个当前目标",
          icon: Layers3,
          action: () => go({ name: "memory" }),
        },
        {
          title: "距离 Lv.5 还有 2 项反馈",
          copy: "完成一次建议纠正与一次任务结果确认",
          icon: CheckCircle2,
          action: () => go({ name: "tasks" }),
        },
        {
          title: "Lv.6 · 懂你",
          copy: "解锁稳定预测、主动推荐和更少重复确认",
          icon: Sparkles,
          action: () => go({ name: "profile" }),
        },
      ],
    },
    honors: {
      title: "荣誉勋章",
      subtitle: "由真实任务与结果解锁",
      items: [
        {
          title: "首次闭环",
          copy: "完成从内容发现到任务交付的完整流程",
          icon: BadgeCheck,
          action: () => go({ name: "tasks" }),
        },
        {
          title: "持续对齐",
          copy: "连续 7 天确认目标、偏好与任务结果",
          icon: Sparkles,
          action: () => go({ name: "memory" }),
        },
        {
          title: "高质量反馈",
          copy: "累计完成 10 次有效纠正与原因说明",
          icon: MessageCircle,
          action: () => go({ name: "profile" }),
        },
      ],
    },
  } as const;
  // 勋章和关系图这两屏以我方为准（第二页/第四页是负责人 B 的域），其余继续走同事的 ConnectedUtility。
  if(runtime&&kind!=='honors'&&kind!=='relationships')
    return <ConnectedUtility kind={kind} go={go} onBack={onBack}/>;
  if (kind === "add-friend")
    return (
      <main className="v277-page v278-utility-page">
        <AppHeader
          title="添加联系人"
          subtitle="先确认身份，再开始联系"
          onBack={onBack}
        />
        <section className="v278-utility-form">
          <span>
            <UserPlus size={24} />
          </span>
          <h2>搜索手机号或邮箱</h2>
          <p>这里只创建一条模拟联系人记录，不会发送外部邀请。</p>
          <label className="v277-field">
            <span>联系方式</span>
            <input
              autoFocus
              value={contact}
              onChange={(event) => setContact(event.target.value)}
              placeholder="手机号或 name@example.com"
            />
          </label>
          <button
            type="button"
            className="v277-primary"
            disabled={!contact.trim()}
            onClick={() => {
              notify("联系人邀请草稿已保存");
              onBack();
            }}
          >
            保存邀请草稿
          </button>
        </section>
      </main>
    );
  const page = definitions[kind];
  // 关系人走后端；勋章走 HonorGallery（它和第二页"理解度"里那一栏是同一个组件）
  const items =
    kind === "relationships" && relationships
      ? relationships.map((person) => ({
          title: person.role ? `${person.name} · ${person.role}` : person.name,
          copy: person.stage || "已确认的关系",
          icon: UserRound,
          action: () => go({ name: "chat", id: person.chatId }),
        }))
      : page.items;
  return (
    <main className="v277-page v278-utility-page">
      <AppHeader title={page.title} subtitle={page.subtitle} onBack={onBack} />
      {kind === "honors" ? <HonorGallery compact /> : null}
      {/* 真数据为空时不要画一个空框，让下面那句说明去讲 */}
      {items.length > 0 ? (
        <section className="v278-utility-list">
          {items.map(({ title, copy, icon: Icon, action }) => (
            <button type="button" key={title} onClick={action}>
              <span>
                <Icon size={21} />
              </span>
              <div>
                <b>{title}</b>
                <p>{copy}</p>
              </div>
              <ChevronRight size={19} />
            </button>
          ))}
        </section>
      ) : null}
      <aside className="v278-utility-note">
        <BadgeCheck size={18} />
        <p>
          {kind === "tools"
            ? "所有工具均遵循同一权限边界：外部发送、发布和删除前必须再次确认。"
            : kind === "notifications"
              ? "这里只显示与你当前目标或任务直接相关的提醒。"
              : kind === "ability"
                ? "评分来自完成的任务和已确认结果，不以使用次数代替能力。"
                : kind === "level"
                  ? "等级代表理解与可托付程度，不以单纯使用次数升级。"
                  : kind === "honors"
                    ? "勋章只记录已经发生且能够被验证的成长。"
                    : kind === "relationships" && relationships?.length === 0
                      ? "还没有已确认的关系。它只从你确认过的记忆里来，不会替你去联系任何人。"
                      : "关系信息只使用你已确认的记忆，不会自动代表你联系任何人。"}
        </p>
      </aside>
    </main>
  );
}

export function ProfileShareSheet({
  state,
  setState,
  onClose,
  notify,
}: {
  state: V277State;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
  onClose: () => void;
  notify: (text: string) => void;
}) {
  const runtime=useRuntime();
  const startY = useRef(0);
  // 空态：没设置过就留空，不拿演示身份顶上（用户名没填就不渲染 @ 那一行）
  const name = state.profile.name || "还没有名字";
  const handle = state.profile.username.replace(/^@/, "");
  const share = async (channel: string) => {
    if(runtime&&state.profileVisibility!=='public'){notify('请先确认公开称呼和简介');return;}
    if(runtime&&channel==='生成海报'){notify('请使用复制链接或系统分享');return;}
    const shareData = {
      title: `${name} 的 Elfred 主页`,
      text: `${state.profile.role || "尚未填写职业"} · Elfred 公开主页`,
      url: runtime?window.location.origin+"/u/"+encodeURIComponent(handle):window.location.origin + window.location.pathname,
    };
    if (channel === "微信好友" || channel === "朋友圈") {
      try {
        if (navigator.share) {
          await navigator.share(shareData);
          return;
        }
      } catch {
        return;
      }
    }
    try {
      await navigator.clipboard.writeText(`${shareData.text}\n${shareData.url}`);
    } catch {notify("复制失败，请重试");return;}
    notify(channel === "生成海报" ? "主页海报已生成" : "公开主页链接已复制");
  };
  const visibility = [
    ["public", "所有人可见"],
    ["contacts", "仅联系人可见"],
    ["private", "仅自己可见"],
  ] as const;
  return (
    <RootPortal>
      <button
        type="button"
        className="v278-sheet-backdrop v279-profile-share-backdrop"
        aria-label="关闭分享个人主页"
        onClick={onClose}
      />
      <section
        className="v279-profile-share-sheet"
        role="dialog"
        aria-modal="true"
        aria-label="分享个人主页"
        onTouchStart={(event) => {
          startY.current = event.touches[0]?.clientY || 0;
        }}
        onTouchEnd={(event) => {
          if ((event.changedTouches[0]?.clientY || 0) - startY.current > 72)
            onClose();
        }}
      >
        <i className="v278-sheet-handle" />
        <header className="v279-sheet-title">
          <h2>分享个人主页</h2>
          <IconButton label="关闭" onClick={onClose}>
            <X size={20} />
          </IconButton>
        </header>
        <section className="v279-share-card">
          {/* 没设头像就是中性底（示例人像已经不再当默认值） */}
          <i className="v279-owner-avatar" />
          <span>
            <b>{name}</b>
            {handle ? <small>@{handle}</small> : null}
            <p>{state.profile.role || "尚未填写职业"}</p>
          </span>
          <QrCode size={68} strokeWidth={2.1} />
        </section>
        <section className="v279-share-methods">
          <h3>分享至</h3>
          <div>
            {[
              ["微信好友", MessageCircle],
              ["朋友圈", Users],
              ["复制链接", Copy],
              ["生成海报", FileText],
            ].map(([label, Icon]) => (
              <button
                type="button"
                key={label as string}
                onClick={() => void share(label as string)}
              >
                <span>
                  <Icon size={22} />
                </span>
                <small>{label as string}</small>
              </button>
            ))}
          </div>
        </section>
        <section className="v279-share-visibility">
          <h3>主页可见范围</h3>
          <div>
            {visibility.map(([value, label]) => (
              <button
                type="button"
                key={value}
                className={state.profileVisibility === value ? "active" : ""}
                onClick={() => {if(runtime?.snapshot){if(value==="contacts"){notify("联系人可见尚未开放，请选择公开或仅自己");return;}void runtime.command("profile.publish",{...entityRef(runtime.snapshot.objects.profile[0]),confirm:true,publish:value==="public"}).catch(()=>{});return;}
                  setState((current) => ({
                    ...current,
                    profileVisibility: value,
                  }));}
                }
              >
                <span>{label}</span>
                <i>{state.profileVisibility === value && <Check size={15} />}</i>
              </button>
            ))}
          </div>
        </section>
        <p className="v279-share-note">
          只分享公开主页资料，不包含私人记忆、任务和对话。
        </p>
      </section>
    </RootPortal>
  );
}


export function ProfileEditPage({
  state,
  setState,
  onBack,
  notify,
}: {
  state: V277State;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
  onBack: () => void;
  notify: (text: string) => void;
}) {
  const runtime=useRuntime();
  const [profile, setProfile] = useState(state.profile);
  const [coverUrl, setCoverUrl] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");
  const dirty =
    JSON.stringify(profile) !== JSON.stringify(state.profile) ||
    Boolean(coverUrl || avatarUrl);
  const loadPreview = (
    event: ChangeEvent<HTMLInputElement>,
    type: "cover" | "avatar",
  ) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if(runtime){if(file.size>250000){notify('图片需小于 250 KB，支持 PNG、JPEG、WebP');return;}const reader=new FileReader();reader.onload=()=>{const data=String(reader.result);if(type==='cover')setCoverUrl(data);else setAvatarUrl(data)};reader.readAsDataURL(file);return;}
    const url = URL.createObjectURL(file);
    if (type === "cover") setCoverUrl(url);
    else setAvatarUrl(url);
  };
  const save = () => {
    if(runtime?.snapshot){void runtime.command('profile.save',{...entityRef(runtime.snapshot.objects.profile[0]),...profile,...(coverUrl?{cover:coverUrl}:{}),...(avatarUrl?{avatar:avatarUrl}:{})}).then(()=>{notify('个人资料已保存');onBack()}).catch(()=>{});return;}
    const memories: V277Memory[] = [
      profile.name && {
        id: "profile-name",
        group: "基础",
        label: "称呼",
        value: profile.name,
        source: "个人资料",
        status: "已确认",
      },
      profile.role && {
        id: "profile-role",
        group: "基础",
        label: "当前角色",
        value: profile.role,
        source: "个人资料",
        status: "已确认",
      },
      profile.focus && {
        id: "profile-focus",
        group: "习惯",
        label: "当前重点",
        value: profile.focus,
        source: "首次目标",
        status: "已确认",
      },
    ].filter(Boolean) as V277Memory[];
    setState((current) => ({
      ...current,
      profile,
      memories: [
        ...memories,
        ...current.memories.filter((item) => !item.id.startsWith("profile-")),
      ],
    }));
    notify("个人资料已更新");
    onBack();
  };
  return (
    <main className="v277-page v278-profile-edit-page v279-profile-edit-page">
      <AppHeader
        title="编辑资料"
        onBack={onBack}
        right={
          <button
            type="button"
            className={`v279-header-save${dirty ? " active" : ""}`}
            disabled={!dirty}
            onClick={save}
          >
            保存
          </button>
        }
      />
      <section className="v279-profile-visual-editor">
        <h2>主页形象</h2>
        <div
          className="v279-profile-cover"
          style={
            coverUrl
              ? ({ "--v279-cover-image": `url(${coverUrl})` } as CSSProperties)
              : undefined
          }
        >
          <label>
            <Camera size={17} />
            更换封面
            <input
              type="file"
              accept="image/*"
              onChange={(event) => loadPreview(event, "cover")}
            />
          </label>
        </div>
        <div className="v279-profile-avatar-row">
          <i
            className="v279-owner-avatar"
            style={
              {
                "--v279-avatar-image": avatarUrl
                  ? `url(${avatarUrl})`
                  : "none",
              } as CSSProperties
            }
          />
          <label>
            更换头像
            <input
              type="file"
              accept="image/*"
              onChange={(event) => loadPreview(event, "avatar")}
            />
          </label>
        </div>
      </section>
      <section className="v279-profile-form-section">
        <h2>个人信息</h2>
        <label>
          <span>昵称</span>
          <input
            value={profile.name}
            onChange={(event) =>
              setProfile({ ...profile, name: event.target.value })
            }
            placeholder="还没有设置"
          />
        </label>
        <label>
          <span>用户名</span>
          <div className="v279-username-field">
            <b>@</b>
            <input
              value={profile.username.replace(/^@/, "")}
              readOnly={Boolean(runtime)}
              onChange={(event) =>
                setProfile({
                  ...profile,
                  username: event.target.value.replace(/^@/, ""),
                })
              }
              placeholder="还没有设置"
            />
          </div>
        </label>
        <label>
          <span>个人简介</span>
          <textarea
            value={profile.bio}
            onChange={(event) =>
              setProfile({ ...profile, bio: event.target.value })
            }
            maxLength={64}
            placeholder="你是谁、擅长什么、正在做什么"
          />
        </label>
        <label>
          <span>领域标签</span>
          <input
            value={profile.tags.join("、")}
            onChange={(event) =>
              setProfile({
                ...profile,
                tags: event.target.value
                  .split(/[、,，]/)
                  .map((tag) => tag.trim())
                  .filter(Boolean)
                  .slice(0, 4),
              })
            }
            placeholder="用「、」分隔，最多 4 个"
          />
        </label>
      </section>
      <section className="v279-profile-display-section">
        <h2>主页展示</h2>
        <button
          type="button"
          onClick={() =>
            setProfile({ ...profile, showLevel: !profile.showLevel })
          }
        >
          <span>
            <b>展示等级与能力</b>
            <small>{runtime?"在本人主页展示理解状态，不生成虚构等级":"在公开主页显示当前等级和能力卡"}</small>
          </span>
          <i className={profile.showLevel ? "on" : ""}>
            <em />
          </i>
        </button>
      </section>
    </main>
  );
}

export function SettingsPage({
  state,
  go,
  setState,
  logout,
}: {
  state: V277State;
  go: (screen: Screen) => void;
  setState: React.Dispatch<React.SetStateAction<V277State>>;
  logout: () => void;
}) {
  const runtime=useRuntime();
  const [active, setActive] = useState<
    | "account"
    | "understanding"
    | "data"
    | "notifications"
    | "privacy"
    | "appearance"
    | "help"
    | null
  >(null);
  const [logoutOpen, setLogoutOpen] = useState(false);
  // 空态：没设置过就留空（不再拿演示身份顶上）
  const name = state.profile.name || "还没有名字";
  const handle = state.profile.username.replace(/^@/, "");
  // 理解度那行用后端真数；后端还没给就说"还没有评估"，不摆写死的 86%
  const alignmentValue = hasLiveAlignment
    ? `${libraryHeader.alignment}% · Lv.${libraryHeader.level}`
    : "还没有评估";
  const groups = [
    {
      title: "个人与 Elfred",
      rows: [
        ["account", "账号与安全", ShieldCheck, "手机号与登录方式"],
        ["understanding", "Elfred 对我的理解", MemoryStick, alignmentValue],
        ["data", "数据与权限", Database, "已确认内容优先"],
      ],
    },
    {
      title: "使用偏好",
      rows: [
        ["notifications", "通知", Bell, state.notifications ? "已开启" : "已关闭"],
        ["privacy", "隐私", ShieldCheck, "始终询问"],
        ["appearance", "外观", Palette, "浅色"],
      ],
    },
  ] as const;
  const settingTitle = {
    account: "账号与安全",
    understanding: "Elfred 对我的理解",
    data: "数据与权限",
    notifications: "通知",
    privacy: "隐私",
    appearance: "外观",
    help: "帮助与反馈",
  };
  return (
    <main className="v277-page v279-settings-page">
      <AppHeader title="设置" onBack={() => go({ name: "profile" })} />
      <button
        type="button"
        className="v279-settings-profile"
        onClick={() => go({ name: "profile-edit" })}
      >
        {/* 没设头像就是中性底（示例人像已经不再当默认值） */}
        <i className="v279-owner-avatar" />
        <span>
          <b>{name}</b>
          {handle ? <small>@{handle}</small> : null}
        </span>
        <ChevronRight size={20} />
      </button>
      {groups.map((group) => (
        <section className="v279-settings-group" key={group.title}>
          <h2>{displayTitle(group.title,'')}</h2>
          <div>
            {group.rows.map(([key, label, Icon, value]) => (
              <button
                type="button"
                key={key}
                onClick={() => setActive(key)}
              >
                <span>
                  <Icon size={21} />
                </span>
                <b>{label}</b>
                <small>{value}</small>
                <ChevronRight size={18} />
              </button>
            ))}
          </div>
        </section>
      ))}
      <button
        type="button"
        className="v279-settings-help"
        onClick={() => setActive("help")}
      >
        <span>
          <HelpCircle size={21} />
        </span>
        <b>帮助与反馈</b>
        <ChevronRight size={18} />
      </button>
      <button
        type="button"
        className="v279-settings-logout"
        onClick={() => setLogoutOpen(true)}
      >
        退出登录
      </button>
      <p className="v279-version">Elfred V28</p>
      {active && (
        <RootPortal>
          <button
            type="button"
            className="v278-sheet-backdrop"
            aria-label="关闭设置选项"
            onClick={() => setActive(null)}
          />
          <section className="v279-setting-sheet" role="dialog" aria-modal="true">
            <i className="v278-sheet-handle" />
            <header className="v279-sheet-title">
              <h2>{settingTitle[active]}</h2>
              <IconButton label="关闭" onClick={() => setActive(null)}>
                <X size={20} />
              </IconButton>
            </header>
            {runtime?<ConnectedSettings active={active} go={go}/>:active === "notifications" ? (
              <button
                type="button"
                className="v279-setting-toggle"
                onClick={() =>
                  setState((current) => ({
                    ...current,
                    notifications: !current.notifications,
                  }))
                }
              >
                <span>
                  <b>任务与消息提醒</b>
                  <small>只提醒需要确认或已经完成的事项</small>
                </span>
                <i className={state.notifications ? "on" : ""}>
                  <em />
                </i>
              </button>
            ) : active === "privacy" ? (
              <div className="v279-setting-options">
                {["始终询问", "仅外部操作询问"].map((option, index) => (
                  <button type="button" key={option}>
                    <span>
                      <b>{option}</b>
                      <small>
                        {index === 0
                          ? "发送、发布、删除、付费与邀请前都需确认"
                          : "只在影响外部对象时进行二次确认"}
                      </small>
                    </span>
                    <i>{index === 0 && <Check size={15} />}</i>
                  </button>
                ))}
              </div>
            ) : active === "appearance" ? (
              <div className="v279-setting-options">
                {["浅色", "跟随系统"].map((option, index) => (
                  <button type="button" key={option}>
                    <span>
                      <b>{option}</b>
                      <small>{index === 0 ? "当前 V28 视觉" : "使用设备外观设置"}</small>
                    </span>
                    <i>{index === 0 && <Check size={15} />}</i>
                  </button>
                ))}
              </div>
            ) : active === "understanding" ? (
              <div className="v279-setting-summary">
                {/* 原来写死 86% / Lv.4 —— 新用户点进来也这么显示，是假数据 */}
                <strong>{hasLiveAlignment ? `${libraryHeader.alignment}%` : "—"}</strong>
                <span>
                  {hasLiveAlignment
                    ? `当前理解度 · Lv.${libraryHeader.level}`
                    : "还没有评估"}
                </span>
                <p>来自已确认的个人资料、任务结果和记忆。待确认内容不会直接用于行动。</p>
                <button type="button" onClick={() => go({ name: "memory" })}>
                  查看记忆库
                </button>
              </div>
            ) : (
              <div className="v279-setting-options">
                {(active === "account"
                  ? ["手机号与登录方式", "登录设备"]
                  : active === "data"
                    ? ["已确认记忆", "外部操作权限"]
                    : ["提交产品反馈", "查看使用帮助"]
                ).map((option) => (
                  <button type="button" key={option}>
                    <span>
                      <b>{option}</b>
                      <small>
                        {active === "help"
                          ? "打开对应帮助入口"
                          : "查看和管理当前设置"}
                      </small>
                    </span>
                    <ChevronRight size={18} />
                  </button>
                ))}
              </div>
            )}
          </section>
        </RootPortal>
      )}
      {logoutOpen && (
        <RootPortal>
          <button
            type="button"
            className="v278-sheet-backdrop"
            aria-label="取消退出登录"
            onClick={() => setLogoutOpen(false)}
          />
          <section className="v279-logout-sheet" role="alertdialog" aria-modal="true">
            <i className="v278-sheet-handle" />
            <h2>确认退出登录？</h2>
            <p>当前浏览器中的任务、记忆与设置仍会保留。</p>
            <div>
              <button type="button" onClick={() => setLogoutOpen(false)}>
                取消
              </button>
              <button type="button" onClick={logout}>
                确认退出
              </button>
            </div>
          </section>
        </RootPortal>
      )}
    </main>
  );
}

