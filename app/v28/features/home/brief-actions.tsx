"use client";
import {displayTitle} from "../../core/display-labels";
import {useState} from 'react';
import {CheckCircle2,ChevronRight} from 'lucide-react';
import {useRuntime,entityRef} from '../../core/runtime-context';
import {Action,Field} from '../../core/runtime-panels';
import {type Entity,statuses} from '../live/types';
import type {Screen} from '../../core/screen';
import {selectedBriefFacts} from './brief-selection.mjs';

export type BriefFact={task_id:string;version:number;title:string;status:string;today?:boolean;focus?:boolean;plan_note?:string};
export function BriefActions({brief,kind,go}:{brief?:Entity;kind:'morning'|'noon';go:(screen:Screen)=>void}) {
  const runtime=useRuntime()!;
  const [selection,setSelection]=useState<{version:number|undefined;ids:string[]}>({version:brief?.version,ids:[]}),[notes,setNotes]=useState<Record<string,string>>({});
  const facts=(brief?.data.facts||[]) as BriefFact[];
  const selected=selectedBriefFacts(facts,selection.ids,selection.version,brief?.version).map(fact=>fact.task_id);
  const setSelected=(ids:string[])=>setSelection({version:brief?.version,ids});
  const available=facts.filter(fact=>!['completed','archived','cancelled'].includes(fact.status));
  return <>
    <section className="v283-brief-section"><h3>{kind==='morning'?'今日安排':'当前进度'}</h3>
      <div className="v283-status-list">{facts.map(fact=><button key={fact.task_id} onClick={()=>go({name:'task',id:fact.task_id})}><CheckCircle2 size={22}/><b>{displayTitle(fact.title,'')}{fact.focus?' · 今日重点':fact.today===false?' · 待确认候选':''}</b><span>{statuses[fact.status]||fact.status}</span><ChevronRight size={18}/></button>)}</div>
      {!facts.length&&<p className="v277-empty">今天还没有任务，可以先补充一个目标。</p>}
    </section>
    {kind==='noon'&&brief&&<section className="v283-brief-section"><h3>根据当前状态提出的调整</h3>{((brief.data.suggestions||[]) as {id:string;task_id:string;reason:string;note:string;planned_date:string}[]).map(proposal=>{const decision=((brief.data.suggestion_decisions||[]) as {id:string;decision:string}[]).find(d=>d.id===proposal.id);return <article key={proposal.id} className="v283-decision-card"><b>{facts.find(f=>f.task_id===proposal.task_id)?.title}</b><p>{proposal.reason}</p><p>{proposal.note} · {proposal.planned_date}</p>{decision?<p>{decision.decision==='accept'?'已接受并同步安排':'已拒绝，安排未改变'}</p>:<><Action run={()=>runtime.command('brief.suggestion',{...entityRef(brief),suggestion_id:proposal.id,decision:'accept'})}>接受这项调整</Action><Action run={()=>runtime.command('brief.suggestion',{...entityRef(brief),suggestion_id:proposal.id,decision:'reject'})}>拒绝，保留原安排</Action></>}</article>})}<p>没有合适建议时，可以在下方自行调整，确认前不会改动任务。</p></section>}
    <section className="v283-brief-section"><h3>{kind==='morning'?'确认今天的重点':'确认下一步调整'}</h3><div className="v283-decision-card">
      <p>{kind==='morning'?'请只勾选同时满足重要、今天相关、需要行动的事项；确认后才进入今日安排。':'勾选需要调整的任务，写下新的下一步；确认后同步保存。'}</p>
      {available.map(fact=><div key={fact.task_id}>
        <label><input type="checkbox" checked={selected.includes(fact.task_id)} onChange={event=>setSelected(event.target.checked?[...selected,fact.task_id]:selected.filter(id=>id!==fact.task_id))}/>{displayTitle(fact.title,'')}</label>
        {kind==='noon'&&selected.includes(fact.task_id)&&<Field name="下一步调整" area value={notes[fact.task_id]??fact.plan_note??''} onChange={value=>setNotes(previous=>({...previous,[fact.task_id]:value}))}/>}
      </div>)}
      <Action disabled={!brief||!selected.length||(kind==='noon'&&selected.some(id=>!(notes[id]??facts.find(f=>f.task_id===id)?.plan_note??'').trim()))} run={async()=>{
        await runtime.command('brief.confirm',{...entityRef(brief!),actions:available.filter(fact=>selected.includes(fact.task_id)).map(fact=>({task_id:fact.task_id,version:fact.version,kind:kind==='morning'?'focus':'adjust',note:notes[fact.task_id]??fact.plan_note??''}))});setSelected([]);setNotes({});
      }}>{kind==='morning'?'确认所选重点':'保存所选调整'}</Action>
      {brief?.data.status==='acknowledged'&&<p role="status">已确认的安排已同步到任务。</p>}
      <Action disabled={!brief} run={async()=>{await runtime.command('brief.refresh',entityRef(brief!));setSelected([]);setNotes({})}}>更新事实快照</Action>
      <button className="v277-secondary" onClick={()=>go({name:'new-task'})}>补充一个目标</button>
      <p>安排确认不会自动启动任务；运行和结果验收仍由你决定。</p>
    </div></section>
  </>;
}
