import {createHmac,randomBytes,randomInt,timingSafeEqual} from 'node:crypto';
import {canonicalEmail} from './email-verification.mjs';
import {passwordHash} from './auth.mjs';
import {fail,hash,id,now} from './store.mjs';

const secret = randomBytes(32).toString('hex');
export const canonicalContact = value => {
  const handle=typeof value==='string'?value.trim():'';
  if (/^1[3-9]\d{9}$/.test(handle)) return {handle,channel:'sms'};
  if (handle.includes('@')) return {handle:canonicalEmail(handle),channel:'email'};
  fail('INVALID_CONTACT','请输入有效的中国手机号或邮箱地址');
};
export const codeChannels = config => ({
  email:Boolean(config.ELFRED_RESEND_API_KEY&&config.ELFRED_EMAIL_FROM),
  sms:Boolean(config.ELFRED_TWILIO_ACCOUNT_SID&&config.ELFRED_TWILIO_AUTH_TOKEN&&config.ELFRED_TWILIO_FROM),
});
const digest=(handle,code,config)=>createHmac('sha256',config.ELFRED_AUTH_CODE_SECRET||secret).update(handle+':'+code).digest('hex');
const count=(store,key,max,time)=>{
  const row=store.db.prepare('SELECT count,until FROM login_attempts WHERE key=?').get(key);
  if(row&&row.until>time&&row.count>=max)fail('RATE_LIMIT','请求过于频繁，请稍后再试',429);
  store.db.prepare('INSERT INTO login_attempts VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=CASE WHEN until<? THEN 1 ELSE count+1 END,until=CASE WHEN until<? THEN excluded.until ELSE until END').run(key,time+900000,time,time);
};

export async function requestAuthCode(store,value,client,config=process.env,fetcher=fetch){
  const {handle,channel}=canonicalContact(value),enabled=codeChannels(config);
  if(!enabled[channel])fail('CODE_NOT_CONFIGURED',channel==='sms'?'短信服务尚未配置':'邮箱发送服务尚未配置',503);
  const time=Date.now(),code=String(randomInt(0,1000000)).padStart(6,'0'),requestId=randomBytes(16).toString('hex');
  store.transaction(()=>{
    const current=store.db.prepare('SELECT requested_at FROM auth_challenges WHERE handle=?').get(handle);
    if(current&&time-current.requested_at<60000)fail('RATE_LIMIT','请等待 1 分钟后重发',429);
    count(store,'auth-code:'+hash(handle),5,time);
    count(store,'auth-code-ip:'+hash(client||'unknown'),20,time);
    store.db.prepare('INSERT INTO auth_challenges(handle,code_digest,expires,requested_at,attempts,request_id) VALUES(?,?,?,?,0,?) ON CONFLICT(handle) DO UPDATE SET code_digest=excluded.code_digest,expires=excluded.expires,requested_at=excluded.requested_at,attempts=0,request_id=excluded.request_id').run(handle,digest(handle,code,config),time+600000,time,requestId);
  });
  try {
    let response;
    if(channel==='email'){
      response=await fetcher('https://api.resend.com/emails',{method:'POST',headers:{Authorization:`Bearer ${config.ELFRED_RESEND_API_KEY}`,'Content-Type':'application/json'},body:JSON.stringify({from:config.ELFRED_EMAIL_FROM,to:[handle],subject:'Elfred 登录验证码',text:`你的 Elfred 登录验证码是 ${code}。10 分钟内有效。如果不是你本人操作，请忽略。`}),signal:AbortSignal.timeout(10000)});
    } else {
      const sid=String(config.ELFRED_TWILIO_ACCOUNT_SID);
      const body=new URLSearchParams({From:String(config.ELFRED_TWILIO_FROM),To:'+86'+handle,Body:`Elfred 验证码：${code}。10 分钟内有效。`});
      response=await fetcher(`https://api.twilio.com/2010-04-01/Accounts/${encodeURIComponent(sid)}/Messages.json`,{method:'POST',headers:{Authorization:'Basic '+Buffer.from(sid+':'+config.ELFRED_TWILIO_AUTH_TOKEN).toString('base64'),'Content-Type':'application/x-www-form-urlencoded'},body:body.toString(),signal:AbortSignal.timeout(10000)});
    }
    if(!response.ok)throw new Error('provider rejected request');
    const receipt=await response.json();if(!receipt?.id&&!receipt?.sid)throw new Error('missing provider receipt');
  }catch{
    store.db.prepare('DELETE FROM auth_challenges WHERE handle=? AND request_id=?').run(handle,requestId);
    fail('CODE_SEND_FAILED','验证码未能发送，请稍后重试',502);
  }
  return {sent:true,channel,expires_in:600,resend_after:60};
}

export function authenticateWithCode(store,value,code,config=process.env){
  const {handle,channel}=canonicalContact(value);
  if(!codeChannels(config)[channel])fail('CODE_NOT_CONFIGURED','验证码服务尚未配置',503);
  if(typeof code!=='string'||!/^\d{6}$/.test(code))fail('INVALID_CODE','请输入 6 位验证码');
  const result=store.transaction(()=>{
    const challenge=store.db.prepare('SELECT * FROM auth_challenges WHERE handle=?').get(handle);
    if(!challenge||challenge.expires<Date.now()||challenge.attempts>=5)fail('INVALID_CODE','验证码无效或已过期，请重新获取');
    const actual=Buffer.from(digest(handle,code,config),'hex'),expected=Buffer.from(challenge.code_digest,'hex');
    if(!timingSafeEqual(actual,expected)){
      store.db.prepare('UPDATE auth_challenges SET attempts=attempts+1 WHERE handle=?').run(handle);
      // Keep the failed attempt even though login itself is not committed.
      return {invalid:true};
    }
    store.db.prepare('DELETE FROM auth_challenges WHERE handle=?').run(handle);
    let user=store.db.prepare('SELECT * FROM users WHERE handle=?').get(handle);
    const created=!user;
    if(!user){
      const userId=id(),name=channel==='email'?handle.split('@')[0].slice(0,60):'新朋友';
      store.db.prepare('INSERT INTO users VALUES(?,?,?,?,?)').run(userId,handle,passwordHash(randomBytes(48).toString('base64url')),name,now());
      user=store.db.prepare('SELECT * FROM users WHERE id=?').get(userId);
    }
    if(channel==='email')store.db.prepare('INSERT OR IGNORE INTO verified_emails(email,user_id,verified_at) VALUES(?,?,?)').run(handle,user.id,now());
    const token=randomBytes(32).toString('base64url');
    store.db.prepare('DELETE FROM sessions WHERE expires<?').run(Date.now());
    store.db.prepare('INSERT INTO sessions VALUES(?,?,?)').run(hash(token),user.id,Date.now()+7*86400000);
    return {token,user:store.user(user.id),created};
  });
  if(result.invalid)fail('INVALID_CODE','验证码不正确');
  return result;
}
