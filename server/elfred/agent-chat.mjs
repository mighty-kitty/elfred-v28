import {fail,now} from './store.mjs';
import {enumeration,string} from './policy.mjs';
import {taskCommand} from './runtime.mjs';
import {resultReceipts} from './agent-plan.mjs';
import {recentChatMessages} from './agent-chat-context.mjs';
import {search} from './knowledge.mjs';
import {captureMemories} from './memory-learning.mjs';
import {dialogueMemoryFeedback} from './memory-feedback.mjs';
import {webIntent} from './public-web.mjs';
import {toolLibraryCommand} from './tool-library.mjs';

const SYSTEMS=['explore','advise','create','connect','execute'];
const NAMES={explore:'探索',advise:'参谋',create:'创作',connect:'连接',execute:'执行'};

function history(store,user,conversation){
  return store.visible(user,'message').filter(item=>item.data.conversation_id===conversation.id)
    .sort((a,b)=>Number(a.data.seq)-Number(b.data.seq));
}

export function agentChatCommand(store,user,action,input){
  if(action==='agent.chat.create'){
    const system=enumeration(input.system,SYSTEMS,'Agent');
    const conversation=store.add('conversation',user,{kind:'agent',system,title:`${NAMES[system]} Agent 对话`,seq:0,status:'active',created_at:now()});
    return {id:conversation.id};
  }
  if(action==='agent.chat.send'){
    const conversation=store.owned(user,input.id,'conversation');
    if(conversation.data.kind!=='agent')fail('INVALID_CONVERSATION','这不是 Agent 对话');
    if(input.model_consent!==true)fail('CONSENT_REQUIRED','请确认将本次对话交给配置的模型服务');
    const text=string(input.text,'消息',6000);
    const local=/搜索|检索|查找/.test(text)&&/我的(?:知识|记忆|资料|任务)|应用内|本地|收件箱/.test(text)?text.replace(/^.*?(搜索|检索|查找)/,'').replace(/(?:我的)?(?:知识库|记忆库|资料库|任务|应用内|本地|收件箱)[里中内的：:\s]*/g,'').trim().slice(0,300):null;
    const lookup=local?null:webIntent(text,input.network||'auto');
    if(input.tool_id&&(lookup||local))fail('INVALID_INPUT','本轮请选择检索或已保存工具，分两轮执行');
    if(input.tool_id){const tool=store.owned(user,input.tool_id,'skill');if(tool.data.kind==='Mini App')fail('MINI_APP_PREVIEW_REQUIRED','Mini App 请在工具页面打开使用');}
    const pending=store.list('task').some(task=>task.owner===user&&task.data.agent_chat?.conversation_id===conversation.id&&['queued','running','cancel_requested','pause_requested'].includes(task.data.status));
    if(pending)fail('AGENT_REPLY_PENDING','请等这一轮回复完成后继续发送',409);
    const seq=conversation.data.seq+1;
    const message=store.add('message',user,{conversation_id:conversation.id,seq,text,actor_type:'human',human_sender_id:user,attachments:[],mentions:[]},{space:conversation.id});
    store.update(conversation,{...conversation.data,seq,last_message_id:message.id},user);
    dialogueMemoryFeedback(store,user,conversation,message);
    captureMemories(store,user,{text,system:conversation.data.system,source:message,origin:'conversation'});
    const recent=recentChatMessages(history(store,user,conversation));
    const goal=text;
    const discoveries=conversation.data.system==='explore'&&/最近|近期|资讯|新闻|变化|关注|发现/.test(text)?store.visible(user,'feed').filter(item=>item.owner===user&&item.data.status==='active'&&item.data.purpose==='discovery'&&item.data.external_url).sort((a,b)=>b.created.localeCompare(a.created)).slice(0,input.tool_id?3:4):[];
    const refs=[...recent,...discoveries].map(item=>({id:item.id,version:item.version}));
    const selected=input.tool_id?toolLibraryCommand(store,user,'tool.use',{id:input.tool_id,version_id:input.tool_version_id,goal,parameters:input.parameters}):null;
    const created=selected?{id:selected.task_id}:taskCommand(store,user,'task.create',{goal,system:conversation.data.system,source_refs:refs,review_mode:'single',criteria:'自然对话回复，承接本线程上下文并明确未知事项',constraints:lookup?'只把本轮公开关键词或链接交给只读联网工具；不发送私人记忆与历史，不对外写入':'仅在本次对话及当前授权资料范围内回答；不自动创建草稿、发送消息或执行外部动作',stop:{maxCalls:lookup||local?2:1,maxTokens:50000,maxUnits:1000,maxSeconds:120,maxAttempts:1,maxReplans:1}});
    let task=store.get(created.id);
    task=store.update(task,{...task.data,stop:selected?{...task.data.stop,maxTokens:64000}:task.data.stop,source_refs:selected?[...task.data.source_refs,...refs]:refs,review_mode:'single',...(lookup?{web_lookup:lookup}:{}),...(local?{local_lookup:local}:{}),internal_search:true,agent_chat:{conversation_id:conversation.id,trigger_id:message.id}},user);
    taskCommand(store,user,'task.confirm',{id:task.id,version:task.version,confirm:true,model_consent:true});
    task=store.get(task.id);
    const run=taskCommand(store,user,'run.start',{id:task.id,version:task.version});
    return {id:message.id,conversation_id:conversation.id,task_id:task.id,run_id:run.id};
  }
  if(action==='agent.chat.task'){
    const conversation=store.owned(user,input.id,'conversation');
    if(conversation.data.kind!=='agent')fail('INVALID_CONVERSATION','这不是 Agent 对话');
    if(input.confirm!==true)fail('CONFIRMATION_REQUIRED','请确认本次任务目标、范围与额度');
    const mode=enumeration(input.mode||'compose',['compose','search','web'],'执行方式');
    if(mode!=='search'&&input.model_consent!==true)fail('CONSENT_REQUIRED','请确认将目标和当前对话交给配置的模型');
    const goal=string(input.goal,mode==='search'?'检索关键词':'任务目标',mode==='search'?300:6000);
    if(mode==='search'){const result=search(store,user,{query:goal});if(result.status==='needs_clarification')fail('SEARCH_CLARIFICATION_REQUIRED',result.intent.uncertainties.join('；')+'。请改成明确的关键词，或到全局搜索设置筛选条件。',409);}
    const refs=mode==='compose'?recentChatMessages(history(store,user,conversation)).map(item=>({id:item.id,version:item.version})):[];
    const lookup=mode==='web'?webIntent(goal,'web'):null;
    const created=taskCommand(store,user,'task.create',{goal,mode:mode==='web'?'compose':mode,system:conversation.data.system,source_refs:refs,review_mode:mode==='web'?'single':'auto',stop:{maxCalls:3,maxTokens:64000,maxUnits:3000,maxSeconds:180,maxAttempts:3,maxReplans:1}});
    let task=store.get(created.id);
    task=store.update(task,{...task.data,...(lookup?{web_lookup:lookup}:{}),agent_chat_draft_conversation_id:conversation.id},user);
    taskCommand(store,user,'task.confirm',{id:task.id,version:task.version,confirm:true,model_consent:input.model_consent});
    task=store.get(task.id);
    const run=taskCommand(store,user,'run.start',{id:task.id,version:task.version});
    return {id:task.id,conversation_id:conversation.id,run_id:run.id};
  }
  if(action==='agent.chat.draft'){
    const conversation=store.owned(user,input.id,'conversation');
    if(conversation.data.kind!=='agent')fail('INVALID_CONVERSATION','这不是 Agent 对话');
    const goal=string(input.goal,'任务目标',8000);
    const refs=history(store,user,conversation).slice(-12).map(item=>({id:item.id,version:item.version}));
    const created=taskCommand(store,user,'task.create',{goal,system:conversation.data.system,source_refs:refs});
    const task=store.get(created.id);
    store.update(task,{...task.data,agent_chat_draft_conversation_id:conversation.id},user);
    return {id:task.id,conversation_id:conversation.id};
  }
}

export function publishAgentChatReply(store,task,run,status){
  if(!task.data.agent_chat||!['completed','awaiting_review'].includes(status))return;
  if(status==='awaiting_review'&&(run.data.verification?.failures||[]).some(failure=>failure.kind!=='human_review_required'))return;
  const conversation=store.get(task.data.agent_chat.conversation_id);
  if(!conversation||conversation.owner!==task.owner||conversation.data.kind!=='agent')return;
  const output=resultReceipts(run.data.receipts||[]).find(receipt=>typeof receipt.output==='string')?.output?.trim();
  if(!output)return;
  const message=store.unique('message',`agent-chat:${run.id}`,()=>{
    const current=store.get(conversation.id),seq=current.data.seq+1;
    const citations=(run.data.receipts||[]).flatMap(receipt=>receipt.citations||[]).filter((citation,index,all)=>all.findIndex(item=>item.url===citation.url)===index);
    const posted=store.add('message',task.owner,{conversation_id:current.id,seq,text:output.slice(0,10000),actor_type:'agent',sender_name:`${NAMES[current.data.system]} Agent`,trigger_id:task.data.agent_chat.trigger_id,task_id:task.id,run_id:run.id,citations,tool_id:task.data.skill_id||null,attachments:[],mentions:[]},{space:current.id});
    store.update(current,{...current.data,seq,last_message_id:posted.id},task.owner);
    return posted;
  });
  const trigger=store.get(task.data.agent_chat.trigger_id);
  if(trigger?.data.actor_type==='human')captureMemories(store,task.owner,{text:trigger.data.text,system:task.data.system,source:trigger,proposals:run.data.memory_proposals||[],origin:'conversation'});
  return message.id;
}
