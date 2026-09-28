import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer,request} from 'node:http';
import {Store} from '../../server/elfred/store.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {ModelProvider} from '../../server/elfred/providers.mjs';
import {apiHandler} from '../../server/elfred/http.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';

test('配置发件服务后，邮箱注册需真实邮件验证码；同一邮箱仍回到同一账号',async t=>{
 const store=new Store(':memory:'),service=new Service(store,new ModelProvider({}));
 const origin='https://elfred.example',emailConfig={ELFRED_RESEND_API_KEY:'test-key',ELFRED_EMAIL_FROM:'Elfred <hello@example.com>',ELFRED_EMAIL_CODE_SECRET:'test-secret'};
 let code='',sent=0;
 const emailFetch=async(url,options)=>{assert.equal(url,'https://api.resend.com/emails');assert.equal(options.headers.Authorization,'Bearer test-key');const body=JSON.parse(options.body);assert.deepEqual(body.to,['member@example.com']);code=body.text.match(/\b\d{6}\b/)[0];sent++;return new Response(JSON.stringify({id:'mail-'+sent}),{status:200})};
 const handler=apiHandler(service,{origin,emailConfig,emailFetch}),server=createServer((req,res)=>void handler(req,res));
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 t.after(async()=>{await new Promise(resolve=>server.close(resolve));store.close()});
 const address=`http://127.0.0.1:${server.address().port}`;
 const call=(path,body)=>new Promise((resolve,reject)=>{const req=request(address+'/api/elfred'+path,{method:body===undefined?'GET':'POST',headers:{Host:'elfred.example',Origin:origin,'X-Elfred-Client':'1',...(body===undefined?{}:{'Content-Type':'application/json'})}},res=>{let text='';res.on('data',chunk=>text+=chunk);res.on('end',()=>resolve({status:res.statusCode,data:JSON.parse(text)}))});req.on('error',reject);req.end(body===undefined?undefined:JSON.stringify(body))});
 assert.deepEqual((await call('/auth/email/status')).data,{configured:true});
 const details={handle:'Member@Example.com',password:'email-password-1',name:'成员'};
 assert.equal((await call('/auth/register',details)).data.error.code,'INVALID_EMAIL_CODE');
 assert.equal((await call('/auth/email/request',{email:details.handle})).status,200);
 assert.equal(sent,1);
 assert.equal((await call('/auth/email/request',{email:details.handle})).status,429);
 assert.equal((await call('/auth/register',{...details,email_code:'000000'})).data.error.code,'INVALID_EMAIL_CODE');
 const registered=await call('/auth/register',{...details,email_code:code});
 assert.equal(registered.status,200);
 assert.equal(store.db.prepare('SELECT user_id FROM verified_emails WHERE email=?').get('member@example.com').user_id,registered.data.user.id);
 assert.equal((await call('/auth/login',{handle:'member@example.com',password:details.password})).data.user.id,registered.data.user.id);
 assert.equal(authenticate(store,' MEMBER@EXAMPLE.COM ',details.password).user.id,registered.data.user.id);
 assert.equal((await call('/auth/email/request',{email:details.handle})).status,409);
});

test('发件服务未配置或拒绝发送时不产生可用验证码',async t=>{
 const store=new Store(':memory:');t.after(()=>store.close());
 const {requestEmailCode,consumeEmailCode}=await import('../../server/elfred/email-verification.mjs');
 await assert.rejects(requestEmailCode(store,'member@example.com','local',{}),{code:'EMAIL_NOT_CONFIGURED'});
 await assert.rejects(requestEmailCode(store,'member@example.com','local',{ELFRED_RESEND_API_KEY:'test',ELFRED_EMAIL_FROM:'hello@example.com'},async()=>new Response('{}',{status:403})),{code:'EMAIL_SEND_FAILED'});
 assert.equal(store.db.prepare('SELECT count(*) AS total FROM email_challenges').get().total,0);
 assert.throws(()=>consumeEmailCode(store,'member@example.com','123456',{ELFRED_RESEND_API_KEY:'test',ELFRED_EMAIL_FROM:'hello@example.com'}),{code:'INVALID_EMAIL_CODE'});
});

test('五次错误输入会锁定当前验证码，重发前不能凭旧码注册',async t=>{
 const store=new Store(':memory:');t.after(()=>store.close());
 const {requestEmailCode,consumeEmailCode}=await import('../../server/elfred/email-verification.mjs');
 const config={ELFRED_RESEND_API_KEY:'test',ELFRED_EMAIL_FROM:'hello@example.com',ELFRED_EMAIL_CODE_SECRET:'test-secret'};
 let code='';
 await requestEmailCode(store,'member@example.com','local',config,async(_,options)=>{code=JSON.parse(options.body).text.match(/\b\d{6}\b/)[0];return new Response(JSON.stringify({id:'mail-1'}),{status:200})});
 const wrong=code==='000000'?'999999':'000000';
 for(let attempt=0;attempt<5;attempt++)assert.throws(()=>consumeEmailCode(store,'member@example.com',wrong,config),{code:'INVALID_EMAIL_CODE'});
 assert.throws(()=>consumeEmailCode(store,'member@example.com',code,config),{code:'INVALID_EMAIL_CODE'});
});
