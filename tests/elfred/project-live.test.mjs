import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {Store,id} from '../../server/elfred/store.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {ModelProvider} from '../../server/elfred/providers.mjs';
import {apiHandler} from '../../server/elfred/http.mjs';

test('两位成员通过持续事件收到已共享阶段，非成员看不到过程稿与反馈',async t=>{
 const store=new Store(':memory:'),service=new Service(store,new ModelProvider({}));let handler;
 const server=createServer((request,response)=>void handler(request,response));await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin='http://127.0.0.1:'+server.address().port;handler=apiHandler(service,{origin});
 t.after(async()=>{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));store.close()});
 const register=async handle=>{const response=await fetch(origin+'/api/elfred/auth/register',{method:'POST',headers:{'Content-Type':'application/json',Origin:origin,'X-Elfred-Client':'1','Idempotency-Key':id()},body:JSON.stringify({handle,name:handle,password:'project-live-password'})});assert.equal(response.status,200);return {cookie:response.headers.get('set-cookie').split(';')[0],...(await response.json()).user}};
 const a=await register('live-a'),b=await register('live-b'),c=await register('live-c'),command=(user,action,input)=>service.command(user.id,id(),action,input),ref=item=>({id:item.id,version:store.get(item.id).version});
 const project=command(a,'project.create',{title:'实时协作',goal:'共同改进页面',basis:'公开原型',task:'核对移动端',criteria:'两人检查后验收',participation:'open',public_scope:'brief',reviewer_id:a.id,fee_terms:'各自承担本人费用',deadline_mode:'none'});
 const post=command(a,'project.publish_post',{...ref(project),confirm:true});command(b,'project.claim',{post_id:post.id,confirm:true});
 const cursor=store.db.prepare('SELECT MAX(seq) AS n FROM events').get().n,controller=new AbortController();
 const response=await fetch(origin+`/api/elfred/events?after=${cursor}`,{headers:{Cookie:b.cookie,Accept:'text/event-stream'},signal:controller.signal});const reader=response.body.getReader();await reader.read();
 const copy=command(a,'copy.create',{project_id:project.id});command(a,'copy.save',{...ref(copy),content:'已核对的共享过程稿'});const stage=command(a,'copy.stage',{...ref(copy),title:'移动端初稿',reviewed:true});
 let events='';const timeout=setTimeout(()=>controller.abort(),6000);
 try{while(!events.includes(stage.id)){const chunk=await reader.read();if(chunk.done)break;events+=new TextDecoder().decode(chunk.value)}assert.match(events,new RegExp(stage.id))}finally{clearTimeout(timeout);controller.abort();await reader.cancel().catch(()=>{})}
 const visible=await fetch(origin+'/api/elfred/bootstrap',{headers:{Cookie:b.cookie}});assert.equal(visible.status,200);const snapshot=await visible.json();assert.ok(snapshot.objects.project_stage.some(item=>item.id===stage.id));
 const feedback=command(b,'project.feedback',{id:project.id,stage_id:stage.id,stage_version:store.get(stage.id).version,kind:'review',content:'建议调整间距'});assert.equal(service.read(a.id,feedback.id).data.stage_ref.id,stage.id);assert.throws(()=>service.read(c.id,feedback.id),{code:'NOT_FOUND'});
});
