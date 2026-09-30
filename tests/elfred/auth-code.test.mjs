import test from 'node:test';
import assert from 'node:assert/strict';
import {Store} from '../../server/elfred/store.mjs';
import {authenticateWithCode,requestAuthCode} from '../../server/elfred/auth-code.mjs';

const config={ELFRED_RESEND_API_KEY:'test-only',ELFRED_EMAIL_FROM:'Elfred <test@example.com>',ELFRED_AUTH_CODE_SECRET:'test-only-secret'};

test('verified email login creates one account and returns to that account on repeat',async()=>{
  const store=new Store(':memory:');let code='';
  const fetcher=async(_url,options)=>{code=JSON.parse(options.body).text.match(/(\d{6})/)?.[1];return {ok:true,json:async()=>({id:'provider-receipt'})}};
  try{
    await requestAuthCode(store,' USER@example.com ','test-client',config,fetcher);
    assert.throws(()=>authenticateWithCode(store,'user@example.com',code==='000000'?'000001':'000000',config),/验证码不正确/);
    const first=authenticateWithCode(store,'user@example.com',code,config);
    assert.equal(first.created,true);
    store.db.prepare('UPDATE auth_challenges SET requested_at=0 WHERE handle=?').run('user@example.com');
    await requestAuthCode(store,'user@example.com','test-client',config,fetcher);
    const second=authenticateWithCode(store,'USER@example.com',code,config);
    assert.equal(second.user.id,first.user.id);
    assert.equal(second.created,false);
  }finally{store.close()}
});

test('SMS uses configured provider and no code is exposed in response',async()=>{
  const store=new Store(':memory:');let request;
  const sms={ELFRED_TWILIO_ACCOUNT_SID:'ACtest',ELFRED_TWILIO_AUTH_TOKEN:'test-only',ELFRED_TWILIO_FROM:'+1234567890',ELFRED_AUTH_CODE_SECRET:'test-only-secret'};
  try{
    const receipt=await requestAuthCode(store,'13800138000','test-client',sms,async(url,options)=>{request={url,options};return {ok:true,json:async()=>({sid:'SMtest'})}});
    assert.equal(receipt.channel,'sms');
    assert.equal(JSON.stringify(receipt).includes('13800138000'),false);
    assert.match(request.options.body,/To=%2B8613800138000/);
    assert.match(request.url,/api\.twilio\.com/);
  }finally{store.close()}
});
