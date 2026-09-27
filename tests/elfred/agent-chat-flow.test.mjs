import test from 'node:test';
import assert from 'node:assert/strict';
import {Store,id} from '../../server/elfred/store.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {Runtime} from '../../server/elfred/runtime.mjs';
import {ModelProvider} from '../../server/elfred/providers.mjs';
import {recentChatMessages} from '../../server/elfred/agent-chat-context.mjs';

function setup(t){
 const store=new Store(':memory:');t.after(()=>store.close());const requests=[];
 const provider=new ModelProvider({ELFRED_MODEL_BASE_URL:'http://127.0.0.1:9999/v1',ELFRED_MODEL_API_KEY:'test-only',ELFRED_MODEL_NAME:'test-model'},async(url,options)=>{
   requests.push(JSON.parse(options.body));return new Response(JSON.stringify({id:'test-receipt',choices:[{message:{content:'按刚才的要求整理完成。'},finish_reason:'stop'}],usage:{total_tokens:80}}),{status:200});
 });
 const service=new Service(store,provider),user=authenticate(store,'chat-flow-test','test-password',true,'测试').user;
 service.initialize(user);const command=(action,input)=>service.command(user.id,id(),action,input);
 return {store,provider,service,user,requests,command};
}

test('真实适配器按 user/assistant 多轮发送，不套任务 JSON 或报告模板，不截断最新要求',async t=>{
 const {store,provider,requests,command}=setup(t);
 const thread=command('agent.chat.create',{system:'explore'});
 command('agent.chat.send',{id:thread.id,text:'只回答：连接正常。',model_consent:true});await new Runtime(store,provider).tick();
 const long='开头明确要求。'+'需要完整保留的背景。'.repeat(80)+'最后只输出一句话。';
 command('agent.chat.send',{id:thread.id,text:long,model_consent:true});await new Runtime(store,provider).tick();
 const sent=requests[1].messages;
 assert.deepEqual(sent.slice(1),[{role:'user',content:'只回答：连接正常。'},{role:'assistant',content:'按刚才的要求整理完成。'},{role:'user',content:long}]);
 assert.doesNotMatch(sent[0].content,/本轮按需加载能力|工作步骤：|默认输出使用/);
 assert.ok(requests[1].max_tokens>=1024);
});

test('历史超过预算时保留最新完整请求和连续最近轮次',()=>{
 const turns=Array.from({length:40},(_,i)=>({id:String(i),data:{actor_type:i%2?'agent':'human',text:'背景'.repeat(2000)}}));
 turns.push({id:'latest',data:{actor_type:'human',text:'关键要求：'+'细节'.repeat(2000)+'最后的验收条件'}});
 const selected=recentChatMessages(turns);
 assert.equal(selected.at(-1).data.text,turns.at(-1).data.text);
 assert.equal(selected[0].data.actor_type,'human');
 assert.ok(selected.length<turns.length);assert.ok(selected.reduce((n,x)=>n+Buffer.byteLength(x.data.text)+80,0)<=22000);
});

test('查询近况只带入本人的真实订阅发现，不读其他账号或旧成果',async t=>{
 const {store,provider,user,requests,command}=setup(t);
 const other=authenticate(store,'chat-flow-other','test-password',true,'其他').user;
 store.add('feed',user.id,{title:'真实 RSS 条目',summary:'订阅摘要',purpose:'discovery',external_url:'https://example.com/news',status:'active'});
 store.add('feed',other.id,{title:'其他人私有发现',purpose:'discovery',external_url:'https://example.com/private',status:'active'});
 store.add('feed',user.id,{title:'旧任务结果',purpose:'outcome',status:'active'});
 const thread=command('agent.chat.create',{system:'explore'});
 command('agent.chat.send',{id:thread.id,text:'最近有什么值得关注的变化',model_consent:true});await new Runtime(store,provider).tick();
 const sent=JSON.stringify(requests[0].messages);
 assert.match(sent,/真实 RSS 条目/);assert.match(sent,/https:\/\/example.com\/news/);
 assert.doesNotMatch(sent,/其他人私有发现|旧任务结果/);
 assert.equal(requests[0].messages.at(-1).content,'最近有什么值得关注的变化');
});

test('确认执行从对话创建真实任务并排队；普通聊天、未授权和跨账号均不能启动任务',async t=>{
 const {store,service,provider,user,command}=setup(t);
 const thread=command('agent.chat.create',{system:'create'});
 const initialTasks=store.list('task').length;
 assert.throws(()=>command('agent.chat.task',{id:thread.id,goal:'写一段简介'}),{code:'CONFIRMATION_REQUIRED'});
 assert.throws(()=>command('agent.chat.task',{id:thread.id,goal:'写一段简介',confirm:true}),{code:'CONSENT_REQUIRED'});
 assert.equal(store.list('task').length,initialTasks);
 const started=command('agent.chat.task',{id:thread.id,goal:'写一段产品简介',confirm:true,model_consent:true});
 const task=store.get(started.id);assert.equal(task.data.status,'queued');assert.equal(task.data.agent_chat,undefined);
 assert.equal(task.data.agent_chat_draft_conversation_id,thread.id);assert.equal(task.data.goal,'写一段产品简介');
 assert.equal(store.get(started.run_id).data.task_id,task.id);
 await new Runtime(store,provider).tick();assert.equal(store.get(started.id).data.status,'awaiting_review');
 assert.equal(store.get(started.run_id).data.receipts[0].output,'按刚才的要求整理完成。');
 const other=authenticate(store,'chat-task-other','test-password',true,'其他').user;service.initialize(other);
 assert.throws(()=>service.command(other.id,id(),'agent.chat.task',{id:thread.id,goal:'越权',confirm:true,model_consent:true}),{code:'NOT_FOUND'});
});

test('对话中的应用内检索实际读取资料，无模型发送或虚构外部执行',async t=>{
 const {store,provider,user,requests,command}=setup(t);
 store.add('knowledge',user.id,{title:'首页设计',content:'首页保持五个 Agent 横向排列',status:'active'});
 const thread=command('agent.chat.create',{system:'explore'});
 assert.throws(()=>command('agent.chat.task',{id:thread.id,goal:'字'.repeat(301),mode:'search',confirm:true}),{code:'INVALID_INPUT'});
 assert.throws(()=>command('agent.chat.task',{id:thread.id,goal:'上周本周的首页设计',mode:'search',confirm:true}),{code:'SEARCH_CLARIFICATION_REQUIRED'});
 assert.equal(store.list('task').length,0);
 const started=command('agent.chat.task',{id:thread.id,goal:'首页设计',mode:'search',confirm:true});
 await new Runtime(store,provider).tick();assert.equal(requests.length,0);
 const run=store.get(started.run_id);assert.equal(run.data.status,'completed');
 assert.equal(run.data.receipts[0].output[0].title,'首页设计');
});
