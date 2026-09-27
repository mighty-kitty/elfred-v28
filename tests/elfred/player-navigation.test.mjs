import test from 'node:test';
import assert from 'node:assert/strict';
import {Store,id} from '../../server/elfred/store.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {Runtime} from '../../server/elfred/runtime.mjs';
import {ModelProvider} from '../../server/elfred/providers.mjs';
import {playerLogs} from '../../server/elfred/player-logs.mjs';
import {dependencyHealth} from '../../server/elfred/dependency-health.mjs';

function fixture(t,provider){
 const store=new Store(':memory:'),service=new Service(store,provider);
 const a=authenticate(store,'player-a','fixture-password',true,'A').user,b=authenticate(store,'player-b','fixture-password',true,'B').user;
 service.initialize(a);service.initialize(b);t.after(()=>store.close());
 const command=(user,action,input)=>service.command(user.id,id(),action,input),ref=obj=>({id:obj.id,version:store.get(obj.id).version});
 return {store,service,a,b,command,ref};
}
test('execution logs contain only recorded events, deduplicate receipts and enforce current source permission',t=>{
 const {store,a,b}=fixture(t,new ModelProvider({}));
 const source=store.add('document',a.id,{title:'仅本人资料',content:'私密内容'});
 let run=store.add('run',a.id,{status:'queued',source_refs:[{id:source.id,version:source.version}],plan:{steps:[{id:'work',phase:'work'},{id:'review',phase:'review'}]},receipts:[]});
 assert.deepEqual(playerLogs(store,a.id,run.id).items.map(item=>item.message),['进入执行队列']);
 assert.throws(()=>playerLogs(store,b.id,run.id),{code:'NOT_FOUND'});
 run=store.update(run,{...run.data,status:'running'},a.id);
 run=store.update(run,{...run.data,receipts:[{id:id(),step_id:'work',phase:'work',at:new Date().toISOString(),output:'不得暴露正文'}]},a.id);
 run=store.update(run,{...run.data,status:'paused'},a.id);
 const messages=playerLogs(store,a.id,run.id).items.map(item=>item.message);
 assert.deepEqual(messages,['进入执行队列','开始执行','生成成果 · 已记录结果','已暂停']);
 assert.ok(!JSON.stringify(messages).includes('核对结果'));
 store.update(source,{...source.data,content:'已修改'},a.id);
 assert.throws(()=>playerLogs(store,a.id,run.id),{code:'NOT_FOUND'});
});
test('task model changes invalidate prior approval, reject cross-account, frozen or unknown models and reach the runner',async t=>{
 const inputs=[],provider={status:()=>({configured:true,model:'default'}),allowedModels:()=>['default','balanced'],generate:async input=>{inputs.push(input);return {output:'可核对的成果',usage:{total_tokens:5},model:input.model}}};
 const {store,a,b,command,ref}=fixture(t,provider),task=command(a,'task.create',{goal:'整理材料',mode:'compose',review_mode:'single'});
 command(a,'task.confirm',{...ref(task),confirm:true,model_consent:true});
 assert.throws(()=>command(b,'task.model_settings',{...ref(task),model:'balanced',review_mode:'single'}),{code:'NOT_FOUND'});
 assert.throws(()=>command(a,'task.model_settings',{...ref(task),model:'unknown',review_mode:'single'}),{code:'MODEL_NOT_AVAILABLE'});
 command(a,'task.model_settings',{...ref(task),model:'balanced',review_mode:'single'});
 assert.equal(store.get(task.id).data.status,'draft');assert.equal(store.list('approval')[0].data.status,'revoked');
 assert.throws(()=>command(a,'run.start',ref(task)),{code:'INVALID_STATE'});
 command(a,'task.confirm',{...ref(task),confirm:true,model_consent:true});const run=command(a,'run.start',ref(task));
 assert.equal(store.get(run.id).data.version_snapshot.model,'balanced');
 assert.throws(()=>command(a,'task.model_settings',{...ref(task),model:'default',review_mode:'single'}),{code:'INVALID_STATE'});
 await new Runtime(store,provider).tick();assert.equal(inputs[0].model,'balanced');
});
test('a historical skip copied from work is dated when recorded, after the review that caused it',t=>{
 const {store,a}=fixture(t,new ModelProvider({}));
 const work={id:id(),step_id:'work',phase:'work',at:'2026-01-01T01:00:00.000Z'},review={id:id(),step_id:'review',phase:'review',at:'2026-01-01T01:01:00.000Z'};
 let run=store.add('run',a.id,{status:'running',plan:{steps:[]},receipts:[work,review]});
 run=store.update(run,{...run.data,status:'completed',receipts:[work,review,{...work,id:id(),step_id:'repair',phase:'repair',provider:'conditional-skip'}]},a.id);
 const messages=playerLogs(store,a.id,run.id).items.map(item=>item.message);
 assert.ok(messages.indexOf('按反馈修订 · 无需修订，已跳过')>messages.indexOf('核对结果 · 已记录结果'));
 assert.equal(messages.at(-1),'本次执行结束');
});
test('model catalog and generation use server credentials without exposing them',async()=>{
 let request;
 const provider=new ModelProvider({ELFRED_MODEL_BASE_URL:'https://models.example/v1',ELFRED_MODEL_API_KEY:'fixture-private-key',ELFRED_MODEL_NAME:'default'},async(url,init)=>{request={url,init};return new Response(JSON.stringify(url.endsWith('/models')?{data:[{id:'balanced'}]}:{choices:[{message:{content:'结果'},finish_reason:'stop'}],usage:{total_tokens:20}}))});
 const catalog=await provider.models();assert.deepEqual(provider.allowedModels(),['default','balanced']);assert.ok(!JSON.stringify(catalog).includes('fixture-private-key'));
 await provider.generate({model:'balanced',goal:'测试',context:[],maxTokens:4000});assert.equal(JSON.parse(request.init.body).model,'balanced');
});
test('dependency health reports local memory separately, checks remote health and never sends user identity or memories',async t=>{
 const provider=new ModelProvider({}),{store,a}=fixture(t,provider);store.add('memory',a.id,{content:'私密偏好',status:'validated'});
 const local=await dependencyHealth(store,provider,a.id,{});assert.equal(local.memory.count,1);assert.equal(local.memory.ok,true);assert.equal(local.emos.ok,false);
 let headers;
 const remote=await dependencyHealth(store,provider,a.id,{ELFRED_PAGE2_API_URL:'http://127.0.0.1:8000'},async(url,init)=>{headers=init.headers;return new Response(JSON.stringify({emos:{ok:true},skill_foundry:{ok:false}}))});
 assert.equal(remote.emos.ok,true);assert.match(remote.emos.impact,/尚未配置/);assert.deepEqual(headers,{});
 const failed=await dependencyHealth(store,provider,a.id,{ELFRED_PAGE2_API_URL:'https://private:secret@service.example'},()=>{throw new Error('secret')});
 assert.equal(failed.emos.ok,false);assert.ok(!JSON.stringify(failed).includes('secret'));
});
