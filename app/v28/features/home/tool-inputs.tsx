"use client";
import {useState} from 'react';
import {useRuntime,entityRef} from '../../core/runtime-context';
import {Action,Field} from '../../core/runtime-panels';
import {type Entity,text} from '../live/types';
import type {Screen} from '../../core/screen';
export type ToolParameter={name:string;required:boolean;hint:string;default_value:string};
export function ParameterEditor({value,onChange}:{value:ToolParameter[];onChange:(next:ToolParameter[])=>void}){
 const update=(i:number,patch:Partial<ToolParameter>)=>onChange(value.map((p,n)=>n===i?{...p,...patch}:p));
 return <details><summary>可重复填写的输入 · {value.length} 项</summary><p>运行前逐项核对，输入只用于本次任务，不会自动保存成长期偏好。</p>{value.map((p,i)=><fieldset key={i}><legend>输入 {i+1}</legend><Field name="输入名称" value={p.name} onChange={name=>update(i,{name})}/><Field name="填写说明" value={p.hint} onChange={hint=>update(i,{hint})}/><Field name="默认内容（可留空）" value={p.default_value} onChange={default_value=>update(i,{default_value})}/><label><input type="checkbox" checked={p.required} onChange={e=>update(i,{required:e.target.checked})}/>运行前必填</label><button type="button" onClick={()=>onChange(value.filter((_,n)=>n!==i))}>移除此输入</button></fieldset>)}<button type="button" disabled={value.length>=8} onClick={()=>onChange([...value,{name:'',required:true,hint:'',default_value:''}])}>添加输入</button></details>;
}
export function ToolRunInputs({tool,goal,setGoal,go,onPreview}:{tool:Entity;goal:string;setGoal:(value:string)=>void;go:(screen:Screen)=>void;onPreview:(id:string)=>void}){
 const runtime=useRuntime()!,schema=(tool.data.parameters||[]) as ToolParameter[],[values,setValues]=useState<Record<string,string>>(()=>Object.fromEntries(schema.map(p=>[p.name,p.default_value]))),missing=schema.some(p=>p.required&&!values[p.name]?.trim());
 return <>{tool.data.kind!=='Mini App'&&<><Field name="本次目标" area value={goal} onChange={setGoal}/>{schema.map(p=><div key={p.name}><Field name={p.name+(p.required?'（必填）':'（可选）')} value={values[p.name]||''} onChange={value=>setValues(old=>({...old,[p.name]:value}))}/>{p.hint&&<small>{p.hint}</small>}</div>)}</>}{[['tool.use','使用工具'],['tool.test','测试此版本']].map(([action,label])=><Action key={action} disabled={missing||!tool.data.version_id||(action==='tool.use'&&tool.data.status!=='active')} run={async()=>{const result=await runtime.command(action,{id:tool.id,version_id:tool.data.version_id,goal,parameters:values});if(result.task_id)go({name:'task',id:result.task_id});else if(result.version_id)onPreview(result.version_id)}}>{label}</Action>)}</>;
}
export function ToolGovernance({tool}:{tool:Entity}){
 const runtime=useRuntime()!,[mastery,setMastery]=useState(text(tool,'mastery')||'unrated'),[days,setDays]=useState(tool.data.idle_days?String(tool.data.idle_days):''),ranks=['unrated','frequent','proficient'],labels=['未标记','常用','熟练'];
 return <details><summary>熟练与闲置状态 · {tool.data.activity==='idle'?'已达到本人设置的闲置时长':tool.data.activity==='archived'?'已归档':'有效'}</summary><p>熟练证据与活跃状态分开记录。归档不删除历史成果，一次失败不会扣除熟练状态。</p><label>本人核对的使用状态<select value={mastery} onChange={e=>setMastery(e.target.value)}>{ranks.map((r,i)=><option key={r} value={r} disabled={i<ranks.indexOf(text(tool,'mastery')||'unrated')}>{labels[i]}</option>)}</select></label><p>常用需重复实际使用，熟练需有本人验收的成果；这不代表 Agent 理解等级或新增权限。</p><Field name="多少天未使用后提示闲置（留空关闭）" type="number" value={days} onChange={setDays}/><Action run={()=>runtime.command('tool.governance',{...entityRef(tool),mastery,idle_days:days?Number(days):null,confirm:true})}>保存使用状态与闲置规则</Action>{Boolean(tool.data.last_used_at)&&<p>最近真实使用：{new Date(text(tool,'last_used_at')).toLocaleString('zh-CN')}</p>}</details>;
}
