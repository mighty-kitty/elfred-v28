"use client";
import {createClientId} from './client-id';
import {finalReceipts} from './result-output';
import {createContext,useContext,useCallback,useEffect,useRef,useState,type ReactNode} from 'react';
import {createInitialV277State,type V277State,type V277TaskStatus,type V277AgentId} from '../../v27-7-state';
import {type Snapshot,type Entity,type Result,text,statuses} from '../features/live/types';

type RuntimeContextValue={snapshot:Snapshot|null;syncStatus:'current'|'stale';lastSynced:string|null;loading:boolean;error:string;refresh:()=>Promise<void>;request:<T>(path:string,body?:unknown,options?:{signal?:AbortSignal})=>Promise<T>;command:(action:string,input:Record<string,unknown>)=>Promise<Result>;login:(handle:string,password:string,register:boolean)=>Promise<void>;logout:()=>Promise<void>;clearError:()=>void;report:(message:string)=>void};
const Context=createContext<RuntimeContextValue|null>(null);
export const useRuntime=()=>useContext(Context);
export function RuntimeProvider({children}:{children:ReactNode}) {
  const [snapshot,setSnapshot]=useState<Snapshot|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState('');
  const [syncStatus,setSyncStatus]=useState<'current'|'stale'>('current'),[lastSynced,setLastSynced]=useState<string|null>(null);
  const csrf=useRef(''),pending=useRef(new Map<string,string>()),identity=useRef(0),refreshSequence=useRef(0);
  const request=useCallback(async<T,>(path:string,body?:unknown,key?:string|{signal?:AbortSignal}):Promise<T>=>{
    const generation=identity.current;
    const response=await fetch('/api/elfred'+path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:body===undefined?{}:{'Content-Type':'application/json','X-Elfred-Client':'1','X-CSRF-Token':csrf.current,...(typeof key==='string'?{'Idempotency-Key':key}:{})},body:body===undefined?undefined:JSON.stringify(body),signal:typeof key==='object'?key.signal:undefined});
    const result=await response.json() as {error?:{message:string}};
    if(!response.ok){if(response.status===401&&generation===identity.current){identity.current++;setSnapshot(null);csrf.current='';pending.current.clear();}throw new Error(result.error?.message||'操作失败，请重试');}
    return result as T;
  },[]);
  const refresh=useCallback(async()=>{
    const generation=identity.current,sequence=++refreshSequence.current;
    const current=()=>generation===identity.current&&sequence===refreshSequence.current;
    try{const session=await request<{user:unknown;csrf:string|null}>('/session');if(!current())return;
    const next=session.user?await request<Snapshot>('/bootstrap'):null;if(!current())return;
    csrf.current=session.csrf||'';setSnapshot(next);setSyncStatus('current');setLastSynced(next?.server_time||null);}catch(error){if(current())setSyncStatus('stale');throw error;}
  },[request]);
  useEffect(()=>{void refresh().catch(err=>setError(err.message)).finally(()=>setLoading(false));},[refresh]);
  useEffect(()=>{if(!snapshot?.user.id)return;let debounce:ReturnType<typeof setTimeout>|undefined;const update=()=>{if(debounce)clearTimeout(debounce);debounce=setTimeout(()=>{void refresh().catch(err=>setError(err.message))},150)};const events=new EventSource('/api/elfred/events');events.addEventListener('changed',update);const timer=setInterval(update,15000);return()=>{events.close();clearInterval(timer);if(debounce)clearTimeout(debounce)}},[snapshot?.user.id,refresh]);
  const command=useCallback(async(action:string,input:Record<string,unknown>)=>{
    const fingerprint=JSON.stringify({action,input});let key=pending.current.get(fingerprint);if(!key){key=createClientId();pending.current.set(fingerprint,key)}
    try {const result=await request<Result>('/commands',{action,input},key);pending.current.delete(fingerprint);try{await refresh();setError('')}catch{setError('操作已保存，页面同步失败；请刷新查看最新状态。')}return result;}catch(err){setError(err instanceof Error?err.message:'操作失败');throw err}
  },[request,refresh]);
  const login=async(handle:string,password:string,register:boolean)=>{const generation=++identity.current;pending.current.clear();try{const result=await request<{csrf:string}>(register?'/auth/register':'/auth/login',{handle,password,name:handle.split('@')[0]});if(generation!==identity.current)return;csrf.current=result.csrf;await refresh();setError('');}catch(err){if(generation===identity.current)setError(err instanceof Error?err.message:'登录失败');throw err}};
  const logout=async()=>{const generation=++identity.current;await request('/auth/logout',{});if(generation!==identity.current)return;identity.current++;csrf.current='';pending.current.clear();setSnapshot(null)};
  return <Context.Provider value={{snapshot,syncStatus,lastSynced,loading,error,refresh,request,command,login,logout,clearError:()=>setError(''),report:setError}}>{children}</Context.Provider>;
}
export function projectState(snapshot:Snapshot|null,previous?:V277State):V277State {
  const empty=createInitialV277State();
  empty.tasks=[];empty.messages={};empty.memories=[];
  if(!snapshot)return {...empty,phase:previous?.phase==='verify'?'verify':'auth',account:{...empty.account,identifier:previous?.account.identifier||''}};
  const profile=snapshot.objects.profile[0],settings=snapshot.objects.settings[0],onboarding=snapshot.objects.onboarding[0];
  const preferences=settings.data.agents as Record<string,{name:string;focus:string;enabled:boolean}>|undefined;
  const agentSetup=Object.fromEntries(Object.entries(empty.agentSetup).map(([id,config])=>{const saved=preferences?.[id==='advisor'?'advise':id];return [id,saved?{name:saved.name||config.name,focus:saved.focus,enabled:saved.enabled}:config]})) as V277State['agentSetup'];
  const completed=onboarding?.data.status==='completed';
  const canUseHome=completed||Boolean(onboarding?.data.deferred_at);
  const taskStatus:Record<string,V277TaskStatus>={draft:'待确认',ready:'待确认',queued:'进行中',running:'进行中',cancel_requested:'进行中',pause_requested:'进行中',completed:'已完成'};
  const messages:V277State['messages']={};
  for(const message of [...(snapshot.objects.message||[])].sort((a,b)=>Number(a.data.seq)-Number(b.data.seq))) {const conversation=String(message.data.conversation_id);(messages[conversation]||=[]).push({id:message.id,role:message.data.actor_type==='agent'?'assistant':message.owner===snapshot.user.id?'user':'assistant',text:text(message,'text'),time:new Date(message.created).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})});}
  return {...empty,agentSetup,phase:canUseHome?'ready':previous&&['welcome','profile-init','agents-init','complete'].includes(previous.phase)?previous.phase:'welcome',account:{identifier:snapshot.user.handle,provider:'contact',verified:true,onboardingComplete:completed},profile:{...empty.profile,name:text(profile,'name'),username:snapshot.user.handle,bio:text(profile,'bio'),showLevel:profile.data.showLevel===true,role:text(profile,'role'),focus:text(onboarding,'intent'),tags:Array.isArray(profile.data.tags)?profile.data.tags as string[]:[]},notifications:settings.data.notifications===true,quiet:settings.data.quiet===true,profileVisibility:profile.data.public?'public':'private',tasks:snapshot.objects.task.filter(task=>task.data.status!=='archived'&&!task.data.agent_chat).map(task=>{
    const run=snapshot.objects.run.find(item=>item.id===task.data.run_id);
    const allReceipts=(run?.data.receipts||[]) as {output:unknown;phase?:string}[];const receipts=finalReceipts(allReceipts);
    return {id:task.id,title:text(task,'title'),brief:text(task,'goal'),source:'本人确认的目标',agent:(task.data.system==='advise'?'advisor':task.data.system) as V277AgentId,status:taskStatus[text(task,'status')]||'已暂停',nextStep:text(task,'plan_note')||statuses[text(task,'status')]||text(task,'status'),result:receipts.flatMap(receipt=>typeof receipt.output==='string'?[receipt.output]:(receipt.output as {title:string;excerpt:string}[]).map(hit=>hit.title+'：'+hit.excerpt)),knowledgeIds:task.data.artifact_id?[String(task.data.artifact_id)]:[],updatedAt:new Date(task.updated).toLocaleString('zh-CN'),runtimeStatus:text(task,'status')};
  }),messages,memories:snapshot.objects.memory.filter(item=>!['deleted','superseded','rejected'].includes(text(item,'status'))&&!item.data.hidden&&(!item.data.expires_at||Date.parse(text(item,'expires_at'))>Date.now())).map(item=>({id:item.id,group:'偏好',label:text(item,'scope'),value:text(item,'content'),source:'本人记录 / 可核对来源',status:['validated','stable'].includes(text(item,'status'))?'已确认':'待确认'})),savedPostIds:snapshot.objects.interaction.filter(item=>item.data.kind==='save'&&item.data.active).map(item=>text(item,'object_id')),hiddenPostIds:snapshot.objects.interaction.filter(item=>item.data.kind==='hide'&&item.data.active).map(item=>text(item,'object_id'))};
}
export const entityRef=(item:Entity)=>({id:item.id,version:item.version});
