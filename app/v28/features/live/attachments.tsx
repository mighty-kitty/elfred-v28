"use client";
import {useEffect,useRef,useState} from 'react';
import {useRuntime} from '../../core/runtime-context';
import {MarkdownContent} from '../../core/markdown-content';
import {Action} from '../../core/runtime-panels';
import type {Screen} from '../../core/screen';
export type FileRef={id:string;name:string;mime:string;size:number};
export function AttachmentList({items=[]}:{items?:FileRef[]}){return <div>{items.map(file=><div key={file.id} style={{margin:'8px 0',maxWidth:'100%',overflowWrap:'anywhere'}}>{/\.(md|markdown)$/i.test(file.name)&&file.size<=500000?<MarkdownAttachment file={file}/>:<>{file.mime.startsWith('image/')?<a href={`/api/elfred/attachments/${file.id}`} target="_blank" rel="noreferrer"><img alt={file.name} src={`/api/elfred/attachments/${file.id}`} style={{maxWidth:'100%',maxHeight:220,borderRadius:12,objectFit:'contain'}}/></a>:file.mime.startsWith('video/')?<video controls preload="none" src={`/api/elfred/attachments/${file.id}`} style={{width:'100%',maxHeight:260}}/>:file.mime.startsWith('audio/')?<audio controls preload="none" src={`/api/elfred/attachments/${file.id}`} style={{width:'100%',maxWidth:260}}/>:null}<a href={`/api/elfred/attachments/${file.id}`} target="_blank" rel="noreferrer">{file.name} · {Math.ceil(file.size/1024)} KB</a></>}</div>)}</div>}
function MarkdownAttachment({file}:{file:FileRef}){
 const runtime=useRuntime(),[open,setOpen]=useState(false),[content,setContent]=useState<string|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const preview=async()=>{if(open){setOpen(false);return;}setOpen(true);setBusy(true);setError('');try{if(!runtime)throw new Error('请登录后预览文档');const result=await runtime.request<{text:string}>('/search-input',{id:file.id,preview:true});setContent(result.text);}catch(e){setError(e instanceof Error?e.message:'文档无法读取');setContent(null);}finally{setBusy(false)}};
 return <><button type="button" className="v277-secondary" aria-expanded={open} disabled={busy} onClick={()=>void preview()}>{file.name} · {open?'收起正文':'阅读正文'}</button>{open&&<section className="elfred-file-preview">{busy?<p role="status">正在读取…</p>:error?<p role="alert">{error}</p>:<MarkdownContent text={content||''}/>}</section>}<a href={`/api/elfred/attachments/${file.id}`} download={file.name}>下载原文件 · {Math.ceil(file.size/1024)} KB</a></>;
}
export function AttachmentPicker({value,onChange,conversationId,go,onBusy,accept,allowRecording=true}:{value:FileRef[];onChange:(files:FileRef[])=>void;conversationId?:string;go?:(screen:Screen)=>void;onBusy?:(busy:boolean)=>void;accept?:string;allowRecording?:boolean}){
 const runtime=useRuntime()!,[busy,setBusy]=useState(false),[recording,setRecording]=useState(false),[error,setError]=useState('');
 const recorder=useRef<MediaRecorder|null>(null),stream=useRef<MediaStream|null>(null),timer=useRef<ReturnType<typeof setTimeout>|null>(null),alive=useRef(true),current=useRef(value);
 useEffect(()=>{current.current=value},[value]);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;if(timer.current)clearTimeout(timer.current);if(recorder.current){recorder.current.onstop=null;if(recorder.current.state==='recording')recorder.current.stop();}stream.current?.getTracks().forEach(track=>track.stop());}},[]);
 useEffect(()=>{onBusy?.(busy||recording);return()=>onBusy?.(false)},[busy,recording,onBusy]);
 const upload=async(file:File)=>{
  if(current.current.length>=6)throw new Error('每次最多 6 个附件');if(file.size>8*1024*1024)throw new Error('附件不能超过 8 MB');
  const base64=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('文件读取失败'));reader.readAsDataURL(file)});
  const result=await runtime.command('attachment.upload',{name:file.name,base64,conversation_id:conversationId});
  if(!alive.current)return;const saved=await runtime.request<{data:{name:string;mime:string;size:number}}>('/objects/'+result.id);if(!alive.current)return;const fileRef={id:result.id,name:saved.data.name,mime:saved.data.mime,size:saved.data.size};current.current=[...current.current,fileRef];onChange(current.current);
 };
 const perform=async(work:()=>Promise<void>)=>{setBusy(true);setError('');try{await work()}catch(e){if(alive.current)setError(e instanceof Error?e.message:'附件操作失败')}finally{if(alive.current)setBusy(false)}};
 const record=async()=>{
  if(recording){recorder.current?.stop();return;}
  if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){setError('当前浏览器不支持录音，请上传音频文件');return;}
  await perform(async()=>{const audio=await navigator.mediaDevices.getUserMedia({audio:true});if(!alive.current){audio.getTracks().forEach(t=>t.stop());return;}stream.current=audio;
   const mime=MediaRecorder.isTypeSupported('audio/webm')?'audio/webm':MediaRecorder.isTypeSupported('audio/mp4')?'audio/mp4':'';
   const rec=new MediaRecorder(audio,mime?{mimeType:mime}:{}),chunks:BlobPart[]=[];recorder.current=rec;let size=0;
   rec.ondataavailable=e=>{chunks.push(e.data);size+=e.data.size;if(size>8*1024*1024&&rec.state==='recording')rec.stop()};
   rec.onstop=()=>{if(timer.current)clearTimeout(timer.current);audio.getTracks().forEach(t=>t.stop());setRecording(false);void perform(()=>upload(new File(chunks,`语音-${Date.now()}.${rec.mimeType.includes('mp4')?'m4a':'webm'}`,{type:rec.mimeType})));};rec.start(500);setRecording(true);timer.current=setTimeout(()=>{if(rec.state==='recording')rec.stop()},60000);
  });
 };
 return <section aria-label="附件" style={{margin:'12px 0'}}><label className="v277-field"><span>{busy?'正在处理附件…':'添加图片或文件（每个最大 8 MB）'}</span><input type="file" disabled={busy||recording||value.length>=6} accept={accept||".png,.jpg,.jpeg,.webp,.pdf,.docx,.pptx,.xlsx,.txt,.md,.csv,.json,.zip,.mp3,.m4a,.wav,.ogg,.webm,.mp4"} multiple onChange={e=>{const files=Array.from(e.target.files||[]);e.target.value='';void perform(async()=>{for(const file of files)await upload(file)})}}/></label>{allowRecording&&<button type="button" className="v277-secondary" disabled={busy||value.length>=6} onClick={()=>void record()}>{recording?'停止并保存录音':'录制语音（最长 60 秒）'}</button>}{error&&<p role="alert">{error}</p>}<AttachmentList items={value}/>{value.map(file=><div key={file.id}><button className="v277-secondary" type="button" disabled={busy} onClick={()=>onChange(value.filter(f=>f.id!==file.id))}>移除 {file.name}</button>{go&&/^(image|audio)\//.test(file.mime)&&<Action run={async()=>{const result=await runtime.command('attachment.analyze',{id:file.id});go({name:'task',id:result.id})}}>准备{file.mime.startsWith('audio/')?'转写':'识别'}任务</Action>}{go&&/\.(pdf|docx|pptx|xlsx|txt|md|csv|json)$/i.test(file.name)&&<Action run={async()=>{await runtime.request('/attachment-parse',{id:file.id});await runtime.refresh();runtime.report('已提取文字并保存到资料，可在任务中选择使用。')}}>提取文字保存为资料</Action>}</div>)}</section>;
}
