"use client";
import {useRuntime} from '../../core/runtime-context';
import {memoryAdmitted} from '../../core/memory-policy.mjs';
import type {Entity} from '../live/types';
export function TaskMemoryReview({task,selected,onChange}:{task:Entity;selected:string[];onChange:(ids:string[])=>void}){
 const runtime=useRuntime();
 const refs=(task.data.memory_refs||[]) as {id:string;version:number}[];
 const entries=refs.map(ref=>({ref,memory:runtime?.snapshot?.objects.memory.find(m=>m.id===ref.id)}));
 if(!entries.length)return null;
 return <details className="v277-edit-card"><summary>本次使用的理解 · {entries.length} 条</summary><p>后台会根据你对具体结构、语气或安排的真实反馈更新理解；普通验收不会自动升级。这里也可选填补充依据。</p>{entries.map(({ref,memory})=><label style={{display:'block',marginBottom:10}} key={ref.id}><input type="checkbox" disabled={!memory||memory.version!==ref.version||!memoryAdmitted(memory)} checked={selected.includes(ref.id)} onChange={e=>onChange(e.target.checked?[...selected,ref.id]:selected.filter(id=>id!==ref.id))}/>{memory?String(memory.data.content):'这条理解已不可用'}{memory&&memory.version!==ref.version?'（理解已变化，不能为旧版本追加证据）':''}</label>)}</details>;
}
