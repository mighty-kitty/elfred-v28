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
 const runtime=useRuntime();
 if(!post.data.project_id)return null;
 const tags=(runtime?.snapshot?.objects.profile[0]?.data.tags||[]) as string[],matched=tags.find(tag=>typeof tag==='string'&&(text(post,'title')+text(post,'content')+text(post,'task')).includes(tag));
 const slots=(post.data.slots||[]) as {id:string;title:string;capacity:number|null;filled:number;deadline?:string;status:string;terms_changed?:boolean}[];
 const completed=slots.filter(slot=>slot.status==='completed').length,claimed=slots.reduce((count,slot)=>count+slot.filled,0);
 return <section className={styles.card} aria-label="共创任务预览"><header><b>共同完成</b><span>{post.data.status==='recruiting'?'招募中':'招募已结束'}</span></header><p>{text(post,'content')}</p><p className={styles.criteria}>交付：{text(post,'task')}</p>{slots.length>0?<div className={styles.stats}><span>{slots.length} 个角色</span><span>{claimed} 人已参与</span><span>{completed} 项已完成</span></div>:null}{slots.slice(0,3).map(slot=><div key={slot.id} className={styles.task}><span>{displayTitle(slot.title,'')}</span><small>{slot.capacity===null?'人数不限':`剩余 ${Math.max(0,slot.capacity-slot.filled)} 位`}</small></div>)}{slots.length>3&&<small>还有 {slots.length-3} 个角色</small>}<p className={styles.criteria}>截止：{text(post,'deadline')||'暂不设截止'} · 预计投入：{text(post,'time_commitment')||'未约定'}</p><p className={styles.criteria}>{matched?`与你关注的「${matched}」相关；请核对具体要求。`:'查看角色和要求，判断是否适合你。'}</p><button type="button" className={styles.link} onClick={onOpen}><span>查看并参与</span><ChevronRight size={15}/></button></section>;
}
