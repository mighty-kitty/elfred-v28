import test from 'node:test';
import assert from 'node:assert/strict';
import {Store,id} from '../../server/elfred/store.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {Runtime} from '../../server/elfred/runtime.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {calendarICS} from '../../app/v28/core/calendar-ics.mjs';
async function setup(t){
 const store=new Store(':memory:');t.after(()=>store.close());
 const provider={status:()=>({configured:true}),generate:async x=>({output:x.goal.phase==='review'?JSON.stringify({decision:'satisfied',issues:[]}):'已核对公开目标，私有原文需另行删减。',usage:{total_tokens:10}})};
 const service=new Service(store,provider),runtime=new Runtime(store,provider),users=['a','b','c'].map(h=>authenticate(store,'handoff-'+h,'handoff-test-password',true,h).user);users.forEach(u=>service.initialize(u));
 const [a,b]=users,cmd=(u,action,input,key=id())=>service.command(u.id,key,action,input),ref=o=>({id:o.id,version:store.get(o.id).version});
 const request=cmd(a,'friend.request',{handle:b.handle});cmd(b,'friend.respond',{...ref(request),decision:'accept'});
 const conversation=store.visible(a.id,'conversation')[0],message=cmd(b,'message.send',{id:conversation.id,text:'下周讨论公开项目的目标'}),privateNote=cmd(a,'knowledge.create',{title:'私有依据',content:'PRIVATE_SOURCE_DO_NOT_SHARE'});
 const assist=cmd(a,'assist.create',{conversation_id:conversation.id,purpose:'整理这次讨论'});cmd(a,'assist.run',{...ref(assist),source_refs:[ref(message),ref(privateNote)],confirm:true,model_consent:true});await runtime.tick();
 const run=store.get(store.get(store.get(assist.id).data.task_id).data.run_id),input={...ref(assist),run_version:run.version,run_id:run.id,title:'经本人核对的摘要',content:'共同讨论项目目标，尚未确认任何人的承诺。',confirm:true,reviewed_summary:true};
 return {store,service,runtime,users,cmd,ref,conversation,message,privateNote,assist,run,input};
}
test('P10 shared minutes require reviewed scope, expose only selected same-chat evidence, never accept others commitments',async t=>{
 const {store,service,users:[a,b,c],cmd,ref,input,conversation,message,privateNote}=await setup(t),before=store.list('message').length;
 assert.throws(()=>cmd(a,'assist.share_record',{...input,reviewed_summary:false}),{code:'SHARING_REVIEW_REQUIRED'});
 assert.throws(()=>cmd(a,'assist.share_record',{...input,source_refs:[ref(privateNote)]}),{code:'NOT_FOUND'});
 const key=id(),result=cmd(a,'assist.share_record',{...input,source_refs:[ref(message)]},key);assert.deepEqual(cmd(a,'assist.share_record',{...input,source_refs:[ref(message)]},key),result);
 assert.equal(store.list('message').length,before+1);assert.equal(store.list('commitment').length,0);assert.equal(store.list('task').length,1);
 const record=service.read(b.id,result.target_id);assert.equal(record.space,conversation.id);assert.equal(record.data.source_refs.length,1);assert.ok(!JSON.stringify(service.bootstrap(b.id)).includes('PRIVATE_SOURCE_DO_NOT_SHARE'));
 assert.throws(()=>service.read(c.id,result.target_id),{code:'NOT_FOUND'});assert.throws(()=>service.read(b.id,result.handoff_id),{code:'NOT_FOUND'});
});
test('P12 calendar draft validates explicit interval and exports actual duration with injection-safe ICS',async t=>{
 const {store,users:[a],cmd,input}=await setup(t);
 assert.throws(()=>cmd(a,'assist.calendar',{...input,start:'2026-09-22T12:00:00Z',end:'2026-09-22T11:00:00Z'}),{code:'INVALID_INPUT'});
 const result=cmd(a,'assist.calendar',{...input,start:'2026-09-22T12:00:00Z',end:'2026-09-22T13:30:00Z'}),note=store.get(result.id);assert.equal(note.data.calendar.status,'draft');
 const ics=calendarICS({id:note.id,title:'中文日程'.repeat(30)+'\nATTENDEE:bad',content:'原会话摘要；由本人确认',...note.data.calendar,created:note.created});
 assert.match(ics,/DTSTART:20260922T120000Z/);assert.match(ics,/DTEND:20260922T133000Z/);assert.ok(!ics.includes('\r\nATTENDEE:'));assert.ok(ics.split('\r\n').every(line=>Buffer.byteLength(line)<=75));
});
test('P13 Brief remains private until separate publish and keeps private source links out of public projection',async t=>{
 const {store,service,users:[a,b],cmd,ref,input,conversation}=await setup(t);
 const result=cmd(a,'assist.project_brief',{...input,criteria:'验收标准',open_task:'开放任务'}),project=store.get(result.id);assert.equal(project.visibility,'members');assert.equal(store.list('post').length,0);assert.throws(()=>service.read(b.id,result.id),{code:'NOT_FOUND'});
 assert.equal(service.read(a.id,result.handoff_id).data.conversation_id,conversation.id);
 assert.throws(()=>cmd(a,'project.publish_post',{...ref(project),confirm:true}),{code:'BRIEF_INCOMPLETE'});
 cmd(a,'project.brief.update',{...ref(project),title:project.data.title,goal:project.data.goal,basis:'可公开的已有基础',task:project.data.task,criteria:project.data.criteria,participation:'application',public_scope:'brief',reviewer_id:a.id,fee_terms:'各自承担本人费用',deadline_mode:'none'});
 const post=cmd(a,'project.publish_post',{...ref(project),confirm:true});const publicPost=service.read(b.id,post.id);assert.ok(!JSON.stringify(publicPost).includes(conversation.id));assert.ok(!JSON.stringify(publicPost).includes('PRIVATE_SOURCE_DO_NOT_SHARE'));
});
test('handoff rejects stale output version, other user and revoked original conversation',async t=>{
 const {store,users:[a,b],cmd,ref,input,conversation}=await setup(t);
 assert.throws(()=>cmd(a,'assist.calendar',{...input,run_version:0}),{code:'VERSION_CONFLICT'});
 assert.throws(()=>cmd(b,'assist.project_brief',{...input,criteria:'c',open_task:'t'}),{code:'NOT_FOUND'});
 const relationship=store.visible(a.id,'friend')[0];cmd(a,'friend.respond',{...ref(relationship),decision:'block'});assert.throws(()=>cmd(a,'assist.calendar',{...input,start:'2026-09-22T12:00:00Z',end:'2026-09-22T13:00:00Z'}),{code:'NOT_FOUND'});assert.equal(store.role(conversation.id,a.id),undefined);
});
test('all exports bind both the displayed run ID and version; published message retains its original evidence',async t=>{
 const {store,users:[a,b],cmd,ref,input,run,assist,message,conversation}=await setup(t);
 const shared=cmd(a,'assist.share_record',{...input,source_refs:[ref(message)]});const frozen=store.get(shared.message_id).data.record_sources;
 const record=store.get(shared.target_id),another=cmd(b,'message.send',{id:conversation.id,text:'新引用'});store.update(record,{...record.data,source_refs:[ref(another)]},a.id);assert.deepEqual(store.get(shared.message_id).data.record_sources,frozen);
 const task=store.get(store.get(assist.id).data.task_id),other=store.add('run',a.id,{...run.data,receipts:run.data.receipts.map(r=>({...r,output:typeof r.output==='string'?'NEW_OUTPUT':r.output}))});
 store.db.prepare('UPDATE objects SET version=? WHERE id=?').run(run.version,other.id);store.update(task,{...task.data,run_id:other.id},a.id);
 for(const action of ['assist.share_record','assist.calendar','assist.project_brief','assist.save_note','assist.followup','assist.fill'])assert.throws(()=>cmd(a,action,{...input,criteria:'验收',open_task:'制作',goal:'旧结果'}),{code:'RESULT_CHANGED'});
 assert.throws(()=>cmd(a,'assist.project_brief',{...input,run_id:other.id,content:'长'.repeat(3001),criteria:'验收',open_task:'制作'}),{code:'INVALID_INPUT'});
});
