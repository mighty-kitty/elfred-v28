import test from 'node:test';
import assert from 'node:assert/strict';
import {Store,id} from '../../server/elfred/store.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {Runtime} from '../../server/elfred/runtime.mjs';
import {toolActivity} from '../../server/elfred/tool-parameters.mjs';
function setup(t){const store=new Store(':memory:');t.after(()=>store.close());const calls=[],provider={status:()=>({configured:true}),generate:async input=>{calls.push(input);return {output:input.goal.phase==='review'?'{"decision":"satisfied","issues":[]}':'可核对成果',usage:{total_tokens:10}}}},service=new Service(store,provider),runtime=new Runtime(store,provider),u=authenticate(store,'parameter-user','test-parameter-password',true,'本人').user;service.initialize(u);const cmd=(a,i)=>service.command(u.id,id(),a,i),ref=o=>({id:o.id,version:store.get(o.id).version});const input={title:'结构化写作',instructions:'依据主题为读者撰写文稿',system:'create',parameters:[{name:'主题',required:true},{name:'读者',default_value:'初学者'}]},tool=cmd('tool.save',input);cmd('tool.activate',ref(tool));return {store,calls,runtime,cmd,ref,u,tool,input};}
test('工具必填与版本校验，输入冻结于任务，不改变模板或长期记忆',t=>{
 const {store,cmd,ref,tool,input}=setup(t),version=store.get(tool.id).data.version_id;assert.throws(()=>cmd('tool.use',{id:tool.id,version_id:version}),{code:'PARAMETER_REQUIRED'});assert.throws(()=>cmd('tool.use',{id:tool.id,version_id:store.get(tool.id).data.version_id,parameters:{主题:'说明',未定义:'越界'}}),{code:'INVALID_PARAMETERS'});
 const result=cmd('tool.use',{id:tool.id,version_id:version,parameters:{主题:'权限边界'}}),task=store.get(result.task_id);assert.deepEqual(task.data.parameter_values,{主题:'权限边界',读者:'初学者'});assert.equal(store.list('memory').length,0);assert.equal(store.get(tool.id).data.uses,0);
 cmd('tool.save',{...input,...ref(tool),instructions:'新的方法',parameters:[{name:'新的必填',required:true}]});cmd('tool.activate',ref(tool));assert.throws(()=>cmd('tool.use',{id:tool.id,version_id:version,parameters:{主题:'旧表单'}}),{code:'VERSION_CONFLICT'});assert.equal(store.get(task.id).data.skill_version_id,version);assert.equal(store.get(task.id).data.parameter_values.主题,'权限边界');
});
test('工具熟练与闲置分开，有真实使用及验收证据，归档不降级',async t=>{
 const {store,calls,runtime,cmd,ref,tool,u}=setup(t);assert.throws(()=>cmd('tool.governance',{...ref(tool),confirm:true,mastery:'proficient'}),{code:'EVIDENCE_REQUIRED'});
 for(let n=0;n<2;n++){const use=cmd('tool.use',{id:tool.id,version_id:store.get(tool.id).data.version_id,parameters:{主题:'任务'+n}}),task={id:use.task_id};cmd('task.confirm',{...ref(task),confirm:true,model_consent:true});cmd('run.start',ref(task));await runtime.tick();cmd('task.accept',{...ref(task),accept:true});}
 cmd('tool.governance',{...ref(tool),confirm:true,mastery:'proficient',idle_days:30});const saved=store.get(tool.id);assert.equal(saved.data.uses,2);assert.equal(saved.data.mastery_evidence.accepted_task_ids.length,2);assert.equal(toolActivity(saved,Date.parse(saved.data.last_used_at)+31*86400000),'idle');assert.equal(saved.data.mastery,'proficient');cmd('tool.archive',ref(tool));cmd('tool.activate',ref(tool));assert.equal(store.get(tool.id).data.mastery,'proficient');assert.throws(()=>cmd('tool.governance',{...ref(tool),confirm:true,mastery:'unrated'}),{code:'MASTERY_PRESERVED'});assert.match(JSON.stringify(calls[0]),/初学者/);
});
test('缺失所见版本拒绝，八项合法输入独立保存而不撑爆目标',t=>{
 const {store,cmd,ref,tool,input}=setup(t);assert.throws(()=>cmd('tool.use',{id:tool.id,parameters:{主题:'未带版本'}}),{code:'VERSION_CONFLICT'});const parameters=Array.from({length:8},(_,i)=>({name:'项目'+i,required:true}));cmd('tool.save',{...input,...ref(tool),parameters});cmd('tool.activate',ref(tool));const values=Object.fromEntries(parameters.map(p=>[p.name,'内'.repeat(1000)])),created=cmd('tool.use',{id:tool.id,version_id:store.get(tool.id).data.version_id,parameters:values});assert.equal(store.get(created.task_id).data.parameter_values.项目7.length,1000);assert.ok(store.get(created.task_id).data.goal.length<8000);
});
test('组合工具保留版本和步骤依赖，将本次输入交给指定系统，最后由主责汇总',async t=>{
 const {store,cmd,ref,tool,input,runtime,calls}=setup(t);const workflow=[{id:'research',system:'explore',goal:'整理证据',depends:[]},{id:'decide',system:'advise',goal:'比较方案',depends:['research']}];cmd('tool.save',{...input,...ref(tool),workflow});cmd('tool.activate',ref(tool));const oldVersion=store.get(tool.id).data.version_id,use=cmd('tool.use',{id:tool.id,version_id:oldVersion,parameters:{主题:'材料比较'}}),task={id:use.task_id};assert.equal(store.get(task.id).data.status,'draft');assert.equal(calls.length,0);cmd('task.collaboration',{...ref(task),confirm:true,steps:store.get(task.id).data.collaboration_steps.map(({parameter_values,...step})=>step)});cmd('task.confirm',{...ref(task),confirm:true,model_consent:true});cmd('run.start',ref(task));await runtime.tick();assert.equal(calls[0].goal.parameters.主题,'材料比较');assert.equal(calls[1].goal.collaboration_evidence.length,1);assert.equal(calls[2].goal.collaboration_evidence.length,2);assert.equal(store.get(task.id).data.skill_version_id,oldVersion);
 const five=Array.from({length:5},(_,i)=>({id:'step-'+i,system:'explore',goal:'整理一项证据',depends:[]}));cmd('tool.save',{...input,...ref(tool),workflow:five});cmd('tool.activate',ref(tool));const draft=cmd('tool.use',{id:tool.id,version_id:store.get(tool.id).data.version_id,parameters:{主题:'五步组合'}});assert.equal(store.get(draft.task_id).data.stop.maxUnits,7000);assert.equal(store.get(draft.task_id).data.status,'draft');
 assert.throws(()=>cmd('tool.save',{...input,...ref(tool),workflow:[{id:'bad',system:'explore',goal:'依赖自己',depends:['bad']}]}),{code:'INVALID_WORKFLOW'});
});
test('工具权限卡按版本保存，外部服务不得在工具创建时直接开放',t=>{
 const {store,cmd,ref,tool,input}=setup(t);
 assert.throws(()=>cmd('tool.save',{...input,...ref(tool),permissions:{read_scope:'本次文件',tool_scope:'已授权工具',external_access:true,confirm_steps:'发布前确认'}}),{code:'EXTERNAL_ACCESS_UNAVAILABLE'});
 cmd('tool.save',{...input,...ref(tool),permissions:{read_scope:'本次文件',tool_scope:'已授权工具',external_access:false,confirm_steps:'发布前确认'}});
 const version=store.get(store.get(tool.id).data.version_id);
 assert.equal(version.data.permissions.read_scope,'本次文件');
 const use=cmd('tool.test',{id:tool.id,version_id:version.id,parameters:{主题:'首页'}});
 assert.match(store.get(use.task_id).data.constraints,/发布前确认/);
});
test('Mini App 可从文字描述发起页面生成，内部任务不进入公开搜索',t=>{
 const {store,cmd}=setup(t);
 assert.throws(()=>cmd('tool.generate',{purpose:'整理采访',source:'采访记录',result:'摘要',confirm:true}),{code:'CONSENT_REQUIRED'});
 const result=cmd('tool.generate',{purpose:'整理采访',source:'采访记录',result:'摘要',confirm:true,model_consent:true});
 const task=store.get(result.task_id);
 assert.equal(task.data.status,'queued');
 assert.equal(task.data.internal_tool_generation,true);
 assert.equal(task.data.internal_search,true);
 assert.match(task.data.goal,/单文件 Mini App/);
});
