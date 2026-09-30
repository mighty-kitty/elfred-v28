"use client";
import {useState} from 'react';
import {ArrowLeft} from 'lucide-react';
import {useRuntime,entityRef} from '../../core/runtime-context';
import {agentAlignment,alignmentStages} from '../../core/agent-alignment.mjs';
import {agentGrowth,GROWTH_STAGES} from '../../core/agent-growth.mjs';
import {Action,Field} from '../../core/runtime-panels';
import {MemoryEvidence} from '../../core/memory-evidence';
import {agentList} from '../../../v27-7-data';
import type {V277AgentId} from '../../../v27-7-state';
import type {Screen} from '../../core/screen';
import {text} from '../live/types';

export function AgentLevelPage({id,onBack,go}:{id:V277AgentId;onBack:()=>void;go:(screen:Screen)=>void}) {
  const runtime=useRuntime()!,snapshot=runtime.snapshot!,system=id==='advisor'?'advise':id;
  const summary=agentAlignment(snapshot.objects.memory,system),growth=agentGrowth(snapshot,system),agent=agentList.find(item=>item.id===id)!;
  const [content,setContent]=useState('');
  return <main className="v277-page v278-utility-page">
    <header className="v277-page-head"><button className="v277-icon-button" aria-label="返回" onClick={onBack}><ArrowLeft size={21}/></button><h1>{agent.name} · 等级与理解</h1></header>
    <section className="v279-stage-card"><div><small>当前成长等级</small><h3>L{growth.level} · {growth.stage}</h3><p>{growth.recentReason}。下一步：{growth.nextCondition}。</p><p>已验收 {growth.outcomeCount} 项成果，已验证 {growth.verifiedMemoryCount} 条本领域理解。成长等级不会自动扩大授权。</p></div></section>
    <section className="v277-edit-card"><h3>十五级成长路径</h3>{GROWTH_STAGES.map(stage=><p key={stage.from}><b>L{stage.from}～L{stage.to} · {stage.label}</b>{growth.level>=stage.from&&growth.level<=stage.to?' · 当前阶段':''}</p>)}<p>L6 起要求至少三项本领域真实验收成果。</p></section>
    <section className="v277-edit-card"><h3>具体理解阶段</h3><p>{summary.levelLabel} · {summary.label}。每条理解分别有来源、适用范围和验证状态，不能用成长等级替代。</p></section>
    <section className="v279-level-stats">{alignmentStages.map(stage=><div key={stage.id}><b>{summary.counts[stage.id]}</b><span>{stage.label}</span></div>)}</section>
    <section className="v277-edit-card"><h3>为什么是这个阶段</h3>{!summary.entries.length&&<p>还没有这个领域的理解依据。你可以自愿记录一个目标或偏好。</p>}
      {summary.entries.map(entry=>{const memory=snapshot.objects.memory.find(item=>item.id===entry.id)!;return <article key={entry.id}><h4>{entry.label}</h4><p>{text(memory,'content')}</p><p>适用用途：{text(memory,'usage_purpose')}</p><button className="v277-secondary" onClick={()=>go({name:'memory-detail',id:memory.id})}>查看、修正或撤销这条理解</button>{['candidate','pending_confirmation'].includes(text(memory,'status'))&&<Action run={()=>runtime.command('memory.decide',{...entityRef(memory),decision:'confirm'})}>确认这条理解及范围</Action>}<MemoryEvidence item={memory}/></article>})}
    </section>
    <section className="v277-edit-card"><h3>补充一条明确表达</h3><Field name={`${agent.name}相关的目标、偏好或约束`} value={content} onChange={setContent} area/><Action disabled={!content.trim()} run={async()=>{const result=await runtime.command('memory.create',{content,scope:system,claim_type:'fact',purpose:`用于${agent.name}相关任务，由本人核对范围`});setContent('');go({name:'memory-detail',id:result.id})}}>保存这条理解</Action></section>
    <section className="v277-edit-card"><h3>理解核对说明</h3>{alignmentStages.map(stage=><p key={stage.id}><b>{stage.label}</b>：{stage.description}</p>)}<p>收藏和调用量不自动升级；读取、发送和付款始终遵守单独授权。</p></section>
  </main>;
}
