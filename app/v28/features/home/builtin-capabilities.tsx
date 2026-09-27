"use client";
import {Observations} from './observations';
import {ExternalTool} from './external-tools';
import {useState} from 'react';
import {useRuntime} from '../../core/runtime-context';
import {Action,Field} from '../../core/runtime-panels';
import type {Screen} from '../../core/screen';
import {ref,text,type Capability,type Entity} from '../live/types';
const kinds:Record<string,string>={skill:'Skill',check:'检查流程',monitor:'观察流程',tool:'操作流程'};
export function BuiltinCapabilities({system,go,initialId}:{initialId?:string;system?:string;go:(screen:Screen)=>void}){
 const runtime=useRuntime()!,snapshot=runtime.snapshot!;
 const [selected,setSelected]=useState(initialId||''),[goal,setGoal]=useState(''),[sources,setSources]=useState<string[]>([]),[reviewMode,setReviewMode]=useState('auto');
 const availableSources=[...snapshot.objects.document,...snapshot.objects.knowledge,...snapshot.objects.resource].filter(item=>!['rejected','superseded','expired','deleted','needs_review','archived'].includes(text(item,'status')));
 const definitions=snapshot.definitions.filter(item=>!system||item.system===system),current=definitions.find(item=>item.id===selected);
 return <details open={Boolean(initialId)||undefined} className="elfred-builtin-capabilities" style={{margin:'16px 20px',padding:14,border:'1px solid #e0e5e8',borderRadius:18,background:'white',fontSize:13}}><summary style={{cursor:'pointer',fontWeight:700}}>内置专业能力 · {definitions.length} 项</summary><p style={{color:'#77858e',lineHeight:1.7}}>选择专业能力，查看适用范围并创建任务。</p>
  <div style={{display:'flex',gap:6,flexWrap:'wrap'}}>{definitions.map(item=><button type="button" key={item.id} aria-pressed={selected===item.id} onClick={()=>setSelected(item.id)} style={{border:'1px solid #dce2e6',borderRadius:14,padding:'8px 10px',background:selected===item.id?'#20282d':'#f5f7f8',color:selected===item.id?'white':'#35434c',cursor:'pointer'}}>{item.name} · {kinds[item.kind]||'Skill'}</button>)}</div>
  {current&&<section><h3>{current.name}</h3><p>{current.purpose}</p><ol>{current.steps.map(step=><li key={step}>{step}</li>)}</ol><p>交付内容：{current.outputs.join('、')}</p>{current.limitations&&<p style={{color:'#697681'}}>当前范围：{current.limitations}</p>}<Field name="用这项能力完成什么" value={goal} onChange={setGoal} area/>{current.id==='explore-1'&&<Observations go={go} initialGoal={goal}/>} {current.id==='explore-0'&&<ExternalTool operation="web_search" goal={goal} go={go}/>} {current.id==='create-1'&&<ExternalTool operation="image_generate" goal={goal} go={go}/>}<details><summary>本次使用的资料 · 已选 {sources.length}/20</summary><div style={{maxHeight:180,overflowY:'auto',padding:'8px 0'}}>{availableSources.length?availableSources.map(item=><label key={item.id} style={{display:'flex',gap:8,padding:'6px 0',alignItems:'start'}}><input type="checkbox" checked={sources.includes(item.id)} disabled={!sources.includes(item.id)&&sources.length>=20} onChange={event=>setSources(previous=>event.target.checked?[...previous,item.id]:previous.filter(id=>id!==item.id))}/><span>{text(item,'title')||text(item,'name')||item.id}</span></label>):<p>先在知识页添加文档或笔记，再选择本次资料。</p>}</div></details><label className="v277-field"><span>结果复核</span><select value={reviewMode} onChange={event=>setReviewMode(event.target.value)}><option value="auto">按任务需要复核</option><option value="independent">要求独立复核</option></select></label><Action disabled={!goal.trim()} run={async()=>{const result=await runtime.command('task.create',{goal,system:current.system,capability_id:current.id,mode:'compose',review_mode:reviewMode,source_refs:availableSources.filter(item=>sources.includes(item.id)).map(ref)});go({name:'task',id:result.id})}}>创建任务草稿</Action></section>}
 </details>;
}
export function TaskCapability({task,run}:{task:Entity;run?:Entity}){
 const runtime=useRuntime();
 const sources=(task.data.source_refs||[]) as {id:string;version:number}[];
 const known=Object.values(runtime?.snapshot?.objects||{}).flat();
 const frozen=run?.data.version_snapshot as {role?:Capability}|undefined;
 const capability=frozen?.role||task.data.capability as Capability|undefined;
 if(!capability?.kind||task.data.mode!=='compose'||task.data.media_operation)return null;
 const plan=run?.data.plan as {steps?:{phase:string}[];review?:{wanted:boolean;available:boolean;reason:string}}|undefined;
 const checks=(run?.data.verification as {capability_checks?:{status:string;missing_sections?:string[]}}|undefined)?.capability_checks;
 return <details className="v277-edit-card"><summary>本次能力：{capability.name} · {kinds[capability.kind]}</summary><p>{capability.purpose}</p><p>版本 {capability.version} · 仅使用本次选择的资料</p>{sources.length?<ul>{sources.map(source=><li key={source.id}>{text(known.find(item=>item.id===source.id),'title')||text(known.find(item=>item.id===source.id),'name')||'所选资料'} · 版本 {source.version}</li>)}</ul>:<p>本次未选择资料。</p>}{plan?<p>{plan.steps?.some(step=>step.phase==='review')?(plan.steps.some(step=>step.phase==='repair')?'生成后进行独立复核，必要时修订一次。':'生成后进行独立复核；本次额度不含自动修订。'):plan.review?.wanted&&!plan.review.available?'本次调用上限不足以增加模型复核，结果需由你检查。':'一轮生成，结果由你核对。'}</p>:<p>普通任务一轮生成；涉及资料、核验或风险时按需增加复核。</p>}<p>检查项：{capability.checks.join('；')}</p>{capability.limitations&&<p>当前范围：{capability.limitations}</p>}{checks?.status==='needs_review'&&<p>结构检查提示：请核对 {checks.missing_sections?.join('、')}；明确指定其他格式的任务以原要求为准。</p>}</details>;
}
