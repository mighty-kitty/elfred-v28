"use client";
import {displayTitle} from "../../core/display-labels";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  CheckCircle2,
  ChevronRight,
  Compass,
  Lightbulb,
  Link2,
  PenLine,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { agentList } from "../../../v27-7-data";
import type { V277State } from "../../../v27-7-state";
import type { Screen } from "../../core/screen";
import {importantBriefEvent} from '../../core/brief-event.mjs';
import {ModuleStatus} from '../../core/module-status';
import {PrivateFeed} from './private-feed';
import {ToolsPage} from './tools-page';
import {RootPortal} from '../../legacy/legacy-ui';
import {InboxSave} from './inbox-save';
import {useRuntime} from "../../core/runtime-context";
import {briefIndex as indexForTimezone,dailyTasks,localDay} from '../../core/local-day.mjs';
import {agentGrowth} from '../../core/agent-growth.mjs';
import './home-v2.css';
import {
  AgentMomentCard,
  BriefSettingsSheet,
  GlobalSearchSheet,
  HomeChannelTabs,
  PullDownPill,
  TaskPlayer,
  agentMoments,
  dailyBriefs,
  defaultBriefPreferences,
  getCurrentBriefIndex,
  readBriefPreferences,
  type DailyBriefKind,
} from "../../legacy/legacy-ui";

export function HomePage({
  state,
  go,
  searchOpen = false,
  closeSearch,
}: {
  state: V277State;
  go: (screen: Screen) => void;
  searchOpen?: boolean;
  closeSearch?: () => void;
}) {
  const runtime=useRuntime();

  const onboarding=runtime?.snapshot?.objects.onboarding[0];
  const firstTask=runtime?.snapshot?.objects.task.find(task=>task.id===onboarding?.data.choice_task_ref);
  const initialGoal=String(onboarding?.data.intent||'');
  const firstTaskLabel=String(onboarding?.data.choice_task_label||firstTask?.data.title||'首个事项');
  const initialUnderstanding=(onboarding?.data.choice_summary||onboarding?.data.understanding||[]) as {certainty:string}[];
  const [dragging,setDragging]=useState(false),[toolsOpen,setToolsOpen]=useState(false);
  const [agentMenu,setAgentMenu]=useState<string|null>(null);
  const [agentUnread,setAgentUnread]=useState<Record<string,number>>({});
  const holdTimer=useRef<ReturnType<typeof setTimeout>|null>(null);
  const holdOpened=useRef(false);
  const [playerCollapsed, setPlayerCollapsed] = useState(false);
  const [localPreferences, setBriefPreferences] = useState(readBriefPreferences);
  const connected=Boolean(runtime);
  const savedPreferences=JSON.stringify(runtime?.snapshot?.objects.settings[0].data.brief_preferences||{});
  const briefPreferences=useMemo(()=>connected?{...defaultBriefPreferences,...JSON.parse(savedPreferences) as Partial<typeof defaultBriefPreferences>}:localPreferences,[connected,savedPreferences,localPreferences]);
  const timezone=String(runtime?.snapshot?.objects.settings[0].data.timezone||Intl.DateTimeFormat().resolvedOptions().timeZone);
  const today=localDay(new Date(),timezone);
  const todayTasks=runtime?dailyTasks(runtime.snapshot?.objects.task||[],timezone,today):[];
  const importantEvent=importantBriefEvent(runtime?.snapshot?.objects.task||[],timezone,today);
  const eventSeen=useRef('');
  const pendingToday=todayTasks.filter(task=>task.data.status!=='completed').length;
  const completedToday=todayTasks.filter(task=>task.data.status==='completed').length;
  const moments=runtime?[]:agentMoments;
  useEffect(()=>{
    if(!runtime?.snapshot)return;
    const counts:Record<string,number>={};
    for(const agent of agentList){
      const system=agent.id==='advisor'?'advise':agent.id;
      let seen='';try{seen=localStorage.getItem(`elfred-agent-seen:${runtime.snapshot.user.id}:${system}`)||''}catch{}
      counts[system]=runtime.snapshot.objects.feed.filter(item=>item.data.system===system&&(!seen||item.created>seen)).length;
    }
    setAgentUnread(counts);
  },[runtime?.snapshot]);
  const [briefIndex, setBriefIndex] = useState(() =>
    getCurrentBriefIndex(readBriefPreferences()),
  );
  const [briefSettingsOpen, setBriefSettingsOpen] = useState(false);
  const briefDeck=useRef<HTMLElement>(null);
  const briefTouch=useRef<{x:number;y:number;id:number}|null>(null);
  const suppressBriefClick=useRef(0);
  const briefUnavailable=Boolean(runtime?.snapshot?.module_errors?.task);
  useEffect(()=>{
    const deck=briefDeck.current;if(!deck)return;
    let accumulated=0,lastEvent=0,lastSwitch=0;
    const wheel=(event:WheelEvent)=>{
      if(event.ctrlKey)return;
      event.preventDefault();event.stopPropagation();
      const time=Date.now();if(time-lastEvent>160)accumulated=0;lastEvent=time;
      if(time-lastSwitch<300)return;
      accumulated+=(Math.abs(event.deltaX)>Math.abs(event.deltaY)?event.deltaX:event.deltaY)*(event.deltaMode===1?16:event.deltaMode===2?deck.clientHeight:1);
      if(Math.abs(accumulated)<28)return;
      const direction=accumulated>0?1:-1;accumulated=0;lastSwitch=time;
      setBriefIndex(current=>(current+direction+3)%3);
    };
    deck.addEventListener('wheel',wheel,{passive:false});
    return()=>deck.removeEventListener('wheel',wheel);
  },[briefUnavailable]);
  const automaticBriefIndex = useRef(getCurrentBriefIndex(briefPreferences));
  const openTasks = state.tasks.filter((task) => task.status !== "已完成");
  const agentIcons = [Compass, Lightbulb, PenLine, Link2, CheckCircle2];
  const kinds: DailyBriefKind[] = ["morning", "noon", "evening"];
  const selectBrief = (next: number) =>
    setBriefIndex((next + kinds.length) % kinds.length);


  useEffect(() => {
    const syncBrief = () => {
      const dayKey = localDay(new Date(),timezone);
      const storedDay = window.localStorage.getItem("elfred-brief-day");
      const nextIndex = connected?indexForTimezone(briefPreferences,timezone):getCurrentBriefIndex(briefPreferences);
      if (storedDay !== dayKey || nextIndex !== automaticBriefIndex.current) {
        window.localStorage.setItem("elfred-brief-day", dayKey);
        automaticBriefIndex.current = nextIndex;
        setBriefIndex(nextIndex);
      }
    };
    syncBrief();
    const timer = window.setInterval(syncBrief, 60_000);
    return () => window.clearInterval(timer);
  }, [briefPreferences,timezone,connected]);

  useEffect(()=>{if(!runtime?.snapshot||!importantEvent)return;const key=runtime.snapshot.user.id+':'+today+':'+importantEvent.key;if(eventSeen.current===key)return;eventSeen.current=key;try{if(sessionStorage.getItem('elfred-important-brief')===key)return;sessionStorage.setItem('elfred-important-brief',key)}catch{}setBriefIndex(importantEvent.index);},[importantEvent?.key,runtime?.snapshot?.user.id,today]);

  return (
    <main
      className={`v277-page v277-home-page v277-reference-page${playerCollapsed ? " player-collapsed" : ""}`}
      onScroll={(event) =>
        setPlayerCollapsed(event.currentTarget.scrollTop > 78)
      }
    >
      <PullDownPill onOpen={() => runtime?setToolsOpen(true):go({ name: "my-tools" })} />
      {toolsOpen&&<RootPortal><button className="v278-sheet-backdrop elfred-tools-backdrop" aria-label="关闭我的工具" onClick={()=>setToolsOpen(false)}/><section role="dialog" aria-modal="true" aria-label="我的工具抽屉" style={{position:"absolute",inset:"30px 0 15%",zIndex:81,background:"#f7f8fa",borderRadius:"0 0 28px 28px",overflow:"auto"}}><ToolsPage onBack={()=>setToolsOpen(false)} go={go}/></section></RootPortal>}
      <div className="v282-home-fixed-head">
        <HomeChannelTabs
          active="home"
          onChange={(next) =>
            next === "community" && go({ name: "community" })
          }
          taskCount={openTasks.length}
          go={go}
        />
        <button
          type="button"
          className="v277-search v277-reference-search v278-global-search-entry"
          aria-label="打开全局搜索"
          onClick={() => go({ name: "search" })}
        >
          <Search size={24} strokeWidth={1.8} />
          <span>找人、机会、内容或工具…</span>
          <ChevronRight size={17} />
        </button>
      </div>
      <ModuleStatus types={['task']}><section
        className={`v283-brief-deck ${briefPreferences.style === "简洁" ? "is-simple" : briefPreferences.style === "紧凑" ? "is-compact" : "is-standard"}`}
        aria-label="三时段简报"
        ref={briefDeck}
        onPointerDown={event=>{if(event.isPrimary)briefTouch.current={x:event.clientX,y:event.clientY,id:event.pointerId};}}
        onPointerMove={event=>{
          const start=briefTouch.current;if(!start||start.id!==event.pointerId)return;
          if(Math.max(Math.abs(event.clientY-start.y),Math.abs(event.clientX-start.x))>8){
            event.currentTarget.setPointerCapture(event.pointerId);
            suppressBriefClick.current=Date.now()+400;
          }
        }}
        onPointerUp={event=>{
          const start=briefTouch.current;briefTouch.current=null;if(!start||start.id!==event.pointerId)return;
          const dx=event.clientX-start.x,dy=event.clientY-start.y;
          const delta=Math.abs(dx)>Math.abs(dy)?dx:dy;
          if(Math.abs(delta)>28){
            suppressBriefClick.current=Date.now()+400;
            setBriefIndex(current=>(current+(delta<0?1:-1)+3)%3);
          }
        }}
        onPointerCancel={()=>{briefTouch.current=null;}}
        onClickCapture={event=>{if(Date.now()<suppressBriefClick.current){event.preventDefault();event.stopPropagation();}}}
      >
        <button
          type="button"
          className="v283-deck-settings"
          aria-label="简报卡组设置"
          onClick={() => setBriefSettingsOpen(true)}
        >
          <SlidersHorizontal size={20} />
        </button>
        <div className="v283-brief-stack">
          {kinds.map((kind, index) => {
            const offset = (index - briefIndex + kinds.length) % kinds.length;
            const item = runtime?{...dailyBriefs[kind],title:kind==='morning'?'从今天的重点开始':kind==='noon'?'核对进展与待处理事项':'核对今日成果与理解',summary:todayTasks.length?`${pendingToday} 项待推进，${completedToday} 项已验收`:onboarding?.data.choice_confirmed_at&&kind==='morning'?`当前关注：${initialGoal.slice(0,36)}`:kind==='morning'?'添加今天的重点':kind==='noon'?'暂无进展':'暂无成果',stats:todayTasks.length?'依据今日任务记录':''}:dailyBriefs[kind];
            const moduleLabel =
              kind === "morning"
                ? briefPreferences.morningModule
                : kind === "noon"
                  ? briefPreferences.noonModule
                  : briefPreferences.eveningModule;
            return (
              <button
                type="button"
                key={kind}
                className={`v283-brief-card layer-${offset}${offset === 0 ? " is-active" : ""}`}
                aria-hidden={offset !== 0}
                tabIndex={offset === 0 ? 0 : -1}
                onClick={() =>
                  offset === 0
                    ? go({ name: "daily-brief", kind })
                    : selectBrief(index)
                }
              >
                <small>{moduleLabel}</small>
                <h2>{displayTitle(item.title,'')}</h2>
                <p>{importantEvent&&importantEvent.index===index?`${importantEvent.reason}：${displayTitle(importantEvent.title,'')}`:item.summary}</p>
                {item.stats&&<span>{item.stats}</span>}
                <strong>
                  {item.cta}
                  <ChevronRight size={17} />
                </strong>
              </button>
            );
          })}
        </div>
        <div className="v283-brief-dots" aria-label="切换简报卡片">
          {kinds.map((kind, index) => (
            <button
              type="button"
              key={kind}
              className={briefIndex === index ? "active" : ""}
              aria-label={`切换到${dailyBriefs[kind].label}`}
              onClick={() => selectBrief(index)}
            />
          ))}
        </div>
      </section></ModuleStatus>
      <ModuleStatus types={['memory']}><section className="v277-agents-strip v277-reference-agents">
        {agentList.map(({ id, name }, index) => {
          const Icon = agentIcons[index];
          const system=id==='advisor'?'advise':id;
          const tasks=runtime?.snapshot?.objects.task.filter(task=>task.data.system===system&&!task.data.internal_search)||[];
          const status=tasks.some(task=>['awaiting_review','awaiting_acceptance'].includes(String(task.data.status)))?'等待确认':tasks.some(task=>['queued','running'].includes(String(task.data.status)))?'执行中':runtime?.snapshot?.objects.observation?.some(item=>item.data.system===system&&item.data.status==='active')?'关注中':'空闲';
          const descriptions=['探索世界','看清自己','形成表达','连接关系','推动事情'];
          const openAgent=()=>{if(holdOpened.current){holdOpened.current=false;return;}try{localStorage.setItem(`elfred-agent-seen:${runtime?.snapshot?.user.id}:${system}`,new Date().toISOString())}catch{}setAgentUnread(current=>({...current,[system]:0}));go({name:'agent',id})};
          return (
            <button
              type="button"
              key={id}
              onClick={openAgent}
              onPointerDown={()=>{holdOpened.current=false;holdTimer.current=setTimeout(()=>{holdOpened.current=true;setAgentMenu(id)},550)}}
              onPointerUp={()=>{if(holdTimer.current)clearTimeout(holdTimer.current)}}
              onPointerLeave={()=>{if(holdTimer.current)clearTimeout(holdTimer.current)}}
              onContextMenu={event=>{event.preventDefault();holdOpened.current=true;setAgentMenu(id)}}
            >
              <span className="elfred-home-agent-icon"><Icon size={23} strokeWidth={1.8} />{Boolean(agentUnread[system])&&<i>{agentUnread[system]}</i>}</span>
              <b>{name}</b>
              <small>{runtime?`L${agentGrowth(runtime.snapshot,system).level} · ${status}`:'L1 · 空闲'}</small>
              <em>{descriptions[index]}</em>
            </button>
          );
        })}
        {agentMenu&&<div className="elfred-home-agent-menu" role="dialog" aria-label="Agent 快捷操作"><button type="button" aria-label="关闭快捷操作" onClick={()=>setAgentMenu(null)}>×</button><b>{agentList.find(item=>item.id===agentMenu)?.name} Agent</b><button type="button" onClick={()=>{go({name:'agent',id:agentMenu as typeof agentList[number]['id']});setAgentMenu(null)}}>交给它一件事</button><button type="button" onClick={()=>{go({name:'agent-settings',id:agentMenu as typeof agentList[number]['id']});setAgentMenu(null)}}>调整关注与权限</button><button type="button" onClick={()=>{go({name:'agent-level',id:agentMenu as typeof agentList[number]['id']});setAgentMenu(null)}}>查看成长等级</button></div>}
      </section></ModuleStatus>
      {runtime&&<ModuleStatus types={['feed','interaction']}><PrivateFeed go={go} onDrag={setDragging} preview/></ModuleStatus>}
      {!runtime&&<section className="v277-feed v277-reference-feed">
        <div className="v277-reference-section-head">
          <h2>Agent 朋友圈</h2>
          <button type="button" onClick={() => go({ name: "feed" })}>
            查看全部
            <ChevronRight size={17} />
          </button>
        </div>
        <div className="v278-home-feed-list">{runtime&&onboarding&&Boolean(onboarding.data.choice_task_ref||onboarding.data.choice_deferred_at||onboarding.data.choice_confirmed_at)&&<div className="v277-empty"><p>{firstTask?firstTaskLabel:onboarding.data.choice_confirmed_at?`当前关注：${initialGoal}`:'初始化进度已保存，可以随时继续。'}</p>{firstTask&&<button onClick={()=>go({name:'task',id:firstTask.id})}>{firstTask.data.status==='completed'?'查看首个成果':'继续首个事项'}</button>}<button onClick={()=>go({name:'onboarding-chat'})}>{initialUnderstanding.some(e=>e.certainty==='uncertain')?'核对仍不确定的理解':'继续初始化与理解核对'}</button></div>}{runtime&&moments.length===0&&!onboarding?.data.choice_confirmed_at&&!onboarding?.data.choice_task_ref&&!onboarding?.data.choice_deferred_at&&<div className="v277-empty"><p>尚无可发布的真实进展。</p><button onClick={()=>go({name:"new-task"})}>从一个目标开始</button></div>}
          {moments.map((moment) => (
            <div key={moment.id} draggable={Boolean(runtime)} onDragStart={e=>{if(runtime){e.dataTransfer.setData('application/x-elfred-content',moment.id);e.dataTransfer.effectAllowed='copy';setDragging(true)}}} onDragEnd={()=>setDragging(false)}><AgentMomentCard moment={moment} go={go}/>{runtime&&<InboxSave objectId={moment.id} go={go}/>}</div>
          ))}
        </div>
      </section>}
      {runtime&&dragging&&<div role="region" aria-label="拖入收件箱" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();const id=e.dataTransfer.getData('application/x-elfred-content');setDragging(false);if(id)void runtime.command('inbox.create',{object_id:id}).then(()=>go({name:'inbox'})).catch(()=>{})}} style={{position:'absolute',bottom:140,left:22,right:22,zIndex:50,padding:22,border:'2px dashed #8d9ca8',borderRadius:20,background:'#f5f8fa',textAlign:'center'}}>放到这里，稍后整理为任务</div>}
      <TaskPlayer state={state} go={go} collapsed={playerCollapsed} />
      {searchOpen && closeSearch && (
        <GlobalSearchSheet state={state} go={go} onClose={closeSearch} />
      )}
      {briefSettingsOpen && (
        <BriefSettingsSheet
          initial={briefPreferences}
          onClose={() => setBriefSettingsOpen(false)}
          onSave={(next) => {
            setBriefPreferences(next);
            setBriefIndex(runtime?indexForTimezone(next,timezone):getCurrentBriefIndex(next));
            setBriefSettingsOpen(false);
          }}
        />
      )}
    </main>
  );
}
