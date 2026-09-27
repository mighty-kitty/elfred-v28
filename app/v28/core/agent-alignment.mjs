import {memoryActive} from './memory-policy.mjs';
export const alignmentStages = [
  {id:'explicit',label:'明确信息',description:'本人明确表达的目标、偏好或约束。'},
  {id:'hypothesis',label:'理解待验证',description:'已形成场景化理解，仍需本人核对。'},
  {id:'scenario_verified',label:'场景已验证',description:'具体理解有对应情境和本人确认的成果依据。'},
  {id:'stable_over_time',label:'跨时间稳定',description:'同一理解有跨时间证据，仍需关注目标变化和反证。'},
];

/** @param {Array<{id:string,version:number,data:Record<string,any>}>} memories */
export function agentAlignment(memories, system) {
  const scoped=memories.filter(item=>item.data.scope===system&&(memoryActive(item)||item.data.status==='needs_review'&&!item.data.hidden&&(!item.data.expires_at||Date.parse(item.data.expires_at)>Date.now())));
  const entries=scoped.map(item=>{
    const state=item.data.status==='needs_review'||item.data.evidence_needs_review?'insufficient':
      ['candidate','pending_confirmation'].includes(item.data.status)?'hypothesis':
      alignmentStages.some(stage=>stage.id===item.data.alignment)?item.data.alignment:'explicit';
    return {id:item.id,version:item.version,state,label:alignmentStages.find(stage=>stage.id===state)?.label||'需要重评'};
  });
  const states=new Set(entries.map(item=>item.state));
  const state=states.size===1?[...states][0]:states.size?'mixed':'insufficient';
  return {system,state,label:state==='mixed'?'理解不一致':state==='insufficient'?(entries.length?'需要重评':'尚无足够理解'):alignmentStages.find(stage=>stage.id===state).label,entries,counts:Object.fromEntries(alignmentStages.map(stage=>[stage.id,entries.filter(item=>item.state===stage.id).length]))};
}
export function memoryOverview(memories){
  const domains=['explore','advise','create','connect','execute'].map(system=>agentAlignment(memories,system));
  const known=domains.filter(domain=>domain.entries.length).length;
  const active=memories.filter(m=>memoryActive(m)),owner=agentAlignment(memories,'owner');
  return {domains,known,label:known?`${known}/5 个领域有记录`:owner.entries.length?owner.label:'尚无足够理解',confirmedCount:active.filter(m=>m.data.status==='validated').length};
}
