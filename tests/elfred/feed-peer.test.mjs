import test from 'node:test';
import assert from 'node:assert/strict';
import {Store,id} from '../../server/elfred/store.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {Runtime} from '../../server/elfred/runtime.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {search} from '../../server/elfred/knowledge.mjs';
import {tickFeedPeerComments} from '../../server/elfred/feed-peer.mjs';

test('本人开启后其他 Agent 按真实事件自动评论，计费有上限且不会生成第二条主帖',async t=>{
 const store=new Store(':memory:'),calls=[];t.after(()=>store.close());const provider={status:()=>({configured:true}),generate:async request=>{calls.push(request);return {output:'先核对活动截止日期与报名规则，再决定是否安排时间。',usage:{total_tokens:12}}}};
 const service=new Service(store,provider),runtime=new Runtime(store,provider),user=authenticate(store,'feed-peer-test','feed-peer-password',true,'本人').user;service.initialize(user);
 const settings=store.visible(user.id,'settings')[0],feed=store.add('feed',user.id,{title:'活动报名有新变化',summary:'公开来源显示报名规则变化，需要用户核对',purpose:'discovery',system:'explore',status:'active',comments:[],external_url:'https://example.com/activity'});
 await runtime.tick();assert.equal(calls.length,0);assert.equal(store.list('task').filter(task=>task.data.internal_peer_comment).length,0);
 service.command(user.id,id(),'feed.peer_comments.policy',{id:settings.id,version:settings.version,enabled:true,daily_limit:1,confirm:true,model_consent:true});
 await runtime.tick();assert.equal(calls.length,1);await runtime.tick();
 const comments=store.get(feed.id).data.comments;assert.equal(comments.length,1);assert.equal(comments[0].system,'advise');assert.match(comments[0].content,/截止日期/);assert.equal(store.list('feed').length,1);
 assert.equal(search(store,user.id,{query:'请作为advise Agent',types:['task']}).hits.length,0);
 const second=store.add('feed',user.id,{title:'另一项资讯',summary:'公开来源有待核对的新变化',purpose:'observation',system:'explore',status:'active',comments:[]});await runtime.tick();assert.equal(store.get(second.id).data.comments.length,0);assert.equal(calls.length,1);
});
test('自主评论失败后保留动态并在退避期结束重试，不被旧失败任务永久卡住',t=>{
 const store=new Store(':memory:');t.after(()=>store.close());const provider={status:()=>({configured:true})};
 const service=new Service(store,provider),user=authenticate(store,'feed-peer-retry','feed-peer-password',true,'本人').user;service.initialize(user);
 const settings=store.visible(user.id,'settings')[0],feed=store.add('feed',user.id,{title:'有来源的事件',summary:'公开资料需要核对',purpose:'discovery',system:'explore',status:'active',comments:[]});
 service.command(user.id,id(),'feed.peer_comments.policy',{id:settings.id,version:settings.version,enabled:true,daily_limit:3,confirm:true,model_consent:true});
 tickFeedPeerComments(store,provider);
 const first=store.list('task').find(task=>task.data.feed_peer_for===feed.id);assert.ok(first);
 store.update(first,{...first.data,status:'blocked'},user.id);
 tickFeedPeerComments(store,provider);
 assert.equal(store.get(first.id).data.peer_comment_failed,true);
 assert.equal(store.get(feed.id).data.comments.length,0);
 const current=store.get(feed.id);store.update(current,{...current.data,peer_comment_retry_after:0},user.id);
 tickFeedPeerComments(store,provider);
 assert.equal(store.list('task').filter(task=>task.data.feed_peer_for===feed.id).length,2);
});
