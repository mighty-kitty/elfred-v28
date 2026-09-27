import test from 'node:test';
import assert from 'node:assert/strict';
import {Store} from '../../server/elfred/store.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {localSearch,semanticSources} from '../../server/elfred/search-engine.mjs';
import {objectScreen} from '../../app/v28/core/object-screen.ts';

function setup(t){const store=new Store(':memory:');t.after(()=>store.close());const a=authenticate(store,'search-flow-a','search-test-only-password',true,'Alice').user,b=authenticate(store,'search-flow-b','search-test-only-password',true,'Bob').user;return {store,a,b};}
test('最近是排序偏好，不猜测日期或阻止关键词结果；明确日期仍限制范围',t=>{
 const {store,a}=setup(t),old=store.add('knowledge',a.id,{title:'首页设计',content:'五个 Agent 保持原排列'}),recent=store.add('knowledge',a.id,{title:'首页设计',content:'五个 Agent 保持原排列'});
 store.db.prepare('UPDATE objects SET created=?,updated=? WHERE id=?').run('2020-01-01T00:00:00Z','2020-01-01T00:00:00Z',old.id);
 const result=localSearch(store,a.id,{query:'最近的首页设计'});assert.equal(result.status,'complete');assert.equal(result.hits[0].id,recent.id);assert.ok(result.hits.some(h=>h.id===old.id));assert.equal(result.intent.after,null);assert.ok(result.intent.interpretation.some(s=>s.includes('未限定时间')));
 assert.ok(!localSearch(store,a.id,{query:'首页设计',after:'2025-01-01'}).hits.some(h=>h.id===old.id));
 assert.equal(localSearch(store,a.id,{query:'上周本周的首页设计'}).status,'needs_clarification');
});
test('真实附件按文件名及小文本检索，私有文件、撤回消息和离群来源不泄漏',t=>{
 const {store,a,b}=setup(t),file=store.add('attachment',a.id,{name:'产品需求.md',mime:'text/plain',size:18,base64:Buffer.from('初始化说明：问三个问题').toString('base64'),status:'ready'});
 assert.equal(localSearch(store,a.id,{query:'产品需求.md',types:['attachment','document']}).hits[0].id,file.id);
 assert.ok(localSearch(store,a.id,{query:'初始化'}).hits.some(h=>h.id===file.id));assert.equal(localSearch(store,b.id,{query:'产品需求'}).hits.length,0);
 const room=store.add('conversation',a.id,{title:'设计群',kind:'group'},{visibility:'members'});store.join(room.id,a.id);store.join(room.id,b.id);
 store.update(file,{...file.data,access_space:room.id},a.id);
 const message=store.add('message',a.id,{conversation_id:room.id,seq:1,text:'看看这份资料',attachments:[{id:file.id}]},{space:room.id,visibility:'members'});
 store.db.prepare('UPDATE objects SET created=? WHERE id=?').run('2020-01-01T00:00:00Z',file.id);
 let result=localSearch(store,b.id,{query:'产品需求',types:['attachment','document'],space:room.id,author:a.id,after:'2025-01-01'});assert.ok(result.hits.some(h=>h.id===file.id&&h.origin_id===message.id));assert.ok(result.hits.every(h=>h.type!=='message'));
 result=localSearch(store,b.id,{query:'初始化',types:['attachment','document'],space:room.id,author:a.id,after:'2025-01-01'});assert.ok(result.hits.some(h=>h.id===file.id&&h.origin_id===message.id));
 assert.ok(semanticSources(store,b.id,{types:['attachment','document']},result.intent).some(o=>o.id===file.id&&o.search_origin_id===message.id));
 // A fresh upload cannot bypass an older sending message's date or sender.
 store.db.prepare('UPDATE objects SET created=? WHERE id=?').run(new Date().toISOString(),file.id);store.db.prepare('UPDATE objects SET created=? WHERE id=?').run('2020-01-01T00:00:00Z',message.id);
 assert.equal(localSearch(store,b.id,{query:'初始化',types:['attachment','document'],after:'2025-01-01'}).hits.length,0);
 assert.equal(semanticSources(store,b.id,{types:['attachment','document']},{after:'2025-01-01'}).some(o=>o.id===file.id),false);
 store.db.prepare('UPDATE objects SET deleted=1 WHERE id=?').run(message.id);assert.equal(localSearch(store,b.id,{query:'产品需求'}).hits.length,0);
 store.db.prepare('DELETE FROM members WHERE space=? AND user_id=?').run(room.id,b.id);assert.equal(localSearch(store,b.id,{query:'初始化'}).hits.length,0);
});
test('完整标题排在只含一个泛词的结果前；明确排除词不被自动放宽',t=>{
 const {store,a}=setup(t),wanted=store.add('document',a.id,{title:'Elfred 首页设计说明.md',content:'保留原版首页排版'});store.add('document',a.id,{title:'其他设计',content:'其他项目的设计'});
 assert.equal(localSearch(store,a.id,{query:'首页设计说明'}).hits[0].id,wanted.id);assert.equal(localSearch(store,a.id,{query:'首页设计说明',exclude:['首页']}).hits.some(h=>h.id===wanted.id),false);
});
test('限定发送者和群聊时不拿人名或群名当内容关键词；未知身份要求澄清',t=>{
 const {store,a,b}=setup(t),room=store.add('conversation',a.id,{title:'设计群',kind:'group'},{visibility:'members'});store.join(room.id,a.id);store.join(room.id,b.id);
 const target=store.add('message',b.id,{conversation_id:room.id,seq:1,text:'报名说明：三个名额'},{space:room.id,visibility:'members'});store.add('message',b.id,{conversation_id:room.id,seq:2,text:'设计群开会'},{space:room.id,visibility:'members'});
 const result=localSearch(store,a.id,{query:'Bob在设计群发的报名说明'});assert.equal(result.status,'complete');assert.equal(result.hits[0].id,target.id);assert.equal(result.intent.author,b.id);assert.equal(result.intent.space,room.id);
 assert.equal(localSearch(store,a.id,{query:'小林发的报名说明'}).status,'needs_clarification');
});
test('搜索对话打开命中的 Agent 历史和消息，文件打开真实来源页面',()=>{
 const conversation={id:'agent-thread',type:'conversation',data:{kind:'agent',system:'advise'}};
 assert.deepEqual(objectScreen(conversation),{name:'agent',id:'advisor',conversationId:'agent-thread',messageId:undefined});
 assert.deepEqual(objectScreen({id:'agent-message',type:'message',data:{conversation_id:'agent-thread'}},undefined,[conversation]),{name:'agent',id:'advisor',conversationId:'agent-thread',messageId:'agent-message'});
 assert.deepEqual(objectScreen({id:'file',type:'attachment',data:{}},'产品需求'),{name:'search-source',id:'file',anchor:'产品需求'});
 assert.deepEqual(objectScreen({id:'human-message',type:'message',data:{conversation_id:'room'}}),{name:'chat',id:'room',messageId:'human-message'});
});
