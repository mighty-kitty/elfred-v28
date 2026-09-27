"use client";
import {displayTitle} from "../../core/display-labels";
import {useState} from 'react';
import {useRuntime,entityRef} from '../../core/runtime-context';
import {Action} from '../../core/runtime-panels';
import {type Entity,text,statuses} from '../live/types';
export function ReflectionGenerator({brief,taskIds}:{brief:Entity;taskIds:string[]}){
 const r=useRuntime()!,[selected,setSelected]=useState<Record<string,number>>({}),s=r.snapshot!,task=s.objects.task.find(t=>t.id===brief.data.reflection_task_id),run=s.objects.run.find(t=>t.id===task?.data.run_id);
 const facts=s.objects.task.filter(t=>taskIds.includes(t.id)&&!t.data.internal_search),stale=Object.entries(selected).some(([id,v])=>!facts.some(f=>f.id===id&&f.version===v));
 return <details><summary>依据今日记录生成待确认反思</summary><p>仅发送勾选的任务名称、状态和安排说明，最多 20 项；本次最多一次模型请求、1000 本地额度。新理解仍由你核对。</p>{facts.map(t=><label key={t.id} style={{display:'block'}}><input type="checkbox" checked={Boolean(selected[t.id])} onChange={e=>setSelected(old=>{const next={...old};if(e.target.checked)next[t.id]=t.version;else delete next[t.id];return next})}/>{displayTitle(text(t,'title'),'')} · {statuses[text(t,'status')]}</label>)}{stale&&<p role="alert">选定记录已变化，请取消后重新勾选。</p>}<Action disabled={stale||!Object.keys(selected).length||Object.keys(selected).length>20||['queued','running'].includes(text(task,'status'))} run={()=>r.command('brief.reflect',{...entityRef(brief),source_refs:Object.entries(selected).map(([id,version])=>({id,version})),confirm:true,model_consent:true})}>确认范围与额度，生成反思</Action>{task&&<p>{statuses[text(task,'status')]||text(task,'status')}{run&&['completed','awaiting_review'].includes(text(run,'status'))&&<Action run={()=>r.command('brief.reflection.apply',{...entityRef(brief),run_id:run.id,run_version:run.version})}>载入这次待确认反思</Action>}{['blocked','failed','paused','partial'].includes(text(task,'status'))&&<Action run={()=>r.command('run.start',entityRef(task))}>恢复未完成的生成</Action>}{run&&['queued','running'].includes(text(run,'status'))&&<Action run={()=>r.command('run.command',{...entityRef(run),command:'cancel'})}>停止生成</Action>}</p>}</details>;
}
