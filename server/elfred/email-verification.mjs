import {createHmac,randomBytes,randomInt,timingSafeEqual} from 'node:crypto';
import {fail,hash,now} from './store.mjs';

// Pending codes may expire on restart when no persistent signing secret is configured.
const processSecret=randomBytes(32).toString('hex');
const emailPattern=/^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?)+$/;
export const emailConfigured=config=>Boolean(config.ELFRED_RESEND_API_KEY&&config.ELFRED_EMAIL_FROM);
export function canonicalEmail(value){
 const email=typeof value==='string'?value.trim().toLowerCase():'';
 if(email.length>80||!emailPattern.test(email))fail('INVALID_EMAIL','请输入有效的邮箱地址');
 return email;
}
const codeDigest=(email,code,config)=>createHmac('sha256',config.ELFRED_EMAIL_CODE_SECRET||processSecret).update(`${email}:${code}`).digest('hex');
function emailLimit(store,key,max,time){
 const row=store.db.prepare('SELECT count,until FROM login_attempts WHERE key=?').get(key);
 if(row&&row.until>time&&row.count>=max)fail('RATE_LIMIT','请求过于频繁，请稍后再试',429);
 store.db.prepare('INSERT INTO login_attempts VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=CASE WHEN until<? THEN 1 ELSE count+1 END,until=CASE WHEN until<? THEN excluded.until ELSE until END').run(key,time+900000,time,time);
}
export async function requestEmailCode(store,value,client,config=process.env,fetcher=fetch){
 const email=canonicalEmail(value);
 if(!emailConfigured(config))fail('EMAIL_NOT_CONFIGURED','邮箱验证服务尚未配置，请暂用密码注册',503);
 if(store.db.prepare('SELECT 1 FROM users WHERE handle=?').get(email))fail('ACCOUNT_EXISTS','该邮箱已注册，请用密码登录',409);
 const time=Date.now();
 const code=String(randomInt(0,1000000)).padStart(6,'0'),requestId=randomBytes(16).toString('hex');
 store.transaction(()=>{
  const current=store.db.prepare('SELECT requested_at FROM email_challenges WHERE email=?').get(email);
  if(current&&time-current.requested_at<60000)fail('RATE_LIMIT','请等待 1 分钟后重发',429);
  emailLimit(store,'email-send:'+hash(email),5,time);
  emailLimit(store,'email-send-ip:'+hash(client||'unknown'),20,time);
  store.db.prepare('INSERT INTO email_challenges(email,code_digest,expires,requested_at,attempts,request_id) VALUES(?,?,?,?,0,?) ON CONFLICT(email) DO UPDATE SET code_digest=excluded.code_digest,expires=excluded.expires,requested_at=excluded.requested_at,attempts=0,request_id=excluded.request_id').run(email,codeDigest(email,code,config),time+600000,time,requestId);
 });
 try{
  const response=await fetcher('https://api.resend.com/emails',{method:'POST',headers:{Authorization:`Bearer ${config.ELFRED_RESEND_API_KEY}`,'Content-Type':'application/json'},body:JSON.stringify({from:config.ELFRED_EMAIL_FROM,to:[email],subject:'Elfred 邮箱验证码',text:`你的 Elfred 邮箱验证码是 ${code}。10 分钟内有效。如果不是你本人操作，请忽略这封邮件。`}),signal:AbortSignal.timeout(10000)});
  if(!response.ok)throw new Error('email provider rejected request');
  const receipt=await response.json();if(!receipt?.id)throw new Error('email provider returned no receipt');
 }catch{
  store.db.prepare('DELETE FROM email_challenges WHERE email=? AND request_id=?').run(email,requestId);
  fail('EMAIL_SEND_FAILED','验证邮件未能发送，请稍后重试',502);
 }
 return {sent:true,expires_in:600,resend_after:60};
}
export function consumeEmailCode(store,value,code,config=process.env){
 const email=canonicalEmail(value);
 if(!emailConfigured(config))fail('EMAIL_NOT_CONFIGURED','邮箱验证服务尚未配置',503);
 if(typeof code!=='string'||!/^\d{6}$/.test(code))fail('INVALID_EMAIL_CODE','请输入 6 位邮箱验证码');
 const challenge=store.db.prepare('SELECT * FROM email_challenges WHERE email=?').get(email);
 if(!challenge||challenge.expires<Date.now()||challenge.attempts>=5)fail('INVALID_EMAIL_CODE','验证码无效或已过期，请重新获取');
 const actual=Buffer.from(codeDigest(email,code,config),'hex'),expected=Buffer.from(challenge.code_digest,'hex');
 if(!timingSafeEqual(actual,expected)){
  store.db.prepare('UPDATE email_challenges SET attempts=attempts+1 WHERE email=?').run(email);
  fail('INVALID_EMAIL_CODE','验证码不正确');
 }
 store.db.prepare('DELETE FROM email_challenges WHERE email=?').run(email);
 return email;
}
export function markVerifiedEmail(store,email,userId){
 store.db.prepare('INSERT INTO verified_emails(email,user_id,verified_at) VALUES(?,?,?)').run(email,userId,now());
}
