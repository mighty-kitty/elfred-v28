import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { Store, id } from '../../server/elfred/store.mjs';
import { authenticate,session } from '../../server/elfred/auth.mjs';
import { Service } from '../../server/elfred/service.mjs';
import { Runtime } from '../../server/elfred/runtime.mjs';
import { ModelProvider } from '../../server/elfred/providers.mjs';
import { planGate, DEFAULT_STOP } from '../../server/elfred/policy.mjs';
import {spawnSync} from 'node:child_process';

function fixture(t,filename=':memory:',provider=new ModelProvider({})) {
  const store=new Store(filename),service=new Service(store,provider),runtime=new Runtime(store,provider);
  const a=authenticate(store,'alice','secure-test-password',true,'Alice').user;
  const b=authenticate(store,'bob','secure-test-password',true,'Bob').user;
  service.initialize(a);service.initialize(b);
  t.after(()=>store.close());
  const command=(user,action,input,key=id())=>service.command(user.id,key,action,input);
  const current=(object)=>({id:object.id,version:store.get(object.id).version});
  const task=(input={})=>{
    const object=command(a,'task.create',{goal:'检索资料',mode:'search',...input});
    command(a,'task.confirm',{...current(object),confirm:true,model_consent:true});
    const run=command(a,'run.start',current(object));return {task:object,run};
  };
  const group=()=>{
    const request=command(a,'friend.request',{handle:'bob'});command(b,'friend.respond',{...current(request),decision:'accept'});
    return command(a,'conversation.create',{title:'测试群',handles:['bob']});
  };
  return {store,service,runtime,a,b,command,current,task,group};
}
test('历史关系屏蔽同时撤销当前私聊且不能重新接受申请',t=>{
  const {a,b,command,current,store}=fixture(t);
  const old=command(a,'friend.request',{handle:'bob'});command(b,'friend.respond',{...current(old),decision:'decline'});
  const next=command(a,'friend.request',{handle:'bob'});const response=command(b,'friend.respond',{...current(next),decision:'accept'});
  command(b,'friend.respond',{...current(old),decision:'block'});
  assert.equal(store.get(next.id).data.status,'blocked');
  assert.throws(()=>command(a,'message.send',{id:response.conversation_id,text:'不得送达'}),{code:'NOT_FOUND'});
});
test('撤销群权限后简报列表、直读、导出均过滤失权事实',t=>{
  const {a,b,command,current,store,service,group}=fixture(t);const conversation=group();
  const message=command(a,'message.send',{id:conversation.id,text:'保密项目代号'});
  const task=command(b,'task.create',{goal:'保密项目代号',source_refs:[current(message)]});
  const brief=command(b,'brief.create',{kind:'morning'});
  command(a,'conversation.remove_member',{...current(conversation),user_id:b.id});
  assert.equal(store.canRead(b.id,store.get(task.id)),false);
  assert.deepEqual(service.read(b.id,brief.id).data.facts,[]);
  assert.deepEqual(service.list(b.id,'brief')[0].data.facts,[]);
  assert.deepEqual(service.export(b.id).objects.brief[0].data.facts,[]);
});
test('预算达到上限后仍可恢复完整checkpoint，仅验证且不重复调用',async t=>{
  let entered,resolve;const started=new Promise(r=>entered=r);
  const provider={status:()=>({configured:true}),generate:async()=>{entered();return new Promise(r=>resolve=r)}};
  const {a,command,current,task,runtime,store}=fixture(t,':memory:',provider);
  const execution=task({mode:'compose',stop:{...DEFAULT_STOP,maxCalls:1,maxAttempts:1,maxUnits:1000}});
  const pending=runtime.tick();await started;command(a,'run.command',{...current(execution.run),command:'pause'});resolve({output:'真实工具返回的测试文本',usage:{total_tokens:5}});await pending;
  assert.equal(store.get(execution.run.id).data.status,'paused');
  command(a,'run.start',current(execution.task));await runtime.tick();
  assert.equal(store.get(execution.task.id).data.status,'awaiting_review');assert.equal(store.list('attempt').length,1);
  command(a,'task.accept',{...current(execution.task),accept:true});assert.equal(store.get(execution.task.id).data.status,'completed');
});
test('离线候选隔离训练与留出、真实调用评估后人工发布、运行版本不受回滚影响',async t=>{
  const provider={status:()=>({configured:true}),generate:async()=>({output:'可供人工对照的测试成果',usage:{total_tokens:5}})};
  const {a,command,current,task,runtime,store}=fixture(t,':memory:',provider);const baselines=[];
  for(let i=0;i<3;i++){const item=task({goal:'基线目标'+i,mode:'compose'});await runtime.tick();command(a,'task.accept',{...current(item.task),accept:true});baselines.push(item.task);}
  const trace=command(a,'trace.extract',{task_id:baselines[0].id});const candidate=command(a,'candidate.create',{trace_id:trace.id,title:'先核对来源',prompt:'先列出来源与限制，再逐项核对完成标准。'});
  assert.throws(()=>command(a,'candidate.evaluate',{...current(candidate),task_ids:[baselines[0].id,baselines[1].id],confirm:true,model_consent:true}),{code:'TRAIN_TEST_LEAK'});
  const evaluation=command(a,'candidate.evaluate',{...current(candidate),task_ids:baselines.slice(1).map(item=>item.id),confirm:true,model_consent:true});
  assert.throws(()=>command(a,'method.release',{evaluation_id:evaluation.id,confirm:true}),{code:'EVALUATION_REQUIRED'});
  await runtime.tick();await runtime.tick();
  const reviews=store.get(evaluation.id).data.tests.map(item=>({run_id:item.run_id,passed:true,note:'已核对来源、标准与基线；此测试只验证门控流程。'}));
  command(a,'evaluation.review',{...current(evaluation),reviews,confirm:true});const method=command(a,'method.release',{evaluation_id:evaluation.id,confirm:true});
  const future=task({goal:'下一项实际目标',mode:'compose'});const snapshot=store.get(future.run.id).data.version_snapshot;
  assert.equal(snapshot.method.id,method.id);command(a,'method.rollback',{confirm:true});assert.deepEqual(store.get(future.run.id).data.version_snapshot,snapshot);
  assert.equal(store.visible(a.id,'method').some(item=>item.data.active),false);
});
test('本人指正自动生成同领域待验证方法，未评估不生效也不跨 Agent 使用',async t=>{
  const provider={status:()=>({configured:true}),generate:async()=>({output:'可核对的初稿',usage:{total_tokens:5}})};
  const {a,command,current,task,runtime,store}=fixture(t,':memory:',provider),item=task({goal:'写一页产品说明',system:'create',mode:'compose'});
  await runtime.tick();command(a,'task.accept',{...current(item.task),accept:false,feedback:'不要把尚未验证的内容写成已完成'});
  const candidate=store.list('candidate').find(entry=>entry.data.origin==='task_correction');assert.ok(candidate);assert.equal(candidate.data.scope_system,'create');assert.match(candidate.data.prompt,/尚未验证/);assert.equal(store.list('method').length,0);
  const baselines=[];for(let index=0;index<2;index++){const baseline=task({goal:'另一个创作任务 '+index,system:'create',mode:'compose'});await runtime.tick();command(a,'task.accept',{...current(baseline.task),accept:true});baselines.push(baseline.task)}
  const evaluation=command(a,'candidate.evaluate',{...current(candidate),task_ids:baselines.map(item=>item.id),confirm:true,model_consent:true});await runtime.tick();await runtime.tick();
  const reviews=store.get(evaluation.id).data.tests.map(test=>({run_id:test.run_id,passed:true,note:'逐项核对来源、标准和原结果'}));command(a,'evaluation.review',{...current(evaluation),reviews,confirm:true});const method=command(a,'method.release',{evaluation_id:evaluation.id,confirm:true});
  assert.equal(store.get(method.id).data.scope_system,'create');const explore=task({goal:'核对另一条资讯',system:'explore',mode:'compose'});assert.equal(store.get(explore.run.id).data.version_snapshot.method,null);
  const future=task({goal:'写另一页文案',system:'create',mode:'compose'});assert.equal(store.get(future.run.id).data.version_snapshot.method.id,method.id);
});
test('账号会话隔离、失败登录、持久重启与退出令牌',t=>{
  const dir=mkdtempSync(path.join(tmpdir(),'elfred-test-')),filename=path.join(dir,'test.sqlite');
  const store=new Store(filename),auth=authenticate(store,'persist','secure-password',true,'存储');
  const object=store.add('knowledge',auth.user.id,{title:'真实记录'});store.close();
  const reopened=new Store(filename);assert.equal(reopened.get(object.id).data.title,'真实记录');assert.equal(session(reopened,auth.token).id,auth.user.id);
  assert.throws(()=>authenticate(reopened,'persist','wrong-password'),{code:'INVALID_LOGIN'});
  reopened.close();rmSync(dir,{recursive:true,force:true});
});
test('双用户私有对象、命令幂等及键冲突',t=>{
  const {store,a,b,command}=fixture(t);const key=id(),input={title:'机密',content:'仅本人'};
  const first=command(a,'knowledge.create',input,key);assert.deepEqual(command(a,'knowledge.create',input,key),first);
  assert.equal(store.visible(a.id,'knowledge').length,1);assert.throws(()=>store.read(b.id,first.id),{code:'NOT_FOUND'});
  assert.throws(()=>command(a,'knowledge.create',{...input,content:'不同'},key),{code:'IDEMPOTENCY_CONFLICT'});
});
test('CAS冲突回滚所有修改',t=>{
  const {a,store,command,current}=fixture(t);const item=command(a,'memory.create',{content:'我重视隐私'});
  command(a,'memory.decide',{...current(item),decision:'confirm'});
  assert.throws(()=>command(a,'memory.decide',{id:item.id,version:1,decision:'reject'}),{code:'VERSION_CONFLICT'});
  assert.equal(store.get(item.id).data.status,'validated');
});
test('DAG循环、未注册工具及缺少有限停止条件拒绝',()=>{
  assert.throws(()=>planGate({steps:[{id:'a',tool:'search.local',depends:['a']}]},{stop:DEFAULT_STOP},['read']),{code:'INVALID_PLAN'});
  assert.throws(()=>planGate({steps:[{id:'a',tool:'shell',depends:[]}]},{stop:DEFAULT_STOP},['read']),{code:'TOOL_FORBIDDEN'});
  assert.throws(()=>planGate({steps:[]},{},['read']),{code:'STOP_POLICY_REQUIRED'});
});
test('文件解析→真实检索回执→独立人工验收→知识沉淀',async t=>{
  const {store,a,command,current,task,runtime}=fixture(t);
  command(a,'document.create',{title:'资料.md',content:'今天的主题：检索资料。'});
  const execution=task();await runtime.tick();
  assert.equal(store.get(execution.run.id).data.receipts.length,1);
  assert.equal(store.get(execution.task.id).data.status,'awaiting_acceptance');
  command(a,'task.accept',{...current(execution.task),accept:true});
  assert.equal(store.get(execution.task.id).data.status,'completed');assert.equal(store.get(execution.task.id).data.satisfaction,'unknown');
  assert.equal(store.visible(a.id,'knowledge').length,1);
});
test('空库检索不得命中当前任务冒充目标完成',async t=>{
  const {task,store,runtime}=fixture(t);const execution=task({goal:'NO_MATCH_987654'});await runtime.tick();
  const run=store.get(execution.run.id);assert.equal(run.data.status,'awaiting_review');assert.deepEqual(run.data.receipts[0].output,[]);assert.equal(run.data.verification.verdict,'not_satisfied');
});
test('未配置模型保留阻塞、无回执无费用',async t=>{
  const {task,store,runtime}=fixture(t);const execution=task({mode:'compose'});await runtime.tick();
  assert.equal(store.get(execution.run.id).data.status,'blocked');assert.equal(store.list('attempt').length,0);
});
test('排队取消不启动工具，重复启动不创建另一活跃Run',async t=>{
  const {task,store,runtime,command,a,current}=fixture(t);const execution=task();
  assert.throws(()=>command(a,'run.start',current(execution.task)),{code:'INVALID_STATE'});
  command(a,'run.command',{...current(execution.run),command:'cancel'});await runtime.tick();assert.equal(store.get(execution.run.id).data.status,'cancelled');assert.equal(store.list('attempt').length,0);
});
test('真人消息顺序、已读单调、群@只真人、私密辅助不触发运行',t=>{
  const {store,a,b,command,current,group}=fixture(t);const room=group();
  const message=command(a,'message.send',{id:room.id,text:'你好',mentions:[b.id]});assert.equal(store.get(message.id).data.seq,1);
  command(b,'conversation.read',{id:room.id,seq:1});command(b,'conversation.read',{id:room.id,seq:0});assert.equal(store.db.prepare('SELECT seq FROM read_cursors WHERE user_id=?').get(b.id).seq,1);
  const assist=command(a,'assist.create',{conversation_id:room.id,purpose:'帮我理解'});assert.equal(store.list('run').length,0);assert.throws(()=>store.read(b.id,assist.id),{code:'NOT_FOUND'});
  assert.throws(()=>command(a,'message.send',{id:room.id,text:'@Agent',mentions:['agent']}),{code:'INVALID_MENTION'});
  command(a,'conversation.remove_member',{...current(room),user_id:b.id});assert.throws(()=>store.read(b.id,message.id),{code:'NOT_FOUND'});
});
test('本人承诺不能由群主代签',t=>{
  const {store,a,b,command,current,group}=fixture(t);const room=group();
  const item=command(a,'commitment.create',{conversation_id:room.id,goal:'准备报告',assignee:b.id});
  assert.throws(()=>command(a,'commitment.respond',{...current(item),accept:true}),{code:'FORBIDDEN'});
  command(b,'commitment.respond',{...current(item),accept:true});assert.equal(store.get(item.id).data.status,'accepted');assert.equal(store.list('task')[0].owner,b.id);assert.equal(store.list('run').length,0);
});
test('屏蔽不能被对方移除关系绕过',t=>{
  const {a,b,command,current}=fixture(t);const request=command(a,'friend.request',{handle:'bob'});
  command(b,'friend.respond',{...current(request),decision:'block'});
  assert.throws(()=>command(a,'friend.respond',{...current(request),decision:'remove'}),{code:'RELATION_UNAVAILABLE'});
  assert.throws(()=>command(a,'friend.request',{handle:'bob'}),{code:'NOT_FOUND'});
});
test('共创两人副本、本人提交、冲突和发布指针',t=>{
  const {a,b,store,command,current}=fixture(t);
  const project=command(a,'project.create',{basis:'已有可公开基础',public_scope:'brief',reviewer_id:a.id,fee_terms:'各自承担费用',deadline_mode:'none',title:'共创',goal:'共同写文章',criteria:'真人审核',task:'撰写'});
  const post=command(a,'project.publish_post',{...current(project),confirm:true});command(b,'project.claim',{post_id:post.id,confirm:true});
  const copy=command(b,'copy.create',{project_id:project.id});command(b,'copy.save',{...current(copy),content:'<script>alert(1)</script>纯文本成果'});
  assert.throws(()=>command(b,'copy.submit',{...current(copy),reviewed:false}),{code:'REVIEW_REQUIRED'});
  const contribution=command(b,'copy.submit',{...current(copy),reviewed:true});command(a,'contribution.review',{...current(contribution),decision:'accept'});
  const release=command(a,'project.release',{...current(project),confirm:true});assert.equal(store.get(project.id).data.release_id,release.id);
  assert.throws(()=>command(a,'project.release',{...current(project),confirm:true,execute:true}),{code:'SANDBOX_UNAVAILABLE'});assert.equal(store.get(project.id).data.release_id,release.id);
  command(a,'project.remove_member',{...current(project),user_id:b.id});assert.throws(()=>store.read(b.id,copy.id),{code:'NOT_FOUND'});
  assert.throws(()=>command(b,'project.claim',{post_id:post.id,confirm:true}),{code:'MEMBERSHIP_REVOKED'});
});
test('检索回执及验收资产随来源撤权，导出不泄露',async t=>{
  const {store,service,a,b,command,current,group,runtime}=fixture(t);const room=group();command(a,'message.send',{id:room.id,text:'群消息特别秘密'});
  const task=command(b,'task.create',{goal:'特别秘密',mode:'search'});command(b,'task.confirm',{...current(task),confirm:true});const run=command(b,'run.start',current(task));await runtime.tick();
  const accepted=command(b,'task.accept',{...current(task),accept:true});
  command(a,'conversation.remove_member',{...current(room),user_id:b.id});assert.throws(()=>store.read(b.id,run.id),{code:'NOT_FOUND'});assert.throws(()=>store.read(b.id,accepted.artifact_id),{code:'NOT_FOUND'});
  const exported=JSON.stringify(service.export(b.id));assert.equal(exported.includes('群消息特别秘密'),false);
});
test('模型结果到达前撤权必须保留可对账未知用量',async t=>{
  let resolve;const provider={status:()=>({configured:true}),generate:()=>new Promise(done=>{resolve=done;})};
  const {store,a,task,command,current,runtime}=fixture(t,':memory:',provider);const execution=task({mode:'compose'});const pending=runtime.tick();
  const approval=store.get(store.get(execution.task.id).data.approval_id);command(a,'approval.revoke',current(approval));
  resolve({output:'供应商返回了结果',provider_operation_id:'receipt-1',usage:{total_tokens:10}});await pending;
  assert.equal(store.get(execution.run.id).data.status,'reconciliation_required');const usage=store.db.prepare('SELECT * FROM usage').get();assert.equal(usage.status,'unknown');
  command(a,'usage.reconcile',{id:usage.id,confirm:true,actual_units:1000,note:'供应商记录已核对'});assert.equal(store.db.prepare('SELECT reserved FROM budget_accounts WHERE owner=?').get(a.id).reserved,0);
});
test('高影响记忆保持待确认，纠正旧理解立即失效',t=>{
  const {store,a,command,current,service}=fixture(t);const original=command(a,'memory.create',{content:'我希望辞职',risk:'high'});assert.equal(store.get(original.id).data.status,'pending_confirmation');
  const derived=command(a,'memory.create',{content:'派生推断',source_refs:[current(original)]});
  command(a,'memory.decide',{...current(original),decision:'correct',content:'我只是暂时疲惫'});assert.equal(store.get(derived.id).data.status,'needs_review');
  assert.equal(service.search(a.id,{query:'辞职',types:['memory']}).hits.length,0);
});
test('收藏不写偏好、记忆或正式任务',t=>{
  const {store,a,command}=fixture(t);const feed=store.add('feed',a.id,{title:'反对的观点',status:'active'});
  command(a,'feed.interact',{id:feed.id,kind:'save'});assert.equal(store.list('memory').length,0);assert.equal(store.list('task').length,0);
});

test('草稿保存返回提交版本，多页面冲突不覆盖已保存内容',t=>{
  const {a,b,command,store,group}=fixture(t);const room=group();
  const first=command(a,'draft.save',{conversation_id:room.id,text:'第一稿',version:0});
  assert.throws(()=>command(a,'draft.save',{conversation_id:room.id,text:'无版本覆盖'}),{code:'VERSION_REQUIRED'});
  assert.equal(first.version,store.get(first.id).version);
  assert.throws(()=>command(a,'draft.save',{conversation_id:room.id,text:'另一页旧稿',version:0}),{code:'VERSION_CONFLICT'});
  const second=command(a,'draft.save',{conversation_id:room.id,text:'第二稿',version:first.version});
  assert.throws(()=>command(a,'draft.save',{conversation_id:room.id,text:'并发旧稿',version:first.version}),{code:'VERSION_CONFLICT'});
  assert.equal(store.get(second.id).data.text,'第二稿');assert.throws(()=>store.read(b.id,first.id),{code:'NOT_FOUND'});
});

test('人工完成、记忆场景依据与任务归档恢复分别保存',t=>{
  const {a,command,current,store}=fixture(t);
  const memory=command(a,'memory.create',{content:'清晰的验收标准能帮助我推进工作'});command(a,'memory.decide',{...current(memory),decision:'confirm'});
  for(const scenario of ['撰写','整理']){
    const task=command(a,'task.create',{goal:scenario,mode:'manual'});command(a,'task.confirm',{...current(task),confirm:true});
    command(a,'task.complete_manual',{...current(task),confirm:true,result:'本人已完成并核对：'+scenario});
    const outcomeId=store.get(task.id).data.outcome_id;
    command(a,'memory.evidence',{...current(memory),outcome_id:outcomeId,scenario,note:'此次标准支持目标达成',confirm:true});
    assert.throws(()=>command(a,'memory.evidence',{...current(memory),outcome_id:outcomeId,scenario,note:'重复',confirm:true}),{code:'DUPLICATE_EVIDENCE'});
    command(a,'task.archive',current(task));assert.equal(store.get(task.id).data.status,'archived');command(a,'task.restore',current(task));assert.equal(store.get(task.id).data.status,'completed');
  }
  assert.equal(store.get(memory.id).data.alignment,'scenario_verified');assert.equal(store.list('attempt').length,0);
});

test('定时任务未到时间不执行，到时执行且排队取消不受时间阻塞',async t=>{
  const {a,command,current,task,runtime,store}=fixture(t);command(a,'document.create',{title:'调度资料.md',content:'调度验证'});
  const scheduled=task({goal:'调度验证',not_before:Date.now()+60000});await runtime.tick();assert.equal(store.get(scheduled.run.id).data.status,'queued');
  const object=store.get(scheduled.task.id);store.update(object,{...object.data,not_before:Date.now()-1},a.id);await runtime.tick();assert.equal(store.get(scheduled.task.id).data.status,'awaiting_acceptance');
  const cancelled=task({not_before:Date.now()+60000});command(a,'run.command',{...current(cancelled.run),command:'cancel'});await runtime.tick();assert.equal(store.get(cancelled.run.id).data.status,'cancelled');
});

test('恢复checkpoint沿用原方法快照且20份资料加方法引用不会超限',async t=>{
  let entered,resolve;const started=new Promise(done=>entered=done);
  const provider={status:()=>({configured:true}),generate:input=>{if(input.goal.phase==='review')return Promise.resolve({output:JSON.stringify({decision:'satisfied',issues:[]}),usage:{total_tokens:3}});entered();return new Promise(done=>resolve=done)}};
  const {a,command,current,task,runtime,store}=fixture(t,':memory:',provider);
  const method=store.add('method',a.id,{active:true,title:'原方法',prompt:'先查证再总结',prompt_hash:'frozen',status:'released'});
  const refs=Array.from({length:20},(_,i)=>current(command(a,'document.create',{title:'来源'+i+'.md',content:'有效资料'+i})));
  const execution=task({mode:'compose',source_refs:refs});const frozen=store.get(execution.run.id).data.version_snapshot;
  const pending=runtime.tick();await started;command(a,'run.command',{...current(execution.run),command:'pause'});resolve({output:'实际测试回执',usage:{total_tokens:3}});await pending;
  assert.equal(store.get(execution.run.id).data.status,'paused');command(a,'method.rollback',{confirm:true});
  const resumed=command(a,'run.start',current(execution.task));assert.deepEqual(store.get(resumed.id).data.version_snapshot,frozen);assert.equal(frozen.method.id,method.id);
  await runtime.tick();assert.equal(store.get(execution.task.id).data.status,'awaiting_review');assert.equal(store.list('attempt').filter(a=>a.data.step_id==='work').length,1);assert.equal(store.list('attempt').length,2); // One work call and one review; sources are read directly.
});

test('留出集拒绝重复目标和三个ID伪装成两项，失败回滚全部评估运行',async t=>{
  const provider={status:()=>({configured:true}),generate:async()=>({output:'测试成果',usage:{total_tokens:2}})};
  const {a,command,current,task,runtime,store}=fixture(t,':memory:',provider);const baselines=[];
  for(const goal of ['相同训练目标','相同训练目标','独立留出目标']){const entry=task({goal,mode:'compose'});await runtime.tick();command(a,'task.accept',{...current(entry.task),accept:true});baselines.push(entry.task)}
  const trace=command(a,'trace.extract',{task_id:baselines[0].id}),candidate=command(a,'candidate.create',{trace_id:trace.id,title:'候选',prompt:'核对事实'});
  const input={...current(candidate),confirm:true,model_consent:true};
  assert.throws(()=>command(a,'candidate.evaluate',{...input,task_ids:[baselines[1].id,baselines[2].id,baselines[1].id]}),{code:'HOLDOUT_REQUIRED'});
  assert.throws(()=>command(a,'candidate.evaluate',{...input,task_ids:[baselines[2].id,baselines[1].id]}),{code:'TRAIN_TEST_LEAK'});
  assert.equal(store.list('run').length,3);assert.equal(store.list('evaluation').length,0);
  assert.throws(()=>command(a,'task.create',{goal:'绕过',evaluation_candidate_id:candidate.id}),{code:'INTERNAL_ONLY'});
});

test('事件流超过300条他人事件仍能获得自己的下一条事件',t=>{
  const {a,b,store,service}=fixture(t);const before=store.db.prepare('SELECT MAX(seq) AS seq FROM events').get().seq;
  for(let i=0;i<305;i++)store.add('knowledge',b.id,{title:'他人事件'+i});
  const own=store.add('knowledge',a.id,{title:'本人事件'});const events=service.events(a.id,before);
  assert.equal(events.length,1);assert.equal(events[0].object_id,own.id);
});

test('留出评估继承项目权限，移除成员后不再向模型传输项目目标',async t=>{
  const seen=[];const provider={status:()=>({configured:true}),generate:async input=>{if(input.goal.phase!=='review')seen.push(input.goal.goal);return {output:'已核对测试结果',usage:{total_tokens:2}}}};
  const {a,b,command,current,store,runtime}=fixture(t,':memory:',provider);
  const project=command(a,'project.create',{basis:'已有可公开基础',public_scope:'brief',reviewer_id:a.id,fee_terms:'各自承担费用',deadline_mode:'none',title:'机密项目',goal:'项目目标',criteria:'核对',task:'整理'}),post=command(a,'project.publish_post',{...current(project),confirm:true});command(b,'project.claim',{post_id:post.id,confirm:true});
  const tasks=[];
  for(const [index,goal] of ['训练目标','机密留出目标','独立留出目标'].entries()){
    const task=command(b,'task.create',{goal,mode:'compose',...(index===1?{project_id:project.id}:{})});command(b,'task.confirm',{...current(task),confirm:true,model_consent:true});command(b,'run.start',current(task));await runtime.tick();command(b,'task.accept',{...current(task),accept:true});tasks.push(task);
  }
  const trace=command(b,'trace.extract',{task_id:tasks[0].id}),candidate=command(b,'candidate.create',{trace_id:trace.id,title:'候选',prompt:'核对来源'});
  const evaluation=command(b,'candidate.evaluate',{...current(candidate),task_ids:tasks.slice(1).map(item=>item.id),confirm:true,model_consent:true}),clone=store.get(evaluation.id).data.tests[0];
  command(a,'project.remove_member',{...current(project),user_id:b.id});assert.throws(()=>store.read(b.id,clone.task_id),{code:'NOT_FOUND'});assert.throws(()=>store.read(b.id,clone.run_id),{code:'NOT_FOUND'});
  await runtime.tick();assert.equal(seen.filter(goal=>goal==='机密留出目标').length,1);assert.equal(store.get(clone.run_id).data.status,'failed');
});

test('SQLite一致性备份与恢复保留账号和对象，恢复前副本可回退',t=>{
  const dir=mkdtempSync(path.join(tmpdir(),'elfred-backup-test-'));t.after(()=>rmSync(dir,{recursive:true,force:true}));
  const database=path.join(dir,'elfred.sqlite'),backup=path.join(dir,'snapshot.sqlite');
  const store=new Store(database),user=authenticate(store,'backup','test-backup-password',true,'备份测试').user;
  const object=store.add('knowledge',user.id,{title:'备份前的数据'});store.close();
  const run=(script,args=[])=>spawnSync(process.execPath,[path.resolve('scripts',script),...args],{encoding:'utf8',env:{...process.env,ELFRED_DATA_DIR:dir}});
  const saved=run('backup-local.mjs',[backup]);assert.equal(saved.status,0,saved.stderr);
  const changed=new Store(database);changed.update(changed.get(object.id),{title:'备份后的修改'},user.id);changed.close();
  assert.notEqual(run('restore-local.mjs',[backup]).status,0);
  const restored=run('restore-local.mjs',[backup,'--confirm']);assert.equal(restored.status,0,restored.stderr);
  const reopened=new Store(database);assert.equal(reopened.get(object.id).data.title,'备份前的数据');assert.equal(reopened.user(user.id).handle,'backup');reopened.close();
});
