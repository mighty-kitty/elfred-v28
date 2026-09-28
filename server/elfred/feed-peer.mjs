import {now} from './store.mjs';
import {DEFAULT_STOP} from './policy.mjs';
import {taskCommand} from './runtime.mjs';
import {resultReceipts} from './agent-plan.mjs';

const peers={explore:'advise',advise:'explore',create:'advise',connect:'advise',execute:'explore'};
const active=['draft','ready','queued','running','pause_requested','cancel_requested'];
const localDate=(at,timezone)=>new Intl.DateTimeFormat('en-CA',{timeZone:timezone||'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(at);

export function tickFeedPeerComments(store,provider){
 for(const task of store.list('task').filter(item=>item.data.internal_peer_comment&&item.data.feed_peer_for)){
  const feed=store.get(task.data.feed_peer_for),run=store.get(task.data.run_id);
  if(!feed||feed.owner!==task.owner||feed.data.status!=='active'||(feed.data.comments||[]).some(comment=>comment.task_id===task.id)||active.includes(task.data.status))continue;
  if(!['awaiting_review','awaiting_acceptance','completed'].includes(task.data.status)||!run)continue;
  const output=resultReceipts(run.data.receipts||[]).find(receipt=>typeof receipt.output==='string'&&receipt.status==='succeeded')?.output;
  if(!output)continue;
  store.transaction(()=>{const current=store.get(feed.id),comments=current.data.comments||[];if(comments.some(comment=>comment.task_id===task.id))return;store.update(current,{...current.data,comments:[...comments,{id:task.id,task_id:task.id,system:task.data.system,content:String(output).slice(0,1200),run_id:run.id,at:now(),status:'模型观点，待用户核对'}]},feed.owner)});
 }
 if(provider.status?.().configured!==true)return;
 for(const feed of store.list('feed').filter(item=>item.data.status==='active'&&!item.data.access_space&&['outcome','observation','discovery'].includes(item.data.purpose)&&!(item.data.comments||[]).length&&Number(item.data.peer_comment_retry_after||0)<=Date.now())){
  const settings=store.visible(feed.owner,'settings')[0],policy=settings?.data.feed_peer_comments;
  if(!policy?.enabled||!peers[feed.data.system]||settings?.data.agents?.[peers[feed.data.system]]?.enabled===false)continue;
  if(store.list('task').some(task=>task.data.feed_peer_for===feed.id))continue;
  const count=store.list('task').filter(task=>task.owner===feed.owner&&task.data.internal_peer_comment&&localDate(Date.parse(task.created),settings?.data.timezone)===localDate(Date.now(),settings?.data.timezone)).length;
  if(count>=policy.daily_limit)continue;
  try{store.transaction(()=>{
   const current=store.get(feed.id);if(current.data.status!=='active'||(current.data.comments||[]).length||store.list('task').some(task=>task.data.feed_peer_for===feed.id))return;
   const peer=peers[current.data.system],goal=`请作为${peer} Agent 评论这条私人朋友圈动态。主帖：${String(current.data.title||'').slice(0,160)}。摘要：${String(current.data.summary||'').slice(0,900)}。从你的专业角度补充一项有依据的判断、风险或下一步问题；不重复主帖，不声称读过未提供的网页，不冒充已执行行动。用自然中文，不超过 120 字。`;
   const created=taskCommand(store,feed.owner,'task.create',{goal,system:peer,mode:'compose',review_mode:'single',source_refs:[{id:current.id,version:current.version}],stop:{...DEFAULT_STOP,maxAttempts:1,maxReplans:1,maxCalls:1,maxUnits:1000,maxTokens:4096,maxSeconds:60}});
   let task=store.get(created.id);task=store.update(task,{...task.data,title:'朋友圈协作评论',internal_peer_comment:true,internal_search:true,feed_peer_for:current.id},feed.owner);
   taskCommand(store,feed.owner,'task.confirm',{id:task.id,version:task.version,confirm:true,model_consent:true});task=store.get(task.id);taskCommand(store,feed.owner,'run.start',{id:task.id,version:task.version});
  });}catch(error){store.transaction(()=>{const current=store.get(feed.id);if(current?.data.status==='active')store.update(current,{...current.data,peer_comment_error:error.code||'TEMPORARY_ERROR',peer_comment_error_detail:String(error.message||'').slice(0,200),peer_comment_retry_after:Date.now()+3600000},feed.owner)});}
  break;
 }
}
