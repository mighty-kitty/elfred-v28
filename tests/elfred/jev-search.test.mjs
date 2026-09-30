import test from 'node:test';
import assert from 'node:assert/strict';
import {JevProvider} from '../../server/elfred/jev-provider.mjs';
import {ModelProvider} from '../../server/elfred/providers.mjs';
import {Store,id} from '../../server/elfred/store.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {Runtime} from '../../server/elfred/runtime.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {localSearch,parseIntent} from '../../server/elfred/search-engine.mjs';
import {searchJudgment} from '../../server/elfred/search-commands.mjs';
import {semanticPreview} from '../../server/elfred/semantic-search.mjs';
const context=[{ref:{id:'doc',version:1},title:'共创报名',content:'人数上限为五人。'}];
const intent={original:'五人共创报名',conditions:['人数上限为五人']};
function mockFetch(calls,{confidence=0.9,invalid=false,usage={input_tokens:300,output_tokens:50}}={}){
 return async(url,options)=>{const body=JSON.parse(options.body);calls.push({url,options,body});const answers=Object.fromEntries(Object.entries(body.questions).map(([key,q])=>[key,{type:'choice',choice:invalid?'not-an-option':key.endsWith('_evidence')?Object.keys(q.criteria).find(k=>q.criteria[k]==='人数上限为五人。')||'none':'satisfied',confidence,probabilities:{}}]));return new Response(JSON.stringify({model:'jev-test',answers,usage}),{status:200});};
}
function setup(t,provider){const store=new Store(':memory:');t.after(()=>store.close());const user=authenticate(store,'jevtest','jev-isolated-test-password',true,'本人').user;const service=new Service(store,provider);service.initialize(user);const command=(action,input)=>service.command(user.id,id(),action,input);return {store,user,service,command,runtime:new Runtime(store,provider)};}

test('Jev uses official typed endpoint, finite evidence, and independent key',async()=>{
 const calls=[],provider=new ModelProvider({TYPESAFE_API_KEY:'test-secret'},mockFetch(calls));
 assert.equal(provider.status().configured,false);assert.equal(provider.status().jev,'configured');assert.ok(!JSON.stringify(provider.status()).includes('test-secret'));
 const r=await provider.judge({context,intent});assert.equal(calls[0].url,'https://api.typesafe.ai/v1/systemone');assert.equal(calls[0].options.headers.Authorization,'Bearer test-secret');assert.equal(calls[0].body.model,'jev-latest');assert.equal(calls[0].body.questions.q0.type,'choice');assert.ok(!('messages' in calls[0].body));
 assert.equal(r.usage.total_tokens,350);assert.equal(JSON.parse(r.output).results[0].checks[0].quote,'人数上限为五人。');
});
test('Jev low confidence abstains; invalid choice or unknown usage cannot succeed',async()=>{
 const r=await new JevProvider({TYPESAFE_API_KEY:'x'},mockFetch([],{confidence:0.4})).judge({context,intent});assert.equal(JSON.parse(r.output).results[0].checks[0].status,'unknown');
 await assert.rejects(new JevProvider({TYPESAFE_API_KEY:'x'},mockFetch([],{invalid:true})).judge({context,intent}),{code:'PROVIDER_INVALID_OUTPUT'});
 await assert.rejects(new JevProvider({TYPESAFE_API_KEY:'x'},mockFetch([],{usage:{}})).judge({context,intent}),{code:'PROVIDER_USAGE_UNKNOWN'});
 const calls=[];await assert.rejects(new JevProvider({},mockFetch(calls)).judge({context,intent}),{code:'PROVIDER_NOT_CONFIGURED'});assert.equal(calls.length,0);
 await assert.rejects(new JevProvider({TYPESAFE_API_KEY:'x'},mockFetch(calls)).judge({context,intent,maxTokens:1}),{code:'CONTEXT_BUDGET_EXCEEDED'});assert.equal(calls.length,0);
});
test('Jev HTTP failures are not automatically replayed; usage overrun is retained',async()=>{
 let calls=0;await assert.rejects(new JevProvider({TYPESAFE_API_KEY:'x'},async()=>{calls++;return new Response('{}',{status:429})}).judge({context,intent}),{code:'PROVIDER_HTTP_ERROR'});assert.equal(calls,1);
 await assert.rejects(new JevProvider({TYPESAFE_API_KEY:'x'},mockFetch([],{usage:{input_tokens:30000,output_tokens:50}})).judge({context,intent}),e=>e.code==='TOKEN_BUDGET_EXCEEDED'&&e.usage.total_tokens===30050);
});
test('search query identity ignores command transport fields; source updates invalidate judgments',async t=>{
 const calls=[],provider=new ModelProvider({TYPESAFE_API_KEY:'x'},mockFetch(calls)),{store,user,command,runtime}=setup(t,provider);
 const doc=command('document.create',{title:'共创报名.md',content:'人数上限为五人。'}),input={query:'共创报名',conditions:['人数上限为五人']};
 const search=localSearch(store,user.id,input);assert.equal(search.query_id,localSearch(store,user.id,{...input,task_id:'ignored',confirm:true,model_consent:true,provider:'jev'}).query_id);
 const created=command('search.judge',{...input,provider:'jev',query_id:localSearch(store,user.id,input).query_id,candidates:[{id:doc.id,version:1}],confirm:true,model_consent:true});await runtime.tick();
 assert.equal(calls.length,1);const result=searchJudgment(store,user.id,{...input,task_id:created.task_id});assert.equal(result.hits.find(h=>h.id===doc.id).condition_status,'satisfied');
 assert.throws(()=>searchJudgment(store,user.id,{...input,query:'完全不同',task_id:created.task_id}),{code:'QUERY_CHANGED'});
 const current=store.get(doc.id);store.update(current,{...current.data,content:'新报名尚未决定人数。'},user.id);
 assert.throws(()=>searchJudgment(store,user.id,{...input,task_id:created.task_id}),{code:'NOT_FOUND'});
 assert.throws(()=>command('search.judge',{...input,provider:'jev',query_id:search.query_id,candidates:[{id:doc.id,version:1}],confirm:true,model_consent:true}),{code:'CANDIDATES_CHANGED'});
});
test('unconfigured Jev blocks before spending and remains resumable',async t=>{
 const provider=new ModelProvider({}),{store,user,command,runtime}=setup(t,provider);const doc=command('document.create',{title:'报名.md',content:'报名说明'}),search=localSearch(store,user.id,{query:'报名'});
 const created=command('search.judge',{query:'报名',provider:'jev',query_id:search.query_id,candidates:[{id:doc.id,version:1}],confirm:true,model_consent:true});await runtime.tick();
 const task=store.get(created.task_id);assert.equal(task.data.status,'blocked');assert.equal(task.data.units,0);assert.equal(task.data.calls,0);
});
test('natural relative dates and sender names require explicit resolution; plain recall stays unknown',t=>{
 assert.ok(parseIntent('上周张三发的方案').uncertainties.length>=2);assert.equal(parseIntent('上周张三发的方案',{author:'user',after:'2026-09-14T00:00:00Z',before:'2026-09-21T00:00:00Z'}).uncertainties.length,0);
 const {store,user,command}=setup(t,new ModelProvider({}));command('document.create',{title:'方案.md',content:'词面相关并不等于满足完整含义'});
 assert.equal(localSearch(store,user.id,{query:'方案'}).hits[0].condition_status,'unknown');
 command('document.create',{title:'导出.md',content:'本软件不支持导出PDF'});assert.equal(localSearch(store,user.id,{query:'导出',conditions:['支持导出PDF']}).hits[0].condition_status,'unknown');
});
test('追问保留原问题并分别处理限定和偏好',t=>{
 const {store,user,command}=setup(t,new ModelProvider({}));
 const a=command('document.create',{title:'首页方案深圳.md',content:'首页设计方案，深圳团队完成。'});
 const b=command('document.create',{title:'首页方案北京.md',content:'首页设计方案，北京团队完成。'});
 const base=localSearch(store,user.id,{query:'首页方案'});
 assert.ok(base.hits.some(hit=>hit.id===a.id)&&base.hits.some(hit=>hit.id===b.id));
 const narrowed=localSearch(store,user.id,{query:'首页方案',followups:['只看深圳']});
 assert.deepEqual(narrowed.intent.followups,['只看深圳']);
 assert.ok(narrowed.hits.some(hit=>hit.id===a.id));
 assert.ok(!narrowed.hits.some(hit=>hit.id===b.id));
 const semantic=semanticPreview(store,user.id,{query:'首页方案',followups:['只看深圳']});
 assert.ok(semantic.chunks.some(chunk=>chunk.id===a.id));
 assert.ok(!semantic.chunks.some(chunk=>chunk.id===b.id));
 const preferred=localSearch(store,user.id,{query:'首页方案',followups:['更偏深圳']});
 assert.equal(preferred.hits[0].id,a.id);
 assert.throws(()=>localSearch(store,user.id,{query:'首页方案',followups:['a'.repeat(121)]}),{code:'INVALID_INPUT'});
});
