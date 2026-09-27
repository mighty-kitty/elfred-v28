"use client";
import {entityTitle,objectNames} from './display-labels';

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { PageMemoryProvider } from './page-memory';
import {useBackSwipe} from './use-back-swipe';
import { RuntimeProvider, useRuntime, projectState, entityRef } from './runtime-context';
import { ConnectedProject, AssetEditor, InboxPage } from './runtime-panels';
import {OnboardingConversation} from '../features/home/onboarding-conversation';
import {SwarmPage} from '../features/home/swarm-page';
import {ToolsPage,ToolEditor} from '../features/home/tools-page';
import {AgentLevelPage} from '../features/home/agent-level-page';
import {SearchSourcePage} from '../features/home/search-source-page';
import {AgentConversationPage} from '../features/home/agent-conversation';
import { text as entityText,statuses as runtimeStatuses } from '../features/live/types';
import { Sparkles } from "lucide-react";
import { DeviceFrame } from "../../device-frame";
import { initialMessages } from "../../v27-7-data";
import {
  V277_STORAGE_KEY,
  createInitialV277State,
  restoreV277State,
  taskFromPost,
  type Post,
  type V277Memory,
  type V277State,
} from "../../v27-7-state";
import { HomePage } from "../features/home/home-page";
import { FeedDetailPage } from "../features/home/feed-detail-page";
import { EveningReflectionPage } from "../features/home/evening-reflection-page";
import {AbilityProfilePage,DimensionDetailPage,EvidenceDetailPage,EvidenceListPage,KnowledgeDetailPage,KnowledgePage,launchWithSkill,MemoryPage,ProfileEditPage,ProfilePage,QuestionnairePage,SettingsPage,setCardLevel} from "../features/pages24";
import { MessagesPage } from "../features/messages/messages-page";
import {Page2Identity} from "./page2-identity";
import type { Screen } from "./screen";
import {
  AgentExperiencePage,
  AgentInitPage,
  AgentMomentDetailPage,
  AgentMomentsPage,
  AgentSettingsPage,
  AgentsPage,
  BottomNav,
  ChatPage,
  CommunityPage,
  CommunityPostDetail,
  CreateToolPage,
  DailyBriefPage,
  FeedPage,
  FriendProfilePage,
  LoginPage,
  MemoryDetail,
  MyToolsPage,
  NewTaskPage,
  OnboardingComplete,
  OnboardingWelcome,
  PostDetail,
  ProfileInitPage,
  StatusBar,
  TaskDetail,
  TaskPlayerPage,
  TasksPage,
  Toast,
  TodayHighlights,
  UtilityPage,
  VerifyPage,
  communityPosts,
  demoTasks,
  v277Knowledge,
  v277Posts,
} from "../legacy/legacy-ui";

export default function ConnectedV28() { return <RuntimeProvider><Page2Identity/><V277App /></RuntimeProvider>; }

export function V277App() {
  const runtime=useRuntime();
  const [state, setLocalState] = useState<V277State>(createInitialV277State);
  const stateRef=useRef(state);
  useEffect(()=>{stateRef.current=state},[state]);
  const setState:React.Dispatch<React.SetStateAction<V277State>>=(update)=>{
    const previous=stateRef.current;
    const next=typeof update==='function'?update(previous):update;
    stateRef.current=next;setLocalState(next);
    if(!runtime?.snapshot)return;
    const snapshot=runtime.snapshot;
    const save=async()=>{
      if(JSON.stringify(previous.profile)!==JSON.stringify(next.profile)) await runtime.command('profile.save',{...entityRef(snapshot.objects.profile[0]),...next.profile});
      if(previous.profile.focus!==next.profile.focus) await runtime.command('onboarding.save',{...entityRef(snapshot.objects.onboarding[0]),intent:next.profile.focus});
      if(previous.notifications!==next.notifications||previous.quiet!==next.quiet) await runtime.command('settings.save',{...entityRef(snapshot.objects.settings[0]),notifications:next.notifications,quiet:next.quiet});
      for(const [id,config] of Object.entries(next.agentSetup))if(JSON.stringify(config)!==JSON.stringify(previous.agentSetup[id as keyof typeof previous.agentSetup])){
        const settings=await runtime.request<import('../features/live/types').Entity>('/objects/'+snapshot.objects.settings[0].id);
        await runtime.command('agent.preferences',{...entityRef(settings),system:id==='advisor'?'advise':id,...config,duty:config.name});
      }
    };
    void save().catch(()=>{});
  };
  const [ready, setReady] = useState(false);
  const [screen, setScreen] = useState<Screen>({ name: "home" });
  const [history, setHistory] = useState<Screen[]>([]);
  const root = useRef<HTMLDivElement>(null);
  const scrollPositions = useRef(new Map<string, number>());
  useLayoutEffect(() => { scrollPositions.current.clear(); }, [runtime?.snapshot?.user.id]);
  useLayoutEffect(() => {
    const page = root.current?.querySelector<HTMLElement>(':scope > .v277-page');
    if (page) page.scrollTop = scrollPositions.current.get(JSON.stringify(screen)) || 0;
  }, [screen, ready, state.phase]);
  const rememberScroll = () => {
    const page = root.current?.querySelector<HTMLElement>(':scope > .v277-page');
    if (page) scrollPositions.current.set(JSON.stringify(screen), page.scrollTop);
  };
  const [toast, setToast] = useState("");
  const openedLink=useRef(false);
  useEffect(()=>{
    if(openedLink.current||!runtime?.snapshot?.user)return;
    const post=new URLSearchParams(window.location.search).get('post');
    if(post&&/^[a-zA-Z0-9-]{1,100}$/.test(post))setScreen({name:'community-post',id:post});
    openedLink.current=true;
  },[runtime?.snapshot?.user.id]);

  useEffect(()=>{
    if(!runtime)return;
    setLocalState(previous=>projectState(runtime.snapshot,previous));
    setReady(!runtime.loading);
  },[runtime?.snapshot,runtime?.loading]);

  useEffect(() => {
    if(runtime)return;
    try {
      const params = new URLSearchParams(window.location.search);
      if (params.get("demo") === "1") {
        setState({
          ...createInitialV277State(),
          phase: "ready",
          account: {
            identifier: "harisen@example.com",
            provider: "contact",
            verified: true,
            onboardingComplete: true,
          },
          profile: {
            ...createInitialV277State().profile,
            name: "Harisen",
            username: "harisen",
            role: "产品经理与创业者",
            bio: "正在把 Personal Agent 做成真正懂你、能行动的数字伙伴。",
            focus: "完成 Elfred 移动端体验",
          },
          tasks: demoTasks,
          memories: [
            {
              id: "demo-focus",
              group: "习惯",
              label: "当前重点",
              value: "完成 Elfred 移动端体验",
              source: "今日计划",
              status: "已确认",
            },
          ],
        });
        const view = params.get("view");
        if (view === "login")
          setState((current) => ({
            ...current,
            phase: "auth",
            account: {
              ...current.account,
              verified: false,
              onboardingComplete: false,
            },
          }));
        else if (view === "verify")
          setState((current) => ({
            ...current,
            phase: "verify",
            account: {
              ...current.account,
              identifier: "harisen@example.com",
              verified: false,
              onboardingComplete: false,
            },
          }));
        else if (view === "welcome")
          setState((current) => ({ ...current, phase: "welcome" }));
        else if (view === "profile-init")
          setState((current) => ({ ...current, phase: "profile-init" }));
        else if (view === "agents-init")
          setState((current) => ({ ...current, phase: "agents-init" }));
        else if (view === "complete")
          setState((current) => ({ ...current, phase: "complete" }));
        else if (view === "morning")
          setScreen({ name: "daily-brief", kind: "morning" });
        else if (view === "noon")
          setScreen({ name: "daily-brief", kind: "noon" });
        else if (view === "evening")
          setScreen({ name: "daily-brief", kind: "evening" });
        else if (view === "agent")
          setScreen({ name: "agent", id: "explore" });
        else if (view === "history")
          setScreen({ name: "agent", id: "explore" });
        else if (view === "moments")
          setScreen({ name: "agent-moments", id: "explore" });
        else if (view === "moment-detail")
          setScreen({
            name: "agent-moment-detail",
            id: "explore",
            postId: "agent-moment-explore-0",
          });
        else if (view === "agent-settings")
          setScreen({ name: "agent-settings", id: "explore" });
        else if (view === "settings") setScreen({ name: "settings" });
        else if (view === "profile-edit") setScreen({ name: "profile-edit" });
        else if (view === "profile-share") setScreen({ name: "profile-share" });
        else if (view === "friend-chat")
          setScreen({ name: "chat", id: "person-linjia" });
        else if (view === "capability")
          setScreen({ name: "knowledge" });
        else setScreen({ name: "home" });
      } else if (params.get("reset") === "1") {
        localStorage.removeItem(V277_STORAGE_KEY);
        setState(createInitialV277State());
        setScreen({ name: "home" });
        setHistory([]);
        window.history.replaceState({}, "", window.location.pathname);
      } else {
        const raw = localStorage.getItem(V277_STORAGE_KEY);
        if (raw) setState(restoreV277State(JSON.parse(raw)));
      }
    } catch {}
    setReady(true);
  }, []);
  useEffect(() => {
    if (ready && !runtime) {
      try {
        localStorage.setItem(V277_STORAGE_KEY, JSON.stringify(state));
      } catch {}
    }
  }, [state, ready]);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 2600);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const go = (next: Screen) => {
    rememberScroll();
    const savedCreation = (screen.name==='create-tool'&&next.name==='tool-detail') ||
      (screen.name==='community-post'&&screen.id==='new'&&next.name==='community-post'&&next.id!=='new');
    setHistory((items) => savedCreation ? items : [...items.slice(-8), screen]);
    setScreen(next);
  };
  const back = () => {
    rememberScroll();
    const previous = history[history.length - 1] || { name: "home" as const };
    setHistory((items) => items.slice(0, -1));
    setScreen(previous);
  };
  useBackSwipe(root,back,ready&&state.phase==='ready'&&screen.name!=='home',runtime?.snapshot?.user.id||'local');
  const notify = (text: string) => setToast(text);

  const finishOnboarding = () => {
    if(runtime?.snapshot){
      void runtime.command('onboarding.complete',{...entityRef(runtime.snapshot.objects.onboarding[0]),skip:true}).then(()=>{setScreen({name:'home'});setHistory([]);notify('初始化已保存，开始你的第一项真实任务');}).catch(()=>{});
      return;
    }
    setState((s) => {
      const memories: V277Memory[] = [
        s.profile.name && {
          id: "profile-name",
          group: "基础",
          label: "称呼",
          value: s.profile.name,
          source: "个人资料",
          status: "已确认",
        },
        s.profile.role && {
          id: "profile-role",
          group: "基础",
          label: "当前角色",
          value: s.profile.role,
          source: "个人资料",
          status: "已确认",
        },
        {
          id: "profile-focus",
          group: "习惯",
          label: "当前重点",
          value: s.profile.focus,
          source: "首次目标",
          status: "已确认",
        },
      ].filter(Boolean) as V277Memory[];
      return {
        ...s,
        phase: "ready",
        account: {
          ...s.account,
          verified: true,
          onboardingComplete: true,
        },
        memories,
        messages: {
          ...s.messages,
          elfred: initialMessages(s.profile.name || "你").elfred,
        },
      };
    });
    setScreen({ name: "home" });
    setHistory([]);
    notify("初始化完成，今日简报已生成");
  };

  const openTaskFromPost = (post: Post) => {
    const result = taskFromPost(post, state.tasks);
    if (result.created) {
      setState((s) => ({ ...s, tasks: result.tasks }));
      notify("任务草稿已创建");
    } else notify("已打开原有任务，没有重复创建");
    go({ name: "task", id: result.task.id });
  };

  const content = useMemo(() => {
    if (!ready)
      return (
        <div className="v277-boot">
          <Sparkles size={24} />
          <b>Elfred</b>
          <p>正在恢复你的工作现场…</p>
        </div>
      );
    if (state.phase === "auth")
      return <LoginPage state={state} setState={setState} />;
    if (state.phase === "verify")
      return <VerifyPage state={state} setState={setState} />;
    if(runtime?.snapshot&&(screen.name==='onboarding-chat'||(screen.name==='home'&&runtime.snapshot.objects.onboarding[0]?.data.status!=='completed'&&!runtime.snapshot.objects.onboarding[0]?.data.deferred_at)))
      return <OnboardingConversation go={go} onExit={()=>{setScreen({name:'home'});setHistory([])}}/>;
    if (!runtime && state.phase === "welcome")
      return <OnboardingWelcome setState={setState} />;
    if (!runtime && state.phase === "profile-init")
      return <ProfileInitPage state={state} setState={setState} />;
    if (!runtime && state.phase === "agents-init")
      return <AgentInitPage state={state} setState={setState} />;
    if (!runtime && state.phase === "complete")
      return (
        <OnboardingComplete
          state={state}
          finish={finishOnboarding}
          onBack={() => setState((current) => ({ ...current, phase: "agents-init" }))}
        />
      );
    if (screen.name === "home") return <HomePage state={state} go={go} />;
    if (screen.name === "tasks")
      return (
        <TasksPage
          state={state}
          go={go}
          setState={setState}
          notify={notify}
          initialView={screen.view}
        />
      );
    if (screen.name === "new-task")
      return (
        <NewTaskPage
          onBack={back}
          setState={setState}
          go={go}
          notify={notify}
        />
      );
    if (screen.name === "task") {
      const task = state.tasks.find((item) => item.id === screen.id);
      return task ? (
        <TaskDetail
          task={task}
          go={go}
          onBack={back}
          setState={setState}
          notify={notify}
        />
      ) : (
        <TasksPage state={state} go={go} setState={setState} notify={notify} />
      );
    }
    if (screen.name === "player")
      return (
        <TaskPlayerPage
          state={state}
          go={go}
          onBack={back}
          setState={setState}
          notify={notify}
        />
      );
    if (screen.name === "highlights")
      return <TodayHighlights state={state} go={go} onBack={back} />;
    if (screen.name === "search")
      return <HomePage state={state} go={go} searchOpen closeSearch={back} />;
    if (screen.name === "agents") return <AgentsPage state={state} go={go} />;
    if (screen.name === "agent")
      return runtime?<AgentConversationPage key={screen.conversationId||screen.id} id={screen.id} conversationId={screen.conversationId} messageId={screen.messageId} go={go} onBack={back}/>: (
        <AgentExperiencePage
          id={screen.id}
          state={state}
          setState={setState}
          go={go}
          onBack={back}
        />
      );
    if (screen.name === "daily-brief") {
      if (screen.kind === "evening")
        return (
          <EveningReflectionPage state={state} onBack={back} notify={notify} />
        );
      return (
        <DailyBriefPage
          kind={screen.kind}
          state={state}
          setState={setState}
          go={go}
          onBack={back}
          notify={notify}
        />
      );
    }
    if (screen.name === "agent-level" && runtime) return <AgentLevelPage key={screen.id} id={screen.id} onBack={back} go={go}/>;
    if (screen.name === "agent-moments")
      return (
        <AgentMomentsPage
          id={screen.id}
          state={state}
          setState={setState}
          go={go}
          onBack={back}
          notify={notify}
        />
      );
    if (screen.name === "agent-moment-detail")
      return (
        <AgentMomentDetailPage
          id={screen.id}
          postId={screen.postId}
          state={state}
          setState={setState}
          onBack={back}
          notify={notify}
        />
      );
    if (screen.name === "agent-settings")
      return (
        <AgentSettingsPage
          id={screen.id}
          onBack={back}
          notify={notify}
        />
      );
    if (screen.name === "feed")
      return <FeedPage state={state} go={go} onBack={back} />;
    if (screen.name === "feed-detail" && runtime)
      return <FeedDetailPage id={screen.id} go={go} onBack={back} />;
    if (screen.name === "post") {
      const post = v277Posts.find((item) => item.id === screen.id);
      return post ? (
        <PostDetail
          post={post}
          state={state}
          onBack={back}
          setState={setState}
          openTaskFromPost={openTaskFromPost}
          notify={notify}
        />
      ) : (
        <HomePage state={state} go={go} />
      );
    }
    if (screen.name === "community-post") {
      if(runtime)return <ConnectedProject id={screen.id} onBack={back} go={go}/>;
      const post = communityPosts.find((item) => item.id === screen.id);
      return post ? (
        <CommunityPostDetail
          post={post}
          state={state}
          setState={setState}
          notify={notify}
          onBack={back}
        />
      ) : (
        <CommunityPage
          state={state}
          go={go}
          setState={setState}
          notify={notify}
        />
      );
    }
    if (screen.name === "knowledge")
      return <KnowledgePage state={state} go={go} setState={setState} runtime={runtime} />;
    if(screen.name==='search-source')return <SearchSourcePage id={screen.id} anchor={screen.anchor} onBack={back}/>;
    if (screen.name === "knowledge-detail") {
      const entity=runtime?.snapshot&&Object.values(runtime.snapshot.objects).flat().find(entry=>entry.id===screen.id);
      const item = runtime?(entity?{id:entity.id,title:entityTitle(entity),purpose:entity.type==='knowledge'?'本人保存的知识资料':'本人当前可读取的资料',source:(objectNames[entity.type]||'资料')+' · '+new Date(entity.created).toLocaleString('zh-CN'),status:runtimeStatuses[entityText(entity,'status')]||entityText(entity,'status'),example:entityText(entity,'content')||entityText(entity,'text')||entityText(entity,'goal')}:undefined):v277Knowledge.find((entry) => entry.id === screen.id);
      return item ? (
        <KnowledgeDetailPage
          item={item}
          go={go}
          onBack={back}
          setState={setState}
        />
      ) : (
        <KnowledgePage state={state} go={go} setState={setState} runtime={runtime} />
      );
    }
    if (screen.name === "memory") return <MemoryPage state={state} go={go} />;
    if (screen.name === "memory-detail") {
      const item = state.memories.find((entry) => entry.id === screen.id);
      return item ? (
        <MemoryDetail
          item={item}
          go={go}
          onBack={back}
          setState={setState}
          notify={notify}
        />
      ) : (
        <MemoryPage state={state} go={go} />
      );
    }
    if (screen.name === "messages")
      return <MessagesPage state={state} go={go} />;
    if (screen.name === "evidence") return <EvidenceListPage go={go} onBack={back}/>;
    if (screen.name === "evidence-detail") return <EvidenceDetailPage id={screen.id} go={go} onBack={back}/>;
    if (screen.name === "dimension") return <DimensionDetailPage id={screen.id} go={go} onBack={back}
      onCreateTask={async(card,goal)=>{
        const result=await launchWithSkill(runtime,card.id||card.title,goal);
        if(result.ok&&result.system&&result.prompt){go({name:'chat',id:result.system,prefill:result.prompt});return {ok:true};}
        return {ok:false,note:result.note};
      }} onUpgrade={card=>setCardLevel(card.title,card.level+1)}/>;
    if (screen.name === "ability-profile") return <AbilityProfilePage go={go} onBack={back}/>;
    // 新用户的「轻量测试」：题目与计分都在我们这边，界面照第二页的风格
    if (screen.name === "questionnaire") return <QuestionnairePage go={go} onBack={back}/>;
    if (screen.name === "chat" && runtime && ['explore','advisor','create','connect','execute'].includes(screen.id))
      return <AgentConversationPage id={screen.id as 'explore'|'advisor'|'create'|'connect'|'execute'} go={go} onBack={back} prefill={screen.prefill}/>;
    if (screen.name === "chat")
      return (
        <ChatPage
          id={screen.id}
          messageId={screen.messageId}
          state={state}
          go={go}
          onBack={back}
          setState={setState}
          notify={notify}
        />
      );
    if (screen.name === "friend-profile")
      return <FriendProfilePage id={screen.id} go={go} onBack={back} />;
    if (screen.name === "community")
      return (
        <CommunityPage
          state={state}
          go={go}
          setState={setState}
          notify={notify}
        />
      );
    if (screen.name === "my-tools")
      return runtime?<ToolsPage go={go} onBack={back}/>:<MyToolsPage go={go} onBack={back}/>;
    if(screen.name==='tool-detail'&&runtime)return <ToolsPage initialId={screen.id} go={go} onBack={back}/>;
    if (screen.name === "create-tool")
      return runtime?<ToolEditor key={screen.id||'new'} id={screen.id} onBack={back} go={go}/>:<CreateToolPage onBack={back} notify={notify}/>;
    if (screen.name === 'inbox' && runtime) return <InboxPage go={go} onBack={back}/>;
    if (screen.name === 'swarm' && runtime) return <SwarmPage go={go} onBack={back}/>;
    if (screen.name === "utility")
      return (
        <UtilityPage kind={screen.kind} go={go} onBack={back} notify={notify} />
      );
    if (screen.name === "profile")
      return (
        <ProfilePage
          state={state}
          setState={setState}
          go={go}
          notify={notify}
          runtime={runtime}
        />
      );
    if (screen.name === "profile-share")
      return (
        <ProfilePage
          state={state}
          setState={setState}
          go={go}
          notify={notify}
          runtime={runtime}
          initialShareOpen
        />
      );
    if (screen.name === "profile-edit")
      return (
        // ⚠️ 2026-09-26：编辑资料换成 features/pages24 里那份（字段点开单独编辑、改完即存）
        <ProfileEditPage
          state={state}
          setState={runtime ? setLocalState : setState}
          go={go}
          onBack={back}
          notify={notify}
          runtime={runtime}
        />
      );
    if(screen.name==='settings')return (
      <SettingsPage
        state={state}
        go={go}
        runtime={runtime}
        notify={notify}
        logout={() => {
          if(runtime){void runtime.logout().catch(()=>{});setScreen({name:'home'});setHistory([]);return;}
          setState((s) => ({
            ...s,
            phase: "auth",
            account: { ...s.account, verified: false },
          }));
          setScreen({ name: "home" });
          setHistory([]);
          notify("已退出登录，本机数据仍保留");
        }}
      />
    );
    return <main className="v277-page"><p className="v277-empty">当前入口不可用，请返回上一页。</p><button className="v277-secondary" onClick={back}>返回上一页</button></main>;
  }, [ready, state, screen, history, toast, runtime]);

  const fullScreen = screen.name === "onboarding-chat" || Boolean(runtime?.snapshot&&screen.name==='home'&&runtime.snapshot.objects.onboarding[0]?.data.status!=='completed'&&!runtime.snapshot.objects.onboarding[0]?.data.deferred_at) ||
    state.phase !== "ready" ||
    [
      "task",
      "post",
      "community-post",
      "feed",
      "agent",
      "agent-level",
      "daily-brief",
      "agent-moments",
      "agent-moment-detail",
      "agent-settings",
      "chat",
      "knowledge-detail",
      "search-source",
      "memory-detail",
      "utility",
      "settings",
      "agents",
      "player",
      "highlights",
      "profile-edit",
      "profile-share",
      "friend-profile",
      "new-task",
      "my-tools",
      "swarm",
      "tool-detail",
      "create-tool",
    ].includes(screen.name);
  return (
    <DeviceFrame label="Elfred V28 产品原型" className="v277-device v279-device v280-device">
      <StatusBar />
      <PageMemoryProvider key={runtime?.snapshot?.user.id || 'local'}><div className="v277-root" ref={root}>{content}</div></PageMemoryProvider>
      {state.phase === "ready" && !fullScreen && (
        <BottomNav
          screen={screen}
          go={go}
          openElfred={() => go(runtime ? { name: "swarm" } : { name: "chat", id: "elfred" })}
        />
      )}
      {toast && <Toast text={toast} />}
      {runtime?.error && <div role="alert" className="v277-toast" onClick={runtime.clearError}>{runtime.error}</div>}
    </DeviceFrame>
  );
}
