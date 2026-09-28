import test from 'node:test';
import assert from 'node:assert/strict';
import {Store,id} from '../../server/elfred/store.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
function setup(t){const store=new Store(':memory:');t.after(()=>store.close());const service=new Service(store,{status:()=>({configured:false})});const users=['a','b','c'].map(h=>authenticate(store,'responsibility-'+h,'test-password-responsibility',true,h).user);users.forEach(u=>service.initialize(u));const cmd=(u,a,i)=>service.command(u.id,id(),a,i),ref=o=>({id:o.id,version:store.get(o.id).version});const [a,b,c]=users;for(const u of [b,c]){const req=cmd(a,'friend.request',{handle:u.handle});cmd(u,'friend.respond',{...ref(req),decision:'accept'});}const group=cmd(a,'conversation.create',{title:'群',handles:[b.handle]});return {store,service,users,cmd,ref,group};}
test('G 历史权限在邀请时冻结；私密辅助与直接读取均不能绕过，移交后旧群主可退出',t=>{
 const {store,service,users:[a,b,c],cmd,ref,group}=setup(t),old=cmd(a,'message.send',{id:group.id,text:'入群前的消息'});
 cmd(a,'conversation.history_policy',{...ref(group),policy:'from_join',confirm:true});cmd(a,'conversation.invite',{...ref(group),handle:c.handle});
 assert.throws(()=>service.read(c.id,old.id),{code:'NOT_FOUND'});assert.equal(service.list(c.id,'message').filter(m=>m.space===group.id).length,0);
 const assist=cmd(c,'assist.create',{conversation_id:group.id,purpose:'读取旧消息'});assert.throws(()=>cmd(c,'assist.run',{...ref(assist),source_refs:[ref(old)],confirm:true,model_consent:true}),{code:'NOT_FOUND'});
 const fresh=cmd(b,'message.send',{id:group.id,text:'入群后的消息'});assert.equal(service.read(c.id,fresh.id).id,fresh.id);
 cmd(a,'conversation.history_policy',{...ref(group),policy:'all',confirm:true});assert.throws(()=>service.read(c.id,old.id),{code:'NOT_FOUND'});
 cmd(a,'conversation.transfer_owner',{...ref(group),user_id:b.id,confirm:true});assert.equal(store.get(group.id).owner,b.id);assert.equal(store.role(group.id,b.id),'owner');
 assert.throws(()=>cmd(a,'conversation.rename',{...ref(group),title:'越权修改'}),{code:'FORBIDDEN'});cmd(a,'conversation.remove_member',{...ref(group),user_id:a.id});assert.equal(store.role(group.id,a.id),undefined);
});
test('G 候选不自动变承诺；群主不能代签或覆盖分歧，负责人离群解除分配并封锁旧任务',t=>{
 const {store,service,users:[a,b],cmd,ref,group}=setup(t),candidate=cmd(a,'commitment.create',{conversation_id:group.id,goal:'核对材料'});
 assert.equal(store.get(candidate.id).data.status,'unassigned');assert.equal(store.list('task').length,0);cmd(a,'commitment.assign',{...ref(candidate),assignee:b.id});
 assert.throws(()=>cmd(a,'commitment.respond',{...ref(candidate),accept:true}),{code:'FORBIDDEN'});cmd(b,'commitment.respond',{...ref(candidate),accept:true});const taskId=store.get(candidate.id).data.task_id;
 const goal=cmd(a,'group.record.save',{conversation_id:group.id,kind:'goal',title:'目标',content:'确认范围',assignee:b.id});assert.throws(()=>cmd(a,'group.record.confirm',{...ref(goal),confirm:true}),{code:'FORBIDDEN'});cmd(b,'group.record.confirm',{...ref(goal),confirm:true});
 const dissent=cmd(b,'group.record.save',{conversation_id:group.id,kind:'disagreement',title:'范围分歧',content:'暂不同意'});assert.throws(()=>cmd(a,'group.record.archive',ref(dissent)),{code:'FORBIDDEN'});
 cmd(b,'conversation.remove_member',{...ref(group),user_id:b.id});assert.equal(store.get(candidate.id).data.status,'unassigned');assert.equal(store.get(candidate.id).data.task_id,null);assert.equal(store.get(candidate.id).data.previous_task_id,taskId);assert.throws(()=>service.read(b.id,taskId),{code:'NOT_FOUND'});
});
test('C 有限或高风险任务先审批，拒绝可说明；未发布的条款不泄漏，重新同意后才能批准',t=>{
 const {store,service,users:[a,b,c],cmd,ref}=setup(t),p=cmd(a,'project.create',{basis:'已有可公开基础',public_scope:'brief',reviewer_id:a.id,fee_terms:'各自承担费用',deadline_mode:'none',title:'作品',goal:'制作作品',criteria:'可用',task:'实现',participation:'open'}),slot=cmd(a,'project.slot.save',{project_id:p.id,title:'有限名额',criteria:'公开的旧标准',capacity:1}),post=cmd(a,'project.publish_post',{...ref(p),confirm:true});
 const claim=cmd(b,'project.claim',{post_id:post.id,slot_id:slot.id,slot_version:store.get(slot.id).version,confirm:true});assert.equal(store.get(claim.id).data.status,'pending');assert.equal(store.role(p.id,b.id),undefined);
 assert.throws(()=>cmd(c,'project.claim',{post_id:post.id,confirm:true}),{code:'SLOT_REQUIRED'});
 cmd(a,'project.slot.save',{...ref(slot),project_id:p.id,title:'有限名额',criteria:'尚未公开的新标准',capacity:1});assert.equal(store.get(claim.id).data.status,'needs_application_confirmation');
 const shown=service.list(c.id,'post').find(o=>o.id===post.id);assert.equal(shown.data.slots[0].criteria,'公开的旧标准');assert.equal(shown.data.slots[0].terms_changed,true);assert.throws(()=>cmd(c,'project.claim',{post_id:post.id,slot_id:slot.id,slot_version:store.get(slot.id).version,confirm:true}),{code:'SLOT_RULES_CHANGED'});
 assert.ok(!JSON.stringify(service.list(b.id,'claim')).includes('尚未公开的新标准'));assert.ok(!JSON.stringify(service.read(b.id,claim.id)).includes('尚未公开的新标准'));
 cmd(a,'project.publish_post',{...ref(p),confirm:true});cmd(b,'project.claim',{post_id:post.id,slot_id:slot.id,slot_version:store.get(slot.id).version,confirm:true});cmd(a,'claim.review',{...ref(claim),accept:true});assert.equal(service.list(b.id,'project_slot')[0].data.filled,1);assert.throws(()=>cmd(c,'project.claim',{post_id:post.id,slot_id:slot.id,slot_version:store.get(slot.id).version,confirm:true}),{code:'SLOT_FULL'});
 const high=cmd(a,'project.slot.save',{project_id:p.id,title:'高风险',criteria:'人工核对',capacity:null,risk:'high'});cmd(a,'project.publish_post',{...ref(p),confirm:true});const apply=cmd(c,'project.claim',{post_id:post.id,slot_id:high.id,slot_version:store.get(high.id).version,confirm:true});assert.equal(store.get(apply.id).data.status,'pending');cmd(a,'claim.review',{...ref(apply),accept:false,note:'请补充验证依据'});assert.equal(store.get(apply.id).data.review_note,'请补充验证依据');
 const open=cmd(a,'project.slot.save',{project_id:p.id,title:'开放任务',criteria:'可撤销',capacity:null,risk:'low'});cmd(a,'project.publish_post',{...ref(p),confirm:true});const immediate=cmd(c,'project.claim',{post_id:post.id,slot_id:open.id,slot_version:store.get(open.id).version,confirm:true});assert.equal(store.get(immediate.id).data.status,'accepted');
});
test('G 离群提议者的事项由群主重新提议，仍由新负责人本人接受',t=>{
 const {store,users:[a,b],cmd,ref,group}=setup(t),candidate=cmd(b,'commitment.create',{conversation_id:group.id,goal:'继续原事项',assignee:b.id});cmd(b,'commitment.respond',{...ref(candidate),accept:true});cmd(b,'conversation.remove_member',{...ref(group),user_id:b.id});cmd(a,'commitment.assign',{...ref(candidate),assignee:a.id});assert.equal(store.get(candidate.id).data.status,'proposed');assert.equal(store.get(candidate.id).data.task_id,null);cmd(a,'commitment.respond',{...ref(candidate),accept:true});assert.equal(store.get(candidate.id).data.status,'accepted');
});
test('C 再确认必须绑定本人看过的规则版本',t=>{
 const {store,users:[a,b],cmd,ref}=setup(t),p=cmd(a,'project.create',{basis:'已有可公开基础',public_scope:'brief',reviewer_id:a.id,fee_terms:'各自承担费用',deadline_mode:'none',title:'作品',goal:'制作作品',criteria:'可用',task:'实现'}),slot=cmd(a,'project.slot.save',{project_id:p.id,title:'任务',criteria:'旧',capacity:null}),post=cmd(a,'project.publish_post',{...ref(p),confirm:true}),claim=cmd(b,'project.claim',{post_id:post.id,slot_id:slot.id,slot_version:store.get(slot.id).version,confirm:true}),oldVersion=store.get(slot.id).version;
 cmd(a,'project.slot.save',{...ref(slot),project_id:p.id,title:'任务',criteria:'新',capacity:null});assert.throws(()=>cmd(b,'claim.reconfirm',{...ref(claim),slot_version:oldVersion,confirm:true}),{code:'VERSION_CONFLICT'});cmd(b,'claim.reconfirm',{...ref(claim),slot_version:store.get(slot.id).version,confirm:true});assert.equal(store.get(claim.id).data.rules_snapshot.criteria,'新');
});
