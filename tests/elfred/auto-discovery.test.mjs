import test from 'node:test';
import assert from 'node:assert/strict';
import {Store,id} from '../../server/elfred/store.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {ModelProvider} from '../../server/elfred/providers.mjs';
import {tickRssObservations} from '../../server/elfred/observation.mjs';

test('初始化偏好自动选公开资讯源；本人启动后首次真实条目进入私人朋友圈',async t=>{
 const store=new Store(':memory:'),service=new Service(store,new ModelProvider({}));t.after(()=>store.close());
 const user=authenticate(store,'discovery-user','local-test-password',true,'本人').user;service.initialize(user);
 const command=(action,input)=>service.command(user.id,id(),action,input),session=()=>service.list(user.id,'onboarding')[0],ref=item=>({id:item.id,version:store.get(item.id).version});
 command('onboarding.choice.answer',{...ref(session()),question_id:'direction',option:'opportunity'});
 command('onboarding.choice.answer',{...ref(session()),question_id:'format',option:'product'});
 command('onboarding.choice.confirm',{...ref(session()),confirm:true});
 const watch=service.list(user.id,'observation')[0];
 assert.ok(watch.data.auto_suggested);assert.equal(watch.data.status,'draft');
 assert.match(watch.data.source_url,/news\.google\.com\/rss\/search/);assert.match(watch.data.goal,/外部趋势与机会/);
 assert.equal(service.list(user.id,'feed').length,0);
 command('observation.start',{...ref(watch),confirm:true});
 const source={id:'source-1',title:'一项可核对的产品开发机会',summary:'公开发布的项目资讯',url:'https://example.org/product',published_at:new Date().toISOString()};
 await tickRssObservations(store,async()=>[source]);
 const first=service.list(user.id,'feed');assert.equal(first.length,1);assert.equal(first[0].data.external_url,source.url);
 assert.match(first[0].data.reason,/初始化偏好/);assert.equal(service.list(user.id,'post').length,0);
 const current=store.get(watch.id);store.update(current,{...current.data,next_at:Date.now()-1},user.id);
 await tickRssObservations(store,async()=>[source]);assert.equal(service.list(user.id,'feed').length,1);
});

test('已有观察达到上限时仍能确认初始化，不阻断首页启动',t=>{
 const store=new Store(':memory:'),service=new Service(store,new ModelProvider({}));t.after(()=>store.close());
 const user=authenticate(store,'discovery-limit','local-test-password',true,'本人').user;service.initialize(user);
 for(let index=0;index<20;index++)store.add('observation',user.id,{goal:`已有观察 ${index}`,status:'draft'});
 const session=service.list(user.id,'onboarding')[0];
 service.command(user.id,id(),'onboarding.choice.answer',{id:session.id,version:session.version,question_id:'direction',option:'opportunity'});
 const updated=service.list(user.id,'onboarding')[0];
 service.command(user.id,id(),'onboarding.choice.confirm',{id:updated.id,version:updated.version,confirm:true});
 assert.ok(service.list(user.id,'onboarding')[0].data.choice_confirmed_at);
 assert.equal(service.list(user.id,'observation').length,20);
 assert.ok(service.bootstrap(user.id).user);
});

test('朋友圈三档密度按本人设置限制真实 RSS 发布，单个 Agent 可覆盖整体档位',async t=>{
 const store=new Store(':memory:'),service=new Service(store,new ModelProvider({}));t.after(()=>store.close());
 const user=authenticate(store,'density-user','local-test-password',true,'本人').user;service.initialize(user);
 const command=(action,input)=>service.command(user.id,id(),action,input),session=()=>service.list(user.id,'onboarding')[0],ref=item=>({id:item.id,version:store.get(item.id).version});
 command('onboarding.choice.answer',{...ref(session()),question_id:'direction',option:'opportunity'});
 command('onboarding.choice.answer',{...ref(session()),question_id:'format',option:'product'});
 command('onboarding.choice.confirm',{...ref(session()),confirm:true,auto_discovery:true});
 const settings=()=>service.list(user.id,'settings')[0],watch=()=>service.list(user.id,'observation')[0];
 command('feed.density.set',{...ref(settings()),mode:'quiet'});
 assert.equal(settings().data.feed_density.global,'quiet');
 const article=index=>({id:`density-${index}`,title:`产品开发机会 ${index}`,summary:'公开市场需求',url:`https://example.org/density-${index}`,published_at:new Date().toISOString()});
 await tickRssObservations(store,async()=>Array.from({length:20},(_,i)=>article(i)));
 assert.equal(service.list(user.id,'feed').length,3);
 assert.equal(watch().data.interval_hours,24);
 store.update(watch(),{...watch().data,next_at:Date.now()-1},user.id);
 await tickRssObservations(store,async()=>Array.from({length:20},(_,i)=>article(i+20)));
 assert.equal(service.list(user.id,'feed').length,12);
 assert.equal(watch().data.last_candidate_count,20);
 command('feed.density.set',{...ref(settings()),system:'explore',mode:'rich'});
 assert.equal(settings().data.feed_density.agents.explore,'rich');
 store.update(watch(),{...watch().data,next_at:Date.now()-1},user.id);
 await tickRssObservations(store,async()=>Array.from({length:20},(_,i)=>article(i+40)));
 assert.equal(service.list(user.id,'feed').length,27);
 assert.ok(watch().data.next_at-Date.now()<=4*3600000);
 command('feed.density.set',{...ref(settings()),system:'explore',mode:'inherit'});
 assert.equal(settings().data.feed_density.agents.explore,undefined);
});
