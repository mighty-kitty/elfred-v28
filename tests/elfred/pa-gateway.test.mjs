import test from 'node:test';
import assert from 'node:assert/strict';
import {Store,id} from '../../server/elfred/store.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {composePlan,roleFor} from '../../server/elfred/agent-plan.mjs';
import {needsGatewayPlan,tickGateway,gatewayPlanFor,gatewayUsage,ELFRED_TOOL_SCOPES} from '../../server/elfred/pa-gateway/index.mjs';

const json=(body,status=200)=>({ok:status<400,status,text:async()=>JSON.stringify(body)});
const config={ELFRED_PA_GATEWAY_URL:'http://127.0.0.1:8790'};
const provider={status:()=>({configured:true,jev:'unconfigured'})};
const MULTI='先查一下这个领域的公开资料，然后比较三种方案的风险和代价，最后写一份对比报告';

function setup(t){
 const store=new Store(':memory:');t.after(()=>store.close());
 const service=new Service(store,provider),user=authenticate(store,'gw-owner-'+Math.random().toString(36).slice(2,8),'gw-password-1',true,'本人').user;
 service.initialize(user);
 return {store,service,user,command:(action,input)=>service.command(user.id,id(),action,input)};
}

/** 造一个"像规划网关"的假服务：只实现我们用到的四条路径。 */
function gatewayFetcher({plan=[],planner='llm',source='llm'}={}){
 const calls=[];
 const fetcher=async(url,init={})=>{
  const method=init.method||'GET',path=new URL(url).pathname;
  calls.push(`${method} ${path}`);
  if(path==='/v1/pa/profiles')return json({pa_id:'pa_gw_1',state:'onboarding'});
  if(path==='/v1/pa/profiles/pa_gw_1')return json({pa_id:'pa_gw_1',state:'onboarding',tool_scopes:ELFRED_TOOL_SCOPES});
  if(/^\/v1\/pa\/[^/]+\/messages$/.test(path))return json({run_id:'run_gw_1',state:'created'});
  if(path==='/v1/runs/run_gw_1')return json({run_id:'run_gw_1',state:'waiting_approval',plan,events:[{type:'plan.created',payload:{planner,source,planning_ms:812,dropped_tools:[]}}]});
  if(path==='/v1/runs/run_gw_1/cancel')return json({run_id:'run_gw_1',state:'cancelled'});
  throw new Error('unexpected '+method+' '+path);
 };
 fetcher.calls=calls;
 return fetcher;
}

const gatewaySteps=[
 {step:1,goal:'检索领域公开资料',tool:'knowledge_search',risk:'low'},
 {step:2,goal:'写本地文件记录对比过程',tool:'local_file_write',risk:'medium'},
 {step:3,goal:'产出对比报告',tool:'task_create',risk:'medium'},
];

/** 走一遍"确认 → 启动"，拿这次运行的计划。 */
function startRun(e,taskId){
 let task=e.store.get(taskId);
 e.command('task.confirm',{id:task.id,version:task.version,confirm:true,model_consent:true});
 task=e.store.get(taskId);
 return e.store.get(e.command('run.start',{id:task.id,version:task.version}).id);
}

test('只有多步/要分工的目标才值得取方案，同一个任务只登记一次',async t=>{
 const e=setup(t);
 assert.equal(needsGatewayPlan({data:{mode:'compose',goal:'把这段话翻译得更书面一些'}}),false);
 assert.equal(needsGatewayPlan({data:{mode:'compose',goal:MULTI}}),true);
 const multi=e.command('task.create',{goal:MULTI});
 const single=e.command('task.create',{goal:'把这封邮件改成更正式的语气'});
 // 登记不发生在创建那一刻（那时还看不出是不是系统流程），由运行时循环按状态扫
 assert.equal(e.store.list('gateway_request').length,0);
 await tickGateway(e.store,provider,config,gatewayFetcher({plan:gatewaySteps}));
 assert.equal(e.store.list('gateway_request').filter(item=>item.data.task_id===multi.id).length,1);
 assert.equal(e.store.list('gateway_request').some(item=>item.data.task_id===single.id),false);
});

test('系统内部流程与已经跑起来的任务都不打扰网关',async t=>{
 const e=setup(t);
 const multi='先查资料，然后比较方案，最后写一份报告';
 // 对话回复：run 在同一个命令里就启动了（状态已不是草稿），而且带着内部标记
 const chat=e.command('task.create',{goal:multi});
 e.store.update(e.store.get(chat.id),{...e.store.get(chat.id).data,status:'queued',agent_chat:{conversation_id:'c1',trigger_id:'m1'}},e.user.id);
 // 群内回复：同样已经跑起来
 const group=e.command('task.create',{goal:multi});
 e.store.update(e.store.get(group.id),{...e.store.get(group.id).data,status:'running',group_agent:{conversation_id:'c2'}},e.user.id);
 // 用户自己的多步任务：还停在草稿，才值得预先取方案
 const real=e.command('task.create',{goal:multi});
 await tickGateway(e.store,provider,config,gatewayFetcher({plan:gatewaySteps}));
 const ids=e.store.list('gateway_request').map(item=>item.data.task_id);
 assert.equal(ids.includes(chat.id),false,'已经跑起来的对话任务不该花这次调用');
 assert.equal(ids.includes(group.id),false,'群内回复同理');
 assert.equal(ids.includes(real.id),true,'用户自己还没跑的多步骤任务要登记');
 // 放了两天的草稿也不再补
 const stale=e.command('task.create',{goal:multi});
 e.store.update(e.store.get(stale.id),{...e.store.get(stale.id).data},e.user.id);
 const staleRow=e.store.get(stale.id);
 e.store.db.prepare('UPDATE objects SET created=? WHERE id=?').run(new Date(Date.now()-3*86400000).toISOString(),stale.id);
 await tickGateway(e.store,provider,config,gatewayFetcher({plan:gatewaySteps}),Date.now());
 assert.equal(e.store.list('gateway_request').map(item=>item.data.task_id).includes(staleRow.id),false,'放太久没人动的草稿不再补');
});

test('没配网关地址就一个请求都不发，如实说「还没交给它」',async t=>{
 const e=setup(t),task=e.command('task.create',{goal:MULTI});
 await tickGateway(e.store,provider,{},gatewayFetcher({plan:gatewaySteps}));
 // 地址都没配，连"登记"这一步都不该发生（登记即代表"要去取方案"）
 assert.equal(e.store.list('gateway_request').length,0);
 assert.equal(e.store.list('gateway_plan').length,0);
 const usage=gatewayUsage(e.store,e.user.id);
 assert.equal(usage.used,false);
 assert.match(usage.evidence,/还没有把任务规划交给它/);
 // 配上网关之后，同一个任务才会被扫到并真的去取方案
 await tickGateway(e.store,provider,config,gatewayFetcher({plan:gatewaySteps}));
 assert.equal(e.store.list('gateway_request').filter(item=>item.data.task_id===task.id).length,1);
});

test('运行时循环取回方案：落成网关计划与使用证据，并取消网关那边停着的运行',async t=>{
 const e=setup(t),fetcher=gatewayFetcher({plan:gatewaySteps});
 const task=e.command('task.create',{goal:MULTI});
 await tickGateway(e.store,provider,config,fetcher);
 let request=e.store.list('gateway_request').find(item=>item.data.task_id===task.id);
 assert.equal(request.data.status,'waiting');
 assert.equal(request.data.gateway_run_id,'run_gw_1');
 await tickGateway(e.store,provider,config,fetcher);
 request=e.store.get(request.id);
 assert.equal(request.data.status,'done');
 const plan=gatewayPlanFor(e.store,e.user.id,task.id);
 assert.equal(plan.data.gateway_run_id,'run_gw_1');
 assert.equal(plan.data.steps.length,3);
 assert.ok(fetcher.calls.includes('POST /v1/pa/pa_gw_1/messages'));
 assert.ok(fetcher.calls.includes('POST /v1/runs/run_gw_1/cancel'));
 const usage=gatewayUsage(e.store,e.user.id);
 assert.equal(usage.used,true);
 assert.match(usage.evidence,/1 次方案/);
});

test('方案里的动作我们落不成可执行步骤时回落应用内计划，并点名跳过了什么',async t=>{
 const e=setup(t),task=e.command('task.create',{goal:MULTI});
 e.store.add('gateway_plan',e.user.id,{task_id:task.id,gateway_run_id:'run_gw_x',planner:'llm',planning_ms:120,at:new Date().toISOString(),steps:[{step:1,goal:'写本地文件',tool:'local_file_write',risk:'medium'}]});
 const run=startRun(e,task.id);
 assert.equal(run.data.plan.plan_source,'in-app-runtime');
 assert.equal(run.data.plan.gateway.adopted,0);
 assert.match(run.data.plan.gateway.skipped.join(''),/local_file_write/);
});

test('方案能落成我们的步骤时运行计划来自网关，且独立复核不丢',async t=>{
 const e=setup(t),task=e.command('task.create',{goal:MULTI});
 e.store.add('gateway_plan',e.user.id,{task_id:task.id,gateway_run_id:'run_gw_x',planner:'llm',planning_ms:120,at:new Date().toISOString(),steps:gatewaySteps});
 const run=startRun(e,task.id);
 const plan=run.data.plan;
 assert.equal(plan.plan_source,'pa-gateway');
 assert.equal(plan.gateway.run_id,'run_gw_x');
 assert.equal(plan.gateway.adopted,2);
 assert.ok(plan.steps.some(step=>step.phase==='context'&&step.tool==='search.local'));
 assert.ok(plan.steps.some(step=>step.phase==='work'&&step.tool==='text.compose'));
 const current=e.store.get(task.id),baseline=composePlan(current,roleFor(current.data.system,current.data.goal));
 assert.equal(plan.steps.filter(step=>step.phase==='review').length,baseline.filter(step=>step.phase==='review').length);
 assert.ok(plan.steps.length<=12);
});

test('网关连不上：请求记下原因，运行仍回落应用内计划',async t=>{
 const e=setup(t),task=e.command('task.create',{goal:MULTI});
 const broken=async()=>{throw new Error('connect ECONNREFUSED 127.0.0.1:8790');};
 await tickGateway(e.store,provider,config,broken);
 const request=e.store.list('gateway_request').find(item=>item.data.task_id===task.id);
 assert.equal(request.data.status,'failed');
 assert.match(request.data.result.reason,/ECONNREFUSED/);
 // 失败之后还能重排一次（这就是 task.plan 命令存在的意义）
 const again=e.command('task.plan',{id:task.id});
 assert.equal(again.status,'pending');
 const retried=e.store.list('gateway_request').find(item=>item.data.task_id===task.id);
 assert.equal(retried.data.status,'pending');
 assert.equal(retried.data.attempt,1);
 await tickGateway(e.store,provider,config,gatewayFetcher({plan:gatewaySteps}));
 assert.equal(e.store.list('gateway_request').find(item=>item.data.task_id===task.id).data.status,'waiting');
 const started=startRun(e,task.id);
 assert.equal(started.data.plan.plan_source,'in-app-runtime');
 assert.equal(started.data.plan.gateway??null,null);
});

test('工具范围变了要同步给网关，免得它规划出我们接不住的动作',async t=>{
 const e=setup(t),fetcher=gatewayFetcher({plan:gatewaySteps});
 e.store.add('gateway_profile',e.user.id,{pa_id:'pa_gw_1',state:'onboarding',at:new Date().toISOString()});
 const task=e.command('task.create',{goal:MULTI});
 await tickGateway(e.store,provider,config,fetcher);
 const profile=e.store.list('gateway_profile').find(item=>item.owner===e.user.id);
 assert.deepEqual(profile.data.tool_scopes,ELFRED_TOOL_SCOPES);
 assert.ok(fetcher.calls.includes('PATCH /v1/pa/profiles/pa_gw_1'));
 assert.equal(e.store.list('gateway_request').find(item=>item.data.task_id===task.id).data.status,'waiting');
});

test('没有授权资料时不摆"读取资料"的走过场步骤',async t=>{
 const e=setup(t),task=e.command('task.create',{goal:MULTI});
 e.store.add('gateway_plan',e.user.id,{task_id:task.id,gateway_run_id:'run_gw_y',planner:'llm',planning_ms:90,at:new Date().toISOString(),steps:[{step:1,goal:'结合记忆理解',tool:'emos_recall',risk:'low'},{step:2,goal:'产出对比报告',tool:'task_create',risk:'medium'}]});
 const run=startRun(e,task.id);
 assert.match(run.data.plan.gateway.skipped.join(''),/没有授权资料可读/);
 assert.equal(run.data.plan.steps.some(step=>step.tool==='context.read'),false);
 assert.ok(run.data.plan.steps.some(step=>step.phase==='work'));
});

test('网关把产出拆成两步时合成一次，但差别写进回执而不是悄悄丢掉',async t=>{
 const e=setup(t),task=e.command('task.create',{goal:MULTI});
 e.store.add('gateway_plan',e.user.id,{task_id:task.id,gateway_run_id:'run_gw_z',planner:'llm',planning_ms:70,at:new Date().toISOString(),steps:[{step:1,goal:'检索资料',tool:'knowledge_search',risk:'low'},{step:2,goal:'比较风险',tool:'task_create',risk:'medium'},{step:3,goal:'撰写报告',tool:'task_create',risk:'medium'}]});
 const run=startRun(e,task.id);
 assert.equal(run.data.plan.plan_source,'pa-gateway');
 assert.equal(run.data.plan.steps.filter(step=>step.phase==='work').length,1);
 assert.match(run.data.plan.gateway.skipped.join(''),/合成一次成果生成/);
});
