import {memoryActive} from '../../app/v28/core/memory-policy.mjs';

// Permissions, versions and time validity are separate requirements. Checking
// only object versions would keep expired source material in a user's profile.
export function memorySourceActive(store,user,object,seen=new Set(),taskId=null) {
  if(!object||!store.canRead(user,object)||seen.has(object.id)||seen.size>32)return false;
  // A grant is permission for a particular task, never durable profile evidence.
  if(object.type==='context_request'||object.type==='context_grant'&&object.data.task_id!==taskId||typeof object.data.expires==='number'&&object.data.expires<=Date.now())return false;
  if(object.data.hidden||object.data.expires_at&&Date.parse(object.data.expires_at)<=Date.now()||['deleted','rejected','superseded','expired','needs_review','withdrawn'].includes(object.data.status))return false;
  seen.add(object.id);
  return (object.data.source_refs||[]).every(ref=>{
    const source=store.get(ref.id);
    return source&&(!ref.version||ref.version===source.version)&&memorySourceActive(store,user,source,new Set(seen),taskId);
  });
}
export function memoryUsable(store,memory){
  return memoryActive(memory)&&memory.data.status==='validated'&&memorySourceActive(store,memory.owner,memory);
}
export function memoryEvidenceActive(store,memory,entry){
  const outcome=store.get(entry.outcome_id),task=outcome&&store.get(outcome.data.task_id);
  return Boolean(outcome?.owner===memory.owner&&outcome.data.verdict==='accepted'&&(!entry.outcome_version||outcome.version===entry.outcome_version)&&task?.owner===memory.owner&&(memory.data.scope==='owner'||task.data.system===memory.data.scope)&&memorySourceActive(store,memory.owner,outcome,new Set(),outcome.data.task_id));
}
export function projectMemory(store,memory){
  const sourceValid=memorySourceActive(store,memory.owner,memory);
  const evidence=memory.data.evidence||[],validEvidence=evidence.filter(entry=>memoryEvidenceActive(store,memory,entry));
  const evidenceInvalid=validEvidence.length!==evidence.length;
  const alignment=evidenceInvalid?((memory.data.counterevidence||[]).some(e=>!e.resolved_at)?'hypothesis':validEvidence.length?'scenario_verified':'explicit'):memory.data.alignment;
  return {...memory,data:{...memory.data,...(memoryActive(memory)&&!sourceValid?{status:'needs_review',alignment:'insufficient'}:{alignment}),evidence_needs_review:evidenceInvalid,valid_evidence_count:validEvidence.length}};
}
