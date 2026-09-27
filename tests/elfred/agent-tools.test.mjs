import test from 'node:test';
import assert from 'node:assert/strict';
import {Store,id} from '../../server/elfred/store.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {Runtime} from '../../server/elfred/runtime.mjs';
import {ModelProvider} from '../../server/elfred/providers.mjs';
import {PublicWeb,publicQuery,webIntent,pageText,readPublicPage} from '../../server/elfred/public-web.mjs';

function setup(t){
 const store=new Store(':memory:');t.after(()=>store.close());const requests=[],queries=[];
 const provider=new ModelProvider({ELFRED_MODEL_BASE_URL:'http://127.0.0.1:9999/v1',ELFRED_MODEL_API_KEY:'test-only'},async(_url,options)=>{requests.push(JSON.parse(options.body));return new Response(JSON.stringify({id:'real-adapter-fixture',choices:[{message:{content:'基于工具结果整理的回复。'},finish_reason:'stop'}],usage:{total_tokens:90}}));});
 provider._publicWeb=new PublicWeb({},async(url)=>{queries.push(url);return [{title:'公开来源',url:'https://nodejs.org/',summary:'搜索摘要',published_at:null}];},async(url)=>{queries.push(url);return {title:'网页正文',url,content:'本次真正读取的网页内容。',evidence:'page_text'};});
 const user=authenticate(store,'agent-tools-owner','pass1234',true,'本人').user,service=new Service(store,provider);service.initialize(user);
 const command=(action,input)=>service.command(user.id,id(),action,input);return {store,user,provider,service,requests,queries,command,runtime:new Runtime(store,provider)};
}

test('五个 Agent 都真实执行联网工具再整理，引用留在聊天，费用和停止条件可核对',async t=>{
 const e=setup(t);
 for(const system of ['explore','advise','create','connect','execute']){
  const thread=e.command('agent.chat.create',{system});
  e.command('agent.chat.send',{id:thread.id,text:'我喜欢简洁回答',model_consent:true});await e.runtime.tick();
  const sent=e.command('agent.chat.send',{id:thread.id,text:'联网搜索 Node.js 官方文档',model_consent:true});await e.runtime.tick();
  const run=e.store.get(sent.run_id),task=e.store.get(sent.task_id);
  assert.equal(run.data.status,'awaiting_review');assert.deepEqual(run.data.plan.steps.map(s=>s.tool),['web.search','text.compose']);
  assert.equal(run.data.receipts[0].provider,'public-bing-rss');assert.equal(run.data.receipts[0].usage.total_tokens,0);assert.equal(task.data.units,1000);assert.equal(task.data.calls,2);
  assert.match(JSON.stringify(e.requests.at(-1)),/公开来源|search_excerpt/);
  const reply=e.store.list('message').find(m=>m.data.run_id===run.id);assert.equal(reply.data.citations[0].url,'https://nodejs.org/');
 }
 assert.equal(e.queries.length,5);assert.ok(e.queries.every(url=>!decodeURIComponent(url).includes('我喜欢简洁回答')));
});

test('明确关闭联网不发公开请求；读取公开网页有单独回执，内网和凭据查询被阻止',async t=>{
 const e=setup(t),thread=e.command('agent.chat.create',{system:'create'});
 e.command('agent.chat.send',{id:thread.id,text:'联网搜索 Node.js',network:'off',model_consent:true});await e.runtime.tick();assert.equal(e.queries.length,0);
 const read=e.command('agent.chat.send',{id:thread.id,text:'请阅读 https://nodejs.org/en/about',model_consent:true});await e.runtime.tick();assert.equal(e.store.get(read.run_id).data.receipts[0].provider,'public-page-reader');assert.match(JSON.stringify(e.requests.at(-1)),/page_text|真正读取/);
 assert.throws(()=>e.command('agent.chat.send',{id:thread.id,text:'请阅读 https://127.0.0.1/private',model_consent:true}),{code:'INVALID_FEED_URL'});
 assert.throws(()=>publicQuery('联网搜索 密码:secret'),{code:'PRIVATE_WEB_QUERY'});assert.throws(()=>publicQuery('搜索我 user@example.com'),{code:'PRIVATE_WEB_QUERY'});
 assert.equal(webIntent('不用联网，帮我写一段简介'),null);assert.equal(pageText('<script>alert(1)</script><h1>正常标题</h1><p>正常正文</p>'),'正常标题 正常正文');
 await assert.rejects(readPublicPage('https://example.com/',{resolver:async()=>[{address:'127.0.0.1'}]}),{code:'WEB_UNAVAILABLE'});
});

test('工具调用冻结版本和输入，按保存说明执行并计数；跨账号、草稿、过期版本不能调用',async t=>{
 const e=setup(t),thread=e.command('agent.chat.create',{system:'advise'});
 const tool=e.command('tool.save',{title:'简报整理',instructions:'固定格式：标题、结论、下一步。',kind:'Skill',system:'advise',parameters:[{name:'受众',required:true}]});
 e.command('tool.activate',{id:tool.id,version:e.store.get(tool.id).version});const version=e.store.get(tool.id).data.version_id;
 assert.throws(()=>e.command('agent.chat.send',{id:thread.id,text:'整理一次',tool_id:tool.id,tool_version_id:'old',model_consent:true}),{code:'VERSION_CONFLICT'});
 assert.throws(()=>e.command('agent.chat.send',{id:thread.id,text:'整理一次',tool_id:tool.id,tool_version_id:version,model_consent:true}),{code:'PARAMETER_REQUIRED'});
 const sent=e.command('agent.chat.send',{id:thread.id,text:'整理一次',tool_id:tool.id,tool_version_id:version,parameters:{受众:'设计团队'},model_consent:true});await e.runtime.tick();
 assert.equal(e.store.get(sent.task_id).data.skill_version_id,version);assert.equal(e.store.get(tool.id).data.uses,1);assert.match(JSON.stringify(e.requests[0]),/固定格式|设计团队/);
 assert.equal(e.store.list('message').find(m=>m.data.run_id===sent.run_id).data.tool_id,tool.id);
 const other=authenticate(e.store,'agent-tools-other','pass1234',true,'其他').user;e.service.initialize(other);
 assert.throws(()=>e.service.command(other.id,id(),'agent.chat.send',{id:thread.id,text:'越权',tool_id:tool.id,model_consent:true}),{code:'NOT_FOUND'});
 e.command('tool.archive',{id:tool.id,version:e.store.get(tool.id).version});assert.throws(()=>e.command('agent.chat.send',{id:thread.id,text:'再次整理',tool_id:tool.id,tool_version_id:version,parameters:{受众:'我'},model_consent:true}),{code:'TOOL_DISABLED'});
});

test('聊天中的本人资料检索使用真实搜索工具并隔离账号，不发送公开查询',async t=>{
 const e=setup(t),other=authenticate(e.store,'private-tools-other','pass1234',true,'其他').user;
 e.store.add('knowledge',e.user.id,{title:'首页方案',content:'五个 Agent 横排',status:'active'});e.store.add('knowledge',other.id,{title:'首页秘密',content:'绝不能被读到',status:'active'});
 const thread=e.command('agent.chat.create',{system:'connect'}),sent=e.command('agent.chat.send',{id:thread.id,text:'搜索我的知识库：首页方案',model_consent:true});await e.runtime.tick();
 assert.equal(e.store.get(sent.run_id).data.plan.steps[0].tool,'search.local');assert.match(JSON.stringify(e.requests.at(-1)),/五个 Agent 横排/);assert.doesNotMatch(JSON.stringify(e.requests.at(-1)),/首页秘密|绝不能/);assert.equal(e.queries.length,0);
});

test('公开检索故障不再生成假回复；无模型服务不会消耗模型额度',async t=>{
 const e=setup(t);e.provider._publicWeb=new PublicWeb({},async()=>{throw new Error('offline');});
 const thread=e.command('agent.chat.create',{system:'execute'}),sent=e.command('agent.chat.send',{id:thread.id,text:'联网搜索资料',model_consent:true});await e.runtime.tick();
 assert.equal(e.store.get(sent.task_id).data.status,'failed');assert.equal(e.requests.length,0);assert.equal(e.store.get(sent.task_id).data.units,0);assert.equal(e.store.list('message').filter(m=>m.data.actor_type==='agent').length,0);
});

test('已有联网任务入口也能使用公开工具，且不召回私人记忆',async t=>{
 const e=setup(t),prepared=e.command('external.prepare',{operation:'web_search',goal:'Node.js 官方资料'});const task=e.store.get(prepared.id);assert.equal(task.data.public_research,true);
 e.command('task.confirm',{id:task.id,version:task.version,confirm:true,model_consent:true});let current=e.store.get(task.id);assert.equal(current.data.memory_refs.length,0);e.command('run.start',{id:current.id,version:current.version});await e.runtime.tick();assert.equal(e.queries.length,1);assert.equal(e.store.get(e.store.get(task.id).data.run_id).data.receipts.length,2);
});

test('注册支持常规八位密码与账号首尾空格，重复注册、错密码和会话失效有明确结果',t=>{
 const store=new Store(':memory:');t.after(()=>store.close());const a=authenticate(store,' new-account ','pass1234',true,'新人');assert.equal(a.user.handle,'new-account');assert.equal(authenticate(store,'NEW-ACCOUNT','pass1234').user.id,a.user.id);
 assert.throws(()=>authenticate(store,'new-account','pass1234',true,'新人'),{code:'ACCOUNT_EXISTS'});assert.throws(()=>authenticate(store,'new-account','wrong123'),{code:'INVALID_LOGIN'});assert.throws(()=>authenticate(store,'another-account','1234567',true,'新人'),{code:'INVALID_PASSWORD'});
});

test('长探索对话使用工具为冻结版本保留来源位置',async t=>{
 const e=setup(t),thread=e.command('agent.chat.create',{system:'explore'});
 for(let i=0;i<8;i++){e.command('agent.chat.send',{id:thread.id,text:'背景信息 '+i,model_consent:true});await e.runtime.tick();}
 for(let i=0;i<4;i++)e.store.add('feed',e.user.id,{title:'订阅来源 '+i,summary:'公开摘要',purpose:'discovery',external_url:'https://nodejs.org/',status:'active'});
 const tool=e.command('tool.save',{title:'资讯简报',kind:'Skill',system:'explore',instructions:'整理为简报'});e.command('tool.activate',{id:tool.id,version:e.store.get(tool.id).version});
 const sent=e.command('agent.chat.send',{id:thread.id,text:'整理最近新闻简报',tool_id:tool.id,tool_version_id:e.store.get(tool.id).data.version_id,model_consent:true});
 assert.ok(e.store.get(sent.task_id).data.source_refs.length<=20);await e.runtime.tick();assert.equal(e.store.get(sent.task_id).data.status,'awaiting_review');
});
