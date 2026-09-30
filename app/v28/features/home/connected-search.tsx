"use client";
import {displayTitle,displayAnchor,markdownExcerpt} from "../../core/display-labels";
import {useEffect,useMemo,useRef,useState,type FormEvent} from 'react';
import {ExternalTool} from './external-tools';
import {SemanticSearch,type SemanticResult} from './semantic-search';
import {ChevronRight,Search,SlidersHorizontal,X} from 'lucide-react';
import {useRuntime,entityRef} from '../../core/runtime-context';
import {RootPortal} from '../../legacy/legacy-ui';
import {Action,Field} from '../../core/runtime-panels';
import {VoiceInput} from '../messages/voice-input';
import {AttachmentPicker,type FileRef} from '../live/attachments';
import {objectScreen} from '../../core/object-screen';
import {type Entity,text,statuses} from '../live/types';
import type {Screen} from '../../core/screen';

type Hit={id:string;version:number;type:string;title:string;excerpt:string;anchor:string;origin_id?:string;channels?:string[];condition_status:string;condition_checks:{condition:string;status:string;evidence:string}[]};
type SearchResult={status:string;query_id:string;hits:Hit[];intent:{terms:string[];conditions:string[];uncertainties:string[];interpretation?:string[];after?:string;before?:string}};
const kinds=[['files','文件'],['knowledge','成果与笔记'],['message','消息'],['conversation','会话和群'],['task','任务'],['feed','Agent 朋友圈'],['inbox','收件箱'],['post','社区帖'],['release','作品'],['project','共创项目'],['skill','工具'],['resource','资源'],['memory','本人理解'],['profile','公开资料'],['friend','联系人'],['assist','辅助记录']];
const typeNames=Object.fromEntries([...kinds,['document','文件'],['attachment','附件']]);
const iso=(value:string)=>value&&Number.isFinite(Date.parse(value))?new Date(value).toISOString():undefined;
const matchReason=(hit:Hit)=>hit.channels?.includes('relation')?'与匹配内容有可追溯的来源关联':hit.channels?.includes('semantic')?'内容含义与问题相近，仍需核对':hit.channels?.includes('keyword')?'标题或正文与你输入的关键词对应':hit.channels?.includes('term_expansion')?'与输入词的相关表达对应':'来自当前可访问内容';

export function ConnectedSearch({go,onClose}:{go:(screen:Screen)=>void;onClose:()=>void}){
 const runtime=useRuntime()!,s=runtime.snapshot!,request=runtime.request;
 const storageKey='elfred-search-input:'+s.user.id;
 // A new search never inherits invisible filters from an earlier visit.
 const [query,setQuery]=useState(()=>{try{return String(JSON.parse(sessionStorage.getItem(storageKey)||'{}').query||'').slice(0,300)}catch{return ''}});
 const [draft,setDraft]=useState(query),[space,setSpace]=useState(''),[author,setAuthor]=useState(''),[kind,setKind]=useState(''),[conditions,setConditions]=useState(''),[exclude,setExclude]=useState(''),[after,setAfter]=useState(''),[before,setBefore]=useState(''),[latest,setLatest]=useState(false);
 const [result,setResult]=useState<SearchResult|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[retry,setRetry]=useState(0),[filtersOpen,setFiltersOpen]=useState(false),[files,setFiles]=useState<FileRef[]>([]),[inputText,setInputText]=useState(''),[consent,setConsent]=useState(false),[judgeProvider,setJudgeProvider]=useState('text'),[judgeTask,setJudgeTask]=useState(''),[parseTask,setParseTask]=useState(''),[judgment,setJudgment]=useState<{hits:Hit[]}|null>(null);
 const [semantic,setSemantic]=useState<SemanticResult|null>(null),[semanticId,setSemanticId]=useState('');
 const [followup,setFollowup]=useState(''),[watchId,setWatchId]=useState(''),[watchConsent,setWatchConsent]=useState(false),[watchStarted,setWatchStarted]=useState(false);
 const inputField=useRef<HTMLInputElement>(null),composing=useRef(false);
 const input={query,space:space||undefined,author:author||undefined,types:kind==='files'?['document','attachment']:kind?[kind]:undefined,conditions:conditions.split('\n').map(c=>c.trim()).filter(Boolean),exclude:exclude.split(/[,，]/).map(c=>c.trim()).filter(Boolean),after:iso(after),before:iso(before),latest:latest||undefined};
 const key=JSON.stringify(input),previousScope=useRef(key);
 // Recheck changed permissions/versions without dropping fresh server hits just
 // because a bootstrap module is missing or its snapshot has not caught up yet.
 const revision=useMemo(()=>Object.entries(s.objects).filter(([type])=>['attachment','document','knowledge','task','message','post','release','memory','resource','conversation','skill','profile','friend','feed','inbox','project','assist'].includes(type)).flatMap(([,items])=>items.filter(o=>!o.data.internal_search&&!o.data.search_query_id).map(o=>o.id+':'+o.version)).join('|'),[s.objects]);
 useEffect(()=>{try{sessionStorage.setItem(storageKey,JSON.stringify({query}))}catch{}},[storageKey,query]);
 useEffect(()=>{
  setSemantic(null);setJudgment(null);setError('');
  if(previousScope.current!==key){previousScope.current=key;setSemanticId('');setResult(null);setJudgeTask('');setWatchId('');setWatchConsent(false);setWatchStarted(false);}
  if(!query.trim()){setResult(null);setBusy(false);return;}
  let active=true;const controller=new AbortController();setBusy(true);
  const timer=setTimeout(()=>{void request<SearchResult>('/search',JSON.parse(key),{signal:controller.signal}).then(r=>{if(active)setResult(r)}).catch(e=>{if(active)setError(e instanceof Error?e.message:'搜索暂时失败')}).finally(()=>{if(active)setBusy(false)})},300);
  return()=>{active=false;clearTimeout(timer);controller.abort()};
 },[key,query,retry,revision,request]);
 const task=s.objects.task.find(t=>t.id===judgeTask),run=s.objects.run.find(r=>r.id===task?.data.run_id),runStatus=text(run,'status');
 useEffect(()=>{if(!judgeTask||!['completed','awaiting_review'].includes(runStatus))return;let active=true;void request<{hits:Hit[]}>('/search-judgment',{task_id:judgeTask,...JSON.parse(key),semantic_task_id:semanticId||undefined}).then(r=>{if(active)setJudgment(r)}).catch(e=>{if(active){setJudgment(null);setError(e.message)}});return()=>{active=false}},[judgeTask,run?.version,runStatus,key,semanticId,revision,request]);
 const parsedTask=s.objects.task.find(t=>t.id===parseTask),parsedRun=s.objects.run.find(r=>r.id===parsedTask?.data.run_id),parsed=(parsedRun?.data.receipts||[]) as {output?:unknown;phase?:string}[];
 const parsedText=[...parsed].reverse().find(r=>typeof r.output==='string'&&r.phase!=='review')?.output;
 const start=async(id:string)=>{const ready=await request<Entity>('/objects/'+id);await runtime.command('task.confirm',{...entityRef(ready),confirm:true,model_consent:true});const next=await request<Entity>('/objects/'+id);await runtime.command('run.start',entityRef(next))};
 const hits=judgment?.hits||semantic?.hits||result?.hits||[];
 const resetFilters=()=>{setSpace('');setAuthor('');setKind('');setConditions('');setExclude('');setAfter('');setBefore('');setLatest(false)};
 const chips=[{label:typeNames[kind],value:kind,clear:()=>setKind('')},{label:'会话：'+text(s.objects.conversation.find(c=>c.id===space),'title'),value:space,clear:()=>{setSpace('');setAuthor('')}},{label:'发送者：'+(s.objects.conversation.flatMap(c=>c.members||[]).find(m=>m.id===author)?.name||'已选择'),value:author,clear:()=>setAuthor('')},{label:'从 '+after.replace('T',' '),value:after,clear:()=>setAfter('')},{label:'到 '+before.replace('T',' '),value:before,clear:()=>setBefore('')},{label:'核对条件',value:conditions,clear:()=>setConditions('')},{label:'排除：'+exclude,value:exclude,clear:()=>setExclude('')},{label:'最新版本',value:latest,clear:()=>setLatest(false)}].filter(c=>c.value);
 const directoryQuery=query.toLowerCase().replace(/帮我|查找|搜索|找一下|请|一下/g,'').replace(/[\s\p{P}]/gu,''),directoryMatch=(name:string,purpose:string)=>Boolean(directoryQuery)&&(name+' '+purpose).toLowerCase().replace(/[\s\p{P}]/gu,'').includes(directoryQuery)&&!input.exclude.some(term=>(name+' '+purpose).toLowerCase().includes(term.toLowerCase()));
 const directoryAllowed=!space&&!author&&!after&&!before&&!conditions&&!latest&&(!kind||kind==='skill');
 const entries: {id:string;title:string;description:string;screen:Screen}[]=directoryAllowed?[...(!kind?s.systems.filter(system=>directoryMatch(system.name+' Agent',system.roles.join(' '))).map(system=>({id:'agent:'+system.id,title:system.name+' Agent',description:'打开本人 Agent 对话',screen:{name:'agent',id:(system.id==='advise'?'advisor':system.id) as 'explore'|'advisor'|'create'|'connect'|'execute'} as Screen})):[]),...s.definitions.filter(capability=>directoryMatch(capability.name,capability.purpose)).map(capability=>({id:'builtin:'+capability.id,title:capability.name,description:'内置能力 · '+capability.purpose,screen:{name:'tool-detail',id:'builtin:'+capability.id} as Screen}))]:[];
 const submit=(event:FormEvent)=>{event.preventDefault();if(composing.current)return;setQuery(draft.trim());inputField.current?.blur()};
 const open=async(hit:Hit)=>{try{const object=await request<Entity>('/objects/'+hit.id);if(object.version!==hit.version){setRetry(v=>v+1);setError('内容已更新，正在重新搜索，请打开新结果');return;}let conversations=s.objects.conversation;if(object.type==='message'&&!conversations.some(c=>c.id===object.data.conversation_id)){const parent=await request<Entity>('/objects/'+object.data.conversation_id);conversations=[...conversations,parent];}go(objectScreen(object,hit.excerpt.split('\n')[0],conversations));}catch(e){setResult(prev=>prev?{...prev,hits:prev.hits.filter(h=>h.id!==hit.id)}:prev);setJudgment(null);setSemantic(null);setError(e instanceof Error?e.message:'来源已不可访问')}};
 const applyQueryText=(value:string)=>{const next=value.slice(0,300);setDraft(next);setQuery(next);setInputText('')};
 return <RootPortal>
  <button className="v278-sheet-backdrop elfred-search-backdrop" aria-label="关闭全局搜索" onClick={onClose}/>
  <section className="v278-half-sheet v278-global-search-page elfred-connected-search" role="dialog" aria-modal="true" aria-label="全局搜索">
   <header className="elfred-search-header">
    <div><h2>全局搜索</h2><button type="button" aria-label="关闭" onClick={onClose}><X size={21}/></button></div>
    <form onSubmit={submit} role="search"><label className="elfred-search-input"><Search size={19}/><input ref={inputField} autoFocus type="search" enterKeyHint="search" aria-label="全局搜索" placeholder="搜索人、消息、文件、任务…" maxLength={300} value={draft} onCompositionStart={()=>{composing.current=true}} onCompositionEnd={e=>{composing.current=false;setQuery(e.currentTarget.value)}} onChange={e=>{setDraft(e.target.value);if(!composing.current)setQuery(e.target.value)}} onKeyDown={e=>{if(e.key==='Enter'&&(e.nativeEvent.isComposing||composing.current))e.preventDefault();if(e.key==='Escape')onClose()}}/>{draft&&<button type="button" aria-label="清空搜索词" onClick={()=>{setDraft('');setQuery('');inputField.current?.focus()}}><X size={16}/></button>}</label><button type="submit" disabled={!draft.trim()}>搜索</button></form>
    <div className="elfred-search-toolbar"><span>{chips.length?`已选 ${chips.length} 项条件`:'全部可访问内容'}</span><button type="button" aria-expanded={filtersOpen} onClick={()=>setFiltersOpen(v=>!v)}><SlidersHorizontal size={15}/>筛选</button></div>
    {!!chips.length&&<div className="elfred-search-chips">{chips.map((chip,i)=><button key={i} type="button" onClick={chip.clear} aria-label={'移除筛选：'+chip.label}>{chip.label}<X size={12}/></button>)}<button type="button" onClick={resetFilters}>清除全部筛选</button></div>}
   </header>
   <div className="elfred-search-body">
    {filtersOpen&&<section className="elfred-search-filters" aria-label="搜索筛选">
     <label className="v277-field">对象类型<select value={kind} onChange={e=>setKind(e.target.value)}><option value="">全部</option>{kinds.map(([v,n])=><option key={v} value={v}>{n}</option>)}</select></label>
     <label className="v277-field">所在会话<select value={space} onChange={e=>{setSpace(e.target.value);setAuthor('')}}><option value="">全部授权范围</option>{s.objects.conversation.map(c=><option key={c.id} value={c.id}>{displayTitle(text(c,'title'),'')}</option>)}</select></label>
     <label className="v277-field">发送者<select value={author} onChange={e=>setAuthor(e.target.value)}><option value="">不限发送者</option>{[...new Map(s.objects.conversation.filter(c=>!space||c.id===space).flatMap(c=>c.members||[]).map(m=>[m.id,m])).values()].map(m=><option key={m.id} value={m.id}>{m.name} · @{m.handle}</option>)}</select></label>
     <Field name="开始时间（消息发送时间）" type="datetime-local" value={after} onChange={setAfter}/><Field name="结束时间（不含）" type="datetime-local" value={before} onChange={setBefore}/><Field name="必须核对的条件，每行一条" area value={conditions} onChange={setConditions}/><Field name="排除关键词，用逗号分开" value={exclude} onChange={setExclude}/>
     <label><input type="checkbox" checked={latest} onChange={e=>setLatest(e.target.checked)}/>只看最新有效版本</label><button type="button" className="elfred-search-done" onClick={()=>setFiltersOpen(false)}>完成筛选</button>
    </section>}
    {!query.trim()&&<section className="elfred-search-welcome"><Search size={30}/><h3>想找什么？</h3><p>输入名称、关键词，或描述你记得的内容。</p><p>可以试试“首页方案”或“上周的报名说明”。</p></section>}
    {busy&&<p className="elfred-search-note" role="status">正在理解需求、检索内容并整理匹配…</p>}
    {error&&<section role="alert" className="elfred-search-notice"><p>{error}</p><button onClick={()=>setRetry(v=>v+1)}>重试</button></section>}
    {result?.status==='needs_clarification'&&<section className="elfred-search-notice"><h3>还需要确认一项条件</h3>{result.intent.uncertainties.map((item,i)=><p key={i}>{item}</p>)}<button type="button" onClick={()=>setFiltersOpen(true)}>选择会话、发送者或时间</button></section>}
    {result?.status==='complete'&&<>
     <div className="elfred-search-summary"><span>{hits.length||entries.length?`找到 ${hits.length+entries.length} 条相关内容`:'没有找到相关内容'}</span>{!!result.intent.interpretation?.length&&<small>{result.intent.interpretation.join('；')}</small>}</div>
     {!hits.length&&!entries.length&&!error&&<section className="elfred-search-empty"><p>{chips.length?'当前筛选条件下没有结果。':'试试更短的关键词，或内容中的其他词。'}</p>{!!chips.length&&<button type="button" onClick={resetFilters}>清除筛选，重新搜索</button>}<p>仅搜索当前可访问的内容；网页搜索需单独启动。</p></section>}
     <div className="elfred-query-results">{hits.map(hit=><article key={hit.id}>
      <button type="button" className="elfred-search-hit" disabled={busy} onClick={()=>void open(hit)}><span className="elfred-search-type">{typeNames[hit.type]||'资料'}</span><span className="elfred-search-copy"><b>{displayTitle(hit.title,'')||'未命名内容'}</b><span>{markdownExcerpt(hit.excerpt)}</span><small>匹配理由：{matchReason(hit)}</small>{judgment&&<small>{hit.condition_status==='satisfied'?'符合核对条件':hit.condition_status==='unsatisfied'?'不满足核对条件':'条件尚待核对'}</small>}</span><ChevronRight size={17}/></button>
      <details className="elfred-search-hit-more"><summary>依据与操作</summary><p>来源定位：{displayAnchor(hit.anchor)} · {new Date(s.objects[hit.type as keyof typeof s.objects]?.find(item=>item.id===hit.id)?.updated||s.server_time).toLocaleDateString('zh-CN')}</p>{hit.condition_checks.map((c,i)=><p key={i}>{c.condition}：{c.status==='satisfied'?'有证据':c.status==='unsatisfied'?'不满足':'待核对'} {c.evidence}</p>)}<div><button type="button" onClick={()=>void open(hit)}>查看</button><Action run={()=>runtime.command('inbox.create',{object_id:hit.id})}>收藏到收件箱</Action><Action run={async()=>{const object=await request<Entity>('/objects/'+hit.id);if(object.version!==hit.version)throw new Error('来源已变化，请重新搜索');const r=await runtime.command('task.create',{goal:'依据资料继续处理：'+query,system:'explore',source_refs:[entityRef(object)]});go({name:'task',id:r.id})}}>转为任务</Action>{hit.origin_id&&<button onClick={()=>void request<Entity>('/objects/'+hit.origin_id).then(o=>go(objectScreen(o,undefined,s.objects.conversation))).catch(e=>setError(e.message))}>查看来源关系</button>}</div></details>
     </article>)}</div>
     {!!entries.length&&<div className="elfred-query-results elfred-search-directory">{entries.map(entry=><article key={entry.id}><button type="button" className="elfred-search-hit" disabled={busy} onClick={()=>go(entry.screen)}><span className="elfred-search-type">入口</span><span className="elfred-search-copy"><b>{displayTitle(entry.title,'')}</b><span>{entry.description}</span></span><ChevronRight size={17}/></button></article>)}</div>}
    </>}
    <details className="elfred-search-input-options"><summary>用图片、文件或语音搜索</summary><VoiceInput onText={setInputText}/><AttachmentPicker value={files} onChange={setFiles}/>{files.map(file=><div key={file.id}><Action run={async()=>{if(/^(image|audio)\//.test(file.mime)){if(!consent){runtime.report('请先同意本次识别调用');return;}const r=await runtime.command('attachment.analyze',{id:file.id});setParseTask(r.id);await start(r.id)}else{const r=await request<{text:string}>('/search-input',{id:file.id});setInputText(r.text.slice(0,300))}}}>解析 {file.name}</Action></div>)}<label><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>同意识别本次图片或语音，使用本人额度</label>{parsedTask&&<p>{statuses[text(parsedTask,'status')]}</p>}{typeof parsedText==='string'&&<button onClick={()=>setInputText(parsedText.slice(0,300))}>核对识别出的文字</button>}</details>
    {inputText&&<section className="v277-edit-card"><Field name="核对后作为查询输入" area value={inputText} onChange={setInputText}/><button onClick={()=>applyQueryText(inputText)}>使用这段文字搜索</button><p>查询附件不会自动保存为长期知识。</p></section>}
    {result?.status==='complete'&&<><form className="elfred-search-followup" onSubmit={event=>{event.preventDefault();const next=followup.trim();if(!next)return;applyQueryText(`${query} ${next}`);setFollowup('')}}><label htmlFor="elfred-search-followup">继续追问或缩小范围</label><div><input id="elfred-search-followup" value={followup} maxLength={120} onChange={event=>setFollowup(event.target.value)} placeholder="例如：更偏设计、只看深圳"/><button type="submit" disabled={!followup.trim()}>继续找</button></div></form><details className="elfred-search-advanced"><summary>继续查找与核对条件</summary>
     <SemanticSearch key={key} refreshKey={revision} input={input} go={go} onResults={(next,id)=>{setSemantic(next);if(semanticId!==id){setSemanticId(id);setJudgment(null);setJudgeTask('')}}}/>
     <details><summary>保存本次搜索并持续关注</summary><p>探索 Agent 会按当前问题每天检查一次公开来源，最多 20 次、30 天；不会联系别人或发布到社区。需要单独确认模型调用与本地额度。{s.provider.web_search!=="configured"&&"当前持续联网服务未配置，保存后可待接入时启动。"}</p>{watchStarted?<p role="status">已开始持续关注；有真实新增来源时会进入私人朋友圈。</p>:!watchId?<Action run={async()=>{const created=await runtime.command('observation.create',{goal:`持续关注并核对：${query}`,interval_hours:24,max_checks:20,expires:new Date(Date.now()+30*86400000).toISOString()});setWatchId(created.id)}}>保存为关注任务</Action>:<><label><input type="checkbox" checked={watchConsent} onChange={event=>setWatchConsent(event.target.checked)}/>确认按上述范围调用已配置的联网服务和模型</label><Action disabled={!watchConsent||s.provider.web_search!=="configured"} run={async()=>{const watch=await request<Entity>('/objects/'+watchId);await runtime.command('observation.start',{...entityRef(watch),confirm:true,model_consent:true});setWatchStarted(true)}}>开始持续关注</Action></>}</details>
     <details><summary>核对候选是否满足要求</summary><p>确认后，文字模型最多核对 20 项，Jev 最多 5 项。仅发送本次问题和可读候选，预留 1000 本地调用额度。没有证据的条件仍标记为待核对。</p><label className="v277-field">核对服务<select value={judgeProvider} disabled={Boolean(judgeTask)} onChange={e=>setJudgeProvider(e.target.value)}><option value="text">文字模型{s.provider.configured?'':' · 未配置'}</option><option value="jev">Jev{s.provider.jev==='configured'?'':' · 未配置'}</option></select></label><Action disabled={!hits.length||Boolean(judgeTask)||busy} run={async()=>{const r=await runtime.command('search.judge',{...input,provider:judgeProvider,semantic_task_id:semanticId||undefined,query_id:result.query_id,candidates:hits.slice(0,judgeProvider==='jev'?5:20).map(h=>({id:h.id,version:h.version})),confirm:true,model_consent:true});setJudgeTask(r.task_id||r.id)}}>确认核对本次候选</Action>{task&&<p>{statuses[text(task,'status')]} <button onClick={()=>go({name:'task',id:task.id})}>查看运行或停止</button></p>}</details>
     <ExternalTool operation="web_search" goal={query} go={go}/>
    </details></>}
   </div>
  </section>
 </RootPortal>;
}
