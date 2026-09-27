"use client";
import {useEffect,useState} from 'react';
import {useRuntime} from '../../core/runtime-context';
import type {Entity} from '../live/types';

export function PlayerRunLog({run}:{run?:Entity}){
 const runtime=useRuntime()!,request=runtime.request,[result,setResult]=useState<{id:string;items:{at:string;message:string}[]}|null>(null),[failed,setFailed]=useState(false);
 const id=run?.id,version=run?.version;
 useEffect(()=>{let active=true;setFailed(false);if(id)void request<{items:{at:string;message:string}[]}>('/runs/'+id+'/logs').then(value=>{if(active)setResult({id,items:value.items})}).catch(()=>{if(active)setFailed(true)});return()=>{active=false}},[id,version,request]);
 const items=result&&result.id===id?result.items:null;
 return <section className="elfred-player-logs" aria-label="实时执行日志" aria-live="polite">{!id?<p>任务启动后，真实执行记录会出现在这里。</p>:failed?<p role="alert">日志暂时加载失败，请重新打开此页。</p>:!items?<p>正在读取执行记录…</p>:!items.length?<p>当前还没有执行记录。</p>:items.map((item,index)=><div key={item.at+':'+index}><time>{new Date(item.at).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}</time><p>{item.message}</p></div>)}</section>;
}
