"use client";
import {displayTitle} from "../../core/display-labels";
import {ChevronRight,Plus,UsersRound} from 'lucide-react';
import {useRuntime} from '../../core/runtime-context';
import {text} from '../live/types';
import type {Screen} from '../../core/screen';
import './community-entry.css';

export function CommunityEntry({go}:{go:(screen:Screen)=>void}){
 const runtime=useRuntime()!;
 const projects=[...(runtime.snapshot?.objects.project||[])].sort((a,b)=>b.updated.localeCompare(a.updated));
 return <section className="community-entry" aria-label="发布与我的共创">
  <button className="community-entry-compose" onClick={()=>go({name:'community-post',id:'new'})}>
   <span className="community-entry-copy"><strong>分享新发现，一起做点事</strong><small>发布动态，或邀请大家参与共创</small></span>
   <span className="community-entry-add"><Plus size={21} strokeWidth={1.8}/></span>
  </button>
  {projects.length>0&&<details className="community-entry-projects">
   <summary><UsersRound size={18}/><strong>我的共创</strong><span>{projects.length} 个项目</span><ChevronRight size={17}/></summary>
   <div className="community-entry-list">{projects.map(project=><button key={project.id} onClick={()=>go({name:'community-post',id:project.id})}>
    <span><strong>{displayTitle(text(project,'title'),'')}</strong><small>{project.owner===runtime.snapshot?.user.id?'我发起的':'我参与的'} · {project.data.recruiting?'招募中':'协作中'} · 修订 {Number(project.data.revision||0)}</small></span><ChevronRight size={17}/>
   </button>)}</div>
  </details>}
 </section>;
}
