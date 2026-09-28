import test from 'node:test';
import assert from 'node:assert/strict';
import {Store,id} from '../../server/elfred/store.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {Runtime} from '../../server/elfred/runtime.mjs';
import {dailyTasks} from '../../app/v28/core/local-day.mjs';
import {plannedModelUnits} from '../../server/elfred/review-policy.mjs';
import {composePlan} from '../../server/elfred/agent-plan.mjs';
function setup(t){
 const store=new Store(':memory:'),calls=[];t.after(()=>store.close());
 const provider={status:()=>({configured:true}),generate:async input=>{calls.push(input);return {output:input.goal.phase==='review'?JSON.stringify({decision:'satisfied',issues:[]}):'已生成：'+input.goal.goal.slice(0,80),usage:{total_tokens:10}}}};
 const service=new Service(store,provider),runtime=new Runtime(store,provider),users=['alice','bob','carol'].map(h=>authenticate(store,h,'original-requirements-password',true,h).user);users.forEach(u=>service.initialize(u));
 const cmd=(u,a,i)=>service.command(u.id,id(),a,i),ref=o=>({id:o.id,version:store.get(o.id).version});
 const start=o=>{const u=users.find(u=>u.id===store.get(o.id).owner);cmd(u,'task.confirm',{...ref(o),confirm:true,model_consent:true});return cmd(u,'run.start',ref(o));};
 const group=()=>{for(const u of users.slice(1)){const request=cmd(users[0],'friend.request',{handle:u.handle});cmd(u,'friend.respond',{...ref(request),decision:'accept'});}return cmd(users[0],'conversation.create',{title:'项目群',handles:['bob','carol']});};
 const project=()=>{const p=cmd(users[0],'project.create',{basis:'已有可公开基础',public_scope:'brief',reviewer_id:users[0].id,fee_terms:'各自承担费用',deadline_mode:'none',title:'多人共创',goal:'共同交付',task:'完成成果',criteria:'本人逐项核对'});const post=cmd(users[0],'project.publish_post',{...ref(p),confirm:true});users.slice(1).forEach(u=>cmd(u,'project.claim',{post_id:post.id,confirm:true}));return p;};
 return {store,service,runtime,users,cmd,ref,start,calls,group,project};
}
test('共创公开的第一项任务有可认领身份，申请与副本沿同一任务',t=>{
 const {store,users:[a,b],cmd,ref}=setup(t);
 const project=cmd(a,'project.create',{title:'公开任务',goal:'共同完成页面',basis:'已有草稿',task:'完善移动布局',criteria:'手机窄屏可读',public_scope:'brief',reviewer_id:a.id,fee_terms:'各自承担费用',deadline_mode:'none',participation:'open'});
 const post=cmd(a,'project.publish_post',{...ref(project),confirm:true}),published=store.get(post.id);
 assert.equal(published.data.slots.length,1);
 assert.equal(published.data.slots[0].title,'完善移动布局');
 const claim=cmd(b,'project.claim',{post_id:post.id,confirm:true});
 assert.equal(store.get(claim.id).data.slot_id,published.data.slots[0].id);
 const copy=cmd(b,'copy.create',{project_id:project.id});
 assert.equal(store.get(copy.id).data.slot_id,published.data.slots[0].id);
 cmd(a,'project.brief.update',{...ref(project),title:'公开任务',goal:'共同完成页面',basis:'已有草稿',task:'完善移动布局与键盘',criteria:'手机窄屏与输入可读',public_scope:'brief',reviewer_id:a.id,fee_terms:'各自承担费用',deadline_mode:'none',participation:'open'});
 assert.equal(store.get(claim.id).data.status,'needs_reconfirmation');
 assert.equal(store.get(post.id).data.slots[0].title,'完善移动布局');
 cmd(a,'project.publish_post',{...ref(project),confirm:true});
 assert.equal(store.get(post.id).data.slots[0].title,'完善移动布局与键盘');
});
test('共创截止日期按发起者日历日执行，过期不能新认领或重新招募',t=>{
 const {store,users:[a,b],cmd,ref}=setup(t);
 const project=cmd(a,'project.create',{title:'有期限的项目',goal:'共同完成页面',basis:'已有草稿',task:'检查移动布局',criteria:'窄屏可读',public_scope:'brief',reviewer_id:a.id,fee_terms:'各自承担费用',deadline_mode:'date',deadline:'2999-12-31',participation:'open'});
 const post=cmd(a,'project.publish_post',{...ref(project),confirm:true});
 store.update(store.get(project.id),{...store.get(project.id).data,deadline:'2020-01-01'},a.id);
 assert.throws(()=>cmd(b,'project.claim',{post_id:post.id,confirm:true}),{code:'CLOSED'});
 assert.throws(()=>cmd(a,'project.recruiting',{...ref(project),enabled:true}),{code:'CLOSED'});
});
test('原稿 H02/H04：未排期想法不进入今日；接受才改安排，拒绝不改',t=>{
 const {store,users:[a],cmd,ref}=setup(t),task=cmd(a,'task.create',{goal:'未来的想法'});
 assert.equal(dailyTasks([store.get(task.id)]).length,0);
 const morning=cmd(a,'brief.create',{kind:'morning'});cmd(a,'brief.confirm',{...ref(morning),actions:[{task_id:task.id,version:ref(task).version,kind:'focus'}]});assert.equal(dailyTasks([store.get(task.id)]).length,1);
 const noon=cmd(a,'brief.create',{kind:'noon'}),suggestion=store.get(noon.id).data.suggestions[0],version=ref(task).version;
 cmd(a,'brief.suggestion',{...ref(noon),suggestion_id:suggestion.id,decision:'reject'});assert.equal(ref(task).version,version);
 cmd(a,'brief.refresh',ref(noon));assert.equal(store.list('run').length,0);
});
test('共创临时调度需发起者验收后才能共享，成员只看到确认的安排',async t=>{
 const {store,service,runtime,users:[a,b],cmd,ref,start,project}=setup(t),p=project();
 cmd(a,'project.budget',{...ref(p),limit:3000,confirm:true});
 const task=cmd(a,'project.dispatch',{id:p.id,goal:'协调页面分工',confirm:true,model_consent:true});
 assert.throws(()=>cmd(a,'project.dispatch.publish',{id:p.id,task_id:task.id,confirm:true}),{code:'REVIEW_REQUIRED'});
 start(task);await runtime.tick();
 assert.ok(['awaiting_review','awaiting_acceptance'].includes(store.get(task.id).data.status));
 cmd(a,'task.accept',{...ref(task),accept:true});
 const feedback=cmd(a,'project.dispatch.publish',{id:p.id,task_id:task.id,confirm:true});
 assert.equal(service.read(b.id,feedback.id).data.kind,'coordination');
 assert.equal(cmd(a,'project.dispatch.publish',{id:p.id,task_id:task.id,confirm:true}).id,feedback.id);
 assert.throws(()=>cmd(b,'project.dispatch.publish',{id:p.id,task_id:task.id,confirm:true}));
});
test('原稿 K03：知识编辑保留对象与来源、阻止旧版本和越权覆盖',t=>{
 const {store,service,users:[a,b],cmd,ref}=setup(t),doc=cmd(a,'document.create',{title:'来源.md',content:'原始事实'}),note=cmd(a,'knowledge.create',{title:'笔记',content:'旧内容',source_refs:[ref(doc)]}),old=ref(note);
 cmd(a,'knowledge.update',{...old,title:'更新的笔记',content:'新内容'});assert.equal(store.get(note.id).data.source_refs[0].id,doc.id);
 assert.throws(()=>cmd(a,'knowledge.update',{...old,title:'过期',content:'覆盖'}),{code:'VERSION_CONFLICT'});
 assert.throws(()=>cmd(b,'knowledge.update',{...ref(note),title:'越权',content:'覆盖'}),{code:'NOT_FOUND'});assert.equal(service.read(a.id,note.id).data.content,'新内容');
});
test('原稿 A10：单次情境可验证；反证阻止稳定；无七天自动升级',t=>{
 const {store,users:[a],cmd,ref}=setup(t);const memory=cmd(a,'memory.create',{content:'方案先讲问题',risk:'high',scope:'create'});cmd(a,'memory.decide',{...ref(memory),decision:'confirm'});
 const evidenceTask=store.add('task',a.id,{system:'create',status:'completed'});const outcomes=[store.add('outcome',a.id,{verdict:'accepted',task_id:evidenceTask.id}),store.add('outcome',a.id,{verdict:'accepted',task_id:evidenceTask.id})];store.db.prepare('UPDATE objects SET created=? WHERE id=?').run('2025-01-01T00:00:00Z',outcomes[0].id);
 cmd(a,'memory.evidence',{...ref(memory),outcome_id:outcomes[0].id,scenario:'评审',note:'实际符合本次目标',confirm:true});assert.equal(store.get(memory.id).data.alignment,'scenario_verified');
 cmd(a,'memory.counterevidence',{...ref(memory),note:'紧急沟通需要先说结论',confirm:true});
 cmd(a,'memory.evidence',{...ref(memory),outcome_id:outcomes[1].id,scenario:'评审',note:'再次核对本次范围',confirm:true});assert.equal(store.get(memory.id).data.alignment,'hypothesis');
 assert.throws(()=>cmd(a,'memory.review_stability',{...ref(memory),confirm:true,note:'还没解决反证'}),{code:'COUNTEREVIDENCE_UNRESOLVED'});
});
test('原稿 A14：草稿、固定和测试不进最近；实际运行只计一次',async t=>{
 const {store,users:[a],cmd,ref,start,runtime}=setup(t),tool=cmd(a,'tool.save',{title:'改写',instructions:'保留事实并改写',kind:'Skill',system:'create'});cmd(a,'tool.activate',ref(tool));
 const use=cmd(a,'tool.use',{id:tool.id,version_id:store.get(tool.id).data.version_id});cmd(a,'shortcut.pin',{skill_id:tool.id});assert.equal(store.get(tool.id).data.last_used_at,undefined);
 const preview=cmd(a,'tool.test',{id:tool.id,version_id:store.get(tool.id).data.version_id});start({id:preview.task_id});await runtime.tick();assert.equal(store.get(tool.id).data.uses,0);
 start({id:use.task_id});await runtime.tick();assert.equal(store.get(tool.id).data.uses,1);assert.ok(store.get(tool.id).data.last_used_at);
});
test('原稿 P多轮：未完成父轮不可追加；完成后携历史，跟进继承撤权而非运行状态版本',async t=>{
 const {store,service,users:[a,b],cmd,ref,runtime,calls,group}=setup(t),g=group(),message=cmd(a,'message.send',{id:g.id,text:'邀请我周五参加评审'}),assist=cmd(b,'assist.create',{conversation_id:g.id,purpose:'帮我婉拒邀请'});
 cmd(b,'assist.run',{...ref(assist),confirm:true,model_consent:true,source_refs:[ref(message)]});
 assert.throws(()=>cmd(b,'assist.create',{conversation_id:g.id,purpose:'温和一点',parent_id:assist.id}),{code:'RUN_ACTIVE'});
 await runtime.tick();const next=cmd(b,'assist.create',{conversation_id:g.id,purpose:'温和一点',parent_id:assist.id});cmd(b,'assist.run',{...ref(next),confirm:true,model_consent:true});await runtime.tick();assert.match(calls.at(-1).goal.goal,/先前问答/);assert.match(calls.at(-1).goal.goal,/婉拒邀请/);
 const followup=cmd(b,'assist.followup',{...ref(assist),run_id:store.get(store.get(assist.id).data.task_id).data.run_id,run_version:store.get(store.get(store.get(assist.id).data.task_id).data.run_id).version}),task={id:store.get(assist.id).data.task_id};cmd(b,'task.accept',{...ref(task),accept:true});assert.ok(service.read(b.id,followup.id));
 cmd(a,'conversation.remove_member',{...ref(g),user_id:b.id});assert.throws(()=>service.read(b.id,followup.id),{code:'NOT_FOUND'});
});
test('原稿 G事项身份：改目标保留ID但清旧验收、反馈与checkpoint',async t=>{
 const {store,users:[a,b],cmd,ref,start,runtime,group,calls}=setup(t),g=group(),c=cmd(a,'commitment.create',{conversation_id:g.id,assignee:b.id,goal:'原目标'}),accepted=cmd(b,'commitment.respond',{...ref(c),accept:true}),task={id:accepted.task_id};start(task);await runtime.tick();cmd(b,'task.accept',{...ref(task),accept:false,feedback:'旧目标修改意见'});
 cmd(a,'commitment.revise',{...ref(c),goal:'新的邮件目标'});assert.equal(cmd(b,'commitment.respond',{...ref(c),accept:true}).task_id,task.id);assert.equal(store.get(task.id).data.status,'draft');assert.equal(store.get(task.id).data.feedback,null);
 start(task);await runtime.tick();assert.match(calls.at(-1).goal.goal,/新的邮件目标/);assert.equal(calls.at(-1).goal.revision_feedback,null);
});
test('原稿 S：自然语言召回、条件未知分组、关系与权限过滤',t=>{
 const {service,users:[a,b],cmd,ref,group}=setup(t),doc=cmd(a,'document.create',{title:'报名说明.md',content:'报名人数上限为100人，满员后停止提交。'});
 const result=service.search(a.id,{query:'找包含报名人数上限的说明'});assert.ok(result.hits.some(h=>h.id===doc.id));assert.equal(result.hits.find(h=>h.id===doc.id).condition_status,'unknown');
 assert.equal(service.search(b.id,{query:'报名人数上限'}).hits.length,0);
 assert.equal(service.search(a.id,{query:'这个群里的报名说明'}).status,'needs_clarification');
 const g=group(),m=cmd(a,'message.send',{id:g.id,text:'报名人数上限为100人'});assert.ok(service.search(b.id,{query:'报名',space:g.id,author:a.id}).hits.some(h=>h.id===m.id));
 assert.equal(service.search(b.id,{query:'报名',space:g.id,author:b.id}).hits.length,0);
});
test('原稿 T04：评估前额度与各实际计划一致',t=>{
 const {store,users:[a],cmd}=setup(t);for(const review_mode of ['single','auto','independent']){const task=cmd(a,'task.create',{goal:'撰写文稿',review_mode});assert.equal(plannedModelUnits(store.get(task.id)),composePlan(store.get(task.id)).length*1000);}
});
test('原稿 C：不同文件并行贡献与修订不覆盖他人的新修改',t=>{
 const {store,users:[a,b,c],cmd,ref,project}=setup(t),p=project();
 const initial=cmd(a,'copy.create',{project_id:p.id});cmd(a,'copy.files',{...ref(initial),files:{'a.md':'A0','b.md':'B0'}});cmd(a,'copy.save',{...ref(initial),content:'基线'});const base=cmd(a,'copy.submit',{...ref(initial),reviewed:true});cmd(a,'contribution.review',{...ref(base),decision:'accept'});
 const one=cmd(b,'copy.create',{project_id:p.id}),two=cmd(c,'copy.create',{project_id:p.id});
 cmd(b,'copy.files',{...ref(one),files:{...store.get(one.id).data.files,'a.md':'A1'}});const first=cmd(b,'copy.submit',{...ref(one),reviewed:true});cmd(a,'contribution.review',{...ref(first),decision:'accept'});
 cmd(c,'copy.files',{...ref(two),files:{...store.get(two.id).data.files,'b.md':'B1'}});const second=cmd(c,'copy.submit',{...ref(two),reviewed:true});cmd(a,'contribution.review',{...ref(second),decision:'changes'});
 const revision=cmd(c,'copy.revise',ref(two));assert.equal(store.get(revision.id).data.files['a.md'],'A1');const final=cmd(c,'copy.submit',{...ref(revision),reviewed:true});cmd(a,'contribution.review',{...ref(final),decision:'accept'});assert.equal(store.get(p.id).data.files['a.md'],'A1');assert.equal(store.get(p.id).data.files['b.md'],'B1');
});
test('原稿 C：AI副本、共享阶段、约定变化停止执行，结束后禁止新工作',async t=>{
 const {store,users:[a,b],cmd,ref,start,runtime,project}=setup(t),p=project(),slot=cmd(a,'project.slot.save',{project_id:p.id,title:'实现',criteria:'核对',capacity:1}),post=cmd(a,'project.publish_post',{...ref(p),confirm:true});const claim=cmd(b,'project.claim',{post_id:post.id,slot_id:slot.id,slot_version:store.get(slot.id).version,confirm:true});cmd(a,'claim.review',{...ref(claim),accept:true});
 const copy=cmd(b,'copy.create',{project_id:p.id,slot_id:slot.id}),task=cmd(b,'copy.ai_prepare',{...ref(copy),goal:'完成说明',confirm:true,model_consent:true});start(task);await runtime.tick();cmd(b,'copy.ai_apply',{...ref(copy),reviewed:true});assert.ok(store.get(copy.id).data.content);
 const stage=cmd(b,'copy.stage',{...ref(copy),title:'第一阶段',reviewed:true});assert.equal(store.read(a.id,stage.id).data.status,'shared');
 cmd(a,'project.slot.save',{...ref(slot),project_id:p.id,title:'实现',criteria:'新标准',capacity:1});assert.equal(store.get(claim.id).data.status,'needs_reconfirmation');assert.throws(()=>runtime.permitted(store.get(store.get(task.id).data.run_id)),{code:'SLOT_RULES_CHANGED'});
 cmd(a,'project.end',{...ref(p),confirm:true});assert.throws(()=>cmd(b,'copy.create',{project_id:p.id}),{code:'PROJECT_CLOSED'});
});
test('原稿 C：真实同文件冲突必须明确解决；文件与网页发布保持一致',t=>{
 const {store,users:[a,b,c],cmd,ref,project}=setup(t),p=project(),x=cmd(b,'copy.create',{project_id:p.id}),y=cmd(c,'copy.create',{project_id:p.id});
 cmd(b,'copy.save',{...ref(x),format:'web',content:'<main>甲</main>'});const one=cmd(b,'copy.submit',{...ref(x),reviewed:true});cmd(a,'contribution.review',{...ref(one),decision:'accept'});
 cmd(c,'copy.save',{...ref(y),format:'web',content:'<main>乙</main>'});const two=cmd(c,'copy.submit',{...ref(y),reviewed:true});cmd(a,'contribution.review',{...ref(two),decision:'accept'});assert.equal(store.get(two.id).data.status,'conflicted');
 const rev=cmd(c,'copy.revise',ref(y));assert.throws(()=>cmd(c,'copy.submit',{...ref(rev),reviewed:true}),{code:'CONFLICT_UNRESOLVED'});cmd(c,'copy.files',{...ref(rev),files:{'index.html':'<main>甲和乙</main>'}});cmd(c,'copy.resolve',{...ref(rev),reviewed:true});const final=cmd(c,'copy.submit',{...ref(rev),reviewed:true});cmd(a,'contribution.review',{...ref(final),decision:'accept'});const release=cmd(a,'project.release',{...ref(p),confirm:true});assert.equal(store.get(release.id).data.content,store.get(release.id).data.files['index.html']);
});
test('原稿 C：公共额度耗尽阻塞且不调用模型，补充后可恢复',async t=>{
 const {store,users:[a],cmd,ref,start,runtime,calls,project}=setup(t),p=project();cmd(a,'project.budget',{...ref(p),limit:0,confirm:true});const task=cmd(a,'project.dispatch',{id:p.id,goal:'协调下一阶段',confirm:true,model_consent:true});start(task);await runtime.tick();assert.equal(store.get(task.id).data.status,'blocked');assert.equal(calls.length,0);
 cmd(a,'project.budget',{...ref(p),limit:3000,confirm:true});cmd(a,'run.start',ref(task));await runtime.tick();assert.ok(calls.length>0);assert.ok(store.get(task.id).data.units<=3000);
});
