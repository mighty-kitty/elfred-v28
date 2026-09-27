"use client";
import {displayTitle} from "../../core/display-labels";
import {useRuntime} from '../../core/runtime-context';
import {type Entity,statuses} from '../live/types';
type Progress={id:string;title:string;status:string;needs_decision:string;updated:string;waiting_on:{id:string;title:string;status:string}[];stages:{id:string;title:string;updated:string}[];participants:{id:string;name:string;system:string|null;status:string;updated:string;dependencies:{id:string;title:string;version:number;status:string}[]}[]};
const states:Record<string,string>={...statuses,not_started:'尚未启动',needs_reconfirmation:'待本人重新确认',dependency_changed:'阶段依据变化，待重验',open:'可认领',closed:'已关闭',unavailable:'已不可用'};
export function ProjectBoard({project}:{project:Entity}){
 const runtime=useRuntime()!,rows=(project.data.progress||[]) as Progress[];
 return <section><h4>任务进度</h4><p role="status">{runtime.syncStatus==='stale'?'同步中断，以下为最后确认状态':Object.keys(runtime.snapshot?.module_errors||{}).length?'部分内容加载失败，请重试':'最近同步'} · {runtime.lastSynced?new Date(runtime.lastSynced).toLocaleString('zh-CN'):'尚未同步'}{(runtime.syncStatus==='stale'||Object.keys(runtime.snapshot?.module_errors||{}).length>0)&&<button onClick={()=>void runtime.refresh().catch(()=>{})}>重新同步</button>}</p>
 {!rows.length&&<p>尚未拆分任务，可先共享阶段成果和讨论。</p>}{rows.map(row=><details key={row.id}><summary>{displayTitle(row.title,'')} · {states[row.status]||row.status}</summary>{row.needs_decision&&<p>{row.needs_decision}</p>}{row.participants.map(p=><article key={p.id}><b>{p.name} · {states[p.status]||p.status}</b><p>更新于 {new Date(p.updated).toLocaleString('zh-CN')}</p>{p.dependencies.map(d=><p key={d.id}>{displayTitle(d.title,'')} · {d.status==='confirmed'?'已核对':d.status==='changed'?'上游有变化，打开本人副本重新选择阶段依据':'来源不可用，需替代资料'}</p>)}</article>)}{row.waiting_on.map(dep=><p key={dep.id}>前置任务：{displayTitle(dep.title,'')} · {states[dep.status]||dep.status}</p>)}{row.stages.map(stage=><p key={stage.id}>已共享过程稿：{displayTitle(stage.title,'')} · {new Date(stage.updated).toLocaleString('zh-CN')}</p>)}<small>这里只展示已约定任务和执行状态，私人指令与未共享正文不进入看板。</small></details>)}</section>;
}
