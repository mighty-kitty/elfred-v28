"use client";
import {useEffect,useState} from 'react';
import {useRuntime} from '../../core/runtime-context';
import {AppHeader as Header} from '../../legacy/legacy-ui';
import {AttachmentList} from '../live/attachments';
import {assetText,text,type Entity} from '../live/types';

export function SearchSourcePage({id,anchor,onBack}:{id:string;anchor?:string;onBack:()=>void}){
 const runtime=useRuntime()!,request=runtime.request,[object,setObject]=useState<Entity|null>(null),[error,setError]=useState(''),[fileText,setFileText]=useState('');
 const current=Object.values(runtime.snapshot!.objects).flat().find(o=>o.id===id);
 useEffect(()=>{let active=true;setObject(null);setFileText('');setError('');void request<Entity>('/objects/'+id).then(async o=>{if(!active)return;setObject(o);if(o.type==='attachment'&&/^(text\/|application\/json$)/.test(text(o,'mime'))&&Number(o.data.size)<=500000){const parsed=await request<{text:string}>('/search-input',{id:o.id,preview:true});if(active)setFileText(parsed.text);}}).catch(e=>{if(active)setError(e instanceof Error?e.message:'内容不可访问')});return()=>{active=false}},[id,current?.version,request]);
 const published=object?.data.published as {name?:string;bio?:string}|undefined;
 const content=object?.type==='profile'&&object.owner!==runtime.snapshot!.user.id?published?.bio||'':object?fileText||assetText(object)||text(object,'summary')||text(object,'purpose')||text(object,'bio'):'';
 const title=object?.type==='profile'&&object.owner!==runtime.snapshot!.user.id?published?.name:object?text(object,'title')||text(object,'name'):'搜索结果';
 return <main className="v277-page elfred-search-source"><Header title="来源内容" onBack={onBack}/>{error?<p className="v277-empty" role="alert">{error}</p>:!object?<p className="v277-empty" role="status">正在读取…</p>:<section className="elfred-search-source-content"><h2>{title||'来源内容'}</h2>{object.type==='attachment'&&<AttachmentList items={[{id:object.id,name:text(object,'name'),mime:text(object,'mime'),size:Number(object.data.size)}]}/>}<p>{anchor&&content.includes(anchor)?<>{content.slice(0,content.indexOf(anchor))}<mark>{anchor}</mark>{content.slice(content.indexOf(anchor)+anchor.length)}</>:content}</p></section>}</main>;
}
