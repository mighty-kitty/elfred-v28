import test from 'node:test';
import assert from 'node:assert/strict';
import {Store,id} from '../../server/elfred/store.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {Runtime} from '../../server/elfred/runtime.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {captureMemories,recallMemories,explicitMemoryStatements,unpackLearningReply} from '../../server/elfred/memory-learning.mjs';
import {syncMemoryHub,memoryHubStatus} from '../../server/elfred/memory-hub.mjs';
import {agentAlignment} from '../../app/v28/core/agent-alignment.mjs';
import {createServer} from 'node:http';
import {apiHandler} from '../../server/elfred/http.mjs';

function setup(t){
 const store=new Store(':memory:');t.after(()=>store.close());const requests=[];
 const provider={status:()=>({configured:true}),generate:async r=>{requests.push(r);return {output:r.conversation?JSON.stringify({reply:'好的，这条理解需要你核对。',memories:[]}):'这是实际生成的结果',usage:{total_tokens:20}};}};
 const service=new Service(store,provider),user=authenticate(store,'learning-owner','test-password',true,'本人').user;service.initialize(user);
 const command=(a,i)=>service.command(user.id,id(),a,i),ref=o=>({id:o.id,version:store.get(o.id).version});
 const learn=async(text,system='create')=>{const thread=command('agent.chat.create',{system});command('agent.chat.send',{id:thread.id,text,model_consent:true});await new Runtime(store,provider).tick();return thread;};
 return {store,service,user,provider,requests,command,ref,learn};
}
test('聊天形成有原句和领域的候选；确认后新线程调用，其他领域和其他账号不调用',async t=>{
 const e=setup(t);await e.learn('以后写产品方案先给结论，再展开依据');
 const m=e.store.list('memory')[0];assert.equal(m.data.status,'candidate');assert.equal(m.data.scope,'create');assert.match(m.data.source_quote,/以后写产品方案/);
 assert.equal(e.store.get(m.data.source_refs[0].id).data.actor_type,'human');
 assert.equal(agentAlignment(e.service.list(e.user.id,'memory'),'create').label,'理解待验证');
 assert.equal(e.requests[0].context.length,0);
 e.command('memory.decide',{...e.ref(m),decision:'confirm'});
 assert.equal(agentAlignment(e.service.list(e.user.id,'memory'),'create').label,'明确信息');
 await e.learn('请写一份产品方案');assert.match(JSON.stringify(e.requests[1].context),/先给结论/);
 await e.learn('请给出建议','advise');assert.doesNotMatch(JSON.stringify(e.requests[2].context),/先给结论/);
 const other=authenticate(e.store,'learning-other','test-password',true,'别人').user;e.service.initialize(other);
 assert.equal(recallMemories(e.store,other.id,'create','产品').length,0);
 const messages=e.store.list('message').filter(m=>m.data.actor_type==='agent');assert.ok(messages.every(m=>m.data.text==='好的，这条理解需要你核对。'));
});
test('临时情绪、一次性要求、引用他人和密钥不进入记忆；模型伪造原句被丢弃',t=>{
 const e=setup(t);
 for(const text of ['今天很难过','帮我写三行代码','他说以后喜欢详细说明','密钥是 sk-this-is-a-fake-secret-only'])assert.equal(explicitMemoryStatements(text).length,0);
 const message=e.store.add('message',e.user.id,{text:'今天只是随便聊聊',actor_type:'human'});
 assert.equal(captureMemories(e.store,e.user.id,{text:message.data.text,system:'create',source:message,proposals:[{content:'用户偏好长文',quote:'我一直喜欢长文'}]}).length,0);
 assert.equal(e.store.list('memory').length,0);
});
test('敏感理解只能待本人确认，拒绝及删除后不能自动重复建立同一理解',async t=>{
 const e=setup(t);await e.learn('请记住我的健康限制：不能熬夜');const m=e.store.list('memory')[0];assert.equal(m.data.risk,'high');assert.equal(m.data.status,'pending_confirmation');
 assert.equal(recallMemories(e.store,e.user.id,'create','健康').length,0);
 e.command('memory.decide',{...e.ref(m),decision:'delete'});await e.learn('请记住我的健康限制：不能熬夜');assert.equal(e.store.list('memory').length,1);
});
test('修正、隐藏、到期、反证会影响后续召回和首页，不按聊天次数升级',async t=>{
 const e=setup(t);await e.learn('以后先给结论');const m=e.store.list('memory')[0];e.command('memory.decide',{...e.ref(m),decision:'confirm'});
 const fixed=e.command('memory.decide',{...e.ref(m),decision:'correct',content:'以后先列问题，再给结论'});
 assert.equal(recallMemories(e.store,e.user.id,'create','结论')[0].id,fixed.id);
 e.command('memory.governance',{...e.ref(fixed),hidden:true});assert.equal(recallMemories(e.store,e.user.id,'create','结论').length,0);assert.equal(agentAlignment(e.service.list(e.user.id,'memory'),'create').label,'尚无足够理解');
 e.command('memory.governance',{...e.ref(fixed),hidden:false});e.command('memory.counterevidence',{...e.ref(fixed),confirm:true,note:'本次场景需要直接给结论'});
 assert.equal(agentAlignment(e.service.list(e.user.id,'memory'),'create').label,'理解待验证');
 e.command('memory.governance',{...e.ref(fixed),expires_at:new Date(Date.now()+1000).toISOString()});
 assert.equal(agentAlignment(e.service.list(e.user.id,'memory'),'create').label,'理解待验证');
 const current=e.store.get(fixed.id);e.store.update(current,{...current.data,expires_at:new Date(Date.now()-1).toISOString()},e.user.id);
 assert.equal(recallMemories(e.store,e.user.id,'create','结论').length,0);assert.equal(agentAlignment(e.service.list(e.user.id,'memory'),'create').label,'尚无足够理解');
});
test('任务读取确认过的记忆；仅验收不升级，明确核对场景后才升级；反馈形成候选',async t=>{
 const e=setup(t);await e.learn('以后写方案先给结论');const m=e.store.list('memory')[0];e.command('memory.decide',{...e.ref(m),decision:'confirm'});
 const runTask=async()=>{const task=e.command('task.create',{goal:'写方案',system:'create',review_mode:'single'});e.command('task.confirm',{...e.ref(task),confirm:true,model_consent:true});e.command('run.start',e.ref(task));await new Runtime(e.store,e.provider).tick();return task;};
 const first=await runTask();assert.match(JSON.stringify(e.requests.at(-1).context),/先给结论/);e.command('task.accept',{...e.ref(first),accept:true});assert.equal(e.store.get(m.id).data.alignment,'explicit');
 const second=await runTask();e.command('task.accept',{...e.ref(second),accept:true,memory_evidence_ids:[m.id],feedback:'以后方案中每次说明适用范围'});
 assert.equal(e.store.get(m.id).data.alignment,'scenario_verified');assert.equal(e.store.get(m.id).data.evidence.length,1);assert.equal(e.store.list('memory').length,2);
 assert.equal(e.store.list('memory').find(x=>x.id!==m.id).data.status,'candidate');
 assert.throws(()=>e.command('memory.review_stability',{...e.ref(m),confirm:true,note:'只凭一次结果'}),{code:'EVIDENCE_REQUIRED'});
});
test('任务授权后记忆被纠正，运行必须停下重新授权，不读取旧理解',async t=>{
 const e=setup(t);await e.learn('以后先给结论');const m=e.store.list('memory')[0];e.command('memory.decide',{...e.ref(m),decision:'confirm'});
 const task=e.command('task.create',{goal:'写方案',system:'create',review_mode:'single'});e.command('task.confirm',{...e.ref(task),confirm:true,model_consent:true});const run=e.command('run.start',e.ref(task));e.command('memory.decide',{...e.ref(m),decision:'delete'});
 await new Runtime(e.store,e.provider).tick();assert.equal(e.requests.length,1);assert.equal(e.store.get(run.id).data.status,'blocked');
});
test('模型结构化回复不暴露 JSON；损坏的结构不能作为自然回复或记忆',()=>{
 assert.deepEqual(unpackLearningReply('{"reply":"自然回复","memories":[]}').reply,'自然回复');
 assert.throws(()=>unpackLearningReply('{"reply":"截断'),{code:'INVALID_CHAT_REPLY'});
 assert.equal(unpackLearningReply('普通文本回复').reply,'普通文本回复');
});
test('中枢未配置保留队列；版本幂等同步、拒绝错配回执、失败退避、删除发送 forget',async t=>{
 const e=setup(t);const m=e.command('memory.create',{content:'以后先给结论',scope:'create'});e.command('memory.decide',{...e.ref(m),decision:'confirm'});
 assert.equal(memoryHubStatus(e.store,e.user.id,{}).configured,false);await syncMemoryHub(e.store,{},()=>{throw new Error('不应请求');});
 const config={ELFRED_MEMORY_HUB_URL:'http://127.0.0.1:9876',ELFRED_MEMORY_HUB_TOKEN:'test-secret'},requests=[];
 const fetcher=async(url,options)=>{requests.push({url,options});const body=JSON.parse(options.body);return new Response(JSON.stringify({id:body.id,owner:body.owner,revision:body.revision,state_hash:body.state_hash}),{status:200});};
 for(let i=0;i<3;i++)await syncMemoryHub(e.store,config,fetcher);
 assert.equal(requests.length,1);assert.equal(requests[0].options.method,'PUT');assert.match(requests[0].options.headers['Idempotency-Key'],new RegExp(m.id));
 e.command('memory.decide',{...e.ref(m),decision:'delete'});await syncMemoryHub(e.store,config,fetcher);assert.equal(requests[1].options.method,'DELETE');assert.equal(JSON.parse(requests[1].options.body).action,'forget');
 const second=e.command('memory.create',{content:'以后多给例子',scope:'create'});e.command('memory.decide',{...e.ref(second),decision:'confirm'});
 for(let i=0;i<3;i++)await syncMemoryHub(e.store,config,async()=>new Response('{}',{status:200}));
 const pending=e.store.list('memory_bridge').find(x=>x.data.status==='pending');assert.ok(pending.data.next_at>Date.now());assert.equal(pending.data.attempts,1);
});
test('理解证据不能跨领域升级，重复确认不清空已有场景证据',async t=>{
 const e=setup(t);await e.learn('以后先给结论');const m=e.store.list('memory')[0];e.command('memory.decide',{...e.ref(m),decision:'confirm'});
 const otherTask=e.store.add('task',e.user.id,{system:'connect'}),otherOutcome=e.store.add('outcome',e.user.id,{task_id:otherTask.id,verdict:'accepted'});
 assert.throws(()=>e.command('memory.evidence',{...e.ref(m),outcome_id:otherOutcome.id,scenario:'沟通',note:'不属于创作领域',confirm:true}),{code:'MEMORY_SCOPE'});
 const task=e.store.add('task',e.user.id,{system:'create'}),outcome=e.store.add('outcome',e.user.id,{task_id:task.id,verdict:'accepted'});
 e.command('memory.evidence',{...e.ref(m),outcome_id:outcome.id,scenario:'写作',note:'符合结构偏好',confirm:true});
 const before=e.store.get(m.id);e.command('memory.decide',{...e.ref(m),decision:'confirm'});assert.equal(e.store.get(m.id).version,before.version);assert.equal(e.store.get(m.id).data.alignment,'scenario_verified');
});
test('已同步理解到期，即使版本没变，中枢也会收到停止使用的回执请求',async t=>{
 const e=setup(t),m=e.command('memory.create',{content:'以后先给结论',scope:'create'});e.command('memory.decide',{...e.ref(m),decision:'confirm'});e.command('memory.governance',{...e.ref(m),expires_at:new Date(Date.now()+60000).toISOString()});
 const calls=[],config={ELFRED_MEMORY_HUB_URL:'http://127.0.0.1:9876',ELFRED_MEMORY_HUB_TOKEN:'test-only'};
 const fetcher=async(url,options)=>{const payload=JSON.parse(options.body);calls.push(options);return new Response(JSON.stringify({id:payload.id,owner:payload.owner,revision:payload.revision}));};
 for(let i=0;i<4;i++)await syncMemoryHub(e.store,config,fetcher);assert.equal(calls.at(-1).method,'PUT');const revision=e.store.get(m.id).version;
 const original=Date.now,at=original()+70000;Date.now=()=>at;
 try{for(let i=0;i<3;i++)await syncMemoryHub(e.store,config,fetcher);assert.equal(calls.at(-1).method,'DELETE');assert.equal(JSON.parse(calls.at(-1).body).revision,revision);}finally{Date.now=original;}
});
test('记忆只读接口要求登录，按当前用户及领域返回，未配置中枢状态明确',async t=>{
 const e=setup(t),m=e.command('memory.create',{content:'以后先给结论',scope:'create'});e.command('memory.decide',{...e.ref(m),decision:'confirm'});
 const login=authenticate(e.store,'learning-owner','test-password'),other=authenticate(e.store,'learning-api-other','test-password',true,'其他');e.service.initialize(other.user);
 let handler;const server=createServer((req,res)=>void handler(req,res));await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin='http://127.0.0.1:'+server.address().port;handler=apiHandler(e.service,{origin});t.after(()=>new Promise(resolve=>server.close(resolve)));
 const request=(path,token)=>fetch(origin+'/api/elfred'+path,{headers:token?{Cookie:'elfred_session='+token}:{}});
 assert.equal((await request('/memory/recall?scope=create&q=结论')).status,401);
 assert.equal((await (await request('/memory/recall?scope=create&q=结论',login.token)).json()).items.length,1);
 assert.equal((await (await request('/memory/recall?scope=advise&q=结论',login.token)).json()).items.length,0);
 assert.equal((await (await request('/memory/recall?scope=create&q=结论',other.token)).json()).items.length,0);
 assert.equal((await request('/memory/recall?scope=all',login.token)).status,400);
 const status=await (await request('/memory/hub',login.token)).json();assert.equal(status.configured,false);assert.equal(status.mode,'local');assert.doesNotMatch(JSON.stringify(status),/Bearer|test-only/);
});


test('来源到期无需版本变化即可停止召回、更新首页并发出中枢删除',async t=>{
 const e=setup(t),doc=e.store.add('document',e.user.id,{content:'用户自己的资料',expires_at:new Date(Date.now()+60000).toISOString()});
 const m=e.command('memory.create',{content:'以后先给结论',scope:'create',source_refs:[e.ref(doc)]});e.command('memory.decide',{...e.ref(m),decision:'confirm'});
 const config={ELFRED_MEMORY_HUB_URL:'http://127.0.0.1:9876',ELFRED_MEMORY_HUB_TOKEN:'test-token'},methods=[];
 const fetcher=async(_url,options)=>{methods.push(options.method);const b=JSON.parse(options.body);return new Response(JSON.stringify({id:b.id,owner:b.owner,revision:b.revision,state_hash:b.state_hash}));};
 for(let i=0;i<3;i++)await syncMemoryHub(e.store,config,fetcher);assert.deepEqual(methods,['PUT']);
 const actualNow=Date.now;Date.now=()=>actualNow()+70000;
 try{assert.equal(recallMemories(e.store,e.user.id,'create','结论').length,0);assert.equal(agentAlignment(e.service.list(e.user.id,'memory'),'create').label,'需要重评');await syncMemoryHub(e.store,config,fetcher);assert.deepEqual(methods,['PUT','DELETE']);}finally{Date.now=actualNow;}
});

test('场景依据失效降为待重评，并更新中枢同版本投影；不形成来源循环',async t=>{
 const e=setup(t),m=e.command('memory.create',{content:'以后先给结论',scope:'create'});e.command('memory.decide',{...e.ref(m),decision:'confirm'});
 const doc=e.store.add('document',e.user.id,{content:'本次任务背景'}),task=e.store.add('task',e.user.id,{system:'create',goal:'方案',memory_refs:[e.ref(m)]}),outcome=e.store.add('outcome',e.user.id,{task_id:task.id,verdict:'accepted',source_refs:[e.ref(doc)]});
 e.command('memory.evidence',{...e.ref(m),outcome_id:outcome.id,scenario:'方案',note:'成果符合偏好',confirm:true});
 assert.equal(agentAlignment(e.service.list(e.user.id,'memory'),'create').label,'场景已验证');assert.ok(e.store.canRead(e.user.id,e.store.get(m.id)));
 const config={ELFRED_MEMORY_HUB_URL:'http://127.0.0.1:9876',ELFRED_MEMORY_HUB_TOKEN:'test-token'},bodies=[];
 const fetcher=async(_url,o)=>{const b=JSON.parse(o.body);bodies.push(b);return new Response(JSON.stringify({id:b.id,owner:b.owner,revision:b.revision,state_hash:b.state_hash}));};
 for(let i=0;i<3;i++)await syncMemoryHub(e.store,config,fetcher);
 e.store.update(doc,{...doc.data,content:'修正背景'},e.user.id);
 assert.equal(agentAlignment(e.service.list(e.user.id,'memory'),'create').label,'需要重评');assert.equal(recallMemories(e.store,e.user.id,'create','结论')[0].data.alignment,'explicit');
 await syncMemoryHub(e.store,config,fetcher);assert.equal(bodies.at(-1).alignment,'explicit');assert.deepEqual(bodies.at(-1).evidence,[]);
 assert.throws(()=>e.command('memory.review_stability',{...e.ref(m),confirm:true,note:'旧证据已不可用'}),{code:'EVIDENCE_CHANGED'});
});

test('重新授权改变记忆快照时不能继承旧成果、检查点或假装只需收尾',async t=>{
 const e=setup(t),m=e.command('memory.create',{content:'以后先给结论',scope:'create'});e.command('memory.decide',{...e.ref(m),decision:'confirm'});
 const task=e.command('task.create',{goal:'写方案：结论',system:'create',review_mode:'single'});e.command('task.confirm',{...e.ref(task),confirm:true,model_consent:true});const first=e.command('run.start',e.ref(task));await new Runtime(e.store,e.provider).tick();
 for(const o of [e.store.get(first.id),e.store.get(task.id)])e.store.update(o,{...o.data,status:'paused'},e.user.id);
 const corrected=e.command('memory.decide',{...e.ref(m),decision:'correct',content:'以后先给背景，最后给结论'});
 e.command('task.renew_approval',{...e.ref(task),confirm:true,model_consent:true});const renewed=e.command('run.start',e.ref(task));
 assert.deepEqual(e.store.get(renewed.id).data.receipts,[]);assert.deepEqual(e.store.get(renewed.id).data.checkpoint,[]);assert.equal(e.store.get(renewed.id).data.memory_refs[0].id,corrected.id);
});

test('提问不写成偏好，模型结构字段顺序不能绕过损坏结构检查',()=>{
 assert.equal(explicitMemoryStatements('我喜欢详细说明吗？').length,0);
 assert.throws(()=>unpackLearningReply('{"memories":[],"reply":null}'),{code:'INVALID_CHAT_REPLY'});
 assert.throws(()=>unpackLearningReply('{"memories":[],"reply":"截断'),{code:'INVALID_CHAT_REPLY'});
});


test('任务专用上下文授权及其衍生物不能扩大成长期记忆，旧数据也不召回',t=>{
 const e=setup(t),task=e.command('task.create',{goal:'看标题',system:'create'}),doc=e.command('knowledge.create',{title:'本次提供标题',content:'只有本次授权的资料'});
 const req=e.command('context.request',{task_id:task.id,task_version:e.ref(task).version,holder:'owner',purpose:'只看标题',fields:['title'],expires:new Date(Date.now()+60000).toISOString()});
 e.command('context.respond',{...e.ref(req),decision:'fulfill',note:'本次标题',source_refs:[e.ref(doc)],confirm:true});const grant=e.store.list('context_grant')[0];
 for(const source of [grant,e.store.add('knowledge',e.user.id,{content:'来源受任务授权限制',source_refs:[e.ref(grant)]})])assert.throws(()=>e.command('memory.create',{content:'以后按这个标题处理',scope:'create',source_refs:[e.ref(source)]}),{code:'MEMORY_SOURCE_SCOPE'});
 const legacy=e.store.add('memory',e.user.id,{content:'以后按这个标题处理',scope:'create',status:'validated',alignment:'explicit',risk:'low',source_refs:[e.ref(grant)]});assert.equal(recallMemories(e.store,e.user.id,'create','标题').length,0);
 const message=e.store.add('message',e.user.id,{text:'我喜欢详细说明吗？',actor_type:'human'});assert.equal(captureMemories(e.store,e.user.id,{text:message.data.text,system:'create',source:message,proposals:[{content:'用户偏好详细说明',quote:message.data.text}]}).length,0);assert.equal(captureMemories(e.store,e.user.id,{text:message.data.text,system:'create',source:message,proposals:[{content:'用户偏好详细说明',quote:'我喜欢详细说明'}]}).length,0);
});
