"use client";

// 第二页/第四页**仅剩的本地状态**：一处"跳页时的交接条"。
//
//   · pendingCard  从成果页点卡名过来 → 到能力库自动打开那张卡（读一次就清）
//
// （原来还有一个 pendingSkill：点了「用它做一件事」时把卡名存这儿、指望对话页来取。
//   对话页从来没读过它，而且现在整张卡是随 Screen 参数带过去的，这条死交接已删除。）
//
// 为什么这里只剩这两件：以前这里还存过"成果裁定 / 知识固化出来的卡 / 手动升级的等级 /
// 待确认素材"——那些都是**产品状态**，本该由服务端算（而且确实有服务端那份），存在浏览器里
// 等于两份真相：换台设备就没了，后端也不知道，界面上的分数还会和它对不上。
// 现在这些一律以后端为准，这个文件只管"跨页传个名字"。

import { getPage2User } from "./page2-api";

type Page2Store = {
  /** 从成果页点卡名过来时，要自动打开哪张卡（打开一次就清掉） */
  pendingCard: string | null;
};

const KEY = "elfred.page2.v3";
const storageKey = () => getPage2User() ? `${KEY}.${getPage2User()}` : null;
const EMPTY: Page2Store = { pendingCard: null };

function readPage2(): Page2Store {
  if (typeof window === "undefined") return EMPTY;
  try {
    const key = storageKey();
    if (!key) return EMPTY;
    const raw = window.localStorage.getItem(key);
    if (!raw) return EMPTY;
    return { ...EMPTY, ...(JSON.parse(raw) as Partial<Page2Store>) };
  } catch {
    return EMPTY;
  }
}

function writePage2(next: Page2Store) {
  if (typeof window === "undefined") return;
  const key = storageKey();
  if (key) window.localStorage.setItem(key, JSON.stringify(next));
}

export function setPendingCard(title: string) {
  writePage2({ ...readPage2(), pendingCard: title });
}

/** 读一次就清掉：读完之后回到这一页不会又自动弹出来 */
export function takePendingCard() {
  const store = readPage2();
  if (!store.pendingCard) return null;
  writePage2({ ...store, pendingCard: null });
  return store.pendingCard;
}
