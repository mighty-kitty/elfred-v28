"use client";
import {displayTitle} from "./display-labels";
import {plannedModelUnits} from '../../../server/elfred/review-policy.mjs';
import {useState} from 'react';
import {useRuntime,entityRef} from './runtime-context';
import {Action,Field,label} from './runtime-panels';
import {type Entity,text} from '../features/live/types';
import type {Screen} from './screen';

export function ImprovementPanel({go}:{go:(screen:Screen)=>void}) {
  const runtime=useRuntime()!,snapshot=runtime.snapshot!;
  const [task,setTask]=useState(''),[trace,setTrace]=useState(''),[title,setTitle]=useState(''),[prompt,setPrompt]=useState('');
  return <section className="v277-edit-card"><h3>方法改进与版本</h3><p>从真实轨迹提取候选方法，在两项留出任务上运行并由本人逐项比较后，才可用于未来任务。</p>
    <label className="v277-field"><span>轨迹来源任务</span><select value={task} onChange={e=>setTask(e.target.value)}><option value="">选择已产生结果的任务</option>{snapshot.objects.task.filter(item=>['completed','partial','failed','awaiting_review','awaiting_acceptance'].includes(text(item,'status'))).map(item=><option key={item.id} value={item.id}>{displayTitle(text(item,'title'),'')}</option>)}</select></label><Action disabled={!task} run={()=>runtime.command('trace.extract',{task_id:task})}>提取轨迹快照</Action>
    <label className="v277-field"><span>候选方法来源</span><select value={trace} onChange={e=>setTrace(e.target.value)}><option value="">选择轨迹</option>{snapshot.objects.trace.map(item=><option key={item.id} value={item.id}>{text(item,'goal')}</option>)}</select></label><Field name="候选方法名称" value={title} onChange={setTitle}/><Field name="方法正文（未来模型指令）" value={prompt} onChange={setPrompt} area/><Action disabled={!trace||!title.trim()||!prompt.trim()} run={()=>runtime.command('candidate.create',{trace_id:trace,title,prompt})}>保存离线候选</Action>
    {snapshot.objects.candidate.map(item=><Candidate key={item.id} item={item}/>)}
    {(snapshot.objects.evaluation||[]).map(item=><Evaluation key={item.id} item={item} go={go}/>)}
    {snapshot.objects.method.map(item=><div key={item.id}><h4>{displayTitle(text(item,'title'),'')} · {item.data.active?'未来任务生效':'历史版本'}</h4><p>{text(item,'prompt')}</p><Action run={()=>runtime.command('method.rollback',{id:item.id,confirm:true})}>确认将未来任务切换到此版</Action></div>)}
    {snapshot.objects.method.some(item=>item.data.active)&&<Action run={()=>runtime.command('method.rollback',{confirm:true})}>确认回滚到内置方法</Action>}
  </section>;
}
function Candidate({item}:{item:Entity}) {
  const runtime=useRuntime()!,snapshot=runtime.snapshot!;
  const [selected,setSelected]=useState<string[]>([]),[consent,setConsent]=useState(false);
  const units=snapshot.objects.task.filter(t=>selected.includes(t.id)).reduce((sum,t)=>sum+plannedModelUnits(t),0);
  return <article className="v277-edit-card"><h4>{displayTitle(text(item,'title'),'')} · 离线候选</h4><p>{text(item,'prompt')}</p><p>选择两项已验收的模型任务作为留出基线：</p>{snapshot.objects.task.filter(task=>task.data.mode==='compose'&&task.data.status==='completed'&&task.id!==item.data.training_task).map(task=><label key={task.id}><input type="checkbox" checked={selected.includes(task.id)} onChange={()=>setSelected(prev=>prev.includes(task.id)?prev.filter(id=>id!==task.id):[...prev,task.id])}/>{displayTitle(text(task,'title'),'')}</label>)}<label><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>确认向已配置模型发送两项目标与原授权资料，最多预留 {units} 本地调用额度（含可能的复核与修订）</label><Action disabled={selected.length!==2||!consent} run={()=>runtime.command('candidate.evaluate',{...entityRef(item),task_ids:selected,confirm:true,model_consent:true})}>运行留出评估</Action></article>;
}
function Evaluation({item,go}:{item:Entity;go:(screen:Screen)=>void}) {
  const runtime=useRuntime()!;
  const tests=item.data.tests as {run_id:string;task_id:string;baseline_task:string}[];
  const [notes,setNotes]=useState<Record<string,string>>({}),[passed,setPassed]=useState<Record<string,boolean>>({});
  return <article className="v277-edit-card"><h4>留出评估 · {label(item)}</h4>{tests.map(test=><section key={test.run_id}><button className="v277-secondary" onClick={()=>go({name:'task',id:test.baseline_task})}>查看已验收基线</button><button className="v277-secondary" onClick={()=>go({name:'task',id:test.task_id})}>查看候选实际结果</button>{item.data.status==='running'&&<><Field name="与基线相比的改进、退步和验收依据" value={notes[test.run_id]||''} onChange={value=>setNotes(prev=>({...prev,[test.run_id]:value}))} area/><label><input type="checkbox" checked={passed[test.run_id]||false} onChange={e=>setPassed(prev=>({...prev,[test.run_id]:e.target.checked}))}/>本人确认该项来源、完成标准和边界均通过</label></>}</section>)}{item.data.status==='running'&&<Action disabled={tests.some(test=>!notes[test.run_id]?.trim())} run={()=>runtime.command('evaluation.review',{...entityRef(item),confirm:true,reviews:tests.map(test=>({run_id:test.run_id,note:notes[test.run_id],passed:passed[test.run_id]===true}))})}>提交两项审查结论</Action>}{item.data.status==='passed'&&<Action run={()=>runtime.command('method.release',{evaluation_id:item.id,confirm:true})}>确认将通过评估的方法发布给未来任务</Action>}</article>;
}
