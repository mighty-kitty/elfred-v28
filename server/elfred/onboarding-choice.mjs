import {fail,now} from './store.mjs';
import {enumeration,string} from './policy.mjs';
import {taskCommand} from './runtime.mjs';
import {alignmentQuestions,alignmentSummary,choiceVersion,firstValueChoices,interestLabels} from '../../app/v28/core/onboarding-choice.mjs';
import {provisionInitialDiscovery} from './auto-discovery.mjs';
import {queueMemorySync} from './memory-hub.mjs';
import {allocateMemory} from './memory-allocation.mjs';

const systems=['explore','advise','create','connect','execute'];
function proposedFirstTasks(store,user,data){
 const task=data.choice_goal_proposal_task_ref&&store.get(data.choice_goal_proposal_task_ref);
 if(!task||task.owner!==user||data.choice_goal_proposal_input!==data.choice_goal?.goal)return [];
 const run=task.data.run_id&&store.get(task.data.run_id);
 const receipt=[...(run?.data.receipts||[])].reverse().find(item=>['work','repair'].includes(item.phase)&&typeof item.output==='string');
 if(!receipt)return [];
 try{
  const source=receipt.output.trim().replace(/^```(?:json)?\s*|\s*```$/g,'');
  const body=JSON.parse(source.slice(source.indexOf('{'),source.lastIndexOf('}')+1));
  if(!Array.isArray(body.first_tasks)||body.first_tasks.length!==3)return [];
  const options=body.first_tasks.map((row,index)=>({id:`suggestion:${index}`,label:String(row.label||'').slice(0,80).trim(),goal:String(row.goal||'').slice(0,500).trim(),system:String(row.system||''),minutes:Number(row.minutes),needs:String(row.needs||'').slice(0,150),deliverable:String(row.deliverable||'').slice(0,150)}));
  return options.every(row=>row.label&&row.goal&&systems.includes(row.system)&&Number.isFinite(row.minutes)&&row.minutes>=1&&row.minutes<=120&&row.deliverable)?options:[];
 }catch{return []}
}

export function onboardingChoiceCommand(store,user,action,input){
 if(!action.startsWith('onboarding.choice.'))return null;
 const session=store.expect(store.owned(user,input.id,'onboarding'),input.version);
 const data=session.data,answers=data.choice_answers||{};
 const update=patch=>{const result=store.update(session,{...data,...patch},user);return {id:result.id,version:result.version}};
 if(action==='onboarding.choice.profile.start')return update({choice_phase:'profile',choice_started_at:data.choice_started_at||now()});
 if(action==='onboarding.choice.profile'){
  const name=string(input.name,'称呼',60),role=string(input.role,'当前角色',60),status=string(input.status,'当前状态',60);
  const interests=interestLabels(input.interests);
  if(!interests.length||interests.length>8||interests.some(item=>item.length>30))fail('INVALID_INPUT','请选择 1—8 个感兴趣的领域');
  const profile=store.visible(user,'profile')[0];
  if(profile)store.update(profile,{...profile.data,name,role,tags:interests},user);
  return update({choice_profile:{name,role,status,interests},choice_phase:'goal'});
 }
 if(action==='onboarding.choice.goal.organize'){
  if(!data.choice_profile)fail('INVALID_STATE','请先填写基础信息');
  if(input.confirm!==true||input.model_consent!==true)fail('CONSENT_REQUIRED','请确认将本次目标交给模型整理');
  const goal=string(input.goal,'近期目标',1000);
  const previous=data.choice_goal_proposal_task_ref&&store.get(data.choice_goal_proposal_task_ref);
  if(previous&&['queued','running'].includes(previous.data.status))return {id:session.id,version:session.version,task_id:previous.id};
  const created=taskCommand(store,user,'task.create',{goal:`把用户的近期目标整理为一张可编辑目标卡，并给出三个不同的可执行起点。只根据用户原话，不补造事实；无法确定的结果或完成标准写空字符串。只输出 JSON，不要 Markdown：{"goal":"","result":"","criteria":"","days":14,"first_tasks":[{"label":"","goal":"","system":"explore","minutes":10,"needs":"","deliverable":""}]}。first_tasks 必须恰好三个；system 从 explore、advise、create、connect、execute 中选；每个起点都要说明具体目标、预计分钟、需要用户提供什么、交付什么。days 只能是 7、14 或 30。不执行外部操作。用户原话：${goal}`,system:'advise',mode:'compose',review_mode:'single',source_refs:[]});
  let task=store.get(created.id);task=store.update(task,{...task.data,title:'整理近期目标',internal_onboarding:true},user);
  taskCommand(store,user,'task.confirm',{id:task.id,version:task.version,confirm:true,model_consent:true});task=store.get(task.id);
  taskCommand(store,user,'run.start',{id:task.id,version:task.version});
  return {...update({choice_goal_proposal_task_ref:task.id,choice_goal_proposal_input:goal}),task_id:task.id};
 }
 if(action==='onboarding.choice.goal'){
  if(!data.choice_profile)fail('INVALID_STATE','请先填写基础信息');
  const goal=string(input.goal,'近期目标',1000),result=string(input.result,'希望完成的结果',1000),criteria=string(input.criteria,'完成标准',1000),days=Number(input.days);
  if(!Number.isInteger(days)||days<7||days>30)fail('INVALID_INPUT','目标时间请选择 7—30 天');
  return update({choice_goal:{goal,result,criteria,days},intent:goal,choice_phase:'team'});
 }
 if(action==='onboarding.choice.team'){
  if(!data.choice_profile||!data.choice_goal)fail('INVALID_STATE','请先完成基础信息和近期目标');
  if(input.confirm!==true)fail('CONFIRMATION_REQUIRED','请确认五个 Agent 的初始方向');
  const focus={};
  for(const system of systems)focus[system]=string(input.focus?.[system],`${system}的初始方向`,200);
  const settings=store.visible(user,'settings')[0];
  if(input.auto_peer_comments===true&&input.model_consent!==true)fail('CONSENT_REQUIRED','请确认其他 Agent 自动评论会调用模型');
  if(settings)store.update(settings,{...settings.data,agents:Object.fromEntries(systems.map(system=>[system,{...settings.data.agents?.[system],focus:focus[system],enabled:settings.data.agents?.[system]?.enabled!==false}])),feed_peer_comments:{enabled:input.auto_peer_comments===true,daily_limit:3,consented_at:input.auto_peer_comments===true?now():settings.data.feed_peer_comments?.consented_at||null}},user);
  const selected=(question_id,agent,question,label)=>({question_id,agent,question,label,option:'specified',certainty:'selected',at:now()});
  const summary=[selected('need','owner','未来 7—30 天的目标',data.choice_goal.goal),selected('interests','explore','感兴趣的领域',data.choice_profile.interests.join('、')),...systems.map(system=>selected(`focus_${system}`,system,`${system} Agent 的当前方向`,focus[system]))];
  materializeInitialMemories(store,user,summary);
  const discovery=provisionInitialDiscovery(store,user,summary,{start:input.auto_discovery===true});
  return update({choice_summary:summary,choice_confirmed_at:now(),choice_phase:'handoff',choice_auto_discovery:input.auto_discovery===true,choice_auto_peer_comments:input.auto_peer_comments===true,choice_discovery_ref:discovery?.id||null,choice_agent_focus:focus,initial_context:Object.fromEntries(['owner',...systems].map(agent=>[agent,{scope:agent,purpose:'本人确认的初始化方向，仅在相关任务中使用',items:summary.filter(item=>item.agent===agent),alignment:'insufficient'}]))});
 }
 if(action==='onboarding.choice.start')return update({choice_version:choiceVersion,choice_mode:enumeration(input.mode||data.choice_mode||'sequential',['sequential','group'],'引导方式'),choice_started_at:data.choice_started_at||now(),choice_phase:data.choice_phase==='handoff'?'handoff':'questions',choice_step:data.choice_step||0});
 if(action==='onboarding.choice.mode')return update({choice_mode:enumeration(input.mode,['sequential','group'],'引导方式')});
 if(action==='onboarding.choice.answer'){
  const index=alignmentQuestions.findIndex(q=>q.id===input.question_id),question=alignmentQuestions[index];
  if(!question)fail('INVALID_INPUT','题目不存在');
  const option=enumeration(input.option,question.options.map(o=>o.id),'选项');
  if(question.id==='interests'&&option==='specified'&&input.tags!==undefined&&(!Array.isArray(input.tags)||input.tags.some(tag=>typeof tag!=='string')))fail('INVALID_INPUT','兴趣领域格式无效');
  const tags=question.id==='interests'&&option==='specified'?interestLabels(input.tags||input.detail):[];
  const detail=tags.join('、');
  if(question.id==='interests'&&option==='specified'&&(!tags.length||tags.length>8||detail.length>120||tags.some(tag=>tag.length<2||tag.length>30||/[<>]/.test(tag))))fail('INVALID_INPUT','请选择 1—8 个领域，每个 2—30 字');
  return update({choice_version:choiceVersion,choice_answers:{...answers,[question.id]:{option,...(detail?{detail,tags}:{}),at:now(),scope:question.agent}},choice_step:data.choice_editing?alignmentQuestions.length:Math.min(index+1,alignmentQuestions.length),choice_phase:data.choice_editing||index+1===alignmentQuestions.length?'summary':'questions',choice_editing:false,choice_confirmed_at:null,choice_summary:null,initial_context:null,initial_boundaries:null});
 }
 if(action==='onboarding.choice.step'){
  if(!Number.isInteger(input.step)||input.step<0||input.step>alignmentQuestions.length)fail('INVALID_INPUT','步骤不存在');
  return update({choice_step:input.step,choice_editing:input.step<alignmentQuestions.length&&['summary','handoff'].includes(data.choice_phase),choice_phase:input.step===alignmentQuestions.length?'summary':'questions'});
 }
 if(action==='onboarding.choice.defer')return update({deferred_at:now(),choice_deferred_at:now()});
 if(action==='onboarding.choice.confirm'){
  if(input.confirm!==true)fail('CONFIRMATION_REQUIRED','请核对初始理解卡');
  const summary=alignmentSummary(answers);
  if(input.auto_discovery!==undefined&&typeof input.auto_discovery!=='boolean')fail('INVALID_INPUT','公开资讯偏好应为开关');
  if(input.auto_peer_comments!==undefined&&typeof input.auto_peer_comments!=='boolean')fail('INVALID_INPUT','Agent 自主评论偏好应为开关');
  if(input.auto_peer_comments===true&&input.model_consent!==true)fail('CONSENT_REQUIRED','请确认自动评论会在每日上限内调用模型');
  const autoDiscovery=input.auto_discovery===true;
  const settings=store.visible(user,'settings')[0],autoPeerComments=input.auto_peer_comments===undefined?settings?.data.feed_peer_comments?.enabled===true:input.auto_peer_comments===true;
  if(settings&&input.auto_peer_comments!==undefined)store.update(settings,{...settings.data,feed_peer_comments:{enabled:autoPeerComments,daily_limit:3,consented_at:autoPeerComments?now():settings.data.feed_peer_comments?.consented_at||null}},user);
  materializeInitialMemories(store,user,summary);
  const discovery=provisionInitialDiscovery(store,user,summary,{start:autoDiscovery});
  if(!autoDiscovery&&discovery?.data.auto_managed&&discovery.data.status==='active')store.update(discovery,{...discovery.data,status:'paused'},user);
  return update({intent:summary.find(item=>item.question_id==='need'&&item.certainty==='selected')?.label||'轻量项目方向待确定',choice_summary:summary,choice_confirmed_at:now(),choice_phase:'handoff',choice_auto_discovery:autoDiscovery,choice_auto_peer_comments:autoPeerComments,choice_discovery_ref:discovery?.id||null,initial_context:Object.fromEntries(['owner','explore','advise','create','connect','execute'].map(agent=>[agent,{scope:agent,purpose:'初始化选择形成的初始假设，需在真实使用中核对',items:summary.filter(item=>item.agent===agent),alignment:'insufficient'}])),initial_boundaries:{initiative:answers.initiative?.option||'unsure',external:answers.external?.option||'unsure',external_confirmation_required:true,source_access:'ask_when_needed',cross_agent:'minimum_necessary_with_confirmation'}});
 }
 if(action==='onboarding.choice.first'){
  if(!data.choice_confirmed_at)fail('CONFIRMATION_REQUIRED','请先核对初始理解卡');
  if(input.confirm!==true)fail('CONFIRMATION_REQUIRED','请确认本次任务使用所示选择摘要');
  if(data.choice_task_ref)return {id:session.id,version:session.version,task_id:data.choice_task_ref};
  const option=String(input.task||'').startsWith('suggestion:')?proposedFirstTasks(store,user,data).find(o=>o.id===input.task):firstValueChoices.find(o=>o.id===input.task);if(!option)fail('INVALID_INPUT','请选择有效的首个事项');
  const summary=alignmentSummary(answers).filter(item=>option.questions?.includes(item.question_id));
  const content=summary.map(item=>`${item.question} ${item.label}${item.certainty==='uncertain'?'（尚未确定）':'（初始选择，非稳定事实）'}`).join('\n');
  const evidence=store.add('document',user,{title:'首个任务的初始化选择',content,provenance_refs:[{id:session.id,version:session.version}],purpose:`本人确认交给${option.system}的最小任务上下文`});
  const v2Goal=data.choice_goal?.goal;
  const firstGoal=v2Goal?`${option.goal} 用户的近期目标是：${v2Goal}。希望完成：${data.choice_goal.result}。验收标准：${data.choice_goal.criteria}。计划在 ${data.choice_goal.days} 天内推进。${option.needs?`如需用户补充：${option.needs}。`:''}${option.deliverable?`预期交付：${option.deliverable}。`:''}`:option.goal;
  const task=taskCommand(store,user,'task.create',{goal:firstGoal,constraints:'仅依据已授权的选择资料；资料不足时列出待确认项。只产出建议或草稿；不联系他人、不发布、不改日程。',system:option.system,mode:'compose',source_refs:[{id:evidence.id,version:evidence.version}]});
  const createdTask=store.get(task.id);
  store.update(createdTask,{...createdTask.data,title:option.label},user);
  if(input.start===true){
   if(input.model_consent!==true)fail('CONSENT_REQUIRED','请确认首个任务使用模型处理目标和所选资料');
   const current=store.get(task.id),confirmed=taskCommand(store,user,'task.confirm',{id:current.id,version:current.version,confirm:true,model_consent:true});
   const ready=store.get(confirmed.id);taskCommand(store,user,'run.start',{id:ready.id,version:ready.version});
  }
  const inbox=store.unique('inbox',`${user}:${task.id}`,()=>store.add('inbox',user,{object_id:task.id,task_id:task.id,title:option.label,summary:input.start===true?'首个任务已排队执行':'初始化的首个待处理事项，等待确认执行',status:'pending',source_refs:[{id:task.id}]}));
  const result=update({choice_task_ref:task.id,choice_task_answers:answers,first_value_ref:data.first_value_ref||task.id,inbox_ref:inbox.id,choice_task_label:option.label,intent:option.label,status:data.status==='completed'?'completed':'first_value_pending'});
  return {...result,task_id:task.id};
 }
 if(action==='onboarding.choice.home'){
  if(!data.choice_confirmed_at)fail('CONFIRMATION_REQUIRED','请先核对初始理解卡，或选择稍后继续');
  if(data.choice_goal&&!data.choice_task_ref)fail('FIRST_TASK_REQUIRED','请先选择并开始第一件任务');
  return update({status:'completed',completed_at:data.completed_at||now(),choice_phase:'handoff',skipped:[...new Set([...(data.skipped||[]),...(data.choice_task_ref?[]:['first_task_deferred'])])]});
 }
 fail('UNKNOWN_COMMAND','不支持的初始化操作');
}

export function materializeInitialMemories(store,user,summary){
  for(const memory of store.list('memory').filter(m=>m.owner===user&&m.data.origin==='initialization'&&!['deleted','rejected','superseded'].includes(m.data.status))){const row=summary.find(s=>s.question_id===memory.data.question_id);if(!row||row.certainty!=='selected'||row.label!==memory.data.choice_label){const changed=store.update(memory,{...memory.data,status:'needs_review',alignment:'insufficient'},user);queueMemorySync(store,changed);}}
  for(const row of summary.filter(s=>s.certainty==='selected')){
    const existing=store.list('memory').find(m=>m.owner===user&&m.data.origin==='initialization'&&m.data.question_id===row.question_id&&m.data.choice_label===row.label&&!['superseded','needs_review'].includes(m.data.status));
    if(existing){if(existing.data.status==='pending_confirmation'&&!existing.data.learning_mode&&!existing.data.hidden){const allocation=allocateMemory(existing.data.content,row.agent,{scope:row.agent,contextual:true});queueMemorySync(store,store.update(existing,{...existing.data,...allocation,status:allocation.risk==='high'?'validated':'learned',alignment:'explicit',initial_alignment:'explicit',learning_mode:'initialization_selected',confirmation_mode:'initialization_summary'},user));}continue;}
    const evidence=store.add('feedback',user,{kind:'initialization_choice',question:row.question,content:row.label,status:'recorded'});
    const content=row.question+' '+row.label;
    const memory=store.add('memory',user,{content,...allocateMemory(content,row.agent,{scope:row.agent,contextual:true}),source_refs:[{id:evidence.id,version:evidence.version}],origin:'initialization',question_id:row.question_id,choice_label:row.label,status:allocateMemory(content,row.agent).risk==='high'?'validated':'learned',alignment:'explicit',initial_alignment:'explicit',learning_mode:'initialization_selected',confirmation_mode:'initialization_summary',claim_type:'fact',evidence:[],usage_purpose:'本人已确认的本次项目初始选择，仅适用于对应项目方向，不推断为跨场景稳定事实'});queueMemorySync(store,memory);
  }
}
