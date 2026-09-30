"use client";

// 第二页/第四页的**运行时状态**：当前快照、当前用户、订阅者、以及喂给各数据层的"就地替换"回调。
//
// 只有这一个地方持有 activeSnapshot / activeCommand：动作层（page2-api.ts）从这里读，
// 数据层（data/*）通过 registerProjector 注册，页面通过 usePage2Live() 订阅。
// 以前这些和投影、动作混在一个 600 行文件里，改一处得通读全文。
import { useEffect, useSyncExternalStore } from "react";
import type { Snapshot } from "../../live/types";
import { projectSnapshot } from "./page2-projector";
import type { LiveCapability, Page2Data, Store } from "./page2-types";

/** 还没拿到快照时的空投影：各块都是 null，页面据此走各自的空态/降级 */
const EMPTY_DATA: Page2Data = {
  capabilities: null,
  todayEvidence: null,
  evidence: null,
  insight: null,
  alignment: null,
  memory: null,
  documents: null,
  pending: null,
  skills: null,
  forge: null,
};
const INITIAL: Store = { status: "loading", data: EMPTY_DATA, reason: "" };

let store: Store = INITIAL;
const listeners = new Set<() => void>();

// ── 当前用户 ────────────────────────────────────────────────────────────────
// 第二/四页的数据是**按用户分开存的**（`capabilities.user_id`、`memories.user_id`、
// `profile_settings.user_id`、skill 的 frontmatter `user_id`），所以每个请求都要说
// "我是谁"。这一层是普通模块，被知识页/个人页/记忆页共用，不能直接调 React hook ——
// 由 `core/page2-identity.tsx`（挂在 RuntimeProvider 里）把当前 handle 推下来。
// 空值 = 不带这个头，后端退回它自己的 `DEMO_USER_ID`（单用户本地跑时的旧行为）。
let activeUser = "";
let activeSnapshot: Snapshot | null = null;
let activeCommand: ((action: string, input: Record<string, unknown>) => Promise<unknown>) | null = null;

/** 当前快照（动作层用它取对象） */
export const currentSnapshot = () => activeSnapshot;
/** 当前命令通道（没登录时是 null，动作层据此如实报"请先登录"） */
export const currentCommand = () => activeCommand;

export function setPage2Runtime(snapshot: Snapshot | null, command: typeof activeCommand) {
  const nextUser = snapshot?.user.id ?? "";
  if (nextUser !== activeUser) {
    activeUser = nextUser;
    activeSnapshot = null;
    publish({ status: "loading", data: EMPTY_DATA, reason: "identity_changed" });
  }
  activeCommand = command;
  activeSnapshot = snapshot;
  if (snapshot) publish({ status: "ready", data: projectSnapshot(snapshot), reason: "shared_runtime" });
  else publish({ status: "loading", data: EMPTY_DATA, reason: "signed_out" });
}

export function getPage2User() {
  return activeUser;
}

export function setPage2User(handle: string | null | undefined) {
  if (!handle) setPage2Runtime(null, null);
}
/** 各数据层登记的"把真数据就地换上去"的函数：先换数据，再让 React 重渲染 */
const projectors: {
  data?: (data: Page2Data) => void;
  cards?: (cards: LiveCapability[]) => void;
}[] = [];

/** 订阅投影变化（`usePage2Live` 用它接进 React；页面不用直接调） */
function subscribePage2(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getPage2State() {
  return store;
}

/**
 * 全部拉一遍。任何一个接口挂了都不影响别的，页面缺哪块就退回哪块的演示数据。
 *
 * `loadSeq`：换用户时会有两次拉取在飞（换人前那次 + 换人后那次）。只有**最新**那次
 * 允许把结果写进 store —— 否则换人前那次晚回来，会把上一个人的数据盖在页面上（串号）。
 */

export function registerProjector(projector: { data?: (data: Page2Data) => void; cards?: (cards: LiveCapability[]) => void }) {
  projectors.push(projector);
  if (store.status !== "loading") projectors.forEach((p) => p.data?.(store.data));
}

function publish(next: Store) {
  store = next;
  // 只有真拿到数据（ready）才动各数据层；offline 时前端继续用演示数据，
  // 连"就地替换"都不做，免得把兜底那套算分逻辑关掉。
  if (next.status === "ready") {
    for (const projector of projectors) {
      try {
        projector.data?.(next.data);
      } catch (error) {
        console.warn("[page2] 数据层更新失败", error);
      }
    }
  }
  for (const listener of listeners) listener();
}

function publishCards(cards: LiveCapability[]) {
  for (const projector of projectors) {
    try {
      projector.cards?.(cards);
    } catch (error) {
      console.warn("[page2] 卡片更新失败", error);
    }
  }
  for (const listener of listeners) listener();
}

export async function loadPage2(force = false): Promise<Store> {
  void force;
  if (activeSnapshot) publish({ status: "ready", data: projectSnapshot(activeSnapshot), reason: "shared_runtime" });
  return store;
}

/** 裁定一条成果：后端会重算卡片分数与成果数，回来的卡直接盖上去 */

export function usePage2Live() {
  const state = useSyncExternalStore(
    subscribePage2,
    getPage2State,
    () => INITIAL,
  );
  useEffect(() => {
    void loadPage2();
  }, []);
  return state;
}

// ─────────────────────────────────────────────────────────────────────────────
// 第四页（我的/个人页）与记忆库的动作。
// 之前这两块**前端一行后端都没接**（编辑资料、动态、勋章、记忆体检/合并/取代/归档/反思全是本地状态），
// 后端接口是我们这边补的（见 `docs/前端闭环审查-20260924.md`）。这里把它们接上：
// 拿不到就返回 null，页面照旧退回演示数据并显式降级——不许假装成功。
// ─────────────────────────────────────────────────────────────────────────────
