"use client";
import {displayTitle} from "../../core/display-labels";
import {finalReceipts} from "../../core/result-output";
import {forwardRef,useImperativeHandle,useRef,useState,useEffect} from 'react';
import {X,Sparkles,Maximize2,Minimize2} from 'lucide-react';
import {useRuntime,entityRef} from '../../core/runtime-context';
import {text,type Entity,statuses} from '../live/types';
import type {Screen} from '../../core/screen';
import './personal-agent.css';
import {ResultHandoffs} from './result-handoffs';

export type PersonalAgentHandle={submit:(query:string)=>Promise<boolean>};
export const PersonalAgentPanel=forwardRef<PersonalAgentHandle,{conversation:Entity;unreadAfter?:number;entry:'personal'|'icebreaker';onClose:()=>void;onFill:(value:string,version:number)=>Promise<void>;onPrompt:(value:string)=>void;go:(screen:Screen)=>void}>(function PersonalAgentPanel({conversation,unreadAfter,entry,onClose,onFill,onPrompt,go},ref){
 const runtime=useRuntime()!,snapshot=runtime.snapshot!;
 const selectionKey='elfred-assist-sources:'+snapshot.user.id+':'+conversation.id;
 const [selected,setSelected]=useState<{id:string;version:number}[]>(()=>{try{const saved=JSON.parse(sessionStorage.getItem(selectionKey)||'[]');return Array.isArray(saved)?saved.filter(r=>typeof r.id==='string'&&Number.isInteger(r.version)).slice(0,20):[]}catch{return []}}),[consent,setConsent]=useState(false),[busy,setBusy]=useState(false),[preview,setPreview]=useState<{value:string;mode:string;version:number}|null>(null);
 const locked=useRef(false);
 const [expanded,setExpanded]=useState(false),[fresh,setFresh]=useState(false);
 const messages=snapshot.objects.message.filter(item=>item.space===conversation.id).sort((a,b)=>Number(b.data.seq)-Number(a.data.seq));
 const unread=messages.filter(m=>Number(m.data.seq)>(unreadAfter??Number(conversation.data.seq))).sort((a,b)=>Number(a.data.seq)-Number(b.data.seq));
 const memberIds=conversation.members?.map(member=>member.id)||[];
 const resources=[...messages,...snapshot.objects.post.filter(item=>memberIds.includes(item.owner)),...snapshot.objects.knowledge,...snapshot.objects.document,...snapshot.objects.memory,...snapshot.objects.resource,...snapshot.objects.shared_record.filter(r=>r.space===conversation.id),...snapshot.objects.commitment.filter(r=>r.space===conversation.id),...snapshot.objects.draft.filter(r=>r.data.conversation_id===conversation.id&&r.owner===snapshot.user.id)];
 const [sourceQuery,setSourceQuery]=useState(''),[sourceLimit,setSourceLimit]=useState(30),[unreadOffset,setUnreadOffset]=useState(0);
 useEffect(()=>{try{sessionStorage.setItem(selectionKey,JSON.stringify(selected))}catch{}},[selectionKey,selected]);
 const stale=selected.some(ref=>!resources.some(r=>r.id===ref.id&&r.version===ref.version));
 const choices=resources.filter(item=>[item.data.title,item.data.text,item.data.content,item.data.goal,item.data.sender_name].filter(Boolean).join(' ').toLowerCase().includes(sourceQuery.toLowerCase()));
 const sessions=snapshot.objects.assist.filter(item=>item.data.conversation_id===conversation.id&&item.data.entry===entry).sort((a,b)=>a.created.localeCompare(b.created));
 const draft=snapshot.objects.draft.find(item=>item.data.conversation_id===conversation.id);
 useImperativeHandle(ref,()=>({submit:async(query)=>{
  if(locked.current)return false;
  if(stale){runtime.report('所选依据已更新或不可访问，请移除旧选择后重新核对。');return false;}
  if(!consent){runtime.report('请先勾选同意将本次请求和所选资料交给模型。');return false;}
  locked.current=true;setBusy(true);
  try{const session=await runtime.command('assist.create',{conversation_id:conversation.id,purpose:query,entry,parent_id:fresh?undefined:sessions.at(-1)?.id});
   const current=await runtime.request<Entity>('/objects/'+session.id);
   await runtime.command('assist.run',{...entityRef(current),confirm:true,model_consent:true,source_refs:selected});setFresh(false);return true;
  }catch{return false;}finally{locked.current=false;setBusy(false);}
 }}));
 const fill=async()=>{if(!preview||locked.current)return;locked.current=true;setBusy(true);try{await onFill(preview.value,preview.version);setPreview(null);onClose()}catch{}finally{locked.current=false;setBusy(false)}};
 return <section className={`elfred-personal-panel${expanded?" is-expanded":""}`} aria-label={entry==='icebreaker'?'破冰辅助，仅自己可见':'个人智能体，仅自己可见'}>
  <header><span><Sparkles size={18}/><b>{entry==='icebreaker'?'重新聊起来':'我的 Elfred'}</b></span><button type="button" aria-label={expanded?"收起私人面板":"展开私人面板"} onClick={()=>setExpanded(!expanded)}>{expanded?<Minimize2 size={18}/>:<Maximize2 size={18}/>}</button><button type="button" disabled={busy} aria-label="退出个人智能体" onClick={onClose}><X size={18}/></button></header>
  <p className="elfred-private-note">仅自己可见 · 原消息草稿已保留 · {fresh?"下次从新话题开始":"继续本次辅助的问答"}</p><button type="button" onClick={()=>setFresh(true)}>开始新话题</button>
  <p>{entry==='icebreaker'?'从历史聊天和双方已公开的近况找一个自然开场。选好依据，在下方写下你的想法。':'直接在下方提问。输入“搜索 关键词”可查找本人有权访问的资料，无需切换搜索框。'}</p>
  {entry==='personal'&&<div className="elfred-private-intents" aria-label="常用辅助方式"><button type="button" onClick={()=>onPrompt('帮我回复这段消息：')}>帮我回复</button><button type="button" onClick={()=>onPrompt('帮我理解这段对话：')}>理解消息</button><button type="button" onClick={()=>onPrompt('搜索 ')}>查资料</button></div>}
  {conversation.data.kind==='group'&&<div><p>本次进入时未读 {unread.length} 条。每次最多引用 20 条，可逐段整理；所选范围会列在结果中。</p><button disabled={!unread.length||busy} onClick={()=>{const start=unreadOffset>=unread.length?0:unreadOffset;setSelected(unread.slice(start,start+20).map(entityRef));setUnreadOffset(start+20)}}>{unreadOffset>=unread.length?'从首段重新选择':`选择未读第 ${unreadOffset+1}—${Math.min(unreadOffset+20,unread.length)} 条`}</button><button disabled={!messages.length||busy} onClick={()=>setSelected(messages.slice(0,20).map(entityRef))}>选择最近 20 条</button></div>}<details><summary>选择本次参考资料（{selected.length}/20）</summary><label>查找更早消息、笔记和当前事项<input aria-label="查找辅助参考资料" value={sourceQuery} onChange={e=>{setSourceQuery(e.target.value);setSourceLimit(30)}}/></label><p>共 {choices.length} 项可读依据。选择消息草稿可将原稿作为本次输入；没有选中的资料不自动读取。</p>{stale&&<p role="alert">部分选择已变化或不可访问，请重新核对。<button onClick={()=>setSelected([])}>清空旧选择</button></p>}{choices.slice(0,sourceLimit).map(item=><label key={item.id}><input type="checkbox" checked={selected.some(r=>r.id===item.id)} disabled={busy||(!selected.some(r=>r.id===item.id)&&selected.length>=20)} onChange={()=>setSelected(prev=>prev.some(r=>r.id===item.id)?prev.filter(r=>r.id!==item.id):[...prev,entityRef(item)])}/><span>{item.type==='draft'?'当前真人消息草稿：':item.type==='message'?text(item,'sender_name')+'：':''}{(displayTitle(text(item,'title'),'')||text(item,'text')||text(item,'content')||text(item,'goal')).slice(0,120)}</span></label>)}{choices.length>sourceLimit&&<button onClick={()=>setSourceLimit(n=>n+30)}>显示更多依据</button>}</details>
  <label className="elfred-consent"><input type="checkbox" checked={consent} disabled={busy} onChange={e=>setConsent(e.target.checked)}/>同意将本次请求与所选资料交给模型生成回复</label>
  {!snapshot.provider.configured&&<small>模型尚未配置。可先搜索资料；生成回复会保存为待配置任务。</small>}
  {sessions.map(session=>{const task=snapshot.objects.task.find(t=>t.id===session.data.task_id),run=snapshot.objects.run.find(r=>r.id===task?.data.run_id);const receipts=(run?.data.receipts||[]) as {phase?:string;output?:unknown}[];const output=finalReceipts(receipts)[0]?.output;return <article key={session.id}><b>你：{text(session,'purpose')}</b><small>{statuses[text(task,'status')]||'请求已保存'}</small>{typeof output==='string'&&<><p className="elfred-agent-output">{output}</p>{Boolean(session.data.coverage)&&<small>{String((session.data.coverage as {label?:string}).label||'')}</small>}<div className="elfred-inline-actions">{['追加','替换'].map(mode=><button type="button" key={mode} disabled={busy} onClick={()=>setPreview({value:mode==='追加'?[text(draft,'text'),output].filter(Boolean).join('\n'):output,mode,version:draft?.version??0})}>{mode}到消息草稿</button>)}<button type="button" disabled={busy} onClick={()=>void runtime.command('assist.save_note',{...entityRef(session),run_id:run?.id,run_version:run?.version,title:text(session,'purpose').slice(0,200)}).then(result=>go({name:'knowledge-detail',id:result.id})).catch(()=>{})}>保存私人纪要</button><button type="button" disabled={busy} onClick={()=>void runtime.command('assist.followup',{...entityRef(session),run_id:run?.id,run_version:run?.version,goal:output.slice(0,8000)}).then(result=>go({name:'task',id:result.id})).catch(()=>{})}>整理为本人任务草稿</button></div>{run&&<ResultHandoffs assist={session} run={run} output={output} conversation={conversation} go={go}/>}</>}{task&&<button type="button" onClick={()=>go({name:'task',id:task.id})}>查看任务{['queued','running'].includes(text(task,'status'))?' / 停止':''}</button>}{!task&&<button type="button" disabled={!consent||busy||stale} onClick={()=>{setBusy(true);void runtime.command('assist.run',{...entityRef(session),confirm:true,model_consent:true,source_refs:selected}).catch(()=>{}).finally(()=>setBusy(false))}}>重试此请求</button>}</article>})}
  {preview&&<section className="elfred-fill-preview"><b>{preview.mode}后预览</b>{preview.version!==(draft?.version??0)&&<p role="alert">消息草稿已在另一页面变化，请取消后重新预览。</p>}<label>回填文字<textarea aria-label="可编辑的回填文字" value={preview.value} onChange={e=>setPreview({...preview,value:e.target.value})}/></label><button type="button" disabled={busy||preview.version!==(draft?.version??0)} onClick={()=>void fill()}>确认回填，暂不发送</button><button type="button" onClick={()=>setPreview(null)}>取消</button></section>}
  {Boolean(draft?.data.previous)&&<button type="button" disabled={busy} onClick={()=>{void onFill(text(draft,'previous'),draft?.version??0).then(onClose).catch(()=>{})}}>恢复上一次消息草稿</button>}
 </section>;
});
