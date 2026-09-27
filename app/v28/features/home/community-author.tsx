"use client";
import {displayTitle} from "../../core/display-labels";
import {useRuntime} from '../../core/runtime-context';
import {Action} from '../../core/runtime-panels';
import {type Entity,text} from '../live/types';
import {ChevronRight} from 'lucide-react';
import styles from './community-card.module.css';
export function FollowAuthor({post}:{post:Entity}){
 const r=useRuntime()!,s=r.snapshot!;if(post.owner===s.user.id)return null;const active=s.objects.interaction.some(i=>i.data.kind==='follow_author'&&i.data.object_id===post.owner&&i.data.active);
 return <Action run={()=>r.command('post.follow_author',{id:post.id})}>{active?'取消关注作者':'关注作者'}</Action>;
}
export function RecruitmentSummary({post,onOpen}:{post:Entity;onOpen:()=>void}){
 if(!post.data.project_id)return null;
 const slots=(post.data.slots||[]) as {id:string;title:string;capacity:number|null;filled:number;deadline?:string;status:string;terms_changed?:boolean}[];
 const completed=slots.filter(slot=>slot.status==='completed').length,claimed=slots.reduce((count,slot)=>count+slot.filled,0);
 return <section className={styles.card} aria-label="共创任务预览"><header><b>共同完成</b><span>{post.data.status==='recruiting'?'招募中':'招募已结束'}</span></header>{slots.length>0?<div className={styles.stats}><span>{slots.length} 项分工</span><span>{claimed} 个参与名额已认领</span><span>{completed} 项已完成</span></div>:<div className={styles.task}><span>{text(post,'task')}</span><small>共同任务</small></div>}{slots.slice(0,3).map(slot=><div key={slot.id} className={styles.task}><span>{displayTitle(slot.title,'')}</span><small>{slot.terms_changed?'约定待核对':slot.status==='completed'?'已完成':slot.status==='open'?'可参与':'已关闭'}</small></div>)}{slots.length>3&&<small>还有 {slots.length-3} 项分工</small>}<p className={styles.criteria}>验收：{text(post,'criteria')}</p><button type="button" className={styles.link} onClick={onOpen}><span>查看协作过程与成果</span><ChevronRight size={15}/></button></section>;
}
