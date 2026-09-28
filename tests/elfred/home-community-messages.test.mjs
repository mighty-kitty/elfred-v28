import test from 'node:test';
import assert from 'node:assert/strict';
import {Store,id} from '../../server/elfred/store.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {ModelProvider} from '../../server/elfred/providers.mjs';
import {agentAlignment} from '../../app/v28/core/agent-alignment.mjs';
import {briefIndex,dailyTasks,localDay} from '../../app/v28/core/local-day.mjs';
import {selectedBriefFacts} from '../../app/v28/features/home/brief-selection.mjs';

function setup(t){
  const store=new Store(':memory:'),service=new Service(store,new ModelProvider({}));
  t.after(()=>store.close());
  const users=['alice','bob','carol'].map(handle=>authenticate(store,handle,'local-test-password',true,handle.toUpperCase()).user);
  users.forEach(user=>service.initialize(user));
  return {store,service,users,cmd:(user,action,input,key=id())=>service.command(user.id,key,action,input),ref:object=>({id:object.id,version:store.get(object.id).version})};
}
test('brief polling clears changed-version selection and drops inaccessible facts without crashing',()=>{
  const facts=[{task_id:'a',status:'draft'},{task_id:'b',status:'completed'}];
  assert.deepEqual(selectedBriefFacts(facts,['a','b','removed'],2,2),[facts[0]]);
  assert.deepEqual(selectedBriefFacts(facts,['a'],1,2),[]);
  assert.deepEqual(selectedBriefFacts([],['a'],2,2),[]);
});
test('brief uses configured timezone and supports routines across midnight',()=>{
  assert.equal(localDay('2026-09-21T17:00:00Z','Asia/Shanghai'),'2026-09-22');
  assert.equal(localDay('2026-09-21T17:00:00Z','America/Los_Angeles'),'2026-09-21');
  assert.equal(briefIndex({morning:'22:00',noon:'03:00',evening:'09:00'},'Asia/Shanghai',new Date('2026-09-21T17:00:00Z')),0);
  const task=(id,status,updated,extra={})=>({id,updated,data:{status,...extra}});
  const tasks=[task('old','completed','2026-09-20T10:00:00Z'),task('today','completed','2026-09-21T17:00:00Z'),task('later','ready','2026-09-21T17:00:00Z',{not_before:Date.parse('2026-09-24T01:00:00Z')}),task('active','running','2026-09-20T10:00:00Z')];
  assert.deepEqual(dailyTasks(tasks,'Asia/Shanghai','2026-09-22').map(item=>item.id),['today','active']);
});
test('brief confirmation writes selected arrangements only; replay is idempotent and never starts runs',t=>{
  const {store,service,users:[a],cmd,ref}=setup(t);
  const task=cmd(a,'task.create',{goal:'复核首页排版'}),other=cmd(a,'task.create',{goal:'未选中的任务'});
  const brief=cmd(a,'brief.create',{kind:'morning'}),input={...ref(brief),actions:[{task_id:task.id,version:ref(task).version,kind:'focus'}]},key=id();
  assert.equal(store.get(task.id).data.focus_date,undefined);
  cmd(a,'brief.confirm',input,key);cmd(a,'brief.confirm',input,key);
  assert.equal(store.get(task.id).data.focus_date,store.get(brief.id).data.local_date);
  assert.equal(store.get(task.id).data.status,'draft');
  assert.equal(store.get(other.id).data.focus_date,undefined);
  assert.equal(service.list(a.id,'run').length,0);
  assert.equal(store.get(brief.id).data.acknowledged_actions.length,1);
});
test('brief changes are atomic and reject stale tasks or tasks outside the snapshot',t=>{
  const {store,users:[a,b],cmd,ref}=setup(t);
  const first=cmd(a,'task.create',{goal:'第一项'}),second=cmd(a,'task.create',{goal:'第二项'}),outsider=cmd(b,'task.create',{goal:'他人的任务'});
  const brief=cmd(a,'brief.create',{kind:'noon'}),oldSecond=ref(second);
  cmd(a,'task.archive',ref(second));
  assert.throws(()=>cmd(a,'brief.confirm',{...ref(brief),actions:[{task_id:first.id,version:ref(first).version,kind:'adjust',note:'先核对事实'},{task_id:second.id,version:oldSecond.version,kind:'focus'}]}),{code:'VERSION_CONFLICT'});
  assert.equal(store.get(first.id).data.plan_note,undefined);
  assert.throws(()=>cmd(a,'brief.confirm',{...ref(brief),actions:[{task_id:outsider.id,version:ref(outsider).version,kind:'focus'}]}),{code:'VERSION_CONFLICT'});
});
test('five agent stages use separate evidence and disclose mixed stages instead of averaging',()=>{
  const memory=(id,scope,alignment,status='validated')=>({id,version:1,data:{scope,alignment,status}});
  const memories=[memory('c','create','scenario_verified'),memory('e','explore','explicit'),memory('a','advise','stable_over_time'),memory('global','owner','stable_over_time')];
  assert.equal(agentAlignment(memories,'create').label,'场景已验证');
  assert.equal(agentAlignment(memories,'explore').label,'明确信息');
  assert.equal(agentAlignment(memories,'connect').label,'尚无足够理解');
  assert.equal(agentAlignment([...memories,memory('c2','create','explicit')],'create').label,'理解处于不同阶段');
  assert.equal(agentAlignment([...memories,memory('c2','create','explicit')],'create').levelLabel,'第 1—3 阶段');
  assert.equal(agentAlignment([memory('old','create','stable_over_time','superseded')],'create').state,'insufficient');
  assert.equal(agentAlignment([memory('pending','create','insufficient','pending_confirmation')],'create').label,'理解待验证');
});
test('community post publishes, edits with version check, and withdrawal closes comment/search access',t=>{
  const {service,users:[a,b],cmd,ref}=setup(t);
  const post=cmd(a,'post.create',{title:'首页讨论',content:'三时段卡片的设计依据',confirm:true});
  const old=ref(post);
  const comment=cmd(b,'post.comment',{id:post.id,content:'可以核对晚间卡'});
  assert.equal(service.read(b.id,post.id).data.author_name,'ALICE');
  assert.throws(()=>cmd(b,'post.edit',{...ref(post),title:'越权',content:'不能覆盖',confirm:true}),{code:'FORBIDDEN'});
  cmd(a,'post.edit',{...ref(post),title:'首页讨论更新',content:'保留原布局',confirm:true});
  assert.throws(()=>cmd(a,'post.edit',{...old,title:'过期修改',content:'旧版本',confirm:true}),{code:'VERSION_CONFLICT'});
  cmd(a,'post.withdraw',{...ref(post),confirm:true});
  assert.throws(()=>service.read(b.id,post.id),{code:'NOT_FOUND'});
  assert.throws(()=>service.read(b.id,comment.id),{code:'NOT_FOUND'});
  assert.throws(()=>cmd(b,'post.comment',{id:post.id,content:'不可继续评论'}),{code:'NOT_FOUND'});
  assert.equal(service.search(b.id,{query:'首页讨论'}).hits.length,0);
});
test('stopping recruitment prevents joining and approving pending claims',t=>{
  const {users:[a,b],cmd,ref}=setup(t);
  const project=cmd(a,'project.create',{basis:'已有可公开基础',public_scope:'brief',reviewer_id:a.id,fee_terms:'各自承担费用',deadline_mode:'none',title:'共创',goal:'改善首页',criteria:'逐项核对',task:'准备说明',participation:'application'});
  const post=cmd(a,'project.publish_post',{...ref(project),confirm:true});
  const claim=cmd(b,'project.claim',{post_id:post.id,confirm:true});
  cmd(a,'project.recruiting',{...ref(project),enabled:false});
  assert.throws(()=>cmd(a,'claim.review',{...ref(claim),accept:true}),{code:'CLOSED'});
  assert.throws(()=>cmd(b,'project.claim',{post_id:post.id,confirm:true}),{code:'CLOSED'});
  cmd(a,'project.recruiting',{...ref(project),enabled:true});
  cmd(a,'claim.review',{...ref(claim),accept:true});
});
test('group naming/invitation require owner and accepted friendship; direct title names the other human',t=>{
  const {service,users:[a,b,c],cmd,ref}=setup(t);
  const request=cmd(a,'friend.request',{handle:b.handle});
  const accepted=cmd(b,'friend.respond',{...ref(request),decision:'accept'});
  assert.equal(service.list(a.id,'conversation')[0].data.title,'BOB');
  assert.equal(service.list(b.id,'conversation')[0].data.title,'ALICE');
  const group=cmd(a,'conversation.create',{title:'首页协作',handles:[b.handle]});
  assert.throws(()=>cmd(b,'conversation.rename',{...ref(group),title:'其他名字'}),{code:'FORBIDDEN'});
  assert.throws(()=>cmd(a,'conversation.invite',{...ref(group),handle:c.handle}),{code:'FRIEND_REQUIRED'});
  const other=cmd(a,'friend.request',{handle:c.handle});cmd(c,'friend.respond',{...ref(other),decision:'accept'});
  cmd(a,'conversation.invite',{...ref(group),handle:c.handle});
  cmd(a,'conversation.rename',{...ref(group),title:'首页与社区'});
  assert.equal(service.list(c.id,'conversation').find(item=>item.id===group.id).data.title,'首页与社区');
  assert.throws(()=>cmd(a,'conversation.remove_member',{id:accepted.conversation_id,version:service.read(a.id,accepted.conversation_id).version,user_id:b.id}),{code:'INVALID_INPUT'});
});
