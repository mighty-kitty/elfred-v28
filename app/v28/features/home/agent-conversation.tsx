"use client";
import './agent-conversation-memory.css';
import {displayTitle} from "../../core/display-labels";

import {useEffect,useRef,useState,type FormEvent,type KeyboardEvent} from 'react';
import {ArrowLeft,ArrowUp,ChevronRight,History,Plus,Search,Settings2} from 'lucide-react';
import {agentList} from '../../../v27-7-data';
import type {V277AgentId} from '../../../v27-7-state';
import type {Screen} from '../../core/screen';
import {useRuntime,entityRef} from '../../core/runtime-context';
import {Action} from '../../core/runtime-panels';
import {statuses,text as entityText} from '../live/types';

const systemOf=(id:V277AgentId)=>id==='advisor'?'advise':id;
const prompts:Record<V277AgentId,string>={
  explore:'帮我看一下最近有什么值得关注的变化',
  advisor:'我有个选择想和你一起分析',
  create:'帮我修改一段内容',
  connect:'帮我梳理一下这段协作关系',
  execute:'帮我拆解这件事的下一步',
};

export function AgentConversationPage({id,go,onBack,prefill,conversationId,messageId}:{id:V277AgentId;conversationId?:string;messageId?:string;go:(screen:Screen)=>void;onBack:()=>void;prefill?:string}){
  const runtime=useRuntime();
  const agent=agentList.find(item=>item.id===id)!;
  const Icon=agent.icon;
  const [selectedId,setSelectedId]=useState<string|null>(conversationId||null);
  const [newThread,setNewThread]=useState(false);
  const [historyOpen,setHistoryOpen]=useState(false);
  const [query,setQuery]=useState('');
  const [input,setInput]=useState('');
  const [sending,setSending]=useState(false);
  const [drafting,setDrafting]=useState(false);
  const thread=useRef<HTMLElement>(null),anchorShown=useRef(false);
  const [taskOpen,setTaskOpen]=useState(false),[taskGoal,setTaskGoal]=useState(''),[taskMode,setTaskMode]=useState('compose'),[taskConsent,setTaskConsent]=useState(false),[startingTask,setStartingTask]=useState(false);
  const composer=useRef<HTMLTextAreaElement>(null);
  const threads=(runtime?.snapshot?.objects.conversation||[]).filter(item=>item.data.kind==='agent'&&item.data.system===systemOf(id)).sort((a,b)=>b.updated.localeCompare(a.updated));
  const activeId=newThread?null:selectedId||threads[0]?.id||null;
  const active=threads.find(item=>item.id===activeId);
  const messages=(runtime?.snapshot?.objects.message||[]).filter(item=>item.data.conversation_id===activeId).sort((a,b)=>Number(a.data.seq)-Number(b.data.seq));
  const runs=(runtime?.snapshot?.objects.task||[]).filter(item=>(item.data.agent_chat as {conversation_id?:string}|undefined)?.conversation_id===activeId).sort((a,b)=>b.created.localeCompare(a.created));
  const pending=runs.find(item=>['queued','running','cancel_requested','pause_requested'].includes(String(item.data.status)));
  const failed=!pending&&runs[0]&&['blocked','failed','partial','reconciliation_required'].includes(String(runs[0].data.status))&&!(runtime?.snapshot?.objects.message||[]).some(message=>message.data.task_id===runs[0].id)?runs[0]:undefined;
  const drafts=(runtime?.snapshot?.objects.task||[]).filter(item=>item.data.agent_chat_draft_conversation_id===activeId&&item.data.status!=='archived').sort((a,b)=>b.created.localeCompare(a.created));
  const existingDrafts=(runtime?.snapshot?.objects.task||[]).filter(item=>item.data.system===systemOf(id)&&item.data.status==='draft'&&!item.data.agent_chat).sort((a,b)=>b.created.localeCompare(a.created));
  const lastHuman=[...messages].reverse().find(item=>item.data.actor_type==='human');

  useEffect(()=>{if(prefill)setInput(current=>current.trim()?current:prefill);},[prefill]);

  useEffect(()=>{if(!thread.current)return;const target=!anchorShown.current&&messageId&&thread.current.querySelector<HTMLElement>('[data-message-id="'+CSS.escape(messageId)+'"]');if(target){thread.current.scrollTop=target.offsetTop-thread.current.offsetTop-24;anchorShown.current=true;}else thread.current.scrollTop=thread.current.scrollHeight;},[activeId,messages.length,pending?.id,messageId]);
  useEffect(()=>{const field=composer.current;if(!field)return;field.style.height='auto';field.style.height=Math.min(field.scrollHeight,130)+'px';field.closest('main')?.style.setProperty('--agent-composer-height',(field.parentElement?.offsetHeight||58)+'px');},[input]);

  const send=async(event?:FormEvent)=>{
    event?.preventDefault();
    const text=input.trim();
    if(!runtime||!text||sending||pending)return;
    setSending(true);
    try{
      let conversationId=activeId;
      if(!conversationId){const created=await runtime.command('agent.chat.create',{system:systemOf(id)});conversationId=created.id;setSelectedId(conversationId);setNewThread(false);}
      await runtime.command('agent.chat.send',{id:conversationId,text,model_consent:true});
      setInput(current=>current.trim()===text?'':current);
    }catch(error){runtime.report(error instanceof Error?error.message:'发送失败');}
    finally{setSending(false);}
  };
  const createDraft=async()=>{
    if(!runtime||!activeId||!lastHuman||drafting)return;
    setDrafting(true);
    try{await runtime.command('agent.chat.draft',{id:activeId,goal:String(lastHuman.data.text)});}
    catch(error){runtime.report(error instanceof Error?error.message:'草稿创建失败');}
    finally{setDrafting(false);}
  };
  const openTask=()=>{
    const meaningful=[...messages].reverse().find(item=>item.data.actor_type==='human'&&!/^(你)?(直接|继续)?(执行|做|开始|继续)(吧|啊)?[。！!]?$/u.test(String(item.data.text).trim()));
    setTaskGoal(String((meaningful||lastHuman)?.data.text||''));setTaskConsent(false);setTaskOpen(true);
  };
  const startTask=async()=>{
    if(!runtime||!activeId||!taskGoal.trim()||!taskConsent||startingTask)return;
    setStartingTask(true);
    try{await runtime.command('agent.chat.task',{id:activeId,goal:taskGoal.trim(),mode:taskMode,confirm:true,model_consent:taskMode==='compose'});setTaskOpen(false);}
    catch(error){runtime.report(error instanceof Error?error.message:'任务未能启动');}
    finally{setStartingTask(false);}
  };
  const keyDown=(event:KeyboardEvent<HTMLTextAreaElement>)=>{
    if(event.key==='Enter'&&!event.shiftKey&&!event.nativeEvent.isComposing){event.preventDefault();void send();}
  };
  const selectThread=(conversationId:string)=>{anchorShown.current=true;setSelectedId(conversationId);setNewThread(false);setHistoryOpen(false);setTaskOpen(false);setInput('');};
  const startThread=()=>{setSelectedId(null);setNewThread(true);setHistoryOpen(false);setTaskOpen(false);setInput('');};
  const filtered=threads.filter(item=>{
    const first=(runtime?.snapshot?.objects.message||[]).find(message=>message.data.conversation_id===item.id&&message.data.actor_type==='human');
    return `${item.data.title||''} ${first?.data.text||''}`.toLowerCase().includes(query.trim().toLowerCase());
  });

  return <main className="v277-page v283-agent-page v283-agent-chat-page">
    <header className="v283-agent-head">
      <span className="v279-agent-head-left">
        <button type="button" className="v277-icon-button" aria-label="返回上一页" onClick={onBack}><ArrowLeft size={21}/></button>
        <button type="button" className="v277-icon-button" aria-label="过往对话" onClick={()=>setHistoryOpen(true)}><History size={20}/></button>
      </span>
      <div className="v283-agent-title">
        <i className={'v283-agent-avatar small agent-'+id}><Icon size={18}/><em/></i>
        <span><b>{agent.name} Agent</b><small>{activeId?'连续对话 · 仅自己可见':'新对话 · 仅自己可见'}</small></span>
      </div>
      <span>
        <button type="button" className="v277-icon-button" aria-label="新对话" onClick={startThread}><Plus size={21}/></button>
        <button type="button" className="v277-icon-button" aria-label="Agent 设置" onClick={()=>go({name:'agent-settings',id})}><Settings2 size={21}/></button>
      </span>
    </header>
    <section ref={thread} className="v283-agent-thread" aria-label={`${agent.name} Agent 对话`}>
      {!messages.length&&<div className="v283-agent-chat-welcome">
        <i className={'v283-agent-avatar hero agent-'+id}><Icon size={38}/><em/></i>
        <h1>和{agent.name} Agent 聊聊</h1>
        <p>{agent.role}</p>
        <button type="button" onClick={()=>setInput(prompts[id])}>{prompts[id]} <ChevronRight size={16}/></button>
        {!!threads.length&&newThread&&<button type="button" onClick={()=>selectThread(threads[0].id)}>继续最近的对话</button>}
      </div>}
      {messages.map(message=><div key={message.id} data-message-id={message.id} className={'v283-agent-chat-row '+(message.data.actor_type==='human'?'mine':'theirs')}>
        {message.data.actor_type!=='human'&&<i className={'v283-agent-avatar small agent-'+id}><Icon size={18}/></i>}
        <div className="v283-agent-chat-bubble">{String(message.data.text||'')}</div>
      </div>)}
      {pending&&<div className="v283-agent-chat-row theirs"><i className={'v283-agent-avatar small agent-'+id}><Icon size={18}/></i><div className="v283-agent-chat-bubble subtle">正在回复…</div></div>}
      {failed&&!pending&&<p className="v283-agent-chat-status">这次回复未完成：{String(((runtime?.snapshot?.objects.run||[]).find(item=>item.id===failed.data.run_id)?.data.error as {message?:string}|undefined)?.message||'请重试发送；已发送的消息仍保留在对话中。')}</p>}
      {!!messages.length&&!pending&&<div className="v283-agent-chat-drafts">
        <button type="button" onClick={()=>void createDraft()} disabled={!lastHuman||drafting}>{drafting?'正在保存…':'将这段对话建为任务草稿'}</button>
        <button type="button" onClick={openTask} disabled={!lastHuman}>执行任务</button>
        {drafts.map(draft=><button type="button" className="v283-agent-chat-draft-link" key={draft.id} onClick={()=>go({name:'task',id:draft.id})}><span className="v283-chat-task-label"><b>{String(displayTitle(draft.data.title,''))}</b><small>{statuses[entityText(draft,'status')]||entityText(draft,'status')}</small></span><span>{draft.data.status==='draft'?'查看草稿':['awaiting_review','awaiting_acceptance','completed'].includes(String(draft.data.status))?'查看结果':'查看任务'} <ChevronRight size={14}/></span></button>)}
      </div>}

      {(runtime?.snapshot?.objects.memory||[]).filter(m=>m.data.scope===systemOf(id)&&['candidate','pending_confirmation'].includes(String(m.data.status))&&!m.data.hidden&&(m.data.source_refs as {id:string}[]|undefined)?.some(ref=>messages.some(message=>message.id===ref.id))).slice(0,3).map(memory=><div className="v277-edit-card" key={memory.id}><small>待核对的理解 · 仅用于{agent.name}领域</small><p>{String(memory.data.content)}</p><div className="v284-memory-actions"><Action run={()=>runtime!.command('memory.decide',{...entityRef(memory),decision:'confirm'})}>确认记住</Action><button type="button" className="v277-secondary" onClick={()=>go({name:'memory-detail',id:memory.id})}>修改</button><Action run={()=>runtime!.command('memory.decide',{...entityRef(memory),decision:'reject'})}>不记这条</Action></div></div>)}
    </section>
    <form className="v283-agent-chat-composer" onSubmit={event=>void send(event)}>
      <textarea ref={composer} value={input} onChange={event=>setInput(event.target.value)} onKeyDown={keyDown} rows={1} placeholder={`问${agent.name} Agent…`} aria-label={`问${agent.name} Agent`}/>
      <button type="submit" disabled={!input.trim()||sending||Boolean(pending)} aria-label="发送消息"><ArrowUp size={20}/></button>
    </form>
    {taskOpen&&<div className="v283-agent-chat-task-layer">
      <button type="button" className="v283-agent-chat-mask" aria-label="关闭任务确认" onClick={()=>!startingTask&&setTaskOpen(false)}/>
      <section role="dialog" aria-modal="true" aria-label="确认执行任务" className="v283-agent-chat-task-form">
        <header><b>执行任务</b><button type="button" disabled={startingTask} onClick={()=>setTaskOpen(false)}>关闭</button></header>
        <label>本次要完成什么<textarea value={taskGoal} maxLength={taskMode==='search'?300:6000} onChange={event=>setTaskGoal(event.target.value)} aria-label="任务目标" rows={3}/></label>
        <label>执行方式<select value={taskMode} onChange={event=>{setTaskMode(event.target.value);setTaskConsent(false);}} aria-label="执行方式"><option value="compose">生成内容、分析或计划</option><option value="search">检索应用内资料</option></select></label>
        <p>{taskMode==='compose'?'使用当前对话，最多 3 次模型调用；结果在任务中核对。':'请输入不超过 300 字的检索关键词；只检索本人可访问的应用内资料，不调用模型。'} 邮件、网页操作、支付和部署尚未接通。</p>
        <label className="v283-chat-task-consent"><input type="checkbox" checked={taskConsent} onChange={event=>setTaskConsent(event.target.checked)}/>确认目标与范围{taskMode==='compose'?'，允许把目标及当前对话交给已配置模型，最多 3000 本地额度':''}</label>
        <button type="button" className="v277-primary" disabled={!taskGoal.trim()||(taskMode==='search'&&taskGoal.trim().length>300)||!taskConsent||startingTask} onClick={()=>void startTask()}>{startingTask?'正在启动…':'确认并开始'}</button>
      </section>
    </div>}
    {historyOpen&&<div className="v283-agent-chat-history-layer">
      <button type="button" className="v283-agent-chat-mask" aria-label="关闭过往对话" onClick={()=>setHistoryOpen(false)}/>
      <aside className="v283-agent-chat-history" role="dialog" aria-modal="true" aria-label="过往对话">
        <header><b>过往对话</b><button type="button" onClick={startThread}><Plus size={17}/> 新对话</button></header>
        <label><Search size={18}/><input value={query} onChange={event=>setQuery(event.target.value)} placeholder="搜索对话"/></label>
        <nav>{filtered.map(item=>{
          const first=(runtime?.snapshot?.objects.message||[]).find(message=>message.data.conversation_id===item.id&&message.data.actor_type==='human');
          return <button type="button" className={item.id===activeId?'active':''} key={item.id} onClick={()=>selectThread(item.id)}><span>{String(first?.data.text||displayTitle(item.data.title,'')).slice(0,32)}</span><small>{new Date(item.updated).toLocaleDateString('zh-CN')}</small></button>;
        })}</nav>
        {!filtered.length&&<p>还没有相关对话</p>}
        {!!existingDrafts.length&&<div className="v283-agent-chat-old-drafts"><b>已有任务草稿</b>{existingDrafts.map(draft=><button type="button" key={draft.id} onClick={()=>{setHistoryOpen(false);go({name:'task',id:draft.id});}}><span>{String(displayTitle(draft.data.title,''))}</span><small>查看草稿 <ChevronRight size={13}/></small></button>)}</div>}
        <button type="button" className="v283-agent-chat-history-close" onClick={()=>setHistoryOpen(false)}>关闭</button>
      </aside>
    </div>}
  </main>;
}
