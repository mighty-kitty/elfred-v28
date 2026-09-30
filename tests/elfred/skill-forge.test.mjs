import test from 'node:test';
import assert from 'node:assert/strict';
import {Store} from '../../server/elfred/store.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {forgeSkills,forgeUsage,skillForgeCommand,tickSkillForge} from '../../server/elfred/skill-forge/index.mjs';

const json = (body, status = 200) => ({ ok: status < 400, status, text: async () => JSON.stringify(body) });

function setup(t){
 const store=new Store(':memory:');t.after(()=>store.close());
 const service=new Service(store,{status:()=>({configured:true})}),user=authenticate(store,'forge-owner','forge-password-1',true,'本人').user;
 service.initialize(user);
 const task=store.add('task',user.id,{title:'把会议记录整理成三条待办',goal:'把会议记录整理成三条待办，标出负责人和截止时间',system:'execute',status:'completed'});
 store.add('outcome',user.id,{task_id:task.id,verdict:'accepted',criteria:'可核对'});
 return {store,service,user,task};
}

/** 造一个"像 Foundry"的假服务：只实现我们用到的四条路径。 */
function foundryFetcher({ skills = [], detail = null, failList = false } = {}) {
  const urls = [];
  const fetcher = async (url) => {
    const path = new URL(url).pathname;
    urls.push(path);
    if (path.endsWith('/events/batch')) return json({ total: 1, counts: { synced: 1 } });
    if (path.endsWith('/skills/passive/scan')) return json({ status: 'completed', draftsCreated: skills.length });
    if (path === '/v1/elfred/skills') {
      if (failList) return json({ detail: 'boom' }, 500);
      return json({ total: skills.length, skills });
    }
    const match = path.match(/\/v1\/elfred\/skills\/(.+)$/);
    if (match) return json(detail);
    throw new Error('unexpected path ' + path);
  };
  fetcher.urls = urls;
  return fetcher;
}

const config = { ELFRED_SKILL_FOUNDRY_URL: 'http://127.0.0.1:8765' };
const foundrySkill = { skill_id: 'skill_demo_1', slug: 'meeting-notes', name: '会议记录整理成三条待办', description: '把会议记录整理成三条待办', status: 'draft', current_version_id: 'skillver_1' };
const foundryDetail = { ...foundrySkill, current_version: { version_id: 'skillver_1', version: '0.1.0', skill_markdown: '---\nname: meeting-notes\n---\n\n## When to Use\n整理会议记录时。\n' } };

test('没配地址就如实说未配置，不假装生成',async t=>{
 const e=setup(t);
 const result=await forgeSkills(e.store,e.user.id,{}, { config: {}, fetcher: foundryFetcher() });
 assert.equal(result.ok,false);
 assert.match(result.reason,/未配置/);
 assert.equal(e.store.list('skill').length,0);
});

test('没有已验收成果时不硬造：让用户先做成一件事',async t=>{
 const store=new Store(':memory:');t.after(()=>store.close());
 const service=new Service(store,{status:()=>({configured:true})}),user=authenticate(store,'forge-empty','forge-password-2',true,'本人').user;
 service.initialize(user);
 const result=await forgeSkills(store,user.id,{}, { config, fetcher: foundryFetcher() });
 assert.equal(result.ok,false);
 assert.match(result.reason,/已验收的成果/);
});

test('喂事件 → 拉草稿 → 落成我们的能力卡，并标出来源与出处',async t=>{
 const e=setup(t),fetcher=foundryFetcher({ skills: [foundrySkill], detail: foundryDetail });
 const result=await forgeSkills(e.store,e.user.id,{}, { config, fetcher });
 assert.equal(result.ok,true);
 assert.equal(result.imported.length,1);
 assert.ok(fetcher.urls.some((u)=>u.endsWith('/events/batch')));
 assert.ok(fetcher.urls.some((u)=>u.endsWith('/skills/passive/scan')));
 const skill=e.store.list('skill').find((item)=>item.owner===e.user.id);
 assert.ok(skill);
 assert.equal(skill.data.source,'foundry');
 assert.equal(skill.data.foundry.skill_id,'skill_demo_1');
 assert.match(String(skill.data.instructions),/When to Use/);
 assert.equal(skill.data.status,'active');
 const usage=forgeUsage(e.store,e.user.id);
 assert.equal(usage.used,true);
 assert.match(usage.evidence,/已从它导入 1 张/);
});

test('同一张草稿不会重复导入；列表挂了如实报错',async t=>{
 const e=setup(t),fetcher=foundryFetcher({ skills: [foundrySkill], detail: foundryDetail });
 await forgeSkills(e.store,e.user.id,{}, { config, fetcher });
 const again=await forgeSkills(e.store,e.user.id,{}, { config, fetcher });
 assert.equal(again.ok,false);
 assert.equal(e.store.list('skill').filter((item)=>item.owner===e.user.id).length,1);
 const broken=await forgeSkills(e.store,e.user.id,{ feed:false }, { config, fetcher: foundryFetcher({ failList: true }) });
 assert.equal(broken.ok,false);
 assert.match(broken.reason,/读 Foundry 技能列表失败/);
});

test('命令只登记请求、运行时循环执行并写回结果',async t=>{
 const e=setup(t),fetcher=foundryFetcher({ skills: [foundrySkill], detail: foundryDetail });
 const first=skillForgeCommand(e.store,e.user.id,'skill.forge',{});
 assert.equal(first.status,'pending');
 const second=skillForgeCommand(e.store,e.user.id,'skill.forge',{});
 assert.equal(second.id,first.id);
 const request=e.store.get(first.id);
 assert.equal(request.data.status,'pending');
 await tickSkillForge(e.store,{status:()=>({configured:true})},config,fetcher);
 const done=e.store.get(first.id);
 assert.equal(done.data.status,'done');
 assert.equal(done.data.result.ok,true);
});
