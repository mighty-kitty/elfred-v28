import test from 'node:test';
import assert from 'node:assert/strict';
import {Store} from '../../server/elfred/store.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {dependencyHealth} from '../../server/elfred/dependency-health.mjs';

function setup(t){
 const store=new Store(':memory:');t.after(()=>store.close());
 const service=new Service(store,{status:()=>({configured:false,jev:'unconfigured'})}),user=authenticate(store,'deps-owner','deps-password-1',true,'本人').user;
 service.initialize(user);
 const provider={status:()=>({configured:false,jev:'unconfigured'})};
 return {store,service,user,provider};
}

const okFetcher=(urls=[])=>async(url)=>{
 urls.push(String(url));
 return {ok:true,text:async()=>JSON.stringify({status:'ok'})};
};

test('上游服务没配地址就如实说尚未配置，不影响应用自己的记忆',async t=>{
 const e=setup(t);
 const result=await dependencyHealth(e.store,e.provider,e.user.id,{});
 assert.equal(result.memory.ok,true);
 for(const key of ['emos','skill_foundry','gateway']){
  assert.equal(result[key].ok,false);
  assert.match(result[key].reason,/尚未配置/);
 }
 assert.equal(result.allGreen,false);
});

test('三个服务配了地址并可达时全绿，探测并发跑',async t=>{
 const e=setup(t),urls=[];
 const config={ELFRED_MEMORY_HUB_URL:'http://127.0.0.1:8200',ELFRED_SKILL_FOUNDRY_URL:'http://127.0.0.1:8765',ELFRED_PA_GATEWAY_URL:'http://127.0.0.1:8790'};
 const result=await dependencyHealth(e.store,e.provider,e.user.id,config,okFetcher(urls));
 assert.equal(result.allGreen,true);
 assert.equal(result.emos.ok,true);
 assert.equal(result.skill_foundry.ok,true);
 assert.equal(result.gateway.ok,true);
 assert.deepEqual(urls.sort(),['http://127.0.0.1:8200/health','http://127.0.0.1:8765/v1/elfred/health','http://127.0.0.1:8790/health']);
});

test('一个上游挂了只影响它自己，其余状态照报',async t=>{
 const e=setup(t);
 const config={ELFRED_MEMORY_HUB_URL:'http://127.0.0.1:8200',ELFRED_SKILL_FOUNDRY_URL:'http://127.0.0.1:8765'};
 const fetcher=async(url)=>url.includes('8765')
  ?({ok:false,text:async()=>''})
  :({ok:true,text:async()=>'{"status":"ok"}'});
 const result=await dependencyHealth(e.store,e.provider,e.user.id,config,fetcher);
 assert.equal(result.emos.ok,true);
 assert.equal(result.skill_foundry.ok,false);
 assert.match(result.skill_foundry.reason,/不可达/);
 assert.match(result.gateway.reason,/尚未配置/);
 assert.equal(result.allGreen,false);
});

test('拒绝把非回环 http 地址当作上游：不探测、按未配置处理',async t=>{
 const e=setup(t),urls=[];
 const result=await dependencyHealth(e.store,e.provider,e.user.id,{ELFRED_MEMORY_HUB_URL:'http://example.com'},okFetcher(urls));
 assert.equal(result.emos.ok,false);
 assert.match(result.emos.reason,/不合规/);
 assert.equal(urls.length,0);
});

test('老部署把状态挂在独立服务上时，没有直连地址的项走它一次',async t=>{
 const e=setup(t),urls=[];
 const fetcher=async(url)=>{
  urls.push(String(url));
  return {ok:true,text:async()=>JSON.stringify({emos:{ok:true,reason:'独立记忆服务可达',impact:'记忆中枢已连接'},skill_foundry:{ok:false,reason:'独立能力服务不可达',impact:'当前仍使用应用内能力'}})};
 };
 const result=await dependencyHealth(e.store,e.provider,e.user.id,{ELFRED_PA_GATEWAY_URL:'http://127.0.0.1:8790',ELFRED_PAGE2_API_URL:'http://127.0.0.1:8000'},fetcher);
 assert.equal(urls.filter(u=>u.endsWith('/health/deps')).length,1);
 assert.equal(result.emos.ok,true);
 assert.equal(result.skill_foundry.ok,false);
 assert.match(result.skill_foundry.reason,/不可达/);
 assert.equal(result.gateway.ok,true);
});
