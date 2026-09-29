import test from 'node:test';
import assert from 'node:assert/strict';
import {Store} from '../../server/elfred/store.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {captureMemories} from '../../server/elfred/memory-learning.mjs';
import {CONDITIONS,needsJevVerdict,registerJevVerdict,jevCommand,tickJev,jevUsage} from '../../server/elfred/jev-verdict/index.mjs';

const ORIGINAL='我平时写方案喜欢先给结论，再补依据。';
const INFERRED='用户偏好先给结论再补依据的方案写法';

function setup(t,jev='configured'){
 const store=new Store(':memory:');t.after(()=>store.close());
 const service=new Service(store,{status:()=>({configured:true,jev})}),user=authenticate(store,'jev-owner-'+Math.random().toString(36).slice(2,8),'jev-password-1',true,'本人').user;
 service.initialize(user);
 const memory=store.add('memory',user.id,{content:INFERRED,source_quote:ORIGINAL,group:'偏好',scope:'owner',risk:'low',status:'learned',alignment:'hypothesis',claim_type:'hypothesis',learning_mode:'automatic_low_risk',source_refs:[],evidence:[]});
 return {store,service,user,memory,provider:{status:()=>({configured:true,jev}),judge:async()=>{throw new Error('没有判定就被调用了');}}};
}

/** 假的 Jev：按给的判定造一份合法的判定回执（含用量）。 */
function judgeWith(statuses,{usage={input_tokens:1200,output_tokens:80,total_tokens:1280}}={}){
 return async({context})=>({
  output:JSON.stringify({results:[{id:context[0].ref.id,checks:CONDITIONS.map((condition,index)=>({condition,status:statuses[index],quote:statuses[index]==='satisfied'?ORIGINAL:'',confidence:0.9}))}]}),
  output_hash:'h',provider_operation_id:'op_jev_1',model:'jev-latest',usage,cost_status:'unreconciled',provider:'typesafe-jev',
 });
}

test('自动学到的理解（含原话照抄）要核对，手工写入的与方法经验不占用 Jev',async t=>{
 const e=setup(t);
 assert.equal(needsJevVerdict({data:{content:ORIGINAL,source_quote:ORIGINAL,claim_type:'fact',origin:'owner_confirmed'}}),false);
 assert.equal(needsJevVerdict({data:{content:ORIGINAL,source_quote:ORIGINAL,learning_mode:'automatic_low_risk'}}),true);
 assert.equal(needsJevVerdict({data:{content:INFERRED,source_quote:ORIGINAL,claim_type:'hypothesis'}}),true);
 const first=registerJevVerdict(e.store,e.user.id,e.memory);
 assert.equal(first.status,'pending');
 const second=registerJevVerdict(e.store,e.user.id,e.memory);
 assert.equal(second.id,first.id);
 assert.equal(e.store.list('jev_request').length,1);
});

test('Jev 没配置就不判定，机会留着而不是假装判过',async t=>{
 const e=setup(t,'not_configured');
 registerJevVerdict(e.store,e.user.id,e.memory);
 const provider={status:()=>({jev:'not_configured'}),judge:async()=>{throw new Error('不该调用');}};
 assert.equal(await tickJev(e.store,provider,{}),null);
 assert.equal(e.store.list('jev_request')[0].data.status,'pending');
 assert.equal(jevUsage(e.store,e.user.id).used,false);
});

test('Jev 明确说这条理解超出原话：降级为待本人确认，回执带用量',async t=>{
 const e=setup(t);
 registerJevVerdict(e.store,e.user.id,e.memory);
 const provider={status:()=>({jev:'configured'}),judge:judgeWith(['satisfied','unsatisfied','satisfied'])};
 await tickJev(e.store,provider,{},async()=>{throw new Error('不该自己发请求');});
 const memory=e.store.get(e.memory.id);
 assert.equal(memory.data.jev_verdict,'unsupported');
 assert.equal(memory.data.status,'pending_confirmation');
 assert.equal(memory.data.alignment,'insufficient');
 assert.equal(memory.data.jev.usage.total_tokens,1280);
 assert.equal(memory.data.jev.run_id,'op_jev_1');
 assert.equal(e.store.list('jev_request')[0].data.status,'done');
 const usage=jevUsage(e.store,e.user.id);
 assert.equal(usage.used,true);
 assert.match(usage.evidence,/1 条理解（合计 1280 tokens）/);
});

test('三条条件都满足：只记判定，不擅自把理解升级成事实',async t=>{
 const e=setup(t);
 registerJevVerdict(e.store,e.user.id,e.memory);
 const provider={status:()=>({jev:'configured'}),judge:judgeWith(['satisfied','satisfied','satisfied'])};
 await tickJev(e.store,provider,{});
 const memory=e.store.get(e.memory.id);
 assert.equal(memory.data.jev_verdict,'supported');
 assert.equal(memory.data.status,'learned');
 assert.equal(memory.data.alignment,'hypothesis');
});

test('判定没覆盖全部条件时如实报错，不改这条理解',async t=>{
 const e=setup(t);
 registerJevVerdict(e.store,e.user.id,e.memory);
 const provider={status:()=>({jev:'configured'}),judge:async()=>({output:JSON.stringify({results:[{id:e.memory.id,checks:[{condition:CONDITIONS[0],status:'satisfied',quote:ORIGINAL,confidence:0.9}]}]}),provider_operation_id:'op_jev_2',model:'jev-latest',usage:{input_tokens:10,output_tokens:5,total_tokens:15}})};
 await tickJev(e.store,provider,{});
 const memory=e.store.get(e.memory.id);
 assert.equal(memory.data.jev,undefined);
 assert.equal(memory.data.status,'learned');
 const request=e.store.list('jev_request')[0];
 assert.equal(request.data.status,'failed');
 assert.match(request.data.result.reason,/条件数量对不上/);
});

test('记忆从对话里自动学到时就已经排好核对，命令可手动重判',async t=>{
 const e=setup(t);
 // 一段话里有四条长期信息：前三条会被原话照抄地记下（不需要核对），第四条由模型改写成理解。
 const sentences=['我平时写方案喜欢先给结论，再补依据。','我通常不喜欢一次给太多背景说明。','我习惯把风险单独列一段。','我希望以后的方案都标出待确认项。'];
 const source=e.store.add('knowledge',e.user.id,{title:'对话',content:sentences.join('')});
 const saved=captureMemories(e.store,e.user.id,{text:sentences.join(''),system:'create',source,proposals:[{content:'用户希望方案里标出待确认项',quote:sentences[3],group:'偏好'}]});
 const inferred=saved.find(item=>item.data.content==='用户希望方案里标出待确认项');
 assert.ok(inferred,'模型改写出来的理解要落库');
 assert.notEqual(inferred.data.content,inferred.data.source_quote);
 // 自动学到（低风险直接生效）的每条都排一次核对；需要本人确认的高风险记忆不用再花这份调用。
 const autoLearned=saved.filter(item=>item.data.learning_mode==='automatic_low_risk');
 assert.ok(autoLearned.length>=2);
 assert.equal(e.store.list('jev_request').length,autoLearned.length);
 const request=e.store.list('jev_request').find(item=>item.data.memory_id===inferred.id);
 assert.ok(request);
 const retry=jevCommand(e.store,e.user.id,'memory.judge',{id:inferred.id});
 assert.equal(retry.status,'pending');
});
