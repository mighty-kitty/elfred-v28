import {sourceRefs} from './knowledge.mjs';
import {validateWebArtifact} from './preview.mjs';
import {fail,now,hash} from './store.mjs';
import {string,bounded} from './policy.mjs';
import {taskCommand} from './runtime.mjs';
import {resultReceipts} from './agent-plan.mjs';
export function projectActive(store,user,id){const p=store.read(user,id,'project');if(!store.role(id,user))fail('FORBIDDEN','需要当前项目成员资格',403);if(p.data.status!=='active')fail('PROJECT_CLOSED','项目已结束，不再接受新的执行或贡献',409);return p;}
export function validateFiles(input){
 if(!input||typeof input!=='object'||Array.isArray(input)||Object.keys(input).length>40)fail('INVALID_FILES','最多 40 个文本文件');
 const files={};let size=0;
 for(const [path,value] of Object.entries(input)){
  if(!/^[\p{L}\p{N}_ ./-]+\.(?:md|txt|html|css|js|json|csv|svg)$/u.test(path)||path.startsWith('/')||path.split('/').some(p=>p==='..'||p==='.'||!p)||typeof value!=='string')fail('INVALID_FILES','文件路径或格式不支持');
  size+=value.length;if(size>200000)fail('INVALID_FILES','项目文本文件合计不能超过 200 KB');files[path]=value;
 }return files;
}
export function mergeFiles(base,upstream,local){const merged={...upstream},conflicts=[];for(const path of new Set([...Object.keys(base),...Object.keys(local)])){if(local[path]===base[path])continue;if(upstream[path]!==base[path]&&upstream[path]!==local[path]){conflicts.push(path);continue;}if(local[path]===undefined)delete merged[path];else merged[path]=local[path];}return {files:merged,conflicts};}
export function projectWorkCommand(store,user,action,input){
 if(!['project.budget','project.dispatch','project.dispatch.publish','project.end','project.leave','copy.ai_prepare','copy.ai_apply','copy.stage','stage.depend','claim.reconfirm','copy.files','copy.resolve'].includes(action))return null;
 if(input.actor_type==='agent')fail('HUMAN_REQUIRED','需要本人操作');
 if(action==='project.budget'){
  const p=store.expect(store.owned(user,input.id,'project'),input.version);if(input.confirm!==true)fail('CONFIRMATION_REQUIRED','请确认本项目公共调度使用本人的额度');
  const used=store.list('task').filter(t=>t.data.project_id===p.id&&t.data.budget_source==='project').reduce((sum,t)=>sum+(t.data.units||0),0);
  const limit=bounded(input.limit,'公共额度',used,100000);return {id:store.update(p,{...p.data,public_budget:{payer:user,limit,confirmed_at:now()}},user).id};
 }
 if(action==='project.end'||action==='project.leave'){
  const p=store.expect(store.read(user,input.id,'project'),input.version);if(input.confirm!==true)fail('CONFIRMATION_REQUIRED','请确认结束或退出');
  if(action==='project.end'&&p.owner!==user)fail('FORBIDDEN','仅发起者可结束项目',403);
  if(action==='project.leave'&&p.owner===user)fail('INVALID_STATE','发起者请结束项目');
  if(!store.role(p.id,user))fail('FORBIDDEN','不是当前成员',403);
  for(const task of store.list('task').filter(t=>t.data.project_id===p.id&&(action==='project.end'||t.owner===user))){const run=store.get(task.data.run_id);if(run&&['running','queued'].includes(run.data.status))store.update(run,{...run.data,status:'cancel_requested'},user);}
  for(const claim of store.list('claim').filter(c=>c.data.project_id===p.id&&(action==='project.end'||c.owner===user)))store.update(claim,{...claim.data,status:'withdrawn',withdrawn_at:now()},user);
  if(action==='project.leave'){store.db.prepare('DELETE FROM members WHERE space=? AND user_id=?').run(p.id,user);return {id:store.update(p,{...p.data,membership_updated:now()},user).id};}
  for(const post of store.list('post').filter(x=>x.data.project_id===p.id))store.update(post,{...post.data,status:'closed'},user);
  return {id:store.update(p,{...p.data,status:'ended',recruiting:false,end_reason:string(input.reason||'本人结束项目','结束原因',1000),ended_at:now()},user).id};
 }
 if(action==='project.dispatch'){
  const p=projectActive(store,user,input.id);if(p.owner!==user||p.data.public_budget?.payer!==user)fail('BUDGET_REQUIRED','先由发起者确认公共调度额度');
  if(input.confirm!==true||input.model_consent!==true)fail('CONSENT_REQUIRED','请确认共享范围、调度目标和额度');
  const shared=[...store.visible(user,'project_stage').filter(x=>x.space===p.id&&x.data.status==='shared'),...store.visible(user,'feedback').filter(x=>x.space===p.id)].slice(0,20);
  const result=taskCommand(store,user,'task.create',{goal:'为项目制定临时调度建议：'+p.data.goal+'。当前请求：'+string(input.goal,'调度目标',3000)+'。只依据共享阶段成果安排建议，不能指挥其他成员私人 Agent，不能代人接受任务或发布。',system:'connect',project_id:p.id,source_refs:shared.map(s=>({id:s.id,version:s.version}))});
  const task=store.get(result.id);store.update(task,{...task.data,title:'项目协作安排',dispatch_for:p.id,budget_source:'project'},user);return {id:result.id,task_id:result.id};
 }
 if(action==='project.dispatch.publish'){
  const p=projectActive(store,user,input.id);if(p.owner!==user||input.confirm!==true)fail('CONFIRMATION_REQUIRED','需由发起者核对后共享调度建议');
  const task=store.owned(user,input.task_id,'task');if(task.data.dispatch_for!==p.id||task.data.status!=='completed')fail('REVIEW_REQUIRED','请先验收本项目的调度建议');
  const run=store.owned(user,task.data.run_id,'run'),output=resultReceipts(run.data.receipts||[]).find(receipt=>typeof receipt.output==='string')?.output;
  if(!output)fail('RESULT_REQUIRED','没有可共享的调度结果');
  const text=string(input.content||output,'调度说明',5000);
  const feedback=store.unique('feedback',`coordination:${p.id}:${task.id}`,()=>store.add('feedback',user,{content:text,kind:'coordination',task_id:task.id,confirmed_by:user,confirmed_at:now(),note:'建议不自动改变成员承诺；任务、范围与费用变化仍需本人确认'},{space:p.id,visibility:'members'}));
  return {id:feedback.id};
 }
 if(action==='claim.reconfirm'){
  const claim=store.expect(store.owned(user,input.id,'claim'),input.version),p=projectActive(store,user,claim.data.project_id),slot=store.read(user,claim.data.slot_id,'project_slot');
  if(input.confirm!==true)fail('CONFIRMATION_REQUIRED','请核对新的任务约定');
  store.expect(slot,input.slot_version);
  if(claim.data.status!=='needs_reconfirmation')fail('INVALID_STATE','只有约定变更后才能重新确认');
  if(slot.data.status!=='open'||(slot.data.deadline&&Date.parse(slot.data.deadline)<=Date.now()))fail('SLOT_CLOSED','任务位已关闭');
  if(slot.data.capacity!==null&&store.list('claim').filter(c=>c.id!==claim.id&&c.data.slot_id===slot.id&&['accepted','needs_reconfirmation'].includes(c.data.status)).length>=slot.data.capacity)fail('SLOT_FULL','任务位人数已满');
  return {id:store.update(claim,{...claim.data,status:'accepted',rules_version:slot.version,rules_snapshot:slot.data,reconfirmed_at:now()},user).id};
 }
 const copy=store.expect(store.owned(user,input.id,'copy'),input.version),p=projectActive(store,user,copy.data.project_id);
 if(copy.data.status!=='draft')fail('INVALID_STATE','已提交副本不可改写，请创建修订副本');
 if(action==='copy.resolve'){
  if(input.reviewed!==true)fail('REVIEW_REQUIRED','需逐文件核对后确认冲突处理');
  if(copy.data.base_revision!==p.data.revision)fail('UPSTREAM_CHANGED','上游再次变化，请重新创建修订副本');
  return {id:store.update(copy,{...copy.data,unresolved_conflicts:[],conflict_resolution:{by:user,at:now(),paths:copy.data.unresolved_conflicts||[]}},user).id};
 }
 if(action==='copy.files'){
  const files=validateFiles(input.files),primary=copy.data.format==='web'?'index.html':'成果.md';
  if(copy.data.content&&!Object.hasOwn(files,primary))fail('PRIMARY_REQUIRED','请保留主成果文件 '+primary);
  const content=files[primary]||'';const build=copy.data.format==='web'?validateWebArtifact(content,files):null;
  const updated=store.update(copy,{...copy.data,files,content,build},user);return {id:updated.id,version:updated.version};
 }
 if(action==='stage.depend'){
  const stage=store.read(user,input.stage_id,'project_stage');if(stage.space!==p.id||stage.data.status!=='shared'||!store.role(p.id,stage.owner))fail('INVALID_DEPENDENCY','请选择本项目当前成员的有效共享阶段成果');
  const refs=(copy.data.stage_refs||[]).filter(r=>r.id!==stage.id&&store.get(r.id)?.data.origin_copy!==stage.data.origin_copy);refs.push({id:stage.id,version:stage.version});
  return {id:store.update(copy,{...copy.data,stage_refs:refs},user).id};
 }
 if(action==='copy.stage'){
  if(input.reviewed!==true||!copy.data.content?.trim())fail('REVIEW_REQUIRED','请先保存并审查将向项目成员共享的阶段内容');
  sourceRefs(store,user,copy.data.stage_refs||[]);
  const stage=store.add('project_stage',user,{project_id:p.id,slot_id:copy.data.slot_id,origin_copy:copy.id,copy_version:copy.version,title:string(input.title,'阶段标题',200),content:copy.data.content,files:copy.data.files||{},content_hash:hash(copy.data.content),status:'shared',stage_kind:input.kind==='blocked'?'blocked':'progress',dependencies:copy.data.stage_refs||[],reviewed_by:user},{space:p.id,visibility:'members'});for(const previous of store.list('project_stage').filter(s=>s.id!==stage.id&&s.data.origin_copy===copy.id&&s.data.status==='shared'))store.update(previous,{...previous.data,status:'superseded',superseded_by:stage.id},user);return {id:stage.id};
 }
 if(action==='copy.ai_prepare'){
  if(input.confirm!==true||input.model_consent!==true)fail('CONSENT_REQUIRED','请确认本人 AI 的任务范围与额度');
  if(copy.data.slot_id&&p.owner!==user&&!store.list('claim').some(c=>c.owner===user&&c.data.slot_id===copy.data.slot_id&&c.data.status==='accepted'))fail('CLAIM_REQUIRED','请先确认当前任务约定');
  const refs=(copy.data.stage_refs||[]).map(ref=>{const stage=store.expect(store.read(user,ref.id,'project_stage'),ref.version);if(!store.role(p.id,stage.owner)||stage.data.status!=='shared')fail('DEPENDENCY_CHANGED','阶段来源已失效');return ref;});
  const slot=copy.data.slot_id?store.read(user,copy.data.slot_id,'project_slot'):null;
  const dependencyRefs=(slot?.data.depends_on||[]).filter(id=>store.get(id)?.data.status!=='completed');
  if(dependencyRefs.some(id=>!refs.some(ref=>store.get(ref.id)?.data.slot_id===id)))fail('DEPENDENCY_PENDING','前置任务未完成，请先选择其已共享的阶段版本');
  const task=taskCommand(store,user,'task.create',{goal:'在本人的独立工作副本内完成：'+string(input.goal||slot?.data.title||p.data.task,'本次任务',3000)+'\n项目目标：'+p.data.goal+'\n当前副本：'+String(copy.data.content||'').slice(0,2000),criteria:slot?.data.criteria||p.data.criteria,system:input.system||'create',project_id:p.id,source_refs:refs});
  const object=store.get(task.id);store.update(object,{...object.data,copy_id:copy.id,copy_version:copy.version,slot_id:copy.data.slot_id||null,slot_rules_version:slot?.version||null,stage_refs:refs,budget_source:'personal'},user);
  store.update(copy,{...copy.data,ai_task_id:task.id},user);return {id:task.id,task_id:task.id};
 }
 if(action==='copy.ai_apply'){
  if(input.reviewed!==true)fail('REVIEW_REQUIRED','请先检查 AI 结果再写入本人副本');
  const task=store.owned(user,copy.data.ai_task_id,'task'),run=store.owned(user,task.data.run_id,'run');
  if(task.data.copy_id!==copy.id||task.data.copy_version+1!==copy.version)fail('COPY_CHANGED','AI 运行期间副本已修改，请手动比较后合并，避免覆盖');
  const output=resultReceipts(run.data.receipts||[]).find(r=>typeof r.output==='string')?.output;if(!output)fail('RESULT_REQUIRED','尚无可核对结果');
  const content=string(output,'模型成果',200000),build=copy.data.format==='web'?validateWebArtifact(content,copy.data.files||{}):null;
  return {id:store.update(copy,{...copy.data,content,build,files:{...(copy.data.files||{}),[copy.data.format==='web'?'index.html':'成果.md']:content},ai_result_ref:{task_id:task.id,run_id:run.id}},user).id};
 }
}
