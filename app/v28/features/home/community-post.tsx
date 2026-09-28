"use client";
import {displayTitle} from "../../core/display-labels";
import {FollowAuthor} from './community-author';
import {AttachmentPicker,AttachmentList,type FileRef} from '../live/attachments';
import {useState} from 'react';
import {ArrowLeft} from 'lucide-react';
import {useRuntime,entityRef} from '../../core/runtime-context';
import {Action,Field} from '../../core/runtime-panels';
import {type Entity,text} from '../live/types';
import {InlineHtmlPreview} from '../../core/inline-html-preview';
import {extractHtmlPreview} from '../../core/inline-html-preview.mjs';
import type {Screen} from '../../core/screen';
type Props={onBack:()=>void;go:(screen:Screen)=>void};
function Header({title,onBack}:{title:string;onBack:()=>void}){return <header className="v277-page-head"><button className="v277-icon-button" aria-label="返回" onClick={onBack}><ArrowLeft size={21}/></button><h1>{title}</h1></header>}
export function CommunityComposer({onBack,go}:Props){
  const runtime=useRuntime()!;
  const [attachments,setAttachments]=useState<FileRef[]>([]),[busy,setBusy]=useState(false);
  const [kind,setKind]=useState('post'),[title,setTitle]=useState(''),[content,setContent]=useState(''),[criteria,setCriteria]=useState(''),[task,setTask]=useState(''),[basis,setBasis]=useState(''),[feeTerms,setFeeTerms]=useState('各自承担本人 Agent 与工具费用；发起者承担公共调度费用'),[deadlineMode,setDeadlineMode]=useState('none'),[deadline,setDeadline]=useState(''),[participation,setParticipation]=useState('application');
  return <main className="v277-page v278-social-detail"><Header title="分享与共创" onBack={onBack}/><section className="v277-edit-card">
    <label className="v277-field"><span>发布类型</span><select value={kind} onChange={e=>setKind(e.target.value)}><option value="post">分享一条社区动态</option><option value="project">发起共创项目</option></select></label>
    <Field name="标题" value={title} onChange={setTitle}/><Field name={kind==='post'?'正文':'共同目标'} area value={content} onChange={setContent}/>
    {kind==='post'&&extractHtmlPreview(content)&&<InlineHtmlPreview source={content} title="发布前网页预览"/>}
    {kind==='project'&&<><Field name="已有基础（只填可以公开的内容）" area value={basis} onChange={setBasis}/><Field name="验收标准" area value={criteria} onChange={setCriteria}/><Field name="开放任务" area value={task} onChange={setTask}/><label className="v277-field"><span>参与方式</span><select value={participation} onChange={e=>setParticipation(e.target.value)}><option value="application">申请后由发起者批准</option><option value="open">确认本人承诺后参与</option></select></label><label className="v277-field"><span>公开范围</span><select value="brief" disabled><option value="brief">公开项目简介、已有基础和招募任务；工作过程仅成员可见</option></select></label><p>审核负责人：你（项目发起者）</p><Field name="费用说明" area value={feeTerms} onChange={setFeeTerms}/><label className="v277-field"><span>截止设置</span><select value={deadlineMode} onChange={e=>setDeadlineMode(e.target.value)}><option value="none">不设截止</option><option value="date">指定日期</option></select></label>{deadlineMode==='date'&&<label className="v277-field"><span>截止日期</span><input type="date" value={deadline} onChange={e=>setDeadline(e.target.value)}/></label>}</>}
    {kind==='post'&&<AttachmentPicker value={attachments} onChange={setAttachments} onBusy={setBusy}/>}<p>{kind==='post'?'发布后，社区用户可以查看正文并参与讨论。':'先保存私有项目，再由你确认是否公开招募。'}</p>
    <Action disabled={busy||!title.trim()||!content.trim()||(kind==='project'&&(!basis.trim()||!criteria.trim()||!task.trim()||!feeTerms.trim()||(deadlineMode==='date'&&!deadline)))} run={async()=>{const result=await runtime.command(kind==='post'?'post.create':'project.create',kind==='post'?{title,content,confirm:true,attachment_ids:attachments.map(file=>file.id)}:{title,goal:content,basis,criteria,task,participation,public_scope:'brief',reviewer_id:runtime.snapshot!.user.id,fee_terms:feeTerms,deadline_mode:deadlineMode,deadline});go({name:'community-post',id:result.id})}}>{kind==='post'?'确认公开发布':'保存私有项目并预览'}</Action>
  </section></main>;
}
export function CommunityDiscussion({post,onBack,go}:Props&{post:Entity}){
  const runtime=useRuntime()!,snapshot=runtime.snapshot!;
  const [comment,setComment]=useState(''),[editing,setEditing]=useState(false),[draft,setDraft]=useState({title:text(post,'title'),content:text(post,'content'),version:post.version});
  const [withdraw,setWithdraw]=useState(false);
  const active=(kind:string)=>snapshot.objects.interaction.some(item=>item.data.object_id===post.id&&item.data.kind===kind&&item.data.active);
  return <main className="v277-page v278-social-detail"><Header title="社区动态" onBack={onBack}/><article className="v278-social-article"><small>{text(post,'author_name')} · {new Date(post.created).toLocaleString('zh-CN')}</small><FollowAuthor post={post}/><h2>{displayTitle(text(post,'title'),'')}</h2><InlineHtmlPreview source={text(post,'content')} title="社区网页预览"/><AttachmentList items={(post.data.attachments||[]) as FileRef[]}/>
    <div className="v277-social-actions"><Action run={()=>runtime.command('post.interact',{id:post.id,kind:'like'})}>{active('like')?'取消赞':'点赞'} · {Number(post.data.likes||0)}</Action><Action run={()=>runtime.command('post.interact',{id:post.id,kind:'save'})}>{active('save')?'取消收藏':'收藏'}</Action><Action run={()=>runtime.command('post.interact',{id:post.id,kind:'hide'}).then(()=>go({name:'community'}))}>隐藏此动态</Action></div>
    {post.owner===snapshot.user.id&&<><button className="v277-secondary" onClick={()=>{setDraft({title:text(post,'title'),content:text(post,'content'),version:post.version});setEditing(true)}}>编辑动态</button><button className="v277-secondary" onClick={()=>setWithdraw(true)}>撤下动态</button></>}
    {withdraw&&<div role="alert"><p>撤下后，其他人将无法继续查看这条动态与评论。</p><Action run={async()=>{await runtime.command('post.withdraw',{...entityRef(post),confirm:true});go({name:'community'})}}>确认撤下</Action><button className="v277-secondary" onClick={()=>setWithdraw(false)}>保留动态</button></div>}
    {editing&&<section className="v277-edit-card"><Field name="标题" value={draft.title} onChange={title=>setDraft(old=>({...old,title}))}/><Field name="正文" area value={draft.content} onChange={content=>setDraft(old=>({...old,content}))}/><Action disabled={!draft.title.trim()||!draft.content.trim()} run={async()=>{await runtime.command('post.edit',{id:post.id,...draft,confirm:true});setEditing(false)}}>确认公开更新</Action><button className="v277-secondary" onClick={()=>setEditing(false)}>取消编辑</button></section>}
  </article><section className="v278-comment-list"><h3>讨论</h3>{snapshot.objects.comment.filter(item=>item.data.post_id===post.id).map(item=><article key={item.id}><b>{text(item,'author_name')}</b><InlineHtmlPreview source={text(item,'content')} title="评论中的网页预览"/></article>)}<Field name="发表评论" value={comment} onChange={setComment} area/><Action disabled={!comment.trim()} run={async()=>{await runtime.command('post.comment',{id:post.id,content:comment});setComment('')}}>发布评论</Action></section></main>;
}
