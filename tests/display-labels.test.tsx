import test from 'node:test';
import assert from 'node:assert/strict';
import {renderToStaticMarkup} from 'react-dom/server';
import {displayTitle,entityTitle,markdownExcerpt,displayAnchor,displayError} from '../app/v28/core/display-labels';
import {Item,Content} from '../app/v28/features/live/ui';
import {text,ref,type Entity,type Snapshot} from '../app/v28/features/live/types';
import {setPage2Runtime,getPage2State,fetchContract,createPage2Task} from '../app/v28/features/pages24/api/page2-api';
import {launchWithSkill} from '../app/v28/features/pages24/api/skill-launch';

const id='db4109c2-5c97-48f4-a80a-646bd6380231';
const entity=(type:string,data:Entity['data']):Entity=>({id,type,owner:'owner',space:null,visibility:'private',version:1790485382411,created:'2026-09-27T04:00:00Z',updated:'2026-09-27T04:00:00Z',data});

test('system identifiers and old generated fixture suffixes have readable labels',()=>{
 assert.equal(displayTitle(id),'未命名内容');
 assert.equal(displayTitle('20260927123456'),'20260927123456');
 assert.equal(displayTitle('延迟选择验收 1790485382411'),'延迟选择验收');
 assert.equal(displayTitle('延迟选择验收 1790485382411C'),'延迟选择验收');
 assert.equal(entityTitle(entity('skill',{title:id})),'工具');
 assert.equal(entityTitle(entity('document',{})),'文档');
 assert.equal(displayAnchor('line:12'),'第 12 行');
 assert.doesNotMatch(displayError('无法读取 '+id),new RegExp(id));
 assert.equal(displayError('Failed to fetch'),'网络连接失败，请检查网络后重试');
 assert.doesNotMatch(displayTitle('语音-1790485382411.m4a'),/1790485382411/);
});

test('meaningful user numbers and original stored names remain intact',()=>{
 for(const title of ['电话 13800138000','订单 1790485382411234','2026-09-27 周报','金额 12345.67 元','模型 GPT-5','测试订单 9876543210123456','验收订单 1790485382411','测试报告 1790485382411'])assert.equal(displayTitle(title),title);
 const item=entity('skill',{title:'延迟选择验收 1790485382411'});
 assert.equal(entityTitle(item),'延迟选择验收');
 assert.equal(text(item,'title'),'延迟选择验收 1790485382411');
 assert.deepEqual(ref(item),{id,version:1790485382411});
});

test('Markdown card excerpts show readable text without markup or unsafe HTML',()=>{
 assert.equal(markdownExcerpt('# 计划\n\n**重点**：\n\n- 完成任务\n- [查看资料](https://example.com)'),'计划 重点： 完成任务 查看资料');
 assert.equal(markdownExcerpt('<script>alert(1)</script>\n\n![截图](https://example.com/tracker.png)'),'截图');
 assert.equal(markdownExcerpt('电话 13800138000，金额 12345.67'),'电话 13800138000，金额 12345.67');
});

test('shared list items never render internal optimistic versions or identifier names',()=>{
 const html=renderToStaticMarkup(<Item item={entity('task',{title:'延迟选择验收 1790485382411',status:'draft'})}/>);
 assert.match(html,/延迟选择验收/);assert.doesNotMatch(html,/1790485382411/);
});

test('library projection cleans labels but preserves source identities and task routing',async()=>{
 const tool=entity('skill',{title:'延迟选择验收 1790485382411',kind:'Skill',system:'create',status:'draft',instructions:'# 步骤\n\n**整理**真实资料'});
 const document={...entity('document',{title:id,content:'# 计划\n\n**重点**',status:'active'}),id:'document-id'};
 const calls:{action:string;input:Record<string,unknown>}[]=[];
 const snapshot={user:{id:'owner',name:'本人',handle:'qa'},objects:{skill:[tool],document:[document],knowledge:[],task:[],memory:[],outcome:[],tool_use:[],friend:[],resource:[]}} as unknown as Snapshot;
 setPage2Runtime(snapshot,async(action,input)=>{calls.push({action,input});return {id:'new-task'}});
 try{
  const data=getPage2State().data;
  assert.equal(data.capabilities?.[0].id,id);
  assert.equal(data.capabilities?.[0].title,'延迟选择验收');
  assert.equal(data.documents?.[0].name,'文档');
  assert.equal(data.documents?.[0].excerpt,'计划 重点');
  assert.equal(data.skills?.[0].name,id);
  const contract=await fetchContract(id,'整理资料');
  assert.equal(contract?.skill?.name,id);
  assert.match(contract?.constraints||'',/# 步骤/);
  await createPage2Task({title:'任务名称',brief:'整理资料',agent:'create',knowledgeIds:['document-id']});
  assert.deepEqual(calls[0].input.source_refs,[{id:'document-id',version:1790485382411}]);
  assert.equal(tool.data.title,'延迟选择验收 1790485382411');
 }finally{setPage2Runtime(null,null)}
});

test('same displayed capability names still launch the selected original tool',async()=>{
 const first=entity('skill',{title:'延迟选择验收 1790485382411A',system:'create',status:'active',instructions:'第一项的独立说明'});
 const second={...entity('skill',{title:'延迟选择验收 1790485382411B',system:'execute',status:'active',instructions:'第二项的独立说明'}),id:'second-tool'};
 const snapshot={user:{id:'owner'},objects:{skill:[first,second],document:[],knowledge:[],task:[],memory:[],outcome:[],tool_use:[],friend:[],resource:[]}} as unknown as Snapshot;
 setPage2Runtime(snapshot,async()=>({id:'new-task'}));
 try{
  assert.equal(getPage2State().data.capabilities?.[0].title,getPage2State().data.capabilities?.[1].title);
  const result=await launchWithSkill({snapshot},second.id);
  assert.equal(result.ok,true);assert.equal(result.system,'execute');
  assert.match(result.prompt||'',/第二项的独立说明/);
  assert.doesNotMatch(result.prompt||'',/第一项的独立说明|1790485382411|second-tool/);
 }finally{setPage2Runtime(null,null)}
});


test('structured execution metadata hides identities without changing user text or source data',()=>{
 const data={id,version:1790485382411,output_hash:'a'.repeat(64),checks:{task_id:id,order_number:'20260927123456',status:'已核对'}};
 const html=renderToStaticMarkup(<Content value={data}/>);
 assert.doesNotMatch(html,/1790485382411|output_hash|task_id|db4109c2/);assert.match(html,/20260927123456/);
 assert.equal(data.id,id);assert.equal(data.checks.task_id,id);
 assert.match(renderToStaticMarkup(<Content value={'订单 20260927123456'}/>),/20260927123456/);
});
