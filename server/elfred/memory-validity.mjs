import {memoryActive,memoryAdmitted} from '../../app/v28/core/memory-policy.mjs';

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
  return memoryActive(memory)&&memoryAdmitted(memory)&&memorySourceActive(store,memory.owner,memory);
}
export function memoryEvidenceActive(store,memory,entry){
  if(entry.source_id){
    const source=store.get(entry.source_id);
    if(source?.owner!==memory.owner||source.version!==entry.source_version||!memorySourceActive(store,memory.owner,source))return false;
    if(entry.reply_id){const reply=store.get(entry.reply_id),run=reply&&store.get(reply.data.run_id),task=run&&store.get(run.data.task_id);if(reply?.owner!==memory.owner||reply.version!==entry.reply_version||reply.data.actor_type!=='agent'||task?.owner!==memory.owner||!memorySourceActive(store,memory.owner,reply)||!memorySourceActive(store,memory.owner,run)||!run.data.memory_refs?.some(ref=>ref.id===memory.id)||task.data.system!==entry.system)return false;}
    if(!entry.outcome_id)return Boolean(entry.reply_id);
  }
  const outcome=store.get(entry.outcome_id),task=outcome&&store.get(outcome.data.task_id);
  return Boolean(outcome?.owner===memory.owner&&outcome.data.verdict==='accepted'&&(!entry.outcome_version||outcome.version===entry.outcome_version)&&task?.owner===memory.owner&&(memory.data.scope==='owner'||task.data.system===memory.data.scope)&&memorySourceActive(store,memory.owner,outcome,new Set(),outcome.data.task_id));
}
export function memoryCounterevidenceActive(store,memory,entry){
  if(entry.resolved_at)return false;
  if(!entry.source_id)return true; // A direct, explicit manual correction.
  const source=store.get(entry.source_id);
  if(source?.owner!==memory.owner||source.version!==entry.source_version||!memorySourceActive(store,memory.owner,source))return false;
  return entry.reply_id||entry.outcome_id?memoryEvidenceActive(store,memory,entry):true;
}
export function projectMemory(store,memory){
  const sourceValid=memorySourceActive(store,memory.owner,memory);
  const evidence=memory.data.evidence||[],validEvidence=evidence.filter(entry=>memoryEvidenceActive(store,memory,entry));
  const evidenceInvalid=validEvidence.length!==evidence.length;
  const counters=memory.data.counterevidence||[],validCounters=counters.filter(e=>memoryCounterevidenceActive(store,memory,e));
  const counterInvalid=counters.some(e=>!e.resolved_at&&!memoryCounterevidenceActive(store,memory,e));
  const alignment=evidenceInvalid||counterInvalid?(validCounters.length?'hypothesis':validEvidence.length?'scenario_verified':memory.data.initial_alignment||'hypothesis'):memory.data.alignment;
  const domainAlignment=Object.fromEntries(['explore','advise','create','connect','execute'].map(system=>{
    const entries=validEvidence.filter(e=>(e.system||store.get(store.get(e.outcome_id)?.data.task_id)?.data.system)===system);
    const counter=validCounters.some(e=>!e.system||e.system===system);
    const stable=entries.length>=2&&new Set(entries.map(e=>e.observed_at.slice(0,10))).size>=2&&new Set(entries.map(e=>e.scenario)).size>=2;
    return [system,counter?'hypothesis':stable?'stable_over_time':entries.length?'scenario_verified':memory.data.initial_alignment||'explicit'];
  }));
  return {...memory,data:{...memory.data,...(memoryActive(memory)&&!sourceValid?{status:'needs_review',alignment:'insufficient'}:{alignment}),domain_alignment:domainAlignment,evidence_needs_review:evidenceInvalid,valid_evidence_count:validEvidence.length}};
}
