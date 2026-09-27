"use client";
import {useRuntime} from '../../core/runtime-context';
import type {Entity} from '../live/types';
export function TaskMemoryReview({task,selected,onChange}:{task:Entity;selected:string[];onChange:(ids:string[])=>void}){
 const runtime=useRuntime();
 const refs=(task.data.memory_refs||[]) as {id:string;version:number}[];
 const entries=refs.map(ref=>({ref,memory:runtime?.snapshot?.objects.memory.find(m=>m.id===ref.id)}));
 if(!entries.length)return null;
 return <details className="v277-edit-card"><summary>本次使用的理解 · {entries.length} 条</summary><p>验收成果不等于验证偏好。只有本次结果确实符合这条理解的适用范围时，才勾选记录场景证据。</p>{entries.map(({ref,memory})=><label style={{display:'block',marginBottom:10}} key={ref.id}><input type="checkbox" disabled={!memory||memory.version!==ref.version||memory.data.status!=='validated'} checked={selected.includes(ref.id)} onChange={e=>onChange(e.target.checked?[...selected,ref.id]:selected.filter(id=>id!==ref.id))}/>{memory?String(memory.data.content):'这条理解已不可用'}{memory&&memory.version!==ref.version?'（理解已变化，不能为旧版本追加证据）':''}</label>)}</details>;
}
