"use client";
import {displayTitle} from "../../core/display-labels";
import {useState} from 'react';
import {useRuntime,entityRef} from '../../core/runtime-context';
import {Action,Field} from '../../core/runtime-panels';
import {calendarICS} from '../../core/calendar-ics.mjs';
import {text,type Entity} from '../live/types';
import {objectScreen} from '../../core/object-screen';
import type {Screen} from '../../core/screen';
type Go=(screen:Screen)=>void;

export function ResultHandoffs({assist,run,output,conversation,go}:{assist:Entity;run:Entity;output:string;conversation:Entity;go:Go}){
 const runtime=useRuntime()!,[mode,setMode]=useState(''),[title,setTitle]=useState(''),[content,setContent]=useState(''),[criteria,setCriteria]=useState(''),[openTask,setOpenTask]=useState(''),[start,setStart]=useState(''),[end,setEnd]=useState(''),[reviewed,setReviewed]=useState(false),[sources,setSources]=useState<string[]>([]),[base,setBase]=useState({assist:assist.version,run:run.version,runId:run.id});
 const messages=runtime.snapshot!.objects.message.filter(m=>m.space===conversation.id);
 const select=(value:string)=>{setMode(value);setTitle(text(assist,'purpose').slice(0,200));setContent(output);setReviewed(false);setSources([]);setBase({assist:assist.version,run:run.version,runId:run.id})};
 const changed=assist.version!==base.assist||run.version!==base.run||run.id!==base.runId;
 return <details className="elfred-result-handoffs"><summary>送到纪要、日程或共创草稿</summary><div className="elfred-inline-actions">{[['share_record','共享纪要'],['calendar','日程或提醒'],['project_brief','共创 Brief']].map(([v,n])=><button key={v} type="button" onClick={()=>select(v)}>{n}</button>)}</div>{mode&&<section className="v277-edit-card">
 <p>{mode==='share_record'?`接收会话：${displayTitle(text(conversation,'title'),'')}。确认后作为本人消息分享；他人的承诺仍待其确认。`:mode==='calendar'?'目标：本人日程草稿，可导出日历文件。尚未连接外部日历，不会自动写入或通知。':'目标：本人私有共创项目草稿，下一步核对开放任务与公开范围后再发布。'}</p>
 <Field name="交付标题" value={title} onChange={setTitle}/><Field name="核对并编辑交付正文" area value={content} onChange={setContent}/><p>正文 {content.length}/{mode==='project_brief'?3000:8000} 字；超过上限请自行精简后确认。</p>
 {mode==='calendar'&&<><Field name="开始时间（本机时区）" type="datetime-local" value={start} onChange={setStart}/><Field name="结束时间（本机时区）" type="datetime-local" value={end} onChange={setEnd}/></>}
 {mode==='project_brief'&&<><Field name="验收标准" area value={criteria} onChange={setCriteria}/><Field name="开放任务及范围" area value={openTask} onChange={setOpenTask}/></>}
 {mode==='share_record'&&<details><summary>附当前会话的原话依据（可不附）</summary>{messages.map(m=><label key={m.id} style={{display:'block'}}><input type="checkbox" checked={sources.includes(m.id)} disabled={!sources.includes(m.id)&&sources.length>=20} onChange={e=>setSources(old=>e.target.checked?[...old,m.id]:old.filter(id=>id!==m.id))}/>{text(m,'sender_name')}：{text(m,'text').slice(0,120)}</label>)}</details>}
 <label><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/>{mode==='calendar'?'已核对时间、目标和内容':'已核对接收范围与这段可分享摘要；私人原文、文件及聊天引用不自动带出'}</label>
 {changed&&<p role="alert">辅助结果已变化，请重新选择去向并核对当前结果。</p>}
 <Action disabled={!reviewed||changed||content.length>(mode==='project_brief'?3000:8000)||!title.trim()||!content.trim()||(mode==='calendar'&&(!start||!end))||(mode==='project_brief'&&(!criteria.trim()||!openTask.trim()))} run={async()=>{const result=await runtime.command('assist.'+mode,{id:assist.id,version:base.assist,run_version:base.run,run_id:base.runId,title,content,confirm:true,reviewed_summary:reviewed,source_refs:messages.filter(m=>sources.includes(m.id)).map(entityRef),criteria,open_task:openTask,start:start?new Date(start).toISOString():undefined,end:end?new Date(end).toISOString():undefined});setMode('');go(mode==='share_record'?{name:'chat',id:conversation.id,messageId:result.id}:mode==='calendar'?{name:'knowledge-detail',id:result.id}:{name:'community-post',id:result.id})}}>{mode==='share_record'?'确认分享纪要到当前会话':mode==='calendar'?'保存本人日程草稿':'保存并打开共创编辑草稿'}</Action><button type="button" onClick={()=>setMode('')}>取消</button>
 </section>}</details>;
}
export function OriginLinks({targetId,go}:{targetId:string;go:Go}){
 const s=useRuntime()?.snapshot;if(!s)return null;
 return <>{(s.objects.handoff||[]).filter(h=>h.data.target_id===targetId&&s.objects.conversation.some(c=>c.id===h.data.conversation_id)).map(h=><button type="button" key={h.id} className="v277-secondary" onClick={()=>go({name:'chat',id:text(h,'conversation_id'),messageId:text(h,'message_id')||undefined})}>返回来源会话 · 仅自己可见</button>)}</>;
}
export function ConversationHandoffs({conversation,go}:{conversation:Entity;go:Go}){
 const s=useRuntime()!.snapshot!,all=Object.values(s.objects).flat();
 const links=(s.objects.handoff||[]).filter(h=>h.data.conversation_id===conversation.id);
 return links.length?<section className="v277-edit-card"><h3>本会话的交付对象 · 仅自己可见</h3>{links.map(h=>{const object=all.find(o=>o.id===h.data.target_id);return <div key={h.id}><p>{displayTitle(text(h,'title'),'')}</p><button disabled={!object} onClick={()=>object&&go(h.data.kind==='share_record'?{name:'chat',id:conversation.id,messageId:text(h,'message_id')}:objectScreen(object))}>{object?'打开同一对象':'来源或对象已不可访问'}</button></div>})}</section>:null;
}
export function SharedRecordCard({message,go}:{message?:Entity;go:Go}){
 const s=useRuntime()?.snapshot,record=s?.objects.shared_record.find(r=>r.id===message?.data.shared_record_id);if(!record)return null;
 return <details><summary>会话纪要</summary><p>由本人确认分享，不代表他人已接受分工或期限。</p>{((message?.data.record_sources||[]) as {id:string;version?:number}[]).map(ref=>{const m=s?.objects.message.find(x=>x.id===ref.id);return m&&m.version===ref.version&&<button key={ref.id} type="button" onClick={()=>go(objectScreen(m))}>原话：{text(m,'text').slice(0,60)}</button>})}</details>;
}
export function CalendarDraft({item}:{item:Entity}){
 const calendar=item.data.calendar as {start:string;end:string}|undefined;if(!calendar)return null;
 return <section className="v277-edit-card"><h3>日程草稿</h3><p>{new Date(calendar.start).toLocaleString('zh-CN')} — {new Date(calendar.end).toLocaleString('zh-CN')}</p><p>尚未写入外部日历。下载后可自行导入日历应用。</p><button type="button" className="v277-secondary" onClick={()=>{const body=calendarICS({id:item.id,title:text(item,'title'),content:text(item,'content'),start:calendar.start,end:calendar.end,created:item.created});const url=URL.createObjectURL(new Blob([body],{type:'text/calendar;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='elfred-event.ics';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}}>下载日历文件</button></section>;
}
