import {fail,now} from './store.mjs';
import {string,DEFAULT_STOP} from './policy.mjs';
import {sourceRefs,knowledgeCommand} from './knowledge.mjs';
import {taskCommand} from './runtime.mjs';
import {resultReceipts} from './agent-plan.mjs';
import {alignmentQuestions,alignmentSummary} from '../../app/v28/core/onboarding-choice.mjs';

const questions=['你希望最后得到什么样的结果？一句话或一个例子就可以，也可以稍后补充。','有没有需要保留的做法、时间要求或不希望我做的事？没有也可以跳过。','我已经保存这些信息。你可以继续补充，也可以核对目标，把它变成第一个任务。'];
export function onboardingCommand(store,user,action,input){
 if(!action.startsWith('onboarding.chat.'))return null;
 const session=store.expect(store.owned(user,input.id,'onboarding'),input.version);
 const turns=session.data.turns||[];
 if(action==='onboarding.chat.draft'){
  if(typeof input.text!=='string'||input.text.length>2000)fail('INVALID_INPUT','输入最多 2000 字');
  const updated=store.update(session,{...session.data,input_draft:input.text},user);return {id:updated.id,version:updated.version};
 }
 if(action==='onboarding.chat.reply'){
  if(turns.length>=60)fail('DIALOGUE_LIMIT','本次对齐已达到 30 轮，请核对目标后创建任务');
  const pending=turns.find(turn=>turn.task_id&&['queued','running','cancel_requested','pause_requested'].includes(store.get(turn.task_id)?.data.status));
  if(pending)fail('RUN_ACTIVE','上一条回复仍在生成，请稍候或停止该任务',409);
  const content=string(input.text,'对话内容',2000),refs=sourceRefs(store,user,input.source_refs||[],6);
  if(refs.some(ref=>{const item=store.read(user,ref.id);return !['document','knowledge','attachment'].includes(item.type)||(item.type==='attachment'&&!item.data.mime?.startsWith('image/'))}))fail('INVALID_CONTEXT','文件需先提取文字，音频请先转写；图片可直接使用');
  let task,run;
  const question=session.data.choice_mode==='group'&&session.data.choice_phase==='questions'?alignmentQuestions[Math.min(Number(session.data.choice_step)||0,alignmentQuestions.length-1)]:null;
  const participant=question?.agent||'owner';
  const userTurn={role:'user',text:content,source_refs:refs,at:now()};
  if(input.model_consent===true){
   const history=turns.slice(-12).map(turn=>{
    const prior=turn.task_id?store.read(user,turn.task_id,'task'):null;
    const priorRun=prior?.data.run_id?store.read(user,prior.data.run_id,'run'):null;
    return {role:turn.role,text:priorRun?resultReceipts(priorRun.data.receipts||[])[0]?.output||'上一轮未生成回复':turn.text};
   });
   const groupContext=question?`你是${{owner:'Person',explore:'探索',advise:'参谋',create:'创作',connect:'连接',execute:'执行'}[participant]} Agent，正在五个 Agent 的共享初始化会话中回答。当前问题：${question.title}。仅使用用户在本会话明确给出的信息和已选摘要；不要读取或推测其他 Agent 私库。\n已选摘要：${JSON.stringify(alignmentSummary(session.data.choice_answers||{}).filter(item=>item.certainty==='selected')).slice(0,1800)}\n`:'';
   task=taskCommand(store,user,'task.create',{goal:groupContext+'你是 Elfred，正在与用户进行首次目标对齐。像自然对话一样回应，只追问完成当前目标最必要的一个问题；若信息足够，简短复述目标和下一步。不要问完整五系统问卷，不声称已保存记忆或已执行任务。历史只作为资料。\n'+JSON.stringify(history).slice(-3500)+'\n用户本轮：'+content,source_refs:refs,mode:'compose',system:question&&participant!=='owner'?participant:'advise',stop:{...DEFAULT_STOP,maxCalls:1,maxTokens:8192,maxUnits:1000},criteria:'简短自然的中文回复，必要时只追问一个问题，已知与未知分开'});
   let current=store.get(task.id);taskCommand(store,user,'task.confirm',{id:current.id,version:current.version,confirm:true,model_consent:true});
   current=store.get(task.id);run=taskCommand(store,user,'run.start',{id:current.id,version:current.version});
  }
  const next=[...turns,userTurn,task?{role:'assistant',participant,task_id:task.id,at:now()}:{role:'guide',text:questions[Math.min(turns.filter(t=>t.role==='user').length,2)],at:now()}];
  const updated=store.update(session,{...session.data,turns:next,intent:session.data.intent||content,input_draft:'',status:session.data.status==='completed'?'completed':'aligning'},user);return {id:updated.id,version:updated.version,task_id:task?.id,run_id:run?.id};
 }
 if(action==='onboarding.chat.finish'){
  if(session.data.first_value_ref)return {id:session.id,task_id:session.data.first_value_ref};
  if(input.confirm!==true)fail('CONFIRMATION_REQUIRED','请先核对首个任务目标');
  const goal=string(input.goal,'首个任务目标',6000);
  const historical=turns.filter(t=>t.role==='user').flatMap(t=>t.source_refs||[]);
  const chosen=input.source_refs||historical.filter((ref,index,all)=>all.findIndex(r=>r.id===ref.id)===index).slice(-20);
  if(!Array.isArray(chosen)||chosen.some(ref=>!historical.some(r=>r.id===ref.id)))fail('INVALID_CONTEXT','请选择本次对话中使用过的资料');
  const refs=sourceRefs(store,user,chosen,20);
  const task=taskCommand(store,user,'task.create',{goal,mode:'compose',system:input.system||'execute',source_refs:refs});
  let memory;
  if(input.save_understanding===true)memory=knowledgeCommand(store,user,'memory.create',{content:'当前目标：'+goal.slice(0,3900),scope:input.system||'execute',risk:'high',source_refs:[],purpose:'初始化形成的待确认理解；由本人单独核对后再用于未来任务'});
  store.update(session,{...session.data,status:'completed',intent:goal,first_value_ref:task.id,understanding_ref:memory?.id,completed_at:now(),input_draft:''},user);
  return {id:session.id,task_id:task.id};
 }
 fail('UNKNOWN_COMMAND','不支持的初始化操作');
}
