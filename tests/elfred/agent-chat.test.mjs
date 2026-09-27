import test from 'node:test';
import assert from 'node:assert/strict';
import {Store,id} from '../../server/elfred/store.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {Runtime} from '../../server/elfred/runtime.mjs';

function setup(t){
  const store=new Store(':memory:');t.after(()=>store.close());
  const calls=[];
  const provider={status:()=>({configured:true}),generate:async request=>{calls.push(request);return {output:calls.length===1?'先说说你希望达到什么结果。':'根据刚才的目标，我建议先整理首页结构。',usage:{total_tokens:30}};}};
  const service=new Service(store,provider);
  const [alice,bob]=['agent-chat-alice','agent-chat-bob'].map(handle=>authenticate(store,handle,'local-test-password',true,handle).user);
  for(const user of [alice,bob])service.initialize(user);
  const command=(user,action,input)=>service.command(user.id,id(),action,input);
  return {store,service,provider,calls,alice,bob,command};
}

test('子 Agent 对话可多轮延续，回复留在私有会话，普通聊天不自动生成可见草稿',async t=>{
  const {store,service,provider,calls,alice,bob,command}=setup(t);
  const thread=command(alice,'agent.chat.create',{system:'create'});
  assert.equal(service.list(bob.id,'conversation').some(item=>item.id===thread.id),false);
  const first=command(alice,'agent.chat.send',{id:thread.id,text:'帮我看看首页',model_consent:true});
  assert.ok(first.run_id);
  assert.equal(store.get(first.task_id).data.agent_chat.conversation_id,thread.id);
  assert.equal(store.list('task').filter(task=>task.data.agent_chat_draft_conversation_id).length,0);
  assert.equal(store.get(first.task_id).data.internal_search,true);
  await new Runtime(store,provider).tick();
  const firstReply=service.list(alice.id,'message').find(item=>item.data.trigger_id===first.id);
  assert.ok(firstReply);assert.equal(firstReply.data.actor_type,'agent');
  assert.equal(service.list(bob.id,'message').some(item=>item.id===firstReply.id),false);
  const second=command(alice,'agent.chat.send',{id:thread.id,text:'就按我们刚才的目标继续',model_consent:true});
  await new Runtime(store,provider).tick();
  assert.equal(calls.length,2);
  assert.deepEqual(calls[1].conversation,[{role:'user',content:'帮我看看首页'},{role:'assistant',content:'先说说你希望达到什么结果。'},{role:'user',content:'就按我们刚才的目标继续'}]);
  assert.equal(calls[1].goal.goal,'就按我们刚才的目标继续');
  assert.doesNotMatch(calls[1].systemPrompt,/默认输出使用以下 Markdown 小标题/);
  const sequence=service.list(alice.id,'message').filter(item=>item.data.conversation_id===thread.id).sort((a,b)=>a.data.seq-b.data.seq);
  assert.deepEqual(sequence.map(item=>item.data.actor_type),['human','agent','human','agent']);
  assert.equal(sequence[3].data.trigger_id,second.id);
  assert.equal(store.list('task').filter(task=>task.data.agent_chat_draft_conversation_id).length,0);
  assert.equal(service.list(alice.id,'notification').filter(item=>item.data.target_id===first.task_id).length,0);
  const draft=command(alice,'agent.chat.draft',{id:thread.id,goal:'形成首页结构方案'});
  assert.equal(store.get(draft.id).data.status,'draft');
  assert.equal(store.get(draft.id).data.agent_chat_draft_conversation_id,thread.id);
  assert.equal(store.get(draft.id).data.goal,'形成首页结构方案');
});

test('子 Agent 会话隔离、模型授权与同一会话的待回复顺序',t=>{
  const {store,alice,bob,command}=setup(t);
  const thread=command(alice,'agent.chat.create',{system:'explore'});
  assert.throws(()=>command(bob,'agent.chat.send',{id:thread.id,text:'偷看',model_consent:true}),{code:'NOT_FOUND'});
  assert.throws(()=>command(alice,'agent.chat.send',{id:thread.id,text:'问题'}),{code:'CONSENT_REQUIRED'});
  assert.equal(store.list('message').length,0);
  command(alice,'agent.chat.send',{id:thread.id,text:'第一个问题',model_consent:true});
  assert.throws(()=>command(alice,'agent.chat.send',{id:thread.id,text:'第二个问题',model_consent:true}),{code:'AGENT_REPLY_PENDING'});
  assert.equal(store.list('message').length,1);
  assert.throws(()=>command(bob,'agent.chat.draft',{id:thread.id,goal:'越权'}),{code:'NOT_FOUND'});
});

test('五个 Agent 各自保留独立会话，历史会话可以继续发送',async t=>{
  const {store,service,provider,alice,command}=setup(t);
  const first=command(alice,'agent.chat.create',{system:'advise'});
  const other=command(alice,'agent.chat.create',{system:'execute'});
  const sent=command(alice,'agent.chat.send',{id:first.id,text:'分析首页方案',model_consent:true});
  await new Runtime(store,provider).tick();
  command(alice,'agent.chat.send',{id:first.id,text:'继续刚才的话题',model_consent:true});
  const threads=service.list(alice.id,'conversation').filter(item=>item.data.kind==='agent');
  assert.deepEqual(new Set(threads.map(item=>item.data.system)),new Set(['advise','execute']));
  assert.equal(service.list(alice.id,'message').filter(item=>item.data.conversation_id===other.id).length,0);
  assert.equal(store.get(sent.task_id).data.system,'advise');
});
