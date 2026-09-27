"use client";
import {displayTitle} from "../../core/display-labels";
import {useState} from 'react';
import {ChevronRight,Plus,Users} from 'lucide-react';
import {AppHeader} from '../../legacy/legacy-ui';
import {useRuntime} from '../../core/runtime-context';
import {Action,Field} from '../../core/runtime-panels';
import type {Screen} from '../../core/screen';
import {text,statuses} from '../live/types';
import styles from './swarm.module.css';
const roles=[['explore','探索','整理方向与依据'],['advise','参谋','比较方案、风险与取舍'],['create','创作','整理完整成果'],['connect','连接','梳理参与者与协作条件'],['execute','执行','安排步骤和验收标准']] as const;
const nameOf=(id:string)=>roles.find(role=>role[0]===id)?.[1]||id;
export function SwarmPage({go,onBack}:{go:(screen:Screen)=>void;onBack:()=>void}){
 const runtime=useRuntime()!,snapshot=runtime.snapshot!;
 const [creating,setCreating]=useState(false),[goal,setGoal]=useState(''),[leader,setLeader]=useState('create'),[mode,setMode]=useState('independent');
 const [members,setMembers]=useState(['explore','advise']),[goals,setGoals]=useState<Record<string,string>>({});
 const [filter,setFilter]=useState('all');
 const tasks=snapshot.objects.task.filter(task=>task.data.status!=='archived'&&(task.data.swarm||(task.data.collaboration_steps as unknown[]|undefined)?.length));
 const bucket=(status:string)=>['running','queued','ready'].includes(status)?'running':['completed','awaiting_acceptance','awaiting_review'].includes(status)?'results':['failed','blocked','partial'].includes(status)?'attention':'draft';
 const selected=roles.map(([id])=>id).filter(id=>id!==leader&&members.includes(id));
 return <main className={`v277-page ${styles.page}`}><AppHeader title="蜂群协作" onBack={onBack}/>
  <header className={styles.intro}><span><Users size={24}/></span><div><h2>一个目标，协作完成</h2><p>分工、依赖与成果放在同一处。</p></div></header>
  <div className={styles.actions}><button onClick={()=>setCreating(!creating)}><Plus size={18}/>{creating?'收起新协作':'发起协作'}</button><button onClick={()=>go({name:'chat',id:'elfred'})}>和我的 Elfred 对话<ChevronRight size={16}/></button></div>
  {creating&&<section className={styles.composer} aria-label="发起蜂群协作"><Field name="共同目标" area value={goal} onChange={setGoal}/><label>由谁汇总成果<select aria-label="主责 Agent" value={leader} onChange={event=>setLeader(event.target.value)}>{roles.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label>
   <p>选择协作分工</p>{roles.filter(([id])=>id!==leader).map(([id,name,duty])=><div key={id} className={styles.assignment}><label><input type="checkbox" checked={members.includes(id)} onChange={event=>setMembers(old=>event.target.checked?[...old,id]:old.filter(value=>value!==id))}/>{name} · {duty}</label>{members.includes(id)&&<Field name={`${name}的具体任务`} value={goals[id]||''} onChange={value=>setGoals(old=>({...old,[id]:value}))}/>}</div>)}
   <label>协作方式<select aria-label="协作方式" value={mode} onChange={event=>setMode(event.target.value)}><option value="independent">各自提供建议，再统一汇总</option><option value="pipeline">按分工顺序接力，再汇总</option></select></label><small>保存后先核对方案和调用额度，再确认启动。这里只使用你写下的目标，已有资料在任务中另选。</small>
   <Action disabled={!goal.trim()||!selected.length} run={async()=>{const result=await runtime.command('swarm.create',{goal,system:leader,mode,steps:selected.map(system=>({system,goal:goals[system]?.trim()||`${roles.find(role=>role[0]===system)![2]}；共同目标：${goal}`})),confirm:true});go({name:'task',id:result.id})}}>保存协作方案</Action>
  </section>}
  <nav className={styles.filters} aria-label="协作状态">{[['all','全部'],['running','进行中'],['results','成果'],['attention','需处理'],['draft','待启动']].map(([id,name])=><button key={id} aria-pressed={filter===id} onClick={()=>setFilter(id)}>{name}</button>)}</nav>
  <section aria-label="协作看板">{tasks.filter(task=>filter==='all'||bucket(text(task,'status'))===filter).map(task=>{
   const run=snapshot.objects.run.find(item=>item.id===task.data.run_id),receipts=(run?.data.receipts||[]) as {step_id:string;status:string}[],steps=(task.data.collaboration_steps||[]) as {id:string;system:string;goal:string;depends:string[]}[];
   return <button key={task.id} className={styles.card} onClick={()=>go({name:'task',id:task.id})}><header><b>{displayTitle(text(task,'title'),'')||text(task,'goal')}</b><small>{statuses[text(task,'status')]||text(task,'status')}</small></header><p>{nameOf(text(task,'system'))}汇总 · {steps.length+1} 位 Agent</p><ul>{steps.map(step=><li key={step.id}><span>{nameOf(step.system)}</span><span>{step.goal}</span><small>{receipts.some(receipt=>receipt.step_id==='collab-'+step.id&&receipt.status==='succeeded')?'已提交建议':step.depends.length?'等待前序结果':'待提交'}</small></li>)}</ul><footer><span>查看分工、过程与成果</span><ChevronRight size={17}/></footer></button>;
  })}{!tasks.some(task=>filter==='all'||bucket(text(task,'status'))===filter)&&<div className={styles.empty}><Users size={28}/><h3>{filter==='all'?'还没有协作事项':'这里暂时没有事项'}</h3><p>{filter==='all'?'写下共同目标，选择分工后即可开始。':'切换其他状态，或发起新的协作。'}</p></div>}</section>
 </main>;
}
