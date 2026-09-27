"use client";
import {useEffect,useState} from 'react';
import {ArrowLeft} from 'lucide-react';
import {useRuntime,entityRef} from '../../core/runtime-context';
import {Action} from '../../core/runtime-panels';
import type {Entity} from '../live/types';

export function PlayerModelSettings({task,onClose}:{task?:Entity;onClose:()=>void}){
 const runtime=useRuntime()!,request=runtime.request,defaultModel=runtime.snapshot?.provider.model||'';
 const [catalog,setCatalog]=useState<{items:{id:string}[];reason?:string}|null>(null),[error,setError]=useState('');
 const [model,setModel]=useState(String(task?.data.model_name||defaultModel)),[review,setReview]=useState(String(task?.data.review_mode||'auto'));
 useEffect(()=>{let active=true;void request<{items:{id:string}[];reason?:string}>('/models').then(result=>{if(active)setCatalog(result)}).catch(()=>{if(active)setError('模型列表加载失败，请关闭后重试')});return()=>{active=false}},[request]);
 const editable=task?.data.mode==='compose'&&!task.data.media_operation&&['draft','ready','blocked','failed','partial','paused','cancelled'].includes(String(task.data.status));
 return <section role="dialog" aria-modal="true" aria-label="任务模型设置" className="elfred-player-model-sheet">
  <header><button type="button" aria-label="返回播放器" onClick={onClose}><ArrowLeft size={22}/></button><h2>任务模型设置</h2></header>
  <p>当前模型：{String(task?.data.model_name||defaultModel||'尚未配置')}</p>
  {!catalog&&!error&&<p role="status">正在读取模型列表…</p>}{error&&<p role="alert">{error}</p>}{catalog?.reason&&<p role="status">{catalog.reason}</p>}
  <label className="v277-field"><span>本任务使用的模型</span><select disabled={!editable||!catalog?.items.length} value={model} onChange={event=>setModel(event.target.value)}>{catalog?.items.map(item=><option key={item.id} value={item.id}>{item.id}</option>)}{!catalog?.items.some(item=>item.id===model)&&<option value={model}>{model||'尚未配置'}</option>}</select></label>
  <label className="v277-field"><span>结果复核</span><select disabled={!editable} value={review} onChange={event=>setReview(event.target.value)}><option value="auto">按任务需要复核</option><option value="single">单次生成，由我核对</option><option value="independent">要求独立复核</option></select></label>
  {editable?<><p>修改后需要重新确认任务，才会按新设置运行。</p><Action disabled={!catalog?.items.length||!model||(model===String(task?.data.model_name||defaultModel)&&review===String(task?.data.review_mode||'auto'))} run={async()=>{const current=await runtime.request<Entity>('/objects/'+task!.id);await runtime.command('task.model_settings',{...entityRef(current),model,review_mode:review});onClose()}}>保存本任务设置</Action></>:<p>正在运行或已产生成果的任务保留原设置，先核对成果或停止运行后再修改。</p>}
 </section>;
}
