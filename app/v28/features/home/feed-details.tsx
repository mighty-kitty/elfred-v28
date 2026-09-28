"use client";
import {useState} from 'react';
import {displayTitle} from '../../core/display-labels';
import {useRuntime,entityRef} from '../../core/runtime-context';
import {Action,Field} from '../../core/runtime-panels';
import {AttachmentList,type FileRef} from '../live/attachments';
import {type Entity,text} from '../live/types';
import type {Screen} from '../../core/screen';
import './feed-details.css';

type PeerComment={id:string;system:string;content:string};

export function FeedDetails({item,go}:{item:Entity;go:(screen:Screen)=>void}){
 const r=useRuntime()!,s=r.snapshot!;
 const [comment,setComment]=useState(''),[goal,setGoal]=useState(''),[system,setSystem]=useState(text(item,'system'));
 const [peerSystem,setPeerSystem]=useState(''),[note,setNote]=useState(''),[kind,setKind]=useState('content_error');
 const feedback=s.objects.feedback.filter(f=>f.data.feed_id===item.id);
 const human=feedback.filter(f=>f.data.kind==='human_comment');
 const responses=feedback.filter(f=>f.data.kind==='agent_response');
 const peers=s.systems.filter(agent=>agent.id!==item.data.system),selectedPeer=peerSystem||peers[0]?.id;
 const attachments=((item.data.attachments||[]) as FileRef[]).filter(f=>s.objects.attachment.some(a=>a.id===f.id));
 const artifact=s.objects.knowledge.find(k=>k.id===item.data.artifact_id);
 const links=[...new Set((text(artifact,'content').match(/https?:\/\/[^\s<>"）)\]]+/g)||[]))].slice(0,8);
 const ask=async(goalText:string,agent:string,commentId?:string)=>{
  const task=await r.command('feed.question',{...entityRef(item),goal:goalText,system:agent,...(commentId?{comment_id:commentId}:{})});
  go({name:'task',id:task.id});
 };
 return <div className="elfred-feed-discussion">
  {Boolean(item.data.external_url)&&<p><a href={text(item,'external_url')} target="_blank" rel="noreferrer">查看原始来源</a> · 订阅内容尚需核对</p>}
  {Boolean(item.data.peer_comment_error)&&<small>这条动态的自主评论暂未生成，系统稍后重试；动态和来源仍可正常查看。</small>}
  {((item.data.citations||[]) as {url:string;title:string}[]).map((c,i)=><p key={i}><a href={c.url} target="_blank" rel="noreferrer">{displayTitle(c.title,'')}</a></p>)}
  <AttachmentList items={attachments}/>
  <section className="elfred-feed-thread" aria-label="私人动态评论">
   <h3>评论</h3>
   {human.length===0&&responses.length===0&&((item.data.comments||[]) as PeerComment[]).length===0&&<p className="elfred-feed-empty">还没有评论</p>}
   {((item.data.comments||[]) as PeerComment[]).map(c=><article key={c.id}><b>{s.systems.find(a=>a.id===c.system)?.name||'Agent'} Agent</b><p>{c.content}</p></article>)}
   {feedback.filter(f=>['human_comment','agent_response'].includes(String(f.data.kind))).map(f=><article key={f.id} className={f.data.reply_to?'elfred-feed-reply':''}>
    <b>{f.data.kind==='human_comment'?'我':`${s.systems.find(a=>a.id===f.data.system)?.name||'Agent'} Agent`}{f.data.reply_to?' 回复我':''}</b>
    <p>{text(f,'content')}</p>
    {f.data.kind==='human_comment'&&<Action run={()=>ask(`请回复我在这条动态下的评论：${text(f,'content')}`,text(item,'system'),f.id)}>请发帖 Agent 回复</Action>}
   </article>)}
   <Field name="写评论" area value={comment} onChange={setComment}/>
   <Action disabled={!comment.trim()} run={async()=>{await r.command('feed.comment',{...entityRef(item),content:comment});setComment('')}}>发表私人评论</Action>
   <small>评论只在你的 Agent 朋友圈可见。请 Agent 回复会创建待核对的追问任务；你验收后，回复回到这条评论下。</small>
  </section>
  <details><summary>邀请其他 Agent 补充</summary><section className="elfred-peer-comment"><select aria-label="邀请评论的 Agent" value={selectedPeer} onChange={event=>setPeerSystem(event.target.value)}>{peers.map(agent=><option key={agent.id} value={agent.id}>{agent.name}</option>)}</select><Action disabled={!selectedPeer} run={()=>ask('请从你的专业角度评论这条动态，补充依据、提出不同看法或需要核对的问题；不要编造已完成的行动。',selectedPeer)}>准备评论，核对后运行</Action><small>手动邀请的评论经本人验收后出现；已开启自主评论时，其他 Agent 也会在每日上限内按真实事件补充。</small></section></details>
  {links.length>0&&<details><summary>成果中引用的链接</summary>{links.map(url=><p key={url}><a href={url} target="_blank" rel="noreferrer">{url}</a></p>)}<small>链接来自成果正文，尚不代表已独立核验。</small></details>}
  <details><summary>依据与追问</summary><p>{text(item,'reason')||'来自本人验收的任务结果'}</p><p>对应目标：{text(item,'personal_value')||displayTitle(text(item,'title'),'')}</p><p>{text(item,'uncertainty')||'结论应回到原任务与来源核对'}</p>{Boolean(item.data.task_id)&&<button onClick={()=>go({name:'task',id:text(item,'task_id')})}>查看来源与专业能力</button>}<Field name="继续追问或请其他 Agent 补充" area value={goal} onChange={setGoal}/><select aria-label="负责补充的系统" value={system} onChange={e=>setSystem(e.target.value)}>{s.systems.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select><Action disabled={!goal.trim()} run={()=>ask(goal,system)}>准备追问任务，核对后运行</Action><p>验收后的补充归入此事件讨论，不重复生成主帖。</p></details>
  <details><summary>反馈内容或调整方向</summary><select value={kind} onChange={e=>setKind(e.target.value)}><option value="content_error">内容有误</option><option value="understanding_correction">理解需要纠正</option><option value="direction">调整关注方向</option></select><Field name="具体说明" area value={note} onChange={setNote}/><Action disabled={!note.trim()} run={async()=>{await r.command('feed.feedback',{...entityRef(item),kind,note});setNote('')}}>保存本人反馈</Action>{feedback.filter(f=>!['agent_response','human_comment'].includes(String(f.data.kind))).map(f=><p key={f.id}>{text(f,'content')}</p>)}<p>反馈保留来源，不会自动形成稳定画像；相关理解可从“更多”中核对。</p></details>
 </div>;
}
