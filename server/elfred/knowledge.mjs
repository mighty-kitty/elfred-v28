import { fail, hash, now } from './store.mjs';
import { string, enumeration } from './policy.mjs';
import {memoryGroup} from '../../app/v28/core/memory-policy.mjs';
import {queueMemorySync} from './memory-hub.mjs';
import {memoryEvidenceActive,memorySourceActive} from './memory-validity.mjs';

export function sourceRefs(store, user, refs=[], maximum=20) {
  if (!Array.isArray(refs) || refs.length>maximum) fail('INVALID_INPUT','最多选择 '+maximum+' 个来源');
  return refs.map(ref=>{
    if (!ref || typeof ref.id!=='string') fail('INVALID_INPUT','来源格式不正确');
    const source=store.read(user,ref.id);
    if(source.data.hidden===true||source.data.expires_at&&Date.parse(source.data.expires_at)<=Date.now())fail('SOURCE_INVALID','资料已隐藏或超过有效期，请先由本人重新核对',409);
    if(source.type==='context_grant')sourceRefs(store,user,source.data.source_refs,10);
    if (ref.version && source.version!==ref.version) fail('SOURCE_CHANGED','来源已变化，请重新确认',409);
    if (['rejected','superseded','expired','deleted','needs_review'].includes(source.data.status)) fail('SOURCE_INVALID','来源已失效',409);
    return {id:source.id,version:source.version};
  });
}
export {localSearch as search} from './search-engine.mjs';
export function knowledgeCommand(store,user,action,input) {
  const before=action.startsWith('memory.')?new Map(store.list('memory').map(m=>[m.id,m.version])):null;
  const result=handleKnowledge(store,user,action,input);
  if(before)for(const memory of store.list('memory'))if(memory.owner===user&&memory.version!==before.get(memory.id))queueMemorySync(store,memory);
  return result;
}
function handleKnowledge(store,user,action,input) {
  if(action==='memory.governance'){
    const memory=store.expect(store.owned(user,input.id,'memory'),input.version);
    if(['deleted','superseded','rejected'].includes(memory.data.status))fail('INVALID_STATE','已失效的理解不能重新用于任务');
    let expires=null;if(input.expires_at){const at=Date.parse(input.expires_at);if(!Number.isFinite(at)||at<=Date.now())fail('INVALID_INPUT','请选择未来的到期时间');expires=new Date(at).toISOString();}
    return {id:store.update(memory,{...memory.data,hidden:input.hidden===true,expires_at:expires,governance_updated_at:now()},user).id};
  }
  if (action==='document.create') {
    const title=string(input.title,'文件名',200), content=string(input.content,'正文',500000);
    if (!/\.(txt|md|csv|json)$/i.test(title)) fail('UNSUPPORTED_FORMAT','本地解析支持 UTF-8 txt/md/csv/json；其他格式请转换为文字',415);
    if (content.includes('\u0000') || content.includes('\ufffd')) fail('INVALID_ENCODING','文件不是有效 UTF-8 文本');
    if (/\.json$/i.test(title)) { try { JSON.parse(content); } catch { fail('INVALID_DOCUMENT','JSON 格式不正确'); } }
    const document=store.add('document',user,{title,content,status:'ready',parser:'utf8-lines-v1',content_hash:hash(content),line_count:content.split('\n').length});
    return {id:document.id};
  }
  if (action==='memory.create') {
    const content=string(input.content,'理解内容',4000);
    const scope=enumeration(input.scope||'owner',['owner','explore','advise','create','connect','execute'],'归属');
    const risk=enumeration(input.risk||'high',['low','high'],'影响');
    const refs=sourceRefs(store,user,input.source_refs);
    if(refs.some(ref=>!memorySourceActive(store,user,store.get(ref.id))))fail('MEMORY_SOURCE_SCOPE','一次任务的上下文授权不能转为长期记忆，请由本人独立核对适用范围',403);
    return {id:store.add('memory',user,{content,scope,group:memoryGroup(content),risk,source_refs:refs,status:risk==='high'?'pending_confirmation':'candidate',alignment:'insufficient',claim_type:input.claim_type==='fact'?'fact':'hypothesis',evidence:[],usage_purpose:string(input.purpose||'由本人核对后用于相关任务','用途',500)}).id};
  }
  if (action==='memory.decide') {
    const memory=store.expect(store.owned(user,input.id,'memory'),input.version);
    const decision=enumeration(input.decision,['confirm','correct','defer','reject','delete'],'决定');
    if (['superseded','deleted'].includes(memory.data.status)) fail('INVALID_STATE','旧理解已失效',409);
    if(decision==='confirm'&&memory.data.status==='validated')return {id:memory.id};
    const status={confirm:'validated',correct:'superseded',defer:'deferred',reject:'rejected',delete:'deleted'}[decision];
    const updated=store.update(memory,{...memory.data,status,alignment:decision==='confirm'?'explicit':'insufficient',decided_at:now()},user);
    for (const derived of store.list('memory').filter(item=>(item.data.source_refs||[]).some(ref=>ref.id===memory.id))) store.update(derived,{...derived.data,status:'needs_review',alignment:'insufficient'},user);
    if (decision==='correct') return {id:store.add('memory',user,{...memory.data,content:string(input.content,'修正内容',4000),group:memoryGroup(input.content),correction_origin_refs:memory.data.source_refs,source_refs:[],supersedes_id:memory.id,status:'validated',alignment:'explicit',evidence:[],counterevidence:[],decided_at:now()}).id};
    return {id:updated.id};
  }
  if(action==='memory.evidence') {
    const memory=store.expect(store.owned(user,input.id,'memory'),input.version);
    if(memory.data.status!=='validated'||input.confirm!==true)fail('CONFIRMATION_REQUIRED','需先由本人确认理解，再核对真实情境证据');
    const outcome=store.owned(user,input.outcome_id,'outcome');
    if(outcome.data.verdict!=='accepted')fail('OUTCOME_REQUIRED','需要本人已验收的结果');
    const task=store.owned(user,outcome.data.task_id,'task');
    if(memory.data.scope!=='owner'&&task.data.system!==memory.data.scope)fail('MEMORY_SCOPE','证据属于其他领域，不能直接提高本领域的理解',403);
    const evidence=[...(memory.data.evidence||[])];
    if(evidence.some(item=>item.outcome_id===outcome.id))fail('DUPLICATE_EVIDENCE','同一结果不能重复计入证据',409);
    evidence.push({outcome_id:outcome.id,outcome_version:outcome.version,scenario:string(input.scenario,'情境',200),note:string(input.note,'理解与结果的对应依据',2000),observed_at:outcome.created,confirmed_at:now()});
    const alignment=(memory.data.counterevidence||[]).some(item=>!item.resolved_at)?'hypothesis':'scenario_verified';
    return {id:store.update(memory,{...memory.data,evidence,alignment},user).id};
  }
  if (action==='knowledge.create') {
    const refs=sourceRefs(store,user,input.source_refs);
    return {id:store.add('knowledge',user,{title:string(input.title,'标题',200),content:string(input.content,'内容',100000),source_refs:refs,status:'active',kind:'note'}).id};
  }
  if(action==='memory.counterevidence'||action==='memory.review_stability') {
    const memory=store.expect(store.owned(user,input.id,'memory'),input.version);
    if(memory.data.status!=='validated'||input.confirm!==true)fail('CONFIRMATION_REQUIRED','请先确认理解和本次核对');
    const note=string(input.note,'核对依据',2000);
    if(action==='memory.counterevidence')return {id:store.update(memory,{...memory.data,alignment:'hypothesis',counterevidence:[...(memory.data.counterevidence||[]),{note,at:now()}]},user).id};
    const evidence=memory.data.evidence||[];
    for(const entry of evidence){if(!memoryEvidenceActive(store,memory,entry))fail('EVIDENCE_CHANGED','原验证证据已失效，请重新核对',409);}
    if(evidence.length<2||new Set(evidence.map(e=>e.observed_at)).size<2)fail('EVIDENCE_REQUIRED','需要分散时间的多次真实情境反馈，不能按天数自动升级');
    if((memory.data.counterevidence||[]).some(e=>!e.resolved_at)&&input.resolve_counterevidence!==true)fail('COUNTEREVIDENCE_UNRESOLVED','请先核对并明确处理未解决反证');
    return {id:store.update(memory,{...memory.data,alignment:'stable_over_time',stability_review:{note,at:now(),evidence_ids:evidence.map(e=>e.outcome_id)},counterevidence:(memory.data.counterevidence||[]).map(e=>({...e,resolved_at:e.resolved_at||now(),resolution:e.resolution||note}))},user).id};
  }
  if(action==='knowledge.update') {
    const item=store.expect(store.owned(user,input.id,'knowledge'),input.version);
    if(item.data.status==='archived')fail('INVALID_STATE','请先恢复笔记再编辑',409);
    return {id:store.update(item,{...item.data,title:string(input.title,'标题',200),content:string(input.content,'内容',100000),edited_by:user,edited_at:now(),kind:item.data.kind==='accepted_result'?'edited_result':item.data.kind},user).id};
  }
  if (action==='knowledge.archive') {
    const item=store.expect(store.owned(user,input.id,'knowledge'),input.version);
    return {id:store.update(item,{...item.data,status:'archived'},user).id};
  }
  return null;
}
