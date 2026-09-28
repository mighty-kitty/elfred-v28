"use client";
import {useEffect,useState,type FormEvent} from 'react';
import {useRuntime} from './runtime-context';
import {displayError} from './display-labels';

export function AccountForm({identifier,onBack}:{identifier:string;onBack:()=>void}){
  const runtime=useRuntime()!;
  const isEmail=identifier.includes('@');
  const [register,setRegister]=useState(false),[password,setPassword]=useState(''),[confirmation,setConfirmation]=useState(''),[emailCode,setEmailCode]=useState(''),[emailReady,setEmailReady]=useState<boolean|null>(null),[emailStatusError,setEmailStatusError]=useState(false),[codeSent,setCodeSent]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  useEffect(()=>{let active=true;void runtime.request<{configured:boolean}>('/auth/email/status').then(result=>{if(active)setEmailReady(result.configured)}).catch(()=>{if(active)setEmailStatusError(true)});return()=>{active=false}},[runtime.request]);
  const submit=async(event:FormEvent)=>{
    event.preventDefault();if(busy)return;
    if(register&&password!==confirmation){setError('两次密码不一致，请重新输入');return;}
    if(register&&isEmail&&emailReady&& !/^\d{6}$/.test(emailCode)){setError('请输入邮件中的 6 位验证码');return;}
    setError('');setBusy(true);
    try{await runtime.login(identifier,password,register,register&&isEmail&&emailReady?emailCode:undefined)}
    catch(reason){setError(reason instanceof Error?displayError(reason.message):'暂时无法连接，请重试')}
    finally{setBusy(false)}
  };
  const sendCode=async()=>{
    if(busy)return;setError('');setBusy(true);
    try{await runtime.request('/auth/email/request',{email:identifier});setEmailCode('');setCodeSent(true)}
    catch(reason){setError(reason instanceof Error?displayError(reason.message):'验证邮件未能发送，请重试')}
    finally{setBusy(false)}
  };
  const changeMode=(value:boolean)=>{setRegister(value);setError('');runtime.clearError();setConfirmation('')};
  return <main className="v280-onboarding-page">
    <header className="v277-app-header"><button type="button" className="v277-icon-button" aria-label="返回账号输入" disabled={busy} onClick={onBack}>←</button><h1>{register?'创建 Elfred 账号':'登录 Elfred'}</h1></header>
    <section className="v280-step-copy"><h2>{identifier}</h2><p>{emailStatusError?'暂时无法检查邮箱验证服务，请检查网络后重试。':register&&isEmail&&emailReady?'用邮件验证码确认邮箱，再设置密码。':isEmail&&emailReady===false?'当前发件服务未配置，可暂用密码登录或创建未验证账号。':'用密码登录。'}</p></section>
    <form className="v280-login-form" onSubmit={event=>void submit(event)}>
      <div className="v280-auth-tabs" role="group" aria-label="账号操作"><button type="button" className={register?'v277-secondary':'v277-primary'} aria-pressed={!register} disabled={busy} onClick={()=>changeMode(false)}>登录</button><button type="button" className={register?'v277-primary':'v277-secondary'} aria-pressed={register} disabled={busy} onClick={()=>changeMode(true)}>注册新账号</button></div>
      {register&&isEmail&&emailReady&&<label><span>邮箱验证码（10 分钟有效）</span><div className="v280-email-code-row"><input type="text" inputMode="numeric" pattern="[0-9]{6}" aria-label="邮箱验证码" autoComplete="one-time-code" maxLength={6} value={emailCode} onChange={event=>{setEmailCode(event.target.value.replace(/\D/g,''));setError('')}}/><button type="button" className="v277-secondary" disabled={busy} onClick={()=>void sendCode()}>{codeSent?'重新发送':'发送验证码'}</button></div>{codeSent&&<small>已向邮件服务提交发送请求，请查看收件箱和垃圾邮件；重发需间隔 1 分钟。</small>}</label>}
      <label><span>密码（8—128 位）</span><input type="password" aria-label="账号密码" minLength={8} maxLength={128} required value={password} autoComplete={register?'new-password':'current-password'} onChange={event=>{setPassword(event.target.value);setError('')}}/></label>
      {register&&<label><span>再次输入密码</span><input type="password" aria-label="确认密码" minLength={8} maxLength={128} required value={confirmation} autoComplete="new-password" onChange={event=>{setConfirmation(event.target.value);setError('')}}/></label>}
      {error&&<p role="alert">{error}{/已注册/.test(error)&&<button type="button" className="v-text" onClick={()=>changeMode(false)}>去登录</button>}</p>}
      <button type="submit" className="v277-primary" disabled={busy||password.length<8||register&&(!confirmation||emailReady===null||isEmail&&emailReady&&!/^\d{6}$/.test(emailCode))}>{busy?'正在处理…':register?'创建账号并继续':'登录并继续'}</button>
    </form>
  </main>;
}
