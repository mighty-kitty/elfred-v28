import {fail,hash,now} from './store.mjs';
import {string} from './policy.mjs';
import {taskCommand} from './runtime.mjs';
import {caseFingerprint} from './improvement-correction.mjs';

// Offline improvement stays separate from online execution and never changes an active run.
export function improvementCommand(store,user,action,input) {
  if(action==='trace.extract') {
    const task=store.owned(user,input.task_id,'task'),run=store.owned(user,task.data.run_id,'run');
    if(!['completed','partial','failed','awaiting_review','awaiting_acceptance'].includes(task.data.status))fail('TERMINAL_REQUIRED','请先等待任务产生可核对结果');
    return {id:store.unique('trace',run.id,()=>store.add('trace',user,{task_id:task.id,run_id:run.id,source_refs:[{id:run.id}],status:'captured',goal:task.data.goal,verdict:run.data.verification?.verdict||'unknown',receipt_hashes:run.data.receipts.map(receipt=>receipt.output_hash),version_snapshot:run.data.version_snapshot,online_status:run.data.status})).id};
  }
  if(action==='candidate.create') {
    const trace=store.owned(user,input.trace_id,'trace');
    return {id:store.add('candidate',user,{trace_id:trace.id,training_task:trace.data.task_id,training_fingerprint:caseFingerprint(store,store.owned(user,trace.data.task_id,'task')),source_refs:[{id:trace.id}],title:string(input.title,'候选方法名',100),prompt:string(input.prompt,'候选方法',6000),status:'draft',prompt_hash:hash(input.prompt.trim()),policy:'offline-human-gated-v1'}).id};
  }
  if(action==='candidate.evaluate') {
    const candidate=store.expect(store.owned(user,input.id,'candidate'),input.version);
    if(input.confirm!==true||input.model_consent!==true)fail('CONSENT_REQUIRED','需确认对留出任务运行模型评估及本地调用配额');
    if(!Array.isArray(input.task_ids)||input.task_ids.length!==2||new Set(input.task_ids).size!==2)fail('HOLDOUT_REQUIRED','请选择两项不同的留出任务');
    if(input.task_ids.includes(candidate.data.training_task))fail('TRAIN_TEST_LEAK','训练样本不能用作留出任务');
    const fingerprints=new Set([candidate.data.training_fingerprint]);
    const tests=input.task_ids.map(taskId=>{
      const baseline=store.owned(user,taskId,'task');
      if(candidate.data.scope_system&&baseline.data.system!==candidate.data.scope_system)fail('SCOPE_MISMATCH','留出任务需与候选方法属于同一 Agent 领域');
      const fingerprint=caseFingerprint(store,baseline);if(fingerprints.has(fingerprint))fail('TRAIN_TEST_LEAK','训练样本与留出样本的目标和来源不可重复');fingerprints.add(fingerprint);
      if(baseline.data.status!=='completed'||baseline.data.mode!=='compose')fail('BASELINE_REQUIRED','留出任务需有本人已验收的模型生成基线');
      const task=taskCommand(store,user,'task.create',{goal:baseline.data.goal,criteria:baseline.data.criteria,constraints:baseline.data.constraints,source_refs:baseline.data.source_refs,project_id:baseline.data.project_id,mode:'compose',system:baseline.data.system,capability_id:baseline.data.capability?.id,review_mode:baseline.data.review_mode,stop:baseline.data.stop});
      taskCommand(store,user,'task.confirm',{id:task.id,version:store.get(task.id).version,confirm:true,model_consent:true});
      const run=taskCommand(store,user,'run.start',{id:task.id,version:store.get(task.id).version,evaluation_candidate_id:candidate.id});
      return {baseline_task:baseline.id,baseline_run:baseline.data.run_id,case_fingerprint:fingerprint,task_id:task.id,run_id:run.id};
    });
    const evaluation=store.add('evaluation',user,{candidate_id:candidate.id,candidate_version:candidate.version,prompt_hash:candidate.data.prompt_hash,tests,status:'running',source_refs:tests.flatMap(test=>[{id:test.baseline_run},{id:test.run_id}]),rubric:'逐项核对来源、验收标准、安全边界、相对基线的改进与退步'});
    return {id:evaluation.id};
  }
  if(action==='evaluation.review') {
    const evaluation=store.expect(store.owned(user,input.id,'evaluation'),input.version);
    if(evaluation.data.status!=='running')fail('INVALID_STATE','评估已审查',409);
    for(const test of evaluation.data.tests) {
      const run=store.owned(user,test.run_id,'run');
      if(!['awaiting_review','completed'].includes(run.data.status)||!run.data.receipts.some(receipt=>typeof receipt.output==='string'&&receipt.output.trim()))fail('EVALUATION_INCOMPLETE','需两项候选运行均返回实际文本结果后再审查');
      if(run.data.version_snapshot.method?.prompt_hash!==evaluation.data.prompt_hash)fail('VERSION_CONFLICT','候选方法快照不匹配',409);
    }
    if(input.confirm!==true||!Array.isArray(input.reviews)||input.reviews.length!==2)fail('REVIEW_REQUIRED','需逐项核对两项留出结果');
    const reviews=evaluation.data.tests.map(test=>{const review=input.reviews.find(item=>item.run_id===test.run_id);if(!review||typeof review.passed!=='boolean')fail('REVIEW_REQUIRED','缺少逐项审查');return {run_id:test.run_id,passed:review.passed,note:string(review.note,'验收与对比依据',3000)}});
    return {id:store.update(evaluation,{...evaluation.data,status:reviews.every(item=>item.passed)?'passed':'failed',reviews,reviewer:user,reviewed_at:now(),judge:'explicit-human-comparison'},user).id};
  }
  if(action==='method.release') {
    const evaluation=store.owned(user,input.evaluation_id,'evaluation'),candidate=store.owned(user,evaluation.data.candidate_id,'candidate');
    if(evaluation.data.status!=='passed'||evaluation.data.prompt_hash!==candidate.data.prompt_hash||input.confirm!==true)fail('EVALUATION_REQUIRED','需通过留出评估并明确批准发布');
    for(const method of store.visible(user,'method').filter(item=>item.data.active&&(item.data.scope_system||null)===(candidate.data.scope_system||null)))store.update(method,{...method.data,active:false},user);
    const method=store.add('method',user,{title:candidate.data.title,prompt:candidate.data.prompt,prompt_hash:candidate.data.prompt_hash,candidate_id:candidate.id,evaluation_id:evaluation.id,source_refs:[{id:candidate.id},{id:evaluation.id}],status:'released',active:true,scope_system:candidate.data.scope_system||null});
    store.add('rollout',user,{method_id:method.id,action:'release',status:'active',approved_by:user,scope:'future-owned-runs-only'});
    return {id:method.id};
  }
  if(action==='method.rollback') {
    if(input.confirm!==true)fail('CONFIRMATION_REQUIRED','请确认未来任务的方法版本');
    const target=input.id?store.owned(user,input.id,'method'):null;
    for(const method of store.visible(user,'method').filter(item=>item.data.active))store.update(method,{...method.data,active:false},user);
    if(target){const latest=store.get(target.id);store.update(latest,{...latest.data,active:true},user);}
    return {id:store.add('rollout',user,{method_id:target?.id||null,action:'rollback',status:'active',approved_by:user,scope:'future-owned-runs-only'}).id};
  }
  return null;
}
