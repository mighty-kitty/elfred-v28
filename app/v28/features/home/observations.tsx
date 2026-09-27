"use client";
import {displayTitle} from "../../core/display-labels";
import {useState} from 'react';
import {useRuntime,entityRef} from '../../core/runtime-context';
import {Action,Field} from '../../core/runtime-panels';
import {text} from '../live/types';
import type {Screen} from '../../core/screen';

const names:Record<string,string>={draft:'待核对',active:'观察中',paused:'已暂停',blocked:'待处理',ended:'已结束',expired:'已到期',completed:'达到检查次数'};
export function Observations({go,initialGoal=''}:{go:(screen:Screen)=>void;initialGoal?:string}){
 const r=useRuntime(),[mode,setMode]=useState<'rss'|'web'>('rss'),[goal,setGoal]=useState(initialGoal),[url,setUrl]=useState(''),[keywords,setKeywords]=useState(''),[system,setSystem]=useState('explore'),[hours,setHours]=useState('24'),[checks,setChecks]=useState('5'),[days,setDays]=useState('7');
 if(!r?.snapshot)return null;
 const watches=r.snapshot.objects.observation||[];
 return <details className="v277-edit-card"><summary>管理信息源与持续关注</summary>
  <p>你授权的信息源会按间隔检查。手工订阅首次只记录现有条目；初始化启用的自动发现会直接筛选匹配线索，之后持续更新私人 Agent 朋友圈，并保留原文链接供你核对。服务停止期间不补抓历史轮次。</p>
  <label>来源方式 <select value={mode} onChange={event=>setMode(event.target.value as 'rss'|'web')}><option value="rss">RSS / Atom 订阅</option><option value="web">公开网页周期搜索</option></select></label>
  <Field name="关注目标" value={goal} onChange={setGoal} area/>
  {mode==='rss'&&<><Field name="公开 HTTPS RSS / Atom 地址" value={url} onChange={setUrl}/><Field name="关注词（用逗号分隔，1—12 个）" value={keywords} onChange={setKeywords}/><label>负责 Agent <select value={system} onChange={event=>setSystem(event.target.value)}>{r.snapshot.systems.map(agent=><option key={agent.id} value={agent.id}>{agent.name}</option>)}</select></label></>}
  <Field name="间隔（1—168 小时）" type="number" value={hours} onChange={setHours}/><Field name={`最多检查次数（${mode==='rss'?'2':'1'}—20）`} type="number" value={checks} onChange={setChecks}/><Field name="有效天数（1—30）" type="number" value={days} onChange={setDays}/>
  {mode==='web'&&<p>公开网页搜索需单独配置联网检索服务与模型授权，首次建立来源基线；同一网页的正文变化暂不识别。</p>}
  <Action disabled={!goal.trim()||(mode==='rss'&&(!url.trim()||!keywords.trim()))} run={async()=>{await r.command('observation.create',{goal,interval_hours:Number(hours),max_checks:Number(checks),expires:new Date(Date.now()+Number(days)*86400000).toISOString(),...(mode==='rss'?{source_url:url,keywords,system}:{})});setGoal('');setUrl('');setKeywords('')}}>保存订阅草稿</Action>
  {watches.map(w=><article key={w.id} style={{borderTop:'1px solid #e5e8eb',padding:'12px 0'}}><b>{displayTitle(text(w,'title'),'')}</b><p>{names[text(w,'status')]} · 已检查 {String(w.data.checks)}{!w.data.auto_managed&&`/${String(w.data.max_checks)}`} 次 · 每 {String(w.data.interval_hours)} 小时</p>
   {Boolean(w.data.source_url)?<><p>RSS：<a href={text(w,'source_url')} target="_blank" rel="noreferrer">{text(w,'source_url')}</a></p><p>关注词：{((w.data.keywords||[]) as string[]).join('、')} · {r.snapshot!.systems.find(agent=>agent.id===w.data.system)?.name||'探索'} Agent</p><p>{w.data.auto_suggested?'根据已确认的选择筛选公开线索，不需要手工订阅。':'首次检查只建立基线，不发布旧条目。'}</p></>:<p>公开网页 · 总上限 {String(w.data.limit_units)} 本地额度、{String(w.data.max_tokens)} tokens。实际费用以供应商账单为准。</p>}
   <p>{w.data.auto_managed?'持续运行，直到你暂停或结束':`截至 ${new Date(Number(w.data.expires)).toLocaleString('zh-CN')}`}</p>{text(w,'last_error')&&<p role="status">{text(w,'last_error')}</p>}{Boolean(w.data.last_checked_at)&&<p>上次检查：{new Date(text(w,'last_checked_at')).toLocaleString('zh-CN')} · {Number(w.data.last_new_sources)||0} 条新线索</p>}
   {w.data.status==='active'&&<><p>下次检查：{new Date(Number(w.data.next_at)).toLocaleString('zh-CN')}</p><Action run={()=>r.command('observation.pause',entityRef(w))}>暂停</Action></>}
   {['draft','paused','blocked'].includes(text(w,'status'))&&<Action run={()=>r.command('observation.start',{...entityRef(w),confirm:true,...(!w.data.source_url?{model_consent:true}:{})})}>确认来源、频率与期限，{w.data.status==='draft'?'启动':'继续'}</Action>}
   {['draft','active','paused','blocked'].includes(text(w,'status'))&&<Action run={()=>r.command('observation.stop',entityRef(w))}>结束</Action>}
   {Boolean(w.data.task_id)&&<button onClick={()=>go({name:'task',id:text(w,'task_id')})}>查看检查记录与用量</button>}
  </article>)}
 </details>;
}
