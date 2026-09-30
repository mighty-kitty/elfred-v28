"use client";

import { ArrowLeft } from "lucide-react";
import type { Screen } from "../../core/screen";
import { PrivateFeed } from "./private-feed";

export function ConnectedFeedPage({ go, onBack }: { go: (screen: Screen) => void; onBack: () => void }) {
  return <main className="v277-page v278-feed-page">
    <header className="v277-page-head"><button type="button" className="v277-icon-button" aria-label="返回" onClick={onBack}><ArrowLeft size={21}/></button><h1>Agent 朋友圈</h1></header>
    <PrivateFeed go={go} onDrag={() => {}} />
  </main>;
}
