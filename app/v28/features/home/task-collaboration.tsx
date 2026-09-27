"use client";
import {displayTitle} from "../../core/display-labels";
import {createClientId} from '../../core/client-id';
import {collaborationLimit} from '../../../../server/elfred/review-policy.mjs';
import {useState} from 'react';
import {useRuntime,entityRef} from '../../core/runtime-context';
import {Action,Field} from '../../core/runtime-panels';
import {text,type Entity} from '../live/types';
const labels:Record<string,string>={explore:'探索',advise:'参谋',create:'创作',connect:'连接',execute:'执行'};
type Step={id:string;system:string;goal:string;depends:string[];source_refs:{id:string;version:number}[]};
export function TaskCollaboration({task}:{task:Entity}){
 const runtime=useRuntime()!,snapshot=runtime.snapshot!,saved=(task.data.collaboration_steps||[]) as Step[];
 const [steps,setSteps]=useState<Step[]>(saved),[reviewer,setReviewer]=useState(String(task.data.reviewer_system||''));
 const stepLimit=collaborationLimit({...task,data:{...task.data,reviewer_system:reviewer||null}});
 const refs=(task.data.source_refs||[]) as {id:string;version:number}[],objects=Object.values(snapshot.objects).flat() as Entity[];
 const update=(index:number,patch:Partial<Step>)=>setSteps(old=>old.map((step,i)=>i===index?{...step,...patch}:step));
 const run=snapshot.objects.run.find(r=>r.id===task.data.run_id),receipts=(run?.data.receipts||[]) as {step_id:string;output:unknown}[];
 return <details><summary>跨系统协作{saved.length?` · ${saved.length} 个协作步骤`:''}</summary><p>每步只使用勾选资料和明确依赖的前序结果。按依赖顺序执行，最终成果由{labels[text(task,'system')]}汇总；各系统的建议不能替代事实或本人验收。</p>
 {task.data.status==='draft'?<>
 {steps.map((step,index)=><fieldset key={step.id}><legend>协作 {index+1}</legend><label>参与系统<select aria-label={`协作 ${index+1} 的系统`} value={step.system} onChange={e=>update(index,{system:e.target.value})}>{Object.entries(labels).filter(([id])=>id!==task.data.system).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label><Field name={`协作 ${index+1} 的目标`} area value={step.goal} onChange={goal=>update(index,{goal})}/><p>仅向此系统提供：</p>{refs.length?refs.map(ref=>{const source=objects.find(o=>o.id===ref.id);return <label key={ref.id} style={{display:'block'}}><input type="checkbox" checked={step.source_refs.some(r=>r.id===ref.id)} onChange={e=>update(index,{source_refs:e.target.checked?[...step.source_refs,ref]:step.source_refs.filter(r=>r.id!==ref.id)})}/>{source?displayTitle(text(source,'title'),'')||source.type:'来源不可用'}</label>}):<small>没有选择资料，仅提供本步目标。</small>}
 {index>0&&<p>可使用哪些前序结果：</p>}{steps.slice(0,index).map(prior=><label key={prior.id} style={{display:'block'}}><input type="checkbox" checked={step.depends.includes(prior.id)} onChange={e=>update(index,{depends:e.target.checked?[...step.depends,prior.id]:step.depends.filter(id=>id!==prior.id)})}/>{labels[prior.system]}：{prior.goal||'尚未填写目标'}</label>)}<button type="button" onClick={()=>setSteps(old=>old.filter(s=>s.id!==step.id).map(s=>({...s,depends:s.depends.filter(id=>id!==step.id)})))}>移除此步骤</button></fieldset>)}
 <button type="button" disabled={steps.length>=stepLimit} onClick={()=>setSteps(old=>[...old,{id:'step-'+createClientId(),system:Object.keys(labels).find(id=>id!==task.data.system)!,goal:'',depends:[],source_refs:[]}])}>添加协作步骤</button>
 <label className="v277-field">成果复核<select value={reviewer} onChange={e=>setReviewer(e.target.value)}><option value="">遵循任务原有复核设置</option>{Object.entries(labels).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label><p>复核会读取主责任务的所选资料和主责成果。跨系统授权不适用时会提示重新核对。转交主责后需重新配置协作。</p><p>当前范围最多 {stepLimit} 个协作步骤，已为主责与所需复核预留位置。</p><Action disabled={steps.length>stepLimit||steps.some(s=>!s.goal.trim())} run={()=>runtime.command('task.collaboration',{...entityRef(task),steps,reviewer_system:reviewer||null,confirm:true})}>确认协作目标、资料与依赖</Action>
 </>:saved.map((step,index)=><article key={step.id}><b>{index+1}. {labels[step.system]}：{step.goal}</b><p>{step.source_refs.length} 项资料 · {step.depends.length} 项前序结果</p>{receipts.filter(r=>r.step_id==='collab-'+step.id).map(r=><pre key={r.step_id} style={{whiteSpace:'pre-wrap'}}>{String(r.output)}</pre>)}</article>)}
 </details>;
}
