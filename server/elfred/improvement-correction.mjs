import {hash,now} from './store.mjs';

const normalized=value=>String(value||'').trim().toLowerCase().replace(/\s+/g,' ');
export const caseFingerprint=(store,task)=>hash(JSON.stringify({goal:normalized(task.data.goal),criteria:normalized(task.data.criteria),constraints:normalized(task.data.constraints),sources:(task.data.source_refs||[]).map(ref=>{const source=store.get(ref.id);return hash(normalized(source?.data.content||source?.data.text||source?.data.goal||source?.data.summary))}).sort()}));

// A correction creates a bounded draft rule, never an active method. The owner
// must review it, compare it on distinct held-out work, and release it.
export function recordCorrectionCandidate(store,user,task,run,feedback){
 const correction=String(feedback||'').trim();if(!correction)return null;
 const trace=store.unique('trace',run.id,()=>store.add('trace',user,{task_id:task.id,run_id:run.id,source_refs:[{id:run.id}],status:'captured',goal:task.data.goal,verdict:run.data.verification?.verdict||'unknown',receipt_hashes:(run.data.receipts||[]).map(receipt=>receipt.output_hash),version_snapshot:run.data.version_snapshot,online_status:run.data.status}));
 const prompt=`仅当未来任务属于${task.data.system} Agent 的相近场景，且本次目标与授权资料支持时，参考用户这次纠正：${correction.slice(0,2000)}。先核对适用范围；不得推断成用户的永久偏好，不得扩大工具、资料或发布权限。`;
 return store.unique('candidate',`correction:${task.id}:${hash(correction)}`,()=>store.add('candidate',user,{trace_id:trace.id,training_task:task.id,training_fingerprint:caseFingerprint(store,task),source_refs:[{id:trace.id}],title:'待验证的改进 · '+String(task.data.title||'任务').slice(0,60),prompt,status:'draft',prompt_hash:hash(prompt),policy:'offline-human-gated-v1',origin:'task_correction',scope_system:task.data.system,correction,created_at:now()}));
}
