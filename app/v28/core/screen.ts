import type { V277AgentId } from "../../v27-7-state";

export type Screen =
  | {
      name:
        | "home"
        | "agents"
        | "feed"
        | "knowledge"
        | "memory"
        | "messages"
        | "profile"
        | "community"
        | "settings"
        | "player"
        | "highlights"
        | "profile-edit"
        | "profile-share"
        | "search"
        | "new-task"
        | "onboarding-chat"
        | "my-tools"
        | "inbox"
        | "swarm";
    }
  | { name: "tasks"; view?: "today" | "projects" }
  | {name:"create-tool";id?:string}
  | {name:"tool-detail";id:string}
  | { name: "post"; id: string }
  | { name: "feed-detail"; id: string }
  | { name: "community-post"; id: string }
  | { name: "task"; id: string }
  | { name: "agent"; id: V277AgentId; conversationId?:string; messageId?:string }
  | { name: "agent-level"; id: V277AgentId }
  | { name: "daily-brief"; kind: "morning" | "noon" | "evening" }
  | { name: "agent-moments"; id: V277AgentId }
  | { name: "agent-moment-detail"; id: V277AgentId; postId: string }
  | { name: "agent-settings"; id: V277AgentId }
  // attach：从能力卡点「用它做一件事」带进对话的那张卡的说明书（界面把它挂成输入框上方的附件，
  // 输入框本身留给用户自己写话）。prefill 仍然只用于"把一句话放进输入框"。
  | { name: "chat"; id: string; messageId?:string; prefill?:string; attach?:{ id: string; title: string; text: string; ask: string } }
  | { name: "friend-profile"; id: string }
  | {name:'search-source';id:string;anchor?:string}
  | { name: "knowledge-detail"; id: string; anchor?:string }
  | { name: "memory-detail"; id: string }
  // 第二页（负责人 B）的四个二级屏
  | { name: "evidence" }
  | { name: "evidence-detail"; id: string }
  | { name: "dimension"; id: string }
| { name: "ability-profile" }
| { name: "questionnaire" }
  | {
      name: "utility";
      kind:
        | "tools"
        | "notifications"
        | "add-friend"
        | "ability"
        | "relationships"
        | "level"
        | "honors";
    };

export type Navigate = (screen: Screen) => void;
