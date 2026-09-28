import test from 'node:test';
import assert from 'node:assert/strict';
import {Store,id} from '../../server/elfred/store.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {ModelProvider} from '../../server/elfred/providers.mjs';
import {validateWebArtifact,PREVIEW_CSP} from '../../server/elfred/preview.mjs';
import {Runtime} from '../../server/elfred/runtime.mjs';
function setup(t){const store=new Store(':memory:'),service=new Service(store,new ModelProvider({}));t.after(()=>store.close());const users=['alice','bob','carol'].map(h=>authenticate(store,h,'local-test-password',true,h).user);users.forEach(u=>service.initialize(u));return {store,service,users,cmd:(u,a,input)=>service.command(u.id,id(),a,input),ref:o=>({id:o.id,version:store.get(o.id).version})};}
test('共创任务人数、前置依赖、截止日期与撤权不可绕过，撤回可重认领',t=>{
 const {store,users:[a,b,c],cmd,ref}=setup(t);
 const project=cmd(a,'project.create',{basis:'已有可公开基础',public_scope:'brief',reviewer_id:a.id,fee_terms:'各自承担费用',deadline_mode:'none',title:'共创',goal:'制作页面',criteria:'可用',task:'制作',participation:'open'});
 const slot=cmd(a,'project.slot.save',{project_id:project.id,title:'设计',criteria:'审核设计',capacity:1});
 const second=cmd(a,'project.slot.save',{project_id:project.id,title:'实现',criteria:'测试通过',capacity:1,depends_on:[slot.id]});
 const expired=cmd(a,'project.slot.save',{project_id:project.id,title:'旧任务',criteria:'已截止',deadline:'2020-01-01',capacity:1});
 assert.throws(()=>cmd(a,'project.slot.save',{...ref(slot),project_id:project.id,title:'设计',criteria:'审核',depends_on:[second.id]}),{code:'DEPENDENCY_CYCLE'});
 const post=cmd(a,'project.publish_post',{...ref(project),confirm:true});
 const dependent=cmd(b,'project.claim',{post_id:post.id,slot_id:second.id,slot_version:store.get(second.id).version,confirm:true});
 cmd(a,'claim.review',{...ref(dependent),accept:true});
 const dependentCopy=cmd(b,'copy.create',{project_id:project.id,slot_id:second.id});
 assert.throws(()=>cmd(b,'copy.ai_prepare',{...ref(dependentCopy),goal:'完成实现',confirm:true,model_consent:true}),{code:'DEPENDENCY_PENDING'});
 assert.equal(store.get(dependent.id).data.status,'accepted');
 assert.throws(()=>cmd(b,'project.claim',{post_id:post.id,slot_id:expired.id,slot_version:store.get(expired.id).version,confirm:true}),{code:'SLOT_CLOSED'});
 const claim=cmd(b,'project.claim',{post_id:post.id,slot_id:slot.id,slot_version:store.get(slot.id).version,confirm:true});
 assert.equal(cmd(b,'project.claim',{post_id:post.id,slot_id:slot.id,slot_version:store.get(slot.id).version,confirm:true}).id,claim.id);
 cmd(a,'claim.review',{...ref(claim),accept:true});
 assert.throws(()=>cmd(c,'project.claim',{post_id:post.id,slot_id:slot.id,slot_version:store.get(slot.id).version,confirm:true}),{code:'SLOT_FULL'});
 cmd(b,'claim.withdraw',ref(claim));cmd(b,'project.claim',{post_id:post.id,slot_id:slot.id,slot_version:store.get(slot.id).version,confirm:true});cmd(a,'claim.review',{...ref(claim),accept:true});assert.equal(store.get(claim.id).data.status,'accepted');
 cmd(a,'project.remove_member',{...ref(project),user_id:b.id});
 assert.throws(()=>cmd(b,'project.claim',{post_id:post.id,confirm:true}),{code:'MEMBERSHIP_REVOKED'});
 assert.throws(()=>cmd(b,'project.claim',{post_id:post.id,slot_id:second.id,slot_version:store.get(second.id).version,confirm:true}),{code:'MEMBERSHIP_REVOKED'});
});
test('公开共创内容来自本人确认；网页经过本人提交、审核和发布并可追溯',t=>{
 const {store,users:[a,b],cmd,ref}=setup(t);
 assert.throws(()=>cmd(a,'post.create',{title:'自动发帖',content:'自动',confirm:true,actor_type:'agent'}),{code:'HUMAN_REQUIRED'});
 const project=cmd(a,'project.create',{basis:'已有可公开基础',public_scope:'brief',reviewer_id:a.id,fee_terms:'各自承担费用',deadline_mode:'none',title:'网页',goal:'计数器',criteria:'点击增加',task:'实现按钮',participation:'open'});
 assert.throws(()=>cmd(a,'project.publish_post',ref(project)),{code:'CONFIRMATION_REQUIRED'});
 const post=cmd(a,'project.publish_post',{...ref(project),confirm:true});
 assert.equal(store.get(post.id).data.author_type,'human');
 cmd(b,'project.claim',{post_id:post.id,confirm:true});
 const copy=cmd(b,'copy.create',{project_id:project.id});
 cmd(b,'copy.save',{...ref(copy),format:'web',content:'<button id="b">0</button><script>let n=0;b.onclick=()=>b.textContent=++n</script>'});
 assert.throws(()=>cmd(b,'copy.submit',ref(copy)),{code:'REVIEW_REQUIRED'});
 const contribution=cmd(b,'copy.submit',{...ref(copy),reviewed:true});
 cmd(a,'contribution.review',{...ref(contribution),decision:'accept'});
 const release=cmd(a,'project.release',{...ref(project),confirm:true,allow_fork:true});
 assert.equal(store.get(release.id).data.preview,'sandboxed-web');assert.equal(store.get(release.id).data.published_by,a.id);
 assert.equal(store.get(release.id).data.build.status,'passed');
 assert.throws(()=>validateWebArtifact('<main>test</main><script>let =</script>'),{code:'BUILD_FAILED'});
 assert.throws(()=>validateWebArtifact('<main>test</main><script src="https://example.com/a.js"></script>'),{code:'EXTERNAL_DEPENDENCY'});
 assert.match(PREVIEW_CSP,/sandbox allow-scripts/);assert.doesNotMatch(PREVIEW_CSP,/allow-same-origin/);
});
test('工具版本固定在具体任务，测试不虚增使用次数，归档后不可调用',t=>{
 const {store,users:[a],cmd,ref}=setup(t);
 const skill=cmd(a,'tool.save',{title:'审稿',instructions:'先核对事实，再检查表达',kind:'Skill'}),v1=store.get(skill.id).data.version_id;
 cmd(a,'tool.activate',ref(skill));const run=cmd(a,'tool.use',{id:skill.id,version_id:store.get(skill.id).data.version_id,goal:'审核稿件'});
 assert.equal(store.get(run.task_id).data.skill_version_id,v1);assert.equal(store.get(skill.id).data.uses,0);
 cmd(a,'tool.save',{...ref(skill),title:'审稿二版',instructions:'增加引用核对',kind:'Skill'});
 assert.equal(store.get(run.task_id).data.skill_version_id,v1);
 cmd(a,'tool.test',{id:skill.id,version_id:store.get(skill.id).data.version_id});assert.equal(store.get(skill.id).data.uses,0);
 cmd(a,'tool.archive',ref(skill));assert.throws(()=>cmd(a,'tool.use',{id:skill.id,version_id:store.get(skill.id).data.version_id}),{code:'TOOL_DISABLED'});
});
test('帖子附件在公开前保持私有，撤下后立即撤回访问',t=>{
 const {store,service,users:[a,b],cmd,ref}=setup(t);
 const file=cmd(a,'attachment.upload',{name:'notes.txt',base64:Buffer.from('公开笔记').toString('base64')});
 assert.throws(()=>service.read(b.id,file.id),{code:'NOT_FOUND'});
 const post=cmd(a,'post.create',{title:'附件',content:'本人确认公开',attachment_ids:[file.id],confirm:true});
 assert.equal(service.read(b.id,file.id).data.name,'notes.txt');assert.equal(service.read(b.id,file.id).data.base64,undefined);
 cmd(a,'post.withdraw',{...ref(post),confirm:true});assert.throws(()=>service.read(b.id,file.id),{code:'NOT_FOUND'});assert.ok(store.read(a.id,file.id));
});
test('多步生成按审查意见至多修正一次，最终成果不夹带模型审查记录且不发布到社区',async t=>{
 const {store,users:[a],cmd,ref}=setup(t),phases=[];
 const provider={status:()=>({configured:true}),generate:async input=>{phases.push(input.goal.phase);return {output:input.goal.phase==='review'?JSON.stringify({decision:'revise',issues:['缺少限制'],guidance:'补充限制'}):input.goal.phase==='repair'?'最终稿，包含限制。':'原始草稿',usage:{total_tokens:10}}}};
 const doc=cmd(a,'document.create',{title:'依据.md',content:'实际限制'}),task=cmd(a,'task.create',{goal:'写一篇有据可查的文稿',mode:'compose',source_refs:[ref(doc)]});
 cmd(a,'task.confirm',{...ref(task),confirm:true,model_consent:true});const run=cmd(a,'run.start',ref(task));
 await new Runtime(store,provider).tick();assert.deepEqual(phases,['work','review','repair']);assert.equal(store.get(run.id).data.verification.repair_performed,true);
 assert.equal(store.get(task.id).data.status,'awaiting_review');const accepted=cmd(a,'task.accept',{...ref(task),accept:true});assert.equal(store.get(accepted.artifact_id).data.content,'最终稿，包含限制。');
 assert.equal(store.list('post').length,0);assert.equal(store.list('comment').length,0);assert.equal(store.list('message').length,0);
 assert.equal(store.get(task.id).data.calls,3); // Context goes directly into the model; no duplicate context.read step.
});
test('音频走转写适配器，需单独确认、使用同一调用预算并保留私密结果',async t=>{
 const {store,users:[a],cmd,ref}=setup(t);let calls=0;
 const provider={status:()=>({configured:true}),transcribe:async input=>{calls++;assert.equal(input.name,'录音.webm');return {output:'真实接口形状的测试转写',usage:null}},generate:()=>{throw new Error('wrong adapter')}};
 const file=cmd(a,'attachment.upload',{name:'录音.webm',base64:Buffer.from('synthetic fixture audio').toString('base64')});
 const task=cmd(a,'attachment.analyze',{id:file.id});assert.throws(()=>cmd(a,'task.confirm',{...ref(task),confirm:true}),{code:'CONSENT_REQUIRED'});
 cmd(a,'task.confirm',{...ref(task),confirm:true,model_consent:true});cmd(a,'run.start',ref(task));await new Runtime(store,provider).tick();
 assert.equal(calls,1);assert.equal(store.get(task.id).data.status,'awaiting_review');assert.equal(store.db.prepare('SELECT spent FROM budget_accounts WHERE owner=?').get(a.id).spent,1000);assert.equal(store.list('message').length,0);
});
test('群消息附件、共享记录撤权；已接受事项修改后负责人必须重新确认',t=>{
 const {store,service,users:[a,b],cmd,ref}=setup(t),friend=cmd(a,'friend.request',{handle:'bob'});cmd(b,'friend.respond',{...ref(friend),decision:'accept'});
 const group=cmd(a,'conversation.create',{title:'群',handles:['bob']}),file=cmd(b,'attachment.upload',{name:'说明.txt',base64:Buffer.from('test').toString('base64'),conversation_id:group.id});
 const message=cmd(b,'message.send',{id:group.id,text:'',attachment_ids:[file.id]});assert.equal(store.get(message.id).data.human_sender_id,b.id);assert.ok(service.read(a.id,file.id));
 const record=cmd(b,'group.record.save',{conversation_id:group.id,title:'共同目标',content:'完成设计',kind:'goal',source_refs:[ref(message)]});
 const commitment=cmd(a,'commitment.create',{conversation_id:group.id,goal:'写稿',assignee:b.id});cmd(b,'commitment.respond',{...ref(commitment),accept:true});
 cmd(a,'commitment.revise',{...ref(commitment),goal:'补充图表',due:'2026-10-01T09:00:00Z'});assert.equal(store.get(commitment.id).data.status,'proposed');assert.ok(store.get(commitment.id).data.previous_task_id);
 assert.throws(()=>cmd(a,'commitment.respond',{...ref(commitment),accept:true}),{code:'FORBIDDEN'});
 cmd(a,'conversation.remove_member',{...ref(group),user_id:b.id});assert.throws(()=>service.read(b.id,file.id),{code:'NOT_FOUND'});assert.throws(()=>service.read(b.id,record.id),{code:'NOT_FOUND'});
});
test('只配置 Key 即有文本、视觉和语音默认地址；Key 不进入状态',async()=>{
 const requests=[],provider=new ModelProvider({OPENAI_API_KEY:'test-only-key'},async(url,init)=>{requests.push({url,init});return new Response(JSON.stringify(url.endsWith('/audio/transcriptions')?{text:'转写'}:{choices:[{message:{content:'识别文字'},finish_reason:'stop'}],usage:{total_tokens:7}}),{status:200})});
 assert.equal(provider.status().configured,true);assert.ok(!JSON.stringify(provider.status()).includes('test-only-key'));
 await provider.generate({goal:'识别',context:[],images:['data:image/png;base64,AA=='],maxTokens:8192});
 assert.match(requests[0].url,/^https:\/\/api\.openai\.com\/v1\/chat\/completions$/);assert.equal(JSON.parse(requests[0].init.body).messages[1].content[1].type,'image_url');
 await provider.transcribe({bytes:Buffer.from('audio fixture'),name:'audio.webm'});assert.match(requests[1].url,/audio\/transcriptions$/);assert.equal(requests[1].init.body.get('model'),'gpt-4o-mini-transcribe');
});
test('文本请求为输入预留预算，预算不足不发送；缺失用量不当成零',async()=>{
 let calls=0;const provider=new ModelProvider({OPENAI_API_KEY:'test-key'},async()=>{calls++;return new Response(JSON.stringify({choices:[{message:{content:'结果'},finish_reason:'stop'}]}),{status:200})});
 await assert.rejects(()=>provider.generate({goal:'测试',context:[{content:'过长上下文'.repeat(100)}],maxTokens:100}),{code:'CONTEXT_BUDGET_EXCEEDED'});assert.equal(calls,0);
 await assert.rejects(()=>provider.generate({goal:'测试',context:[],maxTokens:1000}),{code:'PROVIDER_USAGE_UNKNOWN'});assert.equal(calls,1);
});
test('退回结果后的普通恢复仍继承本人反馈并受修订次数限制',async t=>{
 const {store,users:[a],cmd,ref}=setup(t),feedback=[];
 const provider={status:()=>({configured:true}),generate:async input=>{feedback.push(input.goal.revision_feedback);return {output:input.goal.phase==='review'?'{"decision":"satisfied","issues":[]}':'结果',usage:{total_tokens:2}}}};
 const task=cmd(a,'task.create',{goal:'写说明'});cmd(a,'task.confirm',{...ref(task),confirm:true,model_consent:true});cmd(a,'run.start',ref(task));await new Runtime(store,provider).tick();
 cmd(a,'task.accept',{...ref(task),accept:false,feedback:'改为中文'});const run=cmd(a,'run.start',ref(task));assert.equal(store.get(run.id).data.plan.feedback,'改为中文');assert.equal(store.get(task.id).data.replans,1);
 await new Runtime(store,provider).tick();assert.equal(store.get(task.id).data.status,'awaiting_review');cmd(a,'task.accept',{...ref(task),accept:false,feedback:'再改一次'});
 assert.ok(feedback.includes('改为中文'));assert.throws(()=>cmd(a,'run.start',ref(task)),{code:'REPLAN_LIMIT'});
});
test('供应商已知超限用量入账，费用对账不能重置 token 停止上限',async t=>{
 const {store,users:[a],cmd,ref}=setup(t);let calls=0;
 const provider=new ModelProvider({OPENAI_API_KEY:'test-key'},async()=>{calls++;return new Response(JSON.stringify({choices:[{message:{content:'结果'},finish_reason:'stop'}],usage:{total_tokens:50000}}),{status:200})});
 const task=cmd(a,'task.create',{goal:'测试预算'});cmd(a,'task.confirm',{...ref(task),confirm:true,model_consent:true});cmd(a,'run.start',ref(task));await new Runtime(store,provider).tick();
 assert.equal(store.get(task.id).data.tokens,50000);const usage=store.db.prepare("SELECT * FROM usage WHERE task_id=? AND status='unknown'").get(task.id);assert.ok(usage);
 cmd(a,'usage.reconcile',{id:usage.id,confirm:true,actual_units:1000,note:'已核对实际用量'});assert.throws(()=>cmd(a,'run.start',ref(task)),{code:'STOP_LIMIT'});assert.equal(calls,1);
});

 test('收件箱重复存入不重复创建，处理后可恢复，转任务不自动启动且只创建一次',t=>{
 const {store,users:[a,b],cmd,ref}=setup(t),source=cmd(a,'knowledge.create',{title:'稍后整理',content:'一条本人的资料'});
 const item=cmd(a,'inbox.create',{object_id:source.id});assert.equal(cmd(a,'inbox.create',{object_id:source.id}).id,item.id);assert.equal(store.list('inbox').length,1);
 cmd(a,'inbox.dismiss',ref(item));cmd(a,'inbox.create',{object_id:source.id});assert.equal(store.get(item.id).data.status,'pending');
 assert.throws(()=>cmd(b,'inbox.create',{object_id:source.id}),{code:'NOT_FOUND'});
 const task=cmd(a,'inbox.task',ref(item));assert.equal(store.get(task.id).data.status,'draft');assert.equal(store.list('run').length,0);assert.equal(store.get(item.id).data.status,'processed');
 assert.equal(cmd(a,'inbox.task',ref(item)).id,task.id);cmd(a,'inbox.create',{object_id:source.id});assert.equal(store.get(item.id).data.status,'processed');assert.equal(store.list('task').length,1);
 });
