"use client";
import {displayTitle} from "../../core/display-labels";
import {FollowAuthor} from './community-author';
import {AttachmentPicker,AttachmentList,type FileRef} from '../live/attachments';
import {useState} from 'react';
import {ArrowLeft} from 'lucide-react';
import {useRuntime,entityRef} from '../../core/runtime-context';
import {Action,Field} from '../../core/runtime-panels';
import {type Entity,text} from '../live/types';
import {InlineHtmlPreview} from '../../core/html-preview-component';
import {extractHtmlPreview} from '../../core/inline-html-preview.mjs';
import {CommunityImageGallery} from './community-gallery';
import type {Screen} from '../../core/screen';
import './community-post.css';
type Props={onBack:()=>void;go:(screen:Screen)=>void};
function Header({title,onBack}:{title:string;onBack:()=>void}){return <header className="v277-page-head"><button className="v277-icon-button" aria-label="返回" onClick={onBack}><ArrowLeft size={21}/></button><h1>{title}</h1></header>}
export function CommunityCommentItems({postId}:{postId:string}){
  const runtime=useRuntime()!;
  return <>{runtime.snapshot!.objects.comment.filter(item=>item.data.post_id===postId).map(item=><article className="community-comment" key={item.id}><span className="community-comment-avatar" aria-hidden="true">{text(item,'author_name').slice(0,1)||'人'}</span><div className="community-comment-body"><b>{text(item,'author_name')}</b><InlineHtmlPreview source={text(item,'content')} title="评论中的网页预览"/></div></article>)}</>;
}
export function CommunityComposer({onBack,go}:Props){
  const runtime=useRuntime()!;
  const [attachments,setAttachments]=useState<FileRef[]>([]),[busy,setBusy]=useState(false);
  const [kind,setKind]=useState('post'),[title,setTitle]=useState(''),[content,setContent]=useState(''),[criteria,setCriteria]=useState(''),[task,setTask]=useState(''),[basis,setBasis]=useState(''),[feeTerms,setFeeTerms]=useState('各自承担本人 Agent 与工具费用；发起者承担公共调度费用'),[deadlineMode,setDeadlineMode]=useState('none'),[deadline,setDeadline]=useState(''),[participation,setParticipation]=useState('application');
  const [projectStep,setProjectStep]=useState<'idea'|'publish'>('idea');
  return <main className="v277-page v278-social-detail"><Header title="分享与共创" onBack={onBack}/><section className="v277-edit-card">
    <label className="v277-field"><span>发布类型</span><select value={kind} onChange={e=>{setKind(e.target.value);setProjectStep('idea')}}><option value="post">分享一条社区动态</option><option value="project">发起共创项目</option></select></label>
    {kind==='post'||projectStep==='idea'?<><Field name="标题" value={title} onChange={setTitle}/><Field name={kind==='post'?'正文':'想一起完成什么'} area value={content} onChange={setContent}/></>:<div className="community-project-summary"><b>{title}</b><p>{content}</p><button type="button" onClick={()=>setProjectStep('idea')}>修改目标</button></div>}
    {kind==='post'&&extractHtmlPreview(content)&&<InlineHtmlPreview source={content} title="发布前网页预览"/>}
    {kind==='project'&&projectStep==='idea'&&<><Field name="第一项开放任务" area value={task} onChange={setTask}/><Field name="完成后怎样验收" area value={criteria} onChange={setCriteria}/><Action disabled={!title.trim()||!content.trim()||!task.trim()||!criteria.trim()} run={async()=>setProjectStep('publish')}>下一步：参与与公开设置</Action></>}
    {kind==='project'&&projectStep==='publish'&&<><Field name="已有基础（只填可以公开的内容）" area value={basis} onChange={setBasis}/><label className="v277-field"><span>参与方式</span><select value={participation} onChange={e=>setParticipation(e.target.value)}><option value="application">申请后由发起者批准</option><option value="open">确认本人承诺后参与</option></select></label><Field name="费用说明" area value={feeTerms} onChange={setFeeTerms}/><label className="v277-field"><span>截止设置</span><select value={deadlineMode} onChange={e=>setDeadlineMode(e.target.value)}><option value="none">不设截止</option><option value="date">指定日期</option></select></label>{deadlineMode==='date'&&<label className="v277-field"><span>截止日期</span><input type="date" value={deadline} onChange={e=>setDeadline(e.target.value)}/></label>}<p className="community-project-note">公开范围：仅项目简介、任务与参与约定。工作过程只对项目成员可见；最终由你审核。</p></>}
    {kind==='post'&&<AttachmentPicker value={attachments} onChange={setAttachments} onBusy={setBusy}/>}{kind==='post'&&<p>发布后，社区用户可以查看正文并参与讨论。</p>}
    {(kind==='post'||projectStep==='publish')&&<Action disabled={busy||!title.trim()||!content.trim()||(kind==='project'&&(!basis.trim()||!criteria.trim()||!task.trim()||!feeTerms.trim()||(deadlineMode==='date'&&!deadline)))} run={async()=>{const result=await runtime.command(kind==='post'?'post.create':'project.create',kind==='post'?{title,content,confirm:true,attachment_ids:attachments.map(file=>file.id)}:{title,goal:content,basis,criteria,task,participation,public_scope:'brief',reviewer_id:runtime.snapshot!.user.id,fee_terms:feeTerms,deadline_mode:deadlineMode,deadline});go({name:'community-post',id:result.id})}}>{kind==='post'?'确认公开发布':'保存草稿并预览'}</Action>}
  </section></main>;
}
export function CommunityDiscussion({post,onBack,go}:Props&{post:Entity}){
  const runtime=useRuntime()!,snapshot=runtime.snapshot!;
  const files=(post.data.attachments||[]) as FileRef[];
  const [comment,setComment]=useState(''),[editing,setEditing]=useState(false),[draft,setDraft]=useState({title:text(post,'title'),content:text(post,'content'),version:post.version});
  const [withdraw,setWithdraw]=useState(false);
  const active=(kind:string)=>snapshot.objects.interaction.some(item=>item.data.object_id===post.id&&item.data.kind===kind&&item.data.active);
  return <main className="v277-page v278-social-detail"><Header title="社区动态" onBack={onBack}/><article className="v278-social-article"><small>{text(post,'author_name')} · {new Date(post.created).toLocaleString('zh-CN')}</small><FollowAuthor post={post}/><h2>{displayTitle(text(post,'title'),'')}</h2><InlineHtmlPreview source={text(post,'content')} title="社区网页预览"/><CommunityImageGallery files={files} detail/><AttachmentList items={files.filter(file=>!file.mime.startsWith('image/'))}/>
    <div className="v277-social-actions"><Action run={()=>runtime.command('post.interact',{id:post.id,kind:'like'})}>{active('like')?'取消赞':'点赞'} · {Number(post.data.likes||0)}</Action><Action run={()=>runtime.command('post.interact',{id:post.id,kind:'save'})}>{active('save')?'取消收藏':'收藏'}</Action><Action run={()=>runtime.command('post.interact',{id:post.id,kind:'hide'}).then(()=>go({name:'community'}))}>隐藏此动态</Action></div>
    {post.owner===snapshot.user.id&&<><button className="v277-secondary" onClick={()=>{setDraft({title:text(post,'title'),content:text(post,'content'),version:post.version});setEditing(true)}}>编辑动态</button><button className="v277-secondary" onClick={()=>setWithdraw(true)}>撤下动态</button></>}
    {withdraw&&<div role="alert"><p>撤下后，其他人将无法继续查看这条动态与评论。</p><Action run={async()=>{await runtime.command('post.withdraw',{...entityRef(post),confirm:true});go({name:'community'})}}>确认撤下</Action><button className="v277-secondary" onClick={()=>setWithdraw(false)}>保留动态</button></div>}
    {editing&&<section className="v277-edit-card"><Field name="标题" value={draft.title} onChange={title=>setDraft(old=>({...old,title}))}/><Field name="正文" area value={draft.content} onChange={content=>setDraft(old=>({...old,content}))}/><Action disabled={!draft.title.trim()||!draft.content.trim()} run={async()=>{await runtime.command('post.edit',{id:post.id,...draft,confirm:true});setEditing(false)}}>确认公开更新</Action><button className="v277-secondary" onClick={()=>setEditing(false)}>取消编辑</button></section>}
  </article><section className="v278-comment-list community-comment-list"><h3>讨论</h3><CommunityCommentItems postId={post.id}/><Field name="发表评论" value={comment} onChange={setComment} area/><Action disabled={!comment.trim()} run={async()=>{await runtime.command('post.comment',{id:post.id,content:comment});setComment('')}}>发布评论</Action></section></main>;
}
