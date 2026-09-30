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
  const [roles,setRoles]=useState<string[]>([]),[capacity,setCapacity]=useState(1),[effort,setEffort]=useState('每周 2 小时');
  const [projectStep,setProjectStep]=useState<'idea'|'publish'>('idea');
  return <main className="v277-page v278-social-detail"><Header title="分享与共创" onBack={onBack}/><section className="v277-edit-card">
    <label className="v277-field"><span>发布类型</span><select value={kind} onChange={e=>{setKind(e.target.value);setProjectStep('idea')}}><option value="post">分享一条社区动态</option><option value="project">发起共创项目</option></select></label>
    {kind==='post'||projectStep==='idea'?<><Field name={kind==='post'?'标题':'共创标题（可稍后修改）'} value={title} onChange={setTitle}/><Field name={kind==='post'?'正文':'你想和大家一起完成什么？'} area value={content} onChange={setContent}/></>:<div className="community-project-summary"><b>{title||content.slice(0,40)}</b><p>{content}</p><button type="button" onClick={()=>setProjectStep('idea')}>修改目标</button></div>}
    {kind==='post'&&extractHtmlPreview(content)&&<InlineHtmlPreview source={content} title="发布前网页预览"/>}
    {kind==='project'&&projectStep==='idea'&&<><p>先说清目标，下一步把交付和分工整理成卡片。</p><Action disabled={!content.trim()} run={async()=>setProjectStep('publish')}>继续整理共创要求</Action></>}
    {kind==='project'&&projectStep==='publish'&&<><Field name="最终交付物" area value={task} onChange={setTask}/><Field name="怎样算完成" area value={criteria} onChange={setCriteria}/><p>需要哪些角色？</p><div className="elfred-interest-tags">{['产品','设计','开发','内容','运营'].map(role=><button type="button" key={role} aria-pressed={roles.includes(role)} onClick={()=>setRoles(current=>current.includes(role)?current.filter(item=>item!==role):[...current,role])}>{role}</button>)}</div><label className="v277-field"><span>每个角色需要几人</span><input type="number" min="1" max="20" value={capacity} onChange={event=>setCapacity(Number(event.target.value))}/></label><label className="v277-field"><span>预计投入</span><input value={effort} maxLength={100} onChange={event=>setEffort(event.target.value)}/></label><label className="v277-field"><span>截止设置</span><select value={deadlineMode} onChange={e=>setDeadlineMode(e.target.value)}><option value="none">不设截止</option><option value="date">指定日期</option></select></label>{deadlineMode==='date'&&<label className="v277-field"><span>截止日期</span><input type="date" value={deadline} onChange={e=>setDeadline(e.target.value)}/></label>}<details><summary>背景与参与约定（可展开修改）</summary><Field name="已有基础（只填可以公开的内容）" area value={basis} onChange={setBasis}/><label className="v277-field"><span>参与方式</span><select value={participation} onChange={e=>setParticipation(e.target.value)}><option value="application">申请后由发起者批准</option><option value="open">确认本人承诺后参与</option></select></label><Field name="费用说明" area value={feeTerms} onChange={setFeeTerms}/></details><div className="community-project-summary"><b>发布前预览</b><p>{content}</p><p>交付：{task||'待填写'} · 验收：{criteria||'待填写'}</p><p>角色：{roles.join('、')||'待选择'} · 每个角色 {capacity} 人 · {effort}</p><small>公开仅展示目标、分工和参与约定；工作资料由成员单独授权。</small></div></>}
    {kind==='post'&&<AttachmentPicker value={attachments} onChange={setAttachments} onBusy={setBusy}/>}{kind==='post'&&<p>发布后，社区用户可以查看正文并参与讨论。</p>}
    {(kind==='post'||projectStep==='publish')&&<Action disabled={busy||!content.trim()||(kind==='post'&&!title.trim())||(kind==='project'&&(!criteria.trim()||!task.trim()||!roles.length||!effort.trim()||capacity<1||capacity>20||(deadlineMode==='date'&&!deadline)))} run={async()=>{if(kind==='post'){const result=await runtime.command('post.create',{title,content,confirm:true,attachment_ids:attachments.map(file=>file.id)});go({name:'community-post',id:result.id});return;}const result=await runtime.command('project.create',{title:title.trim()||content.trim().slice(0,60),goal:content,basis:basis.trim()||'暂无可公开的背景资料',criteria,task,participation,public_scope:'brief',reviewer_id:runtime.snapshot!.user.id,fee_terms:feeTerms,deadline_mode:deadlineMode,deadline,time_commitment:effort});for(const role of roles)await runtime.command('project.slot.save',{project_id:result.id,title:`${role} · ${task}`,criteria,capacity,participation,deadline:deadlineMode==='date'?new Date(deadline+'T23:59:59').toISOString():null});go({name:'community-post',id:result.id})}}>{kind==='post'?'确认公开发布':'保存并查看发布预览'}</Action>}
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
