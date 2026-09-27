"use client";
import {useState} from 'react';
import {X,ChevronRight} from 'lucide-react';
import type {V277State,V277AgentId} from '../../../../v27-7-state';
import type {Screen} from '../../../core/screen';
import {RootPortal} from '../../../legacy/legacy-ui';
import {useRuntime} from '../../../core/runtime-context';
import {agentAlignment,alignmentStages} from '../../../core/agent-alignment.mjs';
import {systemNames} from '../../../core/memory-policy.mjs';
import {HonorGallery} from './honor-gallery';
import styles from '../styles/knowledge.module.css';

export function UnderstandingSheet({go,onClose}:{state:V277State;go:(screen:Screen)=>void;empty?:boolean;onClose:()=>void}){
 const runtime=useRuntime(),[tab,setTab]=useState('understanding');
 const memories=runtime?.snapshot?.objects.memory||[];
 return <RootPortal><div className={styles.sheetBackdrop} onClick={onClose}/><section className={styles.sheet} role="dialog" aria-label="理解与依据">
  <header className={styles.sheetHead}><h2>理解与依据</h2><button className={styles.sheetClose} aria-label="关闭" onClick={onClose}><X size={21}/></button></header>
  <nav className={styles.segTabs}><button className={`${styles.segTab}${tab==='understanding'?' '+styles.segTabOn:''}`} onClick={()=>setTab('understanding')}>领域理解</button><button className={`${styles.segTab}${tab==='honors'?' '+styles.segTabOn:''}`} onClick={()=>setTab('honors')}>荣誉</button></nav>
  {tab==='honors'?<HonorGallery/>:<div className="v277-edit-card"><p>五个领域分别核对；聊天次数、记忆数量不换算成等级或权限。</p>
   {['explore','advise','create','connect','execute'].map(system=>{const summary=agentAlignment(memories,system);return <button className="v277-secondary" style={{display:'flex',width:'100%',justifyContent:'space-between',marginBottom:8}} key={system} onClick={()=>{onClose();go({name:'agent-level',id:(system==='advise'?'advisor':system) as V277AgentId})}}><span>{systemNames[system]} · {summary.label}</span><ChevronRight size={17}/></button>})}
   <details><summary>阶段依据</summary>{alignmentStages.map(stage=><p key={stage.id}><b>{stage.label}</b>：{stage.description}</p>)}</details>
   <button className="v277-secondary" onClick={()=>{onClose();go({name:'memory'})}}>查看、纠正或删除记忆</button>
   <p>{runtime?.snapshot?.memory_hub?.configured?'记忆中枢已配置，同步状态以服务回执为准。':'记忆保存在当前服务；外部记忆中枢接口待配置。'}</p>
  </div>}
 </section></RootPortal>;
}
