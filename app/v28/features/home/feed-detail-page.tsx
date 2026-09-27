"use client";
import {displayTitle} from "../../core/display-labels";

import {ArrowLeft} from 'lucide-react';
import {useRuntime} from '../../core/runtime-context';
import type {Screen} from '../../core/screen';
import {text} from '../live/types';
import {FeedDetails} from './feed-details';

export function FeedDetailPage({id,go,onBack}:{id:string;go:(screen:Screen)=>void;onBack:()=>void}){
  const runtime=useRuntime()!;
  const item=runtime.snapshot?.objects.feed.find(candidate=>candidate.id===id);
  return <main className="v277-page" style={{padding:'16px 24px 140px',overflowY:'auto'}}>
    <header style={{display:'flex',alignItems:'center',gap:12,marginBottom:24}}>
      <button type="button" aria-label="返回" onClick={onBack} style={{border:0,background:'transparent',padding:8}}><ArrowLeft size={24}/></button>
      <h1 style={{fontSize:22,margin:0}}>朋友圈动态</h1>
    </header>
    {item?<article style={{lineHeight:1.65,whiteSpace:'pre-wrap'}}>
      <b>{runtime.snapshot?.systems.find(system=>system.id===item.data.system)?.name||'Agent'} Agent</b>
      <small style={{display:'block',color:'#687685'}}>{new Date(item.created).toLocaleString('zh-CN')}</small>
      <h2 style={{fontSize:21,lineHeight:1.35}}>{displayTitle(text(item,'title'),'')}</h2>
      {item.data.synthetic===true&&<p>隔离验收数据，不是真实发现。</p>}
      <p>{text(item,'summary')}</p>
      <FeedDetails item={item} go={go}/>
    </article>:<p>这条动态已不存在或你无权查看。</p>}
  </main>;
}
