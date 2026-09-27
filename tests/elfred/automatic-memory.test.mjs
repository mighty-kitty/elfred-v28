import test from 'node:test';
import assert from 'node:assert/strict';
import {Store,id} from '../../server/elfred/store.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {Runtime} from '../../server/elfred/runtime.mjs';
import {recallMemories,feedbackMemory,captureMemories,explicitMemoryStatements} from '../../server/elfred/memory-learning.mjs';
import {projectMemory} from '../../server/elfred/memory-validity.mjs';
import {agentAlignment} from '../../app/v28/core/agent-alignment.mjs';

function setup(t){
 const store=new Store(':memory:');t.after(()=>store.close());const requests=[];
 const provider={status:()=>({configured:true}),generate:async r=>{requests.push(r);return {output:r.conversation?JSON.stringify({reply:'结论：这是一份针对当前目标的方案。依据和取舍如下。',memories:[]}):'结论：任务的真实结果。依据如下。',usage:{total_tokens:20}};}};
 const service=new Service(store,provider),user=authenticate(store,'auto-memory-owner','auto-memory-password',true,'本人').user;service.initialize(user);
 const command=(a,i)=>service.command(user.id,id(),a,i),ref=o=>({id:o.id,version:store.get(o.id).version});
 const thread=system=>command('agent.chat.create',{system});
 const send=async(conversation,text)=>{command('agent.chat.send',{id:conversation.id,text,model_consent:true});await new Runtime(store,provider).tick();};
 return {store,provider,service,user,command,ref,requests,thread,send};
}

test('低风险表达自动记住；归属由内容决定，入口不会把提醒习惯塞进创作',async t=>{
 const e=setup(t),thread=e.thread('create');await e.send(thread,'以后提醒我安排日程时先列出截止时间');
 const memory=e.store.list('memory')[0];assert.equal(memory.data.scope,'execute');assert.equal(memory.data.status,'learned');assert.equal(memory.data.alignment,'explicit');
 assert.equal(recallMemories(e.store,e.user.id,'create','日程').length,0);assert.equal(recallMemories(e.store,e.user.id,'execute','安排日程')[0].id,memory.id);
 assert.equal(agentAlignment(e.service.list(e.user.id,'memory'),'execute').label,'明确信息');assert.equal(agentAlignment(e.service.list(e.user.id,'memory'),'create').label,'尚无足够理解');
});

test('通用偏好存一份，Person 按任务分配；私有领域不因相同关键词向其他系统开放',async t=>{
 const e=setup(t);await e.send(e.thread('create'),'以后所有 Agent 回复都用简洁中文');const common=e.store.list('memory')[0];assert.equal(common.data.scope,'owner');
 const task=e.command('task.create',{goal:'比较两个方案',system:'advise',review_mode:'single'});e.command('task.confirm',{...e.ref(task),confirm:true,model_consent:true});e.command('run.start',e.ref(task));await new Runtime(e.store,e.provider).tick();
 assert.equal(e.store.get(task.id).data.memory_dispatch.global_refs[0].id,common.id);assert.match(JSON.stringify(e.requests.at(-1).context),/简洁中文/);assert.equal(e.store.list('memory').length,1);
 await e.send(e.thread('explore'),'以后核验信息时先检查原始来源');const scoped=e.store.list('memory').find(m=>m.data.scope==='explore');assert.ok(scoped);
 assert.ok(!recallMemories(e.store,e.user.id,'create','核验来源').some(m=>m.id===scoped.id));assert.equal(e.store.list('memory').filter(m=>m.id===common.id).length,1);
});

test('敏感理解按内容归 Person；原入口能显示候选，未确认不可用，确认后仍只按相关目的分配',async t=>{
 const e=setup(t);await e.send(e.thread('create'),'请记住我的健康限制是不能熬夜');const memory=e.store.list('memory')[0];
 assert.equal(memory.data.scope,'owner');assert.equal(memory.data.status,'pending_confirmation');assert.equal(recallMemories(e.store,e.user.id,'execute','健康限制').length,0);
 e.command('memory.decide',{...e.ref(memory),decision:'confirm'});assert.equal(recallMemories(e.store,e.user.id,'execute','按健康限制安排休息').length,1);assert.equal(recallMemories(e.store,e.user.id,'create','写一首诗').length,0);
});

test('自然反馈自动形成场景证据；不同日期与场景持续成立才稳定，不需要人工点升级',async t=>{
 t.mock.timers.enable({apis:['Date'],now:new Date('2026-09-27T08:00:00Z')});const e=setup(t),thread=e.thread('create');await e.send(thread,'以后写产品方案先给结论');const memory=e.store.list('memory')[0];
 await e.send(thread,'写产品方案甲');await e.send(thread,'这次结构正合适');assert.equal(e.store.get(memory.id).data.alignment,'scenario_verified');assert.equal(e.store.get(memory.id).data.evidence[0].automatic,true);
 await e.send(thread,'写产品方案乙');await e.send(thread,'这次结构正合适');assert.equal(e.store.get(memory.id).data.alignment,'scenario_verified');
 t.mock.timers.setTime(new Date('2026-09-29T08:00:00Z').getTime());await e.send(thread,'写产品方案丙（发布阶段）');await e.send(thread,'这次结构正合适');
 assert.equal(e.store.get(memory.id).data.alignment,'stable_over_time');assert.equal(agentAlignment(e.service.list(e.user.id,'memory'),'create').label,'跨时间稳定');
});

test('模糊称赞、偏好确认回复和普通任务验收不会替用户验证理解',async t=>{
 const e=setup(t),thread=e.thread('create');await e.send(thread,'以后写产品方案先给结论');const memory=e.store.list('memory')[0];await e.send(thread,'这次结构正合适');assert.equal(e.store.get(memory.id).data.evidence.length,0);
 await e.send(thread,'写方案');await e.send(thread,'好');assert.equal(e.store.get(memory.id).data.alignment,'explicit');
 const task=e.command('task.create',{goal:'写方案',system:'create',review_mode:'single'});e.command('task.confirm',{...e.ref(task),confirm:true,model_consent:true});e.command('run.start',e.ref(task));await new Runtime(e.store,e.provider).tick();e.command('task.accept',{...e.ref(task),accept:true});assert.equal(e.store.get(memory.id).data.alignment,'explicit');
});

test('任务验收中的自然反馈自动验证相关理解，负反馈阻止稳定，明确指正替代旧版本',async t=>{
 const e=setup(t),thread=e.thread('create');await e.send(thread,'以后写方案先给结论');const memory=e.store.list('memory')[0];
 const task=e.command('task.create',{goal:'写方案甲',system:'create',review_mode:'single'});e.command('task.confirm',{...e.ref(task),confirm:true,model_consent:true});e.command('run.start',e.ref(task));await new Runtime(e.store,e.provider).tick();e.command('task.accept',{...e.ref(task),accept:true,feedback:'这次结构正合适'});assert.equal(e.store.get(memory.id).data.alignment,'scenario_verified');
 await e.send(thread,'写方案乙');await e.send(thread,'这次结构不合适');assert.equal(e.store.get(memory.id).data.alignment,'hypothesis');
 await e.send(thread,'以后写方案改成先给背景，不要再先给结论');assert.equal(e.store.get(memory.id).data.status,'superseded');const replacement=recallMemories(e.store,e.user.id,'create','写方案')[0];assert.match(replacement.data.content,/先给背景/);assert.equal(replacement.data.alignment,'explicit');
});

test('全局理解的场景证据按使用系统分别计算，创作验证不把参谋一起升级',async t=>{
 const e=setup(t),thread=e.thread('create');await e.send(thread,'以后所有 Agent 回复都用简洁中文');await e.send(thread,'写方案甲');await e.send(thread,'这次中文篇幅正合适');
 const memories=e.service.list(e.user.id,'memory');assert.equal(agentAlignment(memories,'create').label,'场景已验证');assert.equal(agentAlignment(memories,'advise').label,'明确信息');
});

test('共享项目不能自动读取个人偏好；自动记忆不越过账户边界且删除不会重复建立',async t=>{
 const e=setup(t);await e.send(e.thread('create'),'以后所有 Agent 回复都用简洁中文');const memory=e.store.list('memory')[0],other=authenticate(e.store,'auto-memory-other','auto-memory-password',true,'别人').user;e.service.initialize(other);
 assert.equal(recallMemories(e.store,other.id,'create','中文').length,0);
 const project=e.command('project.create',{title:'真实协作',goal:'写方案',criteria:'审核后交付',task:'合作写方案'});const task=e.command('task.create',{goal:'写方案',system:'create',project_id:project.id});e.command('task.confirm',{...e.ref(task),confirm:true,model_consent:true});assert.deepEqual(e.store.get(task.id).data.memory_refs,[]);
 assert.deepEqual(feedbackMemory(e.store,e.user.id,e.store.get(task.id),'以后合作写方案先给结论','task_acceptance'),[]);assert.equal(e.store.list('memory').length,1);
 e.command('memory.decide',{...e.ref(memory),decision:'delete'});await e.send(e.thread('create'),'以后所有 Agent 回复都用简洁中文');assert.equal(e.store.list('memory').length,1);assert.equal(recallMemories(e.store,e.user.id,'create','中文').length,0);
});

test('旧版本低风险候选能自动迁移，撤销和敏感候选不会被迁移成有效记忆',t=>{
 const e=setup(t),source=e.store.add('message',e.user.id,{text:'以后提醒我安排日程',actor_type:'human'});
 const old=e.store.add('memory',e.user.id,{content:source.data.text,source_quote:source.data.text,scope:'create',risk:'low',status:'candidate',alignment:'insufficient',origin:'conversation',source_refs:[e.ref(source)]});
 e.service.bootstrap(e.user.id);assert.equal(e.store.get(old.id).data.status,'learned');assert.equal(e.store.get(old.id).data.scope,'execute');const version=e.store.get(old.id).version;e.service.bootstrap(e.user.id);assert.equal(e.store.get(old.id).version,version);
});

test('有效工具方法沉淀为专业领域经验，只用于同一工具版本，不冒充用户理解或改写工具',async t=>{
 const e=setup(t),tool=e.command('tool.save',{title:'方案方法',instructions:'先列方案结论，再解释依据',system:'create',kind:'Skill'});e.command('tool.activate',e.ref(tool));
 const use=e.command('tool.use',{...e.ref(tool),version_id:e.store.get(tool.id).data.version_id,goal:'写方案甲',parameters:{}}),task={id:use.task_id};e.command('task.confirm',{...e.ref(task),confirm:true,model_consent:true});e.command('run.start',e.ref(task));await new Runtime(e.store,e.provider).tick();e.command('task.accept',{...e.ref(task),accept:true});
 const experience=e.store.list('memory').find(m=>m.data.kind==='method_experience');assert.ok(experience);assert.equal(e.service.list(e.user.id,'memory').length,0);assert.equal(recallMemories(e.store,e.user.id,'create','方案').length,0);
 assert.equal(recallMemories(e.store,e.user.id,'create','方案',{skillId:tool.id})[0].id,experience.id);assert.equal(e.store.get(tool.id).data.revision,1);
});

test('临时状态和单次喜好不形成画像，隐含健康、身份和价值观只能待确认',async t=>{
 const e=setup(t);
 for(const text of ['我现在很难过，只想一个人待着','我现在很难过','我喜欢今天这场比赛'])assert.equal(explicitMemoryStatements(text).length,0);
 for(const text of ['我平时服用降压药','我现在在读大学','我一直认为赚钱比诚实更重要','我平时服用一种新的片剂']){await e.send(e.thread('create'),text);assert.equal(e.store.list('memory').find(m=>m.data.content===text)?.data.status,'pending_confirmation');}
});

test('限定场景的偏好不变全局，模型截取短原句不能扩大分配范围或派生第二份画像',t=>{
 const e=setup(t),text='写产品方案时，我偏好简洁',source=e.store.add('message',e.user.id,{text,actor_type:'human'});
 captureMemories(e.store,e.user.id,{text,system:'create',source,proposals:[{content:'以后所有 Agent 回复都用简洁风格',quote:'我偏好简洁',scope:'owner'}]});
 assert.equal(e.store.list('memory').length,1);assert.equal(e.store.list('memory')[0].data.scope,'create');assert.equal(recallMemories(e.store,e.user.id,'connect','联系团队').length,0);
 const bounded='以后给团队写报告，回复时用简洁中文',other=e.store.add('message',e.user.id,{text:bounded,actor_type:'human'});captureMemories(e.store,e.user.id,{text:bounded,system:'create',source:other});assert.equal(e.store.list('memory').find(m=>m.data.content===bounded).data.scope,'create');
});

test('指正只替代同一情境，产品方案调整不删除周报理解，也不被周报任务召回',async t=>{
 const e=setup(t),thread=e.thread('create');await e.send(thread,'以后写周报先给结论');await e.send(thread,'以后写产品方案先给结论');await e.send(thread,'以后写产品方案改为先背景后结论');
 const weekly=e.store.list('memory').find(m=>m.data.content==='以后写周报先给结论');assert.equal(weekly.data.status,'learned');assert.equal(e.store.list('memory').find(m=>m.data.content==='以后写产品方案先给结论').data.status,'superseded');
 const refs=recallMemories(e.store,e.user.id,'create','写周报');assert.deepEqual(refs.map(m=>m.id),[weekly.id]);
});

test('连续表扬不能把反馈回复当成另一个实际应用而升级',async t=>{
 t.mock.timers.enable({apis:['Date'],now:new Date('2026-09-27T08:00:00Z')});const e=setup(t),thread=e.thread('create');await e.send(thread,'以后写方案先给结论');await e.send(thread,'写方案甲');await e.send(thread,'这次结构正合适');
 t.mock.timers.setTime(new Date('2026-09-29T08:00:00Z').getTime());await e.send(thread,'这次结构正合适');const memory=e.store.list('memory')[0];assert.equal(memory.data.evidence.length,1);assert.equal(memory.data.alignment,'scenario_verified');
});

test('明显否定和混合正负反馈不会计作正证据',async t=>{
 const e=setup(t),thread=e.thread('create');await e.send(thread,'以后写方案先给结论');const memory=e.store.list('memory')[0];
 for(const feedback of ['这次结构不满意','这次结构不正确','这次结构正合适，但篇幅不满意']){await e.send(thread,'写方案甲');await e.send(thread,feedback);assert.equal(e.store.get(memory.id).data.evidence.length,0);assert.equal(e.store.get(memory.id).data.alignment,'hypothesis');}
});

test('手动与旧版全局场景证据也只验证实际使用的领域',async t=>{
 const e=setup(t);await e.send(e.thread('create'),'以后所有 Agent 回复都用简洁中文');const memory=e.store.list('memory')[0],task=e.store.add('task',e.user.id,{system:'create'}),outcome=e.store.add('outcome',e.user.id,{task_id:task.id,verdict:'accepted'});
 e.command('memory.evidence',{...e.ref(memory),outcome_id:outcome.id,scenario:'创作方案',note:'回复篇幅合适',confirm:true});assert.equal(e.store.get(memory.id).data.evidence[0].system,'create');
 const current=e.store.get(memory.id);e.store.update(current,{...current.data,evidence:current.data.evidence.map(({system,...entry})=>entry)},e.user.id);
 const projected=projectMemory(e.store,e.store.get(memory.id));assert.equal(projected.data.domain_alignment.create,'scenario_verified');assert.equal(projected.data.domain_alignment.advise,'explicit');
});

test('撤销验证依据不能把推断提升为明确事实',async t=>{
 const e=setup(t),thread=e.thread('create');await e.send(thread,'以后写方案先给结论');let memory=e.store.list('memory')[0];e.store.update(memory,{...memory.data,initial_alignment:'hypothesis',alignment:'hypothesis',claim_type:'hypothesis'},e.user.id);await e.send(thread,'写方案甲');await e.send(thread,'这次结构正合适');memory=e.store.get(memory.id);
 const source=e.store.get(memory.data.evidence[0].source_id);e.store.update(source,{...source.data,status:'deleted'},e.user.id);assert.equal(projectMemory(e.store,memory).data.alignment,'hypothesis');
});

test('已确认 Person 健康理解修正及旧版迁移后仍可按相关用途分配',async t=>{
 const e=setup(t);await e.send(e.thread('create'),'请记住我的健康限制是不能熬夜');const memory=e.store.list('memory')[0];e.command('memory.decide',{...e.ref(memory),decision:'confirm'});e.command('memory.decide',{...e.ref(memory),decision:'correct',content:'我的健康限制是不能熬夜和久坐'});assert.equal(recallMemories(e.store,e.user.id,'execute','按健康限制安排休息').length,1);
 const source=e.store.add('message',e.user.id,{text:'请记住我的健康限制是不能久坐',actor_type:'human'});const old=e.store.add('memory',e.user.id,{content:source.data.text,source_quote:source.data.text,scope:'create',risk:'high',status:'validated',alignment:'explicit',origin:'conversation',source_refs:[e.ref(source)]});e.service.bootstrap(e.user.id);assert.equal(e.store.get(old.id).data.scope,'owner');assert.ok(recallMemories(e.store,e.user.id,'execute','按健康限制安排休息').some(m=>m.id===old.id));
});

test('删除或改变负反馈来源后反证不再阻止有效理解，手动反证仍有效',async t=>{
 const e=setup(t),thread=e.thread('create');await e.send(thread,'以后写方案先给结论');await e.send(thread,'写方案甲');await e.send(thread,'这次结构不合适');let memory=e.store.list('memory')[0];assert.equal(projectMemory(e.store,memory).data.alignment,'hypothesis');
 const source=e.store.get(memory.data.counterevidence[0].source_id);e.store.update(source,{...source.data,status:'deleted'},e.user.id);assert.equal(projectMemory(e.store,memory).data.alignment,'explicit');assert.equal(projectMemory(e.store,memory).data.domain_alignment.create,'explicit');
 e.command('memory.counterevidence',{...e.ref(memory),confirm:true,note:'本人仍在重新核对结构偏好'});memory=e.store.get(memory.id);assert.equal(projectMemory(e.store,memory).data.alignment,'hypothesis');
});
