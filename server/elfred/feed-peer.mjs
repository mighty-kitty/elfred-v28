import {now} from './store.mjs';
import {DEFAULT_STOP} from './policy.mjs';
import {taskCommand} from './runtime.mjs';
import {resultReceipts} from './agent-plan.mjs';

const peers={explore:'advise',advise:'explore',create:'advise',connect:'advise',execute:'explore'};
const active=['draft','ready','queued','running','pause_requested','cancel_requested'];
const eligible=feed=>feed.data.status==='active'&&!feed.data.access_space&&['outcome','observation','discovery'].includes(feed.data.purpose)&&feed.data.synthetic!==true;
const peerValue=feed=>Number(Boolean(feed.data.artifact_id))*4+Number(Boolean(feed.data.external_url))*3+Math.min(String(feed.data.summary||'').length/120,3)+(/风险|变化|判断|机会|阻塞|合作/.test(String(feed.data.title||'')+String(feed.data.summary||''))?2:0);
/** Approximately 70% no comment, 25% one and 5% two, prioritizing evidenced posts. */
export function peerCommentLimit(feed,allFeeds){
 const pool=allFeeds.filter(item=>item.owner===feed.owner&&eligible(item)).sort((a,b)=>peerValue(b)-peerValue(a)||String(a.created).localeCompare(String(b.created))||a.id.localeCompare(b.id));
 const rank=pool.findIndex(item=>item.id===feed.id);
 if(rank<0)return 0;
 if(rank<Math.floor(pool.length*0.05))return 2;
 return rank<Math.ceil(pool.length*0.30)?1:0;
}
const localDate=(at,timezone)=>new Intl.DateTimeFormat('en-CA',{timeZone:timezone||'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(at);
function commentText(output){
 const lines=String(output).split(/\r?\n/).map(line=>line.replace(/^\s*(?:#{1,6}\s*|[-*•]\s*)/,'').replace(/\*\*/g,'').trim()).filter(line=>line&&!/^(?:目标|任务|审查范围|待核对主张|证据核对|风险与证据|背景|输出要求|应对与停止条件)(?:[:：]|$)/.test(line));
 const useful=lines.find(line=>line.length>=16&&/[。！？]/.test(line))||lines.find(line=>line.length>=16)||lines[0]||'';
 return useful.slice(0,240);
}

export function tickFeedPeerComments(store,provider){
 for(const task of store.list('task').filter(item=>item.data.internal_peer_comment&&item.data.feed_peer_for)){
  const feed=store.get(task.data.feed_peer_for),run=store.get(task.data.run_id);
  if(!feed||feed.owner!==task.owner||feed.data.status!=='active'||(feed.data.comments||[]).some(comment=>comment.task_id===task.id)||active.includes(task.data.status))continue;
  if(!['awaiting_review','awaiting_acceptance','completed'].includes(task.data.status)||!run){
   if(!task.data.peer_comment_failed)store.transaction(()=>{const current=store.get(feed.id),failed=store.get(task.id);store.update(failed,{...failed.data,peer_comment_failed:true},feed.owner);store.update(current,{...current.data,peer_comment_failure_for:task.id,peer_comment_error:'COMMENT_FAILED',peer_comment_retry_after:Date.now()+3600000},feed.owner)});
   continue;
  }
  const output=commentText(resultReceipts(run.data.receipts||[]).find(receipt=>typeof receipt.output==='string'&&receipt.status==='succeeded')?.output||'');
  if(!output){
   if(!task.data.peer_comment_failed)store.transaction(()=>{const current=store.get(feed.id),failed=store.get(task.id);store.update(failed,{...failed.data,peer_comment_failed:true},feed.owner);store.update(current,{...current.data,peer_comment_failure_for:task.id,peer_comment_error:'EMPTY_RESULT',peer_comment_retry_after:Date.now()+3600000},feed.owner)});
   continue;
  }
  store.transaction(()=>{const current=store.get(feed.id),comments=current.data.comments||[];if(comments.some(comment=>comment.task_id===task.id))return;store.update(current,{...current.data,comments:[...comments,{id:task.id,task_id:task.id,reply_to:task.data.feed_peer_reply_to||null,system:task.data.system,content:String(output).slice(0,1200),run_id:run.id,at:now(),status:'模型观点，待用户核对'}],peer_comment_error:null,peer_comment_failure_for:null,peer_comment_retry_after:0},feed.owner)});
 }
 if(provider.status?.().configured!==true)return;
 const allFeeds=store.list('feed');
 for(const feed of allFeeds.filter(item=>eligible(item)&&(item.data.comments||[]).length<peerCommentLimit(item,allFeeds)&&Number(item.data.peer_comment_retry_after||0)<=Date.now()).sort((a,b)=>peerValue(b)-peerValue(a))){
  const settings=store.visible(feed.owner,'settings')[0],policy=settings?.data.feed_peer_comments;
  if(!policy?.enabled||!peers[feed.data.system]||settings?.data.agents?.[peers[feed.data.system]]?.enabled===false)continue;
  const existing=feed.data.comments||[],reply=existing.length===1?existing[0]:null;
  if(reply&&settings?.data.agents?.[feed.data.system]?.enabled===false)continue;
  if(store.list('task').some(task=>task.data.feed_peer_for===feed.id&&!task.data.peer_comment_failed&&!existing.some(comment=>comment.task_id===task.id)))continue;
  const count=store.list('task').filter(task=>task.owner===feed.owner&&task.data.internal_peer_comment&&localDate(Date.parse(task.created),settings?.data.timezone)===localDate(Date.now(),settings?.data.timezone)).length;
  if(count>=policy.daily_limit)continue;
  try{store.transaction(()=>{
   const current=store.get(feed.id),comments=current.data.comments||[];if(current.data.status!=='active'||comments.length>=peerCommentLimit(current,store.list('feed'))||store.list('task').some(task=>task.data.feed_peer_for===feed.id&&!task.data.peer_comment_failed&&!comments.some(comment=>comment.task_id===task.id)))return;
   const responseTo=comments.length===1?comments[0]:null;
   const peer=responseTo?current.data.system:peers[current.data.system],goal=responseTo?`请作为${peer} Agent 回复${responseTo.system} Agent 在你的私人朋友圈动态下的评论。主帖：${String(current.data.title||'').slice(0,160)}。你的原摘要：${String(current.data.summary||'').slice(0,500)}。对方评论：${String(responseTo.content||'').slice(0,400)}。只回应一个具体观点或疑问；不编造来源或已执行行动。仅输出一句自然中文评论，不写目标、审查范围、标题或 Markdown，不超过 120 字。`:`请作为${peer} Agent 评论这条私人朋友圈动态。主帖：${String(current.data.title||'').slice(0,160)}。摘要：${String(current.data.summary||'').slice(0,900)}。从你的专业角度补充一项有依据的判断、风险或下一步问题；不重复主帖，不声称读过未提供的网页，不冒充已执行行动。仅输出一句自然中文评论，不写目标、审查范围、标题或 Markdown，不超过 120 字。`;
   const created=taskCommand(store,feed.owner,'task.create',{goal,system:peer,mode:'compose',review_mode:'single',source_refs:[{id:current.id,version:current.version}],stop:{...DEFAULT_STOP,maxAttempts:1,maxReplans:1,maxCalls:1,maxUnits:1000,maxTokens:4096,maxSeconds:60}});
   let task=store.get(created.id);task=store.update(task,{...task.data,title:responseTo?'朋友圈协作回复':'朋友圈协作评论',internal_peer_comment:true,internal_search:true,feed_peer_for:current.id,feed_peer_reply_to:responseTo?.id||null},feed.owner);
   taskCommand(store,feed.owner,'task.confirm',{id:task.id,version:task.version,confirm:true,model_consent:true});task=store.get(task.id);taskCommand(store,feed.owner,'run.start',{id:task.id,version:task.version});
  });}catch(error){store.transaction(()=>{const current=store.get(feed.id);if(current?.data.status==='active')store.update(current,{...current.data,peer_comment_error:error.code||'TEMPORARY_ERROR',peer_comment_error_detail:String(error.message||'').slice(0,200),peer_comment_retry_after:Date.now()+3600000},feed.owner)});}
  break;
 }
}
