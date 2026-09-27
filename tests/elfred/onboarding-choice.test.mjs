import test from 'node:test';
import assert from 'node:assert/strict';
import {Store,id} from '../../server/elfred/store.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {ModelProvider} from '../../server/elfred/providers.mjs';
import {Runtime} from '../../server/elfred/runtime.mjs';
import {alignmentQuestions,alignmentSummary} from '../../app/v28/core/onboarding-choice.mjs';
function setup(t){const store=new Store(':memory:'),service=new Service(store,new ModelProvider({}));t.after(()=>store.close());const users=['alice','bob'].map(h=>authenticate(store,h,'local-test-password',true,h).user);users.forEach(u=>service.initialize(u));const cmd=(u,a,input)=>service.command(u.id,id(),a,input),session=u=>service.list(u.id,'onboarding')[0],ref=o=>({id:o.id,version:store.get(o.id).version});return {store,service,users,cmd,session,ref};}
function chooseAll(env,user,mode='sequential'){const {cmd,session,ref}=env;cmd(user,'onboarding.choice.start',{...ref(session(user)),mode});for(const q of alignmentQuestions)cmd(user,'onboarding.choice.answer',{...ref(session(user)),question_id:q.id,option:q.options[0].id});}

test('逐个与同场使用原始记录相同的八题、选项、顺序和初始理解，选择不启动模型',t=>{
 const e=setup(t),{store,service,users:[a,b],cmd,session,ref}=e;chooseAll(e,a);chooseAll(e,b,'group');
 const normalized=user=>alignmentSummary(session(user).data.choice_answers).map(({at,...item})=>item);
 assert.deepEqual(normalized(a),normalized(b));assert.equal(session(a).data.choice_step,8);assert.equal(session(b).data.choice_phase,'summary');
 assert.deepEqual(alignmentQuestions.map(q=>q.agent),['owner','explore','advise','create','connect','execute','owner','owner']);
 for(const q of alignmentQuestions)assert.deepEqual(q.options.slice(-3).map(o=>o.id),['none','unsure','skip']);
 cmd(a,'onboarding.choice.confirm',{...ref(session(a)),confirm:true});
 for(const type of ['approval','run','task','conversation','message','attachment','connector'])assert.equal(store.list(type).length,0,type);
 assert.equal(store.list('memory').length,8);assert.ok(store.list('memory').every(m=>m.data.status==='pending_confirmation'&&m.data.alignment==='insufficient'));
 const context=session(a).data.initial_context;
 assert.equal(context.create.items.length,1);assert.equal(context.create.items[0].question_id,'format');assert.equal(context.connect.items[0].question_id,'cooperation');
 assert.equal(context.create.alignment,'insufficient');assert.equal(service.list(a.id,'onboarding').length,1);
});

test('选项和进度持久化、切换不重置、可返回修改与跳过；不能覆盖另一页面的新版选择',t=>{
 const {users:[a,b],cmd,service,session,ref}=setup(t);
 cmd(a,'onboarding.chat.draft',{...ref(session(a)),text:'旧流程里未发送的文字'});
 cmd(a,'onboarding.choice.start',{...ref(session(a)),mode:'sequential'});
 const stale=ref(session(a));cmd(a,'onboarding.choice.answer',{...stale,question_id:'need',option:'make'});
 assert.throws(()=>cmd(a,'onboarding.choice.answer',{...stale,question_id:'need',option:'act'}),{code:'VERSION_CONFLICT'});
 cmd(a,'onboarding.choice.defer',{...ref(session(a))});cmd(a,'onboarding.choice.mode',{...ref(session(a)),mode:'group'});
 const recovered=service.bootstrap(a.id).objects.onboarding[0];assert.equal(recovered.data.choice_step,1);assert.equal(recovered.data.choice_answers.need.option,'make');assert.ok(recovered.data.deferred_at);assert.equal(recovered.data.status,'collecting');assert.equal(recovered.data.input_draft,'旧流程里未发送的文字');
 cmd(a,'onboarding.choice.step',{...ref(session(a)),step:0});cmd(a,'onboarding.choice.answer',{...ref(session(a)),question_id:'need',option:'none'});
 cmd(a,'onboarding.choice.step',{...ref(session(a)),step:8});cmd(a,'onboarding.choice.confirm',{...ref(session(a)),confirm:true});
 assert.ok(session(a).data.choice_summary.every(item=>item.certainty==='uncertain'));
 assert.throws(()=>cmd(b,'onboarding.choice.answer',{...ref(session(a)),question_id:'need',option:'act'}),{code:'NOT_FOUND'});
 assert.throws(()=>cmd(a,'onboarding.choice.answer',{...ref(session(a)),question_id:'invented',option:'act'}),{code:'INVALID_INPUT'});
 assert.throws(()=>cmd(a,'onboarding.choice.answer',{...ref(session(a)),question_id:'external',option:'auto_send'}),{code:'INVALID_INPUT'});
});

test('修改清除旧的确认和理解；可以重新确认，也可以先进入首页不强制任务或 Skill',t=>{
 const e=setup(t),{users:[a],cmd,session,ref,store}=e;chooseAll(e,a);cmd(a,'onboarding.choice.confirm',{...ref(session(a)),confirm:true});
 cmd(a,'onboarding.choice.step',{...ref(session(a)),step:2});cmd(a,'onboarding.choice.answer',{...ref(session(a)),question_id:'criteria',option:'unsure'});assert.equal(session(a).data.choice_phase,'summary');
 assert.equal(session(a).data.initial_context,null);assert.equal(session(a).data.choice_confirmed_at,null);
 assert.throws(()=>cmd(a,'onboarding.choice.first',{...ref(session(a)),task:'outline',confirm:true}),{code:'CONFIRMATION_REQUIRED'});
 cmd(a,'onboarding.choice.confirm',{...ref(session(a)),confirm:true});assert.equal(session(a).data.initial_context.advise.items[0].certainty,'uncertain');
 cmd(a,'onboarding.choice.home',{...ref(session(a))});assert.equal(session(a).data.status,'completed');assert.ok(session(a).data.skipped.includes('first_task_deferred'));assert.equal(store.list('task').length,0);assert.equal(store.list('skill').length,0);
});

test('首个事项真实存入收件箱且幂等；只传选中任务所需摘要，修改初始化不篡改已有任务',t=>{
 const e=setup(t),{users:[a,b],cmd,session,ref,store,service}=e;chooseAll(e,a);cmd(a,'onboarding.choice.confirm',{...ref(session(a)),confirm:true});
 const result=cmd(a,'onboarding.choice.first',{...ref(session(a)),task:'compare',confirm:true});
 const repeat=cmd(a,'onboarding.choice.first',{...ref(session(a)),task:'outline',confirm:true});assert.equal(result.task_id,repeat.task_id);assert.equal(store.list('task').length,1);assert.equal(store.list('inbox').length,1);
 const task=store.get(result.task_id),source=store.get(task.data.source_refs[0].id);assert.equal(task.data.system,'advise');assert.equal(task.data.status,'draft');assert.match(source.data.content,/选择方向时/);assert.doesNotMatch(source.data.content,/这个项目需要别人参与吗|你希望以什么节奏开始/);assert.equal(store.list('approval').length,0);
 assert.throws(()=>service.read(b.id,source.id),{code:'NOT_FOUND'});
 const before=source.data.content;cmd(a,'onboarding.choice.answer',{...ref(session(a)),question_id:'criteria',option:'risk'});assert.equal(service.read(a.id,source.id).data.content,before);assert.ok(service.read(a.id,result.task_id));
 cmd(a,'task.confirm',{...ref(task),confirm:true,model_consent:true});assert.ok(service.list(a.id,'inbox').some(item=>item.data.task_id===task.id));
 const inbox=store.list('inbox')[0];assert.equal(cmd(a,'inbox.task',{...ref(inbox)}).id,task.id);assert.equal(store.list('task').length,1);
});

test('主动程度不扩大授权；无 Key 不伪造首个成果，配置后模型确实收到选择并经用户验收',async t=>{
 const e=setup(t),{users:[a,b],cmd,session,ref,store,service}=e;chooseAll(e,a);chooseAll(e,b);
 for(const u of [a,b]){
  cmd(u,'onboarding.choice.answer',{...ref(session(u)),question_id:'initiative',option:'low_risk'});cmd(u,'onboarding.choice.confirm',{...ref(session(u)),confirm:true});
  const result=cmd(u,'onboarding.choice.first',{...ref(session(u)),task:'outline',confirm:true});const task=store.get(result.task_id);
  assert.throws(()=>cmd(u,'run.start',{...ref(task)}),{code:'INVALID_STATE'});
  assert.throws(()=>cmd(u,'task.confirm',{...ref(task),confirm:true}),{code:'CONSENT_REQUIRED'});
  cmd(u,'task.confirm',{...ref(task),confirm:true,model_consent:true});cmd(u,'run.start',{...ref(task)});
  if(u===a){await new Runtime(store,new ModelProvider({})).tick();assert.equal(store.get(task.id).data.status,'blocked');assert.equal(service.list(u.id,'knowledge').length,0);}
  else{
   let payload='';const provider={status:()=>({configured:true}),generate:async(args)=>{payload+=JSON.stringify(args);return {output:args.goal.phase==='review'?'{"decision":"satisfied","issues":[]}':'明确标注的候选起步方案：先选一个小问题，形成概念草案；实际领域待用户确认。',usage:{total_tokens:10}}}};
   await new Runtime(store,provider).tick();assert.match(payload,/近期兴趣|感兴趣/);assert.equal(store.get(task.id).data.status,'awaiting_review');
   cmd(u,'task.accept',{...ref(task),accept:true});assert.equal(store.get(task.id).data.status,'completed');assert.equal(service.list(u.id,'knowledge').length,1);
   assert.ok(service.list(u.id,'inbox').some(item=>item.data.task_id===task.id));
  }
 }
});



test('旧账号已确认的初始化恢复为待核对理解，重复读取及本人删除不会重新建立',t=>{
 const e=setup(t),{users:[a],cmd,session,ref,store,service}=e;chooseAll(e,a);
 const summary=alignmentSummary(session(a).data.choice_answers);store.update(session(a),{...session(a).data,choice_summary:summary,choice_confirmed_at:new Date().toISOString()},a.id);
 assert.equal(store.list('memory').length,0);const snapshot=service.bootstrap(a.id);assert.equal(snapshot.objects.memory.length,8);assert.ok(snapshot.objects.memory.every(m=>m.data.status==='pending_confirmation'));
 const m=snapshot.objects.memory[0];cmd(a,'memory.decide',{...ref(m),decision:'delete'});service.bootstrap(a.id);service.bootstrap(a.id);
 assert.equal(store.list('memory').length,8);assert.equal(service.list(a.id,'memory').length,7);
 cmd(a,'onboarding.choice.confirm',{...ref(session(a)),confirm:true});assert.equal(store.list('memory').length,8);
});
