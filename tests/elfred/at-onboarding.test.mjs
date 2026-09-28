import test from 'node:test';
import assert from 'node:assert/strict';
import {Store,id} from '../../server/elfred/store.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {ModelProvider} from '../../server/elfred/providers.mjs';
import {Runtime} from '../../server/elfred/runtime.mjs';
function setup(t){const store=new Store(':memory:'),service=new Service(store,new ModelProvider({}));t.after(()=>store.close());const users=['alice','bob'].map(h=>authenticate(store,h,'local-test-password',true,h).user);users.forEach(u=>service.initialize(u));return {store,service,users,cmd:(u,a,input)=>service.command(u.id,id(),a,input),ref:o=>({id:o.id,version:store.get(o.id).version})};}
test('初始化对话持久化、跳过再继续、并发保护与首次任务幂等',t=>{
 const {store,service,users:[a,b],cmd,ref}=setup(t),session=service.list(a.id,'onboarding')[0];
 cmd(a,'onboarding.chat.draft',{...ref(session),text:'我要做作品集'});const stale=ref(session);
 cmd(a,'onboarding.chat.reply',{...ref(session),text:'我要做作品集'});
 assert.throws(()=>cmd(a,'onboarding.chat.reply',{...stale,text:'重复'}),{code:'VERSION_CONFLICT'});
 assert.equal(store.get(session.id).data.turns[1].role,'guide');assert.equal(store.list('task').length,0);
 assert.equal(service.bootstrap(a.id).objects.onboarding[0].data.turns[0].text,'我要做作品集');
 assert.throws(()=>service.read(b.id,session.id),{code:'NOT_FOUND'});
 cmd(a,'onboarding.complete',{...ref(session),skip:true});cmd(a,'onboarding.chat.reply',{...ref(session),text:'三页网页，保持黑白风格'});
 assert.equal(store.get(session.id).data.status,'completed');
 const first=cmd(a,'onboarding.chat.finish',{...ref(session),goal:'三页作品集，保持黑白风格',system:'create',save_understanding:true,confirm:true});
 const repeat=cmd(a,'onboarding.chat.finish',{...ref(session),goal:'三页作品集',system:'create',confirm:true});
 assert.equal(first.task_id,repeat.task_id);assert.equal(store.list('task').length,1);assert.equal(store.get(first.task_id).data.status,'draft');
 assert.equal(store.list('memory')[0].data.status,'pending_confirmation');assert.equal(store.list('memory')[0].data.scope,'create');
 assert.equal(store.list('message').length,0);
});
test('初始化模型对话需同意、串行、真实结果与历史上下文，缺 Key 不伪造回复',async t=>{
 const {store,service,users:[a],cmd,ref}=setup(t),session=service.list(a.id,'onboarding')[0];
 const first=cmd(a,'onboarding.chat.reply',{...ref(session),text:'帮我准备面试',model_consent:true});
 assert.throws(()=>cmd(a,'onboarding.chat.reply',{...ref(session),text:'下一条',model_consent:true}),{code:'RUN_ACTIVE'});
 let goals=[];const provider={status:()=>({configured:true}),generate:async({goal})=>{goals.push(goal.goal);return {output:'面试的岗位是什么？',usage:{total_tokens:10}}}};
 await new Runtime(store,provider).tick();assert.equal(store.get(first.task_id).data.status,'awaiting_review');assert.equal(store.list('message').length,0);
 cmd(a,'onboarding.chat.reply',{...ref(session),text:'产品经理',model_consent:true});await new Runtime(store,provider).tick();assert.match(goals[1],/面试的岗位是什么/);
 const blocked=cmd(a,'onboarding.chat.reply',{...ref(session),text:'帮我整理',model_consent:true});await new Runtime(store,new ModelProvider({})).tick();
 assert.equal(store.get(blocked.task_id).data.status,'blocked');assert.equal(store.get(blocked.run_id).data.receipts.length,0);
});
test('群聊对齐由当前 Agent 回答，只共享本次已选摘要',async t=>{
 const {store,service,users:[a],cmd,ref}=setup(t),session=service.list(a.id,'onboarding')[0];
 cmd(a,'onboarding.choice.start',{...ref(session),mode:'group'});
 cmd(a,'onboarding.choice.answer',{...ref(session),question_id:'need',option:'direction'});
 cmd(a,'onboarding.choice.answer',{...ref(session),question_id:'direction',option:'interest'});
 const reply=cmd(a,'onboarding.chat.reply',{...ref(session),text:'我对 AI 产品感兴趣',model_consent:true});
 const task=store.get(reply.task_id);assert.equal(task.data.system,'explore');assert.match(task.data.goal,/探索 Agent/);assert.match(task.data.goal,/找到方向/);
 assert.equal(store.get(session.id).data.turns.at(-1).participant,'explore');
 const provider={status:()=>({configured:true}),generate:async()=>({output:'你更想探索哪些具体产品？',usage:{total_tokens:10}})};
 await new Runtime(store,provider).tick();assert.equal(store.get(task.id).data.status,'awaiting_review');
 assert.equal(store.list('memory').length,0);
});
test('@ 本人辅助仅本人可见，不增加真人消息、通知与未读，填草稿后需人工发送',async t=>{
 const {store,service,users:[a,b],cmd,ref}=setup(t),friend=cmd(a,'friend.request',{handle:'bob'});const room=cmd(b,'friend.respond',{...ref(friend),decision:'accept'}).conversation_id;
 const msg=cmd(b,'message.send',{id:room,text:'明天方便讨论吗'}),draft=cmd(a,'draft.save',{conversation_id:room,version:0,text:'我的原稿'});
 const before=service.list(b.id,'conversation')[0].unread,notifications=service.list(b.id,'notification').length;
 const assist=cmd(a,'assist.create',{conversation_id:room,purpose:'帮我准备温和拒绝的表达'});
 assert.equal(store.list('run').length,0);assert.throws(()=>cmd(a,'assist.run',{...ref(assist),source_refs:[ref(msg)]}),{code:'CONSENT_REQUIRED'});
 cmd(a,'assist.run',{...ref(assist),source_refs:[ref(msg)],confirm:true,model_consent:true});
 const task=store.get(assist.id).data.task_id;assert.throws(()=>service.read(b.id,task),{code:'NOT_FOUND'});
 const provider={status:()=>({configured:true}),generate:async({goal})=>({output:goal.phase==='review'?'{"decision":"satisfied","issues":[]}':'谢谢邀请，这次暂时不方便。',usage:{total_tokens:10}})};
 await new Runtime(store,provider).tick();cmd(a,'assist.fill',{...ref(assist),run_id:store.get(store.get(assist.id).data.task_id).data.run_id,run_version:store.get(store.get(store.get(assist.id).data.task_id).data.run_id).version,draft_version:store.get(draft.id).version,mode:'append'});
 assert.match(store.get(draft.id).data.text,/我的原稿\n谢谢邀请/);assert.equal(store.get(draft.id).data.previous,'我的原稿');
 assert.equal(store.list('message').length,1);assert.equal(service.list(b.id,'notification').length,notifications);assert.equal(service.list(b.id,'conversation')[0].unread,before);
 assert.throws(()=>service.read(b.id,assist.id),{code:'NOT_FOUND'});
});
test('破冰只用选定可读资料，不能读对方私库，移出群后私密任务也撤权',t=>{
 const {store,service,users:[a,b],cmd,ref}=setup(t),friend=cmd(a,'friend.request',{handle:'bob'});cmd(b,'friend.respond',{...ref(friend),decision:'accept'});
 const room=cmd(a,'conversation.create',{title:'测试群',handles:['bob']}),privateDoc=cmd(a,'document.create',{title:'私库.txt',content:'不得共享'});
 const post=cmd(a,'post.create',{title:'公开近况',content:'最近完成了新作品',confirm:true});
 const assist=cmd(b,'assist.create',{conversation_id:room.id,purpose:'自然打招呼',entry:'icebreaker'});
 assert.throws(()=>cmd(b,'assist.run',{...ref(assist),source_refs:[ref(privateDoc)],confirm:true,model_consent:true}),{code:'NOT_FOUND'});
 cmd(b,'assist.run',{...ref(assist),source_refs:[ref(post)],confirm:true,model_consent:true});const taskId=store.get(assist.id).data.task_id;
 assert.match(store.get(taskId).data.goal,/不编造近况/);assert.ok(service.read(b.id,taskId));
 cmd(a,'conversation.remove_member',{...ref(room),user_id:b.id});assert.throws(()=>service.read(b.id,taskId),{code:'NOT_FOUND'});
});

test('初始化拒绝未解析附件；超过二十份历史资料仍能选择子集完成',t=>{
 const {store,service,users:[a],cmd,ref}=setup(t),session=service.list(a.id,'onboarding')[0];
 const file=cmd(a,'attachment.upload',{name:'raw.txt',base64:Buffer.from('应当先解析').toString('base64')});
 assert.throws(()=>cmd(a,'onboarding.chat.reply',{...ref(session),text:'请阅读附件',source_refs:[ref(file)],model_consent:true}),{code:'INVALID_CONTEXT'});
 const docs=Array.from({length:24},(_,index)=>cmd(a,'document.create',{title:`资料${index}.txt`,content:'可读取的正文'}));
 for(let i=0;i<4;i++)cmd(a,'onboarding.chat.reply',{...ref(session),text:'根据资料确定目标 '+i,source_refs:docs.slice(i*6,i*6+6).map(ref)});
 const result=cmd(a,'onboarding.chat.finish',{...ref(session),goal:'仅使用选中的两份资料',source_refs:[ref(docs[0]),ref(docs[23])],confirm:true});
 assert.deepEqual(store.get(result.task_id).data.source_refs.map(r=>r.id),[docs[0].id,docs[23].id]);
});
