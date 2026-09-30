import {fail,now,hash} from './store.mjs';
import {bounded,string,enumeration} from './policy.mjs';
import {externalToolCommand} from './external-tools.mjs';
import {taskCommand} from './runtime.mjs';
import {readRss,validatedFeedUrl} from './rss.mjs';
import {discoveryRelevance} from './discovery-policy.mjs';
import {feedDensity} from './feed-density.mjs';

const activeRuns=['queued','running','pause_requested','cancel_requested'];
const success=['completed','awaiting_acceptance','awaiting_review'];
export function observationUsage(store,watch){
 const tasks=store.list('task').filter(t=>t.owner===watch.owner&&t.data.observation_id===watch.id);
 return tasks.reduce((total,task)=>{const unknown=Boolean(store.db.prepare("SELECT id FROM usage WHERE task_id=? AND status='unknown'").get(task.id));return {tokens:total.tokens+(task.data.tokens||0),reserved_tokens:total.reserved_tokens+(unknown?Math.max(0,task.data.stop.maxTokens-(task.data.tokens||0)):0),units:total.units+(task.data.units||0),unknown:total.unknown||unknown};},{tokens:0,reserved_tokens:0,units:0,unknown:false});
}
function requestStop(store,watch){
 const task=store.get(watch.data.task_id),run=store.get(task?.data.run_id||null);
 if(run&&['queued','running'].includes(run.data.status))store.update(run,{...run.data,status:'pause_requested'},watch.owner);
}
function knownSources(citations){
 return [...new Set(citations.flatMap(c=>{try{const u=new URL(c.url);if(!['http:','https:'].includes(u.protocol))return [];u.hash='';for(const key of [...u.searchParams.keys()])if(/^utm_|^(fbclid|gclid)$/i.test(key))u.searchParams.delete(key);u.searchParams.sort();return [u.href]}catch{return []}}))].sort();
}
export function observationCommand(store,user,action,input){
 if(action==='observation.create'){
  const goal=string(input.goal,'持续关注的问题',3000),interval=bounded(input.interval_hours,'检查间隔（小时）',1,168),checks=bounded(input.max_checks,'最多检查次数',1,20),expires=Date.parse(input.expires);
  if(!Number.isFinite(expires)||expires<=Date.now()||expires>Date.now()+30*86400000)fail('INVALID_INPUT','观察期限需在未来 30 天内');
  if(store.visible(user,'observation').filter(w=>['draft','active','paused','blocked'].includes(w.data.status)).length>=20)fail('OBSERVATION_LIMIT','请先结束不再需要的观察');
  const source_url=input.source_url?validatedFeedUrl(input.source_url):null;
  if(source_url&&checks<2)fail('INVALID_INPUT','RSS 订阅至少检查 2 次：首次建立基线，之后才发布新发现');
  const keywords=source_url?String(input.keywords||'').split(/[,，\n]/).map(word=>word.trim()).filter(Boolean):[];
  if(source_url&&(!keywords.length||keywords.length>12||keywords.some(word=>word.length>50)))fail('INVALID_INPUT','RSS 订阅需填写 1—12 个关注词，每项不超过 50 字');
  const system=source_url?enumeration(input.system||'explore',['explore','advise','create','connect','execute'],'负责 Agent'):'explore';
  return {id:store.add('observation',user,{goal,title:goal.slice(0,80),interval_hours:interval,max_checks:checks,limit_units:source_url?0:checks*1000,max_tokens:source_url?0:checks*24000,expires,status:'draft',checks:0,seen_sources:[],seen_items:[],baseline:false,task_id:null,processed_task_id:null,next_at:null,scope:source_url?'rss_new_items':'public_web_new_sources',source_url,keywords,system}).id};
 }
 if(!action.startsWith('observation.'))return null;
 const watch=store.expect(store.owned(user,input.id,'observation'),input.version);
 if(action==='observation.pause'||action==='observation.stop'){
  if(!['draft','active','paused','blocked'].includes(watch.data.status))fail('INVALID_STATE','观察已结束');
  requestStop(store,watch);
  return {id:store.update(watch,{...watch.data,status:action.endsWith('stop')?'ended':'paused'},user).id};
 }
 if(action==='observation.start'){
  if(!['draft','paused','blocked'].includes(watch.data.status))fail('INVALID_STATE','当前观察不能启动');
  if(input.confirm!==true||!watch.data.source_url&&input.model_consent!==true)fail('CONSENT_REQUIRED','请确认信息源、公开互联网范围、频率、期限和总额度');
  if(watch.data.source_url){
   if(!watch.data.auto_managed&&(watch.data.expires<=Date.now()||watch.data.checks>=watch.data.max_checks))fail('STOP_LIMIT','订阅已到期限或检查次数上限');
   return {id:store.update(watch,{...watch.data,status:'active',next_at:Date.now(),authorized_at:now(),last_error:null},user).id};
  }
  const task=store.get(watch.data.task_id),run=store.get(task?.data.run_id||null);
  const finishOnly=task&&run&&success.includes(task.data.status)&&watch.data.processed_task_id!==task.id;
  if(!finishOnly&&(watch.data.expires<=Date.now()||watch.data.checks>=watch.data.max_checks))fail('STOP_LIMIT','观察已到期限或检查次数上限，请另建新的观察范围');
  if(run&&activeRuns.includes(run.data.status))fail('RUN_ACTIVE','上次检查尚未停止，请稍后刷新');
  const used=observationUsage(store,watch);
  if(used.unknown)fail('RECONCILIATION_REQUIRED','请在检查任务中核对未知用量，再继续观察');
  if(!finishOnly&&(used.tokens+used.reserved_tokens>=watch.data.max_tokens||used.units>=watch.data.limit_units))fail('STOP_LIMIT','观察已达到累计用量上限，不能通过恢复重置额度');
  return {id:store.update(watch,{...watch.data,status:'active',next_at:Date.now(),authorized_at:now(),last_error:null,...(task&&run&&!success.includes(task.data.status)?{processed_task_id:task.id}:{})},user).id};
 }
 return null;
}

// A single bounded check per due window: downtime does not accumulate catch-up calls.
// Each check is a regular task with its own receipts and the existing account budget gate.
export function tickObservations(store,provider,at=Date.now()){
 for(const candidate of store.list('observation').filter(w=>!w.data.source_url&&(w.data.status==='active'||(w.data.task_id&&w.data.processed_task_id!==w.data.task_id)))){
  try{store.transaction(()=>{
   let watch=store.get(candidate.id);
   const user=watch.owner,task=store.get(watch.data.task_id),run=store.get(task?.data.run_id||null);
   if(task&&watch.data.processed_task_id!==task.id){
    if(!run||activeRuns.includes(run.data.status)){
     if(watch.data.status==='active'&&watch.data.expires<=at){requestStop(store,watch);store.update(watch,{...watch.data,status:'expired'},user);}return;
    }
    if(success.includes(task.data.status)&&run.data.receipts?.some(r=>r.status==='succeeded')){
     const receipts=run.data.receipts.filter(r=>r.status==='succeeded'),urls=knownSources(receipts.flatMap(r=>r.citations||[])),added=urls.filter(url=>!watch.data.seen_sources.includes(url));
     if((watch.data.baseline||watch.data.auto_suggested)&&added.length){
      const initial=watch.data.auto_suggested&&!watch.data.baseline;
      const sourceSummary=String(receipts.find(r=>typeof r.output==='string')?.output||'').trim().slice(0,900);
      const event=store.unique('feed','observation:'+task.id,()=>store.add('feed',user,{title:initial?'探索 Agent 找到与你方向相关的公开线索':'关注的问题有新增来源',summary:initial?(sourceSummary||`根据初始化选择找到 ${added.length} 个公开来源，请打开核对。`):`「${watch.data.goal.slice(0,150)}」检索到 ${added.length} 个此前未见的公开来源。需要你核对相关性和事实。`,system:'explore',topic:initial?'初始化方向':'持续关注',status:'active',purpose:'observation',event_key:task.id,task_id:task.id,source_refs:[{id:run.id}],citations:receipts.flatMap(r=>r.citations||[]).filter(c=>knownSources([c]).some(u=>added.includes(u))),reason:initial?'来自本人初始化偏好和已确认的公开检索；仅有真实来源时发布':'来自本人授权的周期联网检查，仅按来源网址去重',personal_value:watch.data.goal,uncertainty:'搜索结果是待核对线索，不代表用户已选择方向或事实已验证',comments:[],attachments:[]}));
      store.unique('notification',event.id,()=>store.add('notification',user,{kind:'observation_change',target_id:task.id,status:'unread',summary:'持续关注发现新增公开来源'}));
     }
     watch=store.update(watch,{...watch.data,processed_task_id:task.id,baseline:true,seen_sources:[...new Set([...watch.data.seen_sources,...urls])],last_checked_at:now(),last_new_sources:added.length,last_error:null},user);
    }else{
     store.update(watch,{...watch.data,status:watch.data.status==='active'?'blocked':watch.data.status,processed_task_id:task.id,last_error:run.data.error?.message||'上次检查没有完成，请查看记录并核对后恢复'},user);return;
    }
   }
   if(watch.data.status!=='active')return;
   if(watch.data.expires<=at||watch.data.checks>=watch.data.max_checks){store.update(watch,{...watch.data,status:watch.data.expires<=at?'expired':'completed'},user);return;}
   if(watch.data.next_at>at)return;
   if(provider.status().web_search!=='configured'){
    store.update(watch,{...watch.data,status:'blocked',last_error:'联网检索服务未配置，尚未发出检查请求'},user);return;
   }
   const used=observationUsage(store,watch),remainingTokens=watch.data.max_tokens-used.tokens-used.reserved_tokens;
   if(used.unknown||remainingTokens<=0||used.units+1000>watch.data.limit_units){store.update(watch,{...watch.data,status:'blocked',last_error:used.unknown?'存在未知用量，请先核对供应商记录':'观察累计用量达到上限，不能继续调用'},user);return;}
   const account=store.db.prepare('SELECT * FROM budget_accounts WHERE owner=?').get(user);
   if(!account||account.reserved+account.spent+1000>account.limit_units){store.update(watch,{...watch.data,status:'blocked',last_error:'账户剩余额度不足，补充后由本人恢复'},user);return;}
   const prepared=externalToolCommand(store,user,'external.prepare',{operation:'web_search',goal:watch.data.goal});
   let next=store.get(prepared.id);next=store.update(next,{...next.data,stop:{...next.data.stop,maxTokens:Math.min(24000,remainingTokens)},observation_id:watch.id,internal_search:true},user);
   taskCommand(store,user,'task.confirm',{id:next.id,version:next.version,confirm:true,model_consent:true});next=store.get(next.id);
   taskCommand(store,user,'run.start',{id:next.id,version:next.version});
   store.update(watch,{...watch.data,task_id:next.id,checks:watch.data.checks+1,next_at:at+watch.data.interval_hours*3600000},user);
  });}catch(error){store.transaction(()=>{const watch=store.get(candidate.id);if(watch?.data.status==='active')store.update(watch,{...watch.data,status:'blocked',last_error:error.code?error.message:'观察暂时停止，请核对检查记录'},watch.owner);});}
 }
}

// RSS polling is source based and does not call a model. It only publishes
// owner-selected keyword matches as unverified leads, with the original URL.
export async function tickRssObservations(store,reader=readRss,at=Date.now()){
 const due=store.list('observation').filter(w=>w.data.source_url&&w.data.status==='active'&&Number(w.data.next_at)<=at).slice(0,1);
 for(const candidate of due){
  if(store.visible(candidate.owner,'settings')[0]?.data.agents?.[candidate.data.system]?.enabled===false){store.transaction(()=>{const watch=store.get(candidate.id);if(watch?.data.status==='active')store.update(watch,{...watch.data,status:'paused',last_error:'负责 Agent 已停用，资讯发现已暂停'},watch.owner)});continue;}
  if((candidate.data.expires<=at||candidate.data.checks>=candidate.data.max_checks)&&!candidate.data.auto_managed){
   store.transaction(()=>{const w=store.get(candidate.id);if(w?.data.status==='active')store.update(w,{...w.data,status:w.data.expires<=at?'expired':'completed'},w.owner)});continue;
  }
  let items;
  try {
   const urls=(candidate.data.auto_suggested?candidate.data.source_urls:null)||[candidate.data.source_url];
   const results=await Promise.allSettled(urls.slice(0,3).map(async url=>(await reader(url)).map(item=>({...item,discovered_from:url}))));
   const successful=results.filter(result=>result.status==='fulfilled');
   if(!successful.length)throw new Error('No feed available');
   items=[...new Map(successful.flatMap(result=>result.value).map(item=>[item.url,item])).values()];
  }
  catch { store.transaction(()=>{const w=store.get(candidate.id);if(w?.data.status==='active'&&w.version===candidate.version){const failures=(w.data.failures||0)+1;store.update(w,{...w.data,status:w.data.auto_managed?'active':'blocked',failures,next_at:at+Math.min(86400000,900000*2**Math.min(failures-1,7)),last_error:w.data.auto_managed?'资讯来源暂时无法读取，将自动重试；本次没有发布动态':'RSS 来源暂时无法读取，请核对地址后继续；本次没有发布动态'},w.owner)}});continue; }
  store.transaction(()=>{
   const watch=store.get(candidate.id);
   if(!watch||watch.data.status!=='active'||watch.version!==candidate.version||(!watch.data.auto_managed&&watch.data.expires<=Date.now()))return;
   const settings=store.visible(watch.owner,'settings')[0],density=feedDensity(settings,watch.data.system);
   const seen=new Set(watch.data.seen_items||[]),seenUrls=new Set(watch.data.seen_urls||[]),fresh=items.filter(item=>!seenUrls.has(hash(item.url))&&(watch.data.auto_suggested||!seen.has(item.id)));
   const candidates=watch.data.auto_suggested?fresh.slice(0,density.candidates):fresh;
   const interests=watch.data.interests||[];
   const localDay=value=>new Intl.DateTimeFormat('sv-SE',{timeZone:settings?.data.timezone||'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(value));
   const today=localDay(at),postedToday=watch.data.auto_suggested?store.visible(watch.owner,'feed').filter(item=>item.data.purpose==='discovery'&&localDay(item.created)===today).length:0;
   const limit=watch.data.auto_suggested?Math.min(watch.data.baseline?density.perCheck:3,Math.max(0,density.dailyMax-postedToday)):5;
   const matches=(watch.data.auto_suggested?(interests.length?candidates.filter(item=>discoveryRelevance(item,interests)>0).sort((a,b)=>discoveryRelevance(b,interests)-discoveryRelevance(a,interests)):candidates):candidates.filter(item=>watch.data.keywords.some(word=>(item.title+' '+item.summary).toLocaleLowerCase().includes(word.toLocaleLowerCase())))).slice(0,limit);
   if((watch.data.baseline||watch.data.auto_suggested)&&store.visible(watch.owner,'settings')[0]?.data.agents?.[watch.data.system]?.enabled!==false){
    for(const item of [...matches].reverse())store.unique('feed',`${watch.owner}:rss:${hash(item.url)}`,()=>store.add('feed',watch.owner,{title:item.title,summary:item.summary||'查看原始来源并核对内容。',system:watch.data.system,topic:watch.data.auto_suggested?'初始化方向':watch.data.goal.slice(0,100),status:'active',purpose:'discovery',event_key:`rss:${watch.id}:${hash(item.id)}`,task_id:null,source_subscription_id:watch.id,external_url:item.url,published_at:item.published_at,source_name:new URL(item.discovered_from||watch.data.source_url).hostname,source_refs:[],reason:watch.data.auto_suggested?'Agent 根据初始化偏好选择公开资讯查询，取得真实 RSS 条目；相关性仍需核对':'来自你授权的 RSS 来源，标题或摘要命中关注词',personal_value:watch.data.goal,uncertainty:'订阅标题和摘要仅是线索，事实与行动条件仍需核对原文',comments:[],attachments:[]}));
   }
   const checks=watch.data.checks+1;
   store.update(watch,{...watch.data,checks,baseline:true,seen_items:[...new Set([...candidates.map(item=>item.id),...seen])].slice(0,300),seen_urls:[...new Set([...candidates.map(item=>hash(item.url)),...seenUrls])].slice(0,300),last_candidate_count:candidates.length,last_checked_at:now(),last_new_sources:matches.length,next_at:at+(watch.data.auto_suggested?density.intervalHours:watch.data.interval_hours)*3600000,status:watch.data.auto_managed||checks<watch.data.max_checks?'active':'completed',failures:0,last_error:null},watch.owner);
  });
 }
}
