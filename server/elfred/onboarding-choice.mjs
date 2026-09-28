import {fail,now} from './store.mjs';
import {enumeration} from './policy.mjs';
import {taskCommand} from './runtime.mjs';
import {alignmentQuestions,alignmentSummary,choiceVersion,firstValueChoices} from '../../app/v28/core/onboarding-choice.mjs';
import {provisionInitialDiscovery} from './auto-discovery.mjs';
import {queueMemorySync} from './memory-hub.mjs';
import {allocateMemory} from './memory-allocation.mjs';

export function onboardingChoiceCommand(store,user,action,input){
 if(!action.startsWith('onboarding.choice.'))return null;
 const session=store.expect(store.owned(user,input.id,'onboarding'),input.version);
 const data=session.data,answers=data.choice_answers||{};
 const update=patch=>{const result=store.update(session,{...data,...patch},user);return {id:result.id,version:result.version}};
 if(action==='onboarding.choice.start')return update({choice_version:choiceVersion,choice_mode:enumeration(input.mode||data.choice_mode||'sequential',['sequential','group'],'引导方式'),choice_started_at:data.choice_started_at||now(),choice_phase:data.choice_phase==='handoff'?'handoff':'questions',choice_step:data.choice_step||0});
 if(action==='onboarding.choice.mode')return update({choice_mode:enumeration(input.mode,['sequential','group'],'引导方式')});
 if(action==='onboarding.choice.answer'){
  const index=alignmentQuestions.findIndex(q=>q.id===input.question_id),question=alignmentQuestions[index];
  if(!question)fail('INVALID_INPUT','题目不存在');
  const option=enumeration(input.option,question.options.map(o=>o.id),'选项');
  const detail=question.id==='interests'&&option==='specified'?String(input.detail||'').trim():'';
  if(question.id==='interests'&&option==='specified'&&(detail.length<2||detail.length>120||/[<>]/.test(detail)))fail('INVALID_INPUT','请填写 2—120 字感兴趣的领域');
  return update({choice_version:choiceVersion,choice_answers:{...answers,[question.id]:{option,...(detail?{detail}:{}),at:now(),scope:question.agent}},choice_step:data.choice_editing?alignmentQuestions.length:Math.min(index+1,alignmentQuestions.length),choice_phase:data.choice_editing||index+1===alignmentQuestions.length?'summary':'questions',choice_editing:false,choice_confirmed_at:null,choice_summary:null,initial_context:null,initial_boundaries:null});
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
  const autoDiscovery=input.auto_discovery===true;
  materializeInitialMemories(store,user,summary);
  const discovery=provisionInitialDiscovery(store,user,summary,{start:autoDiscovery});
  if(!autoDiscovery&&discovery?.data.auto_managed&&discovery.data.status==='active')store.update(discovery,{...discovery.data,status:'paused'},user);
  return update({intent:summary.find(item=>item.question_id==='need'&&item.certainty==='selected')?.label||'轻量项目方向待确定',choice_summary:summary,choice_confirmed_at:now(),choice_phase:'handoff',choice_auto_discovery:autoDiscovery,choice_discovery_ref:discovery?.id||null,initial_context:Object.fromEntries(['owner','explore','advise','create','connect','execute'].map(agent=>[agent,{scope:agent,purpose:'初始化选择形成的初始假设，需在真实使用中核对',items:summary.filter(item=>item.agent===agent),alignment:'insufficient'}])),initial_boundaries:{initiative:answers.initiative?.option||'unsure',external:answers.external?.option||'unsure',external_confirmation_required:true,source_access:'ask_when_needed',cross_agent:'minimum_necessary_with_confirmation'}});
 }
 if(action==='onboarding.choice.first'){
  if(!data.choice_confirmed_at)fail('CONFIRMATION_REQUIRED','请先核对初始理解卡');
  if(input.confirm!==true)fail('CONFIRMATION_REQUIRED','请确认本次任务使用所示选择摘要');
  if(data.choice_task_ref)return {id:session.id,version:session.version,task_id:data.choice_task_ref};
  const option=firstValueChoices.find(o=>o.id===input.task);if(!option)fail('INVALID_INPUT','请选择首个事项');
  const summary=alignmentSummary(answers).filter(item=>option.questions.includes(item.question_id));
  const content=summary.map(item=>`${item.question} ${item.label}${item.certainty==='uncertain'?'（尚未确定）':'（初始选择，非稳定事实）'}`).join('\n');
  const evidence=store.add('document',user,{title:'首个任务的初始化选择',content,provenance_refs:[{id:session.id,version:session.version}],purpose:`本人确认交给${option.system}的最小任务上下文`});
  const task=taskCommand(store,user,'task.create',{goal:option.goal,constraints:'仅依据已授权的选择资料；用户尚未给出具体领域、个人经历或日程，不得虚构。可提供清晰标注的候选示例，资料不足时列出待确认项。只产出建议或草稿；不联系他人、不发布、不改日程。',system:option.system,mode:'compose',source_refs:[{id:evidence.id,version:evidence.version}]});
  const createdTask=store.get(task.id);
  store.update(createdTask,{...createdTask.data,title:option.label},user);
  const inbox=store.unique('inbox',`${user}:${task.id}`,()=>store.add('inbox',user,{object_id:task.id,task_id:task.id,title:option.label,summary:'初始化的首个待处理事项，等待确认执行',status:'pending',source_refs:[{id:task.id}]}));
  const result=update({choice_task_ref:task.id,choice_task_answers:answers,first_value_ref:data.first_value_ref||task.id,inbox_ref:inbox.id,choice_task_label:option.label,intent:option.label,status:data.status==='completed'?'completed':'first_value_pending'});
  return {...result,task_id:task.id};
 }
 if(action==='onboarding.choice.home'){
  if(!data.choice_confirmed_at)fail('CONFIRMATION_REQUIRED','请先核对初始理解卡，或选择稍后继续');
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
