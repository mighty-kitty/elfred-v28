import {projectActive} from './project-work.mjs';
import {fail,now} from './store.mjs';
import {string,bounded,enumeration} from './policy.mjs';
export function publicSlots(store,projectId){return store.list('project_slot').filter(s=>s.space===projectId).map(s=>({id:s.id,...s.data,rules_version:s.version,filled:store.list('claim').filter(c=>c.data.slot_id===s.id&&['accepted','needs_reconfirmation'].includes(c.data.status)).length}));}
// Only operational status is live. Edited recruitment terms stay private until republished.
export function publishedSlots(store,post){return (post.data.slots||[]).map(published=>{const current=store.get(published.id);return {...published,filled:store.list('claim').filter(c=>c.data.slot_id===published.id&&['accepted','needs_reconfirmation'].includes(c.data.status)).length,status:current?.data.status||'closed',terms_changed:Boolean(current&&published.rules_version!==current.version)};});}
export function requiresApproval(project,slot){return project.data.participation==='application'||Boolean(slot&&(slot.data.capacity!==null||slot.data.risk==='high'||slot.data.participation==='application'));}
export function checkSlot(store,project,slot,requested){
 if(requested&&(!slot||slot.type!=='project_slot'||slot.space!==project.id))fail('INVALID_SLOT','任务位不存在');
 if(!slot)return;
 if(slot.data.status!=='open'||slot.data.deadline&&Date.parse(slot.data.deadline)<=Date.now())fail('SLOT_CLOSED','此任务位已关闭或超过截止时间');
 // Members may claim before prerequisites finish; execution requires completed or explicitly shared stage versions.
 if(slot.data.capacity!==null&&store.list('claim').filter(c=>c.data.slot_id===slot.id&&['accepted','needs_reconfirmation'].includes(c.data.status)).length>=slot.data.capacity)fail('SLOT_FULL','此任务位已满员');
}
export function slotCommand(store,user,action,input){
 if(action==='project.slot.save'){
  const project=store.owned(user,input.project_id,'project');projectActive(store,user,project.id);
  const slot=input.id?store.expect(store.read(user,input.id,'project_slot'),input.version):null;
  if(slot&&slot.space!==project.id)fail('INVALID_SLOT','任务位不属于此项目');
  const depends=Array.isArray(input.depends_on)?[...new Set(input.depends_on)]:[];
  if(depends.length>20)fail('INVALID_INPUT','前置任务过多');
  const visit=(id,seen=new Set())=>{if(id===slot?.id||seen.has(id))fail('DEPENDENCY_CYCLE','任务依赖不能形成循环');const source=store.read(user,id,'project_slot');if(source.space!==project.id)fail('INVALID_SLOT','只能依赖本项目任务');const next=new Set(seen).add(id);for(const dep of source.data.depends_on||[])visit(dep,next);};
  depends.forEach(id=>visit(id));
  let deadline=null;if(input.deadline){if(!Number.isFinite(Date.parse(input.deadline)))fail('INVALID_INPUT','截止时间不正确');deadline=new Date(input.deadline).toISOString();}
  const data={title:string(input.title,'任务名称',200),criteria:string(input.criteria,'验收标准',2000),capacity:input.capacity===null?null:bounded(input.capacity??1,'人数',1,100),risk:enumeration(input.risk||slot?.data.risk||'low',['low','high'],'任务风险'),participation:enumeration(input.participation||slot?.data.participation||'open',['open','application'],'参与方式'),deadline,depends_on:depends,status:slot?.data.status||'open',...(slot?.data.auto_brief?{auto_brief:true}:{})};
  if(slot&&data.capacity!==null&&store.list('claim').filter(c=>c.data.slot_id===slot.id&&['accepted','needs_reconfirmation'].includes(c.data.status)).length>data.capacity)fail('CAPACITY_CONFLICT','人数不能低于已经接纳的人数');
  if(slot)for(const claim of store.list('claim').filter(c=>c.data.slot_id===slot.id&&['accepted','needs_reconfirmation'].includes(c.data.status)))store.update(claim,{...claim.data,status:'needs_reconfirmation',previous_rules:claim.data.rules_snapshot||slot.data,new_rules:data},user);
  if(slot)for(const claim of store.list('claim').filter(c=>c.data.slot_id===slot.id&&c.data.status==='pending'))store.update(claim,{...claim.data,status:'needs_application_confirmation',previous_rules:claim.data.rules_snapshot||slot.data,new_rules:data},user);
  return {id:slot?store.update(slot,data,user).id:store.add('project_slot',user,data,{space:project.id,visibility:'members'}).id};
 }
 if(action==='project.slot.close'){
  const slot=store.expect(store.read(user,input.id,'project_slot'),input.version);store.owned(user,slot.space,'project');
  return {id:store.update(slot,{...slot.data,status:'closed'},user).id};
 }
 if(action==='claim.withdraw'){
  const claim=store.expect(store.owned(user,input.id,'claim'),input.version);
  if(!['pending','accepted','needs_reconfirmation','needs_application_confirmation'].includes(claim.data.status))fail('INVALID_STATE','当前认领不可撤回');
  return {id:store.update(claim,{...claim.data,status:'withdrawn',withdrawn_at:now()},user).id};
 }
 return null;
}
