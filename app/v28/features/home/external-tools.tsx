"use client";
import {displayTitle} from "../../core/display-labels";
import {useRuntime} from '../../core/runtime-context';
import {Action} from '../../core/runtime-panels';
import {AttachmentList,type FileRef} from '../live/attachments';
import type {Entity} from '../live/types';
import type {Screen} from '../../core/screen';
export function ExternalTool({operation,goal,go}:{operation:'web_search'|'image_generate';goal:string;go:(screen:Screen)=>void}){
 const r=useRuntime()!,image=operation==='image_generate',publicWeb=!image&&r.snapshot!.provider.public_web==='available'&&r.snapshot!.provider.web_search!=='configured';
 return <details><summary>{image?'生成实际图片':'到互联网继续查找'}{r.snapshot!.provider[operation]==='configured'||publicWeb?'':' · 服务未配置'}</summary><p>{image?'仅将当前描述交给图片服务，生成一张 1024 × 1024 预览图。':'仅将当前问题交给联网服务；这会产生公开网页搜索，所选私人资料不会自动发送。'} {publicWeb?'最多一次公开检索、一次模型整理':'本次最多 1 次请求'}、1000 本地额度。供应商实际费用需按服务账单核对。</p><Action disabled={!goal.trim()||goal.length>(publicWeb?300:3000)} run={async()=>{const result=await r.command('external.prepare',{operation,goal});go({name:'task',id:result.id})}}>准备{image?'图片生成':'联网检索'}任务，核对后启动</Action></details>;
}
export function ExternalResults({task}:{task:Entity}){
 const s=useRuntime()!.snapshot!,run=s.objects.run.find(r=>r.id===task.data.run_id),receipts=(run?.data.receipts||[]) as {attachment_id?:string;citations?:{url:string;title:string}[]}[],files=receipts.flatMap(r=>{const file=s.objects.attachment.find(a=>a.id===r.attachment_id);return file?[{id:file.id,name:String(file.data.name),mime:String(file.data.mime),size:Number(file.data.size)}]:[]}) as FileRef[],citations=receipts.flatMap(r=>r.citations||[]);
 return files.length||citations.length?<section><h3>实际执行结果</h3><AttachmentList items={files}/>{citations.map((c,i)=><p key={c.url+':'+i}><a href={c.url} target="_blank" rel="noreferrer">{i+1}. {displayTitle(c.title,'')}</a></p>)}</section>:null;
}
