import test from 'node:test';
import assert from 'node:assert/strict';
import {Store} from '../../server/elfred/store.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {memoryHubStatus,syncMemoryHub} from '../../server/elfred/memory-hub.mjs';
import {memoryUsable} from '../../server/elfred/memory-validity.mjs';

function setup(t){
 const store=new Store(':memory:');t.after(()=>store.close());
 const service=new Service(store,{status:()=>({configured:true})}),user=authenticate(store,'hub-owner','hub-password-1',true,'本人').user;
 service.initialize(user);
 const memory=store.add('memory',user.id,{content:'以后讨论排期时先看本周已经确认的事项',scope:'owner',group:'习惯',status:'validated',learning_mode:'owner_confirmed',usage_purpose:'安排日程时先核对已确认事项',source_refs:[],evidence:[]});
 return {store,service,user,memory};
}

/** 造一个"像 EMOS 回执"的响应：字段必须与请求一一对上，否则同步会判失败。 */
const receipt = (payload) => async (url, init) => {
  const body = JSON.parse(init.body);
  return { ok: true, text: async () => JSON.stringify({ id: body.id, revision: body.revision, owner: body.owner, state_hash: body.state_hash }) };
};

test('没配令牌就不推：记忆只留在应用库里，状态如实说未配置',async t=>{
 const e=setup(t);
 await syncMemoryHub(e.store,{},receipt({}));
 assert.equal(e.store.list('memory_bridge').length,0);
 const status=memoryHubStatus(e.store,e.user.id,{});
 assert.equal(status.configured,false);
 assert.equal(status.mode,'local');
 assert.equal(status.pending,0);
});

test('配了地址与令牌：记忆真的推出去，回执对上才记 synced',async t=>{
 const e=setup(t),config={ELFRED_MEMORY_HUB_URL:'http://127.0.0.1:8200',ELFRED_MEMORY_HUB_TOKEN:'x'.repeat(32)};
 assert.equal(memoryUsable(e.store,e.store.get(e.memory.id)),true);
 await syncMemoryHub(e.store,config,receipt({}));
 const events=e.store.list('memory_bridge').filter((item)=>item.data.memory_id===e.memory.id);
 assert.equal(events.length,1);
 assert.equal(events[0].data.status,'synced');
 assert.ok(events[0].data.synced_at);
 const status=memoryHubStatus(e.store,e.user.id,config);
 assert.equal(status.configured,true);
 assert.equal(status.mode,'adapter');
 assert.equal(status.last_synced_at,events[0].data.synced_at);
});

test('回执对不上（少字段 / 版本不符）时不算成功，保留待重试',async t=>{
 const e=setup(t),config={ELFRED_MEMORY_HUB_URL:'http://127.0.0.1:8200',ELFRED_MEMORY_HUB_TOKEN:'x'.repeat(32)};
 const wrong=async()=>({ok:true,text:async()=>JSON.stringify({id:'someone-else',revision:1,owner:'nope',state_hash:'0'})});
 await syncMemoryHub(e.store,config,wrong);
 const events=e.store.list('memory_bridge').filter((item)=>item.data.memory_id===e.memory.id);
 assert.equal(events[0].data.status,'pending');
 assert.equal(events[0].data.attempts,1);
 assert.ok(events[0].data.next_at>0);
});
