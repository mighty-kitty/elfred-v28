"use client";
import {displayTitle} from "../../core/display-labels";
import {useEffect,useRef,useState} from 'react';
import {ArrowLeft,ChevronRight,Plus,Pin,Play,Layers3} from 'lucide-react';
import {useRuntime,entityRef} from '../../core/runtime-context';
import {Action,Field} from '../../core/runtime-panels';
import {text,type Entity} from '../live/types';
import type {Screen} from '../../core/screen';
import {ParameterEditor,ToolRunInputs,ToolGovernance,type ToolParameter} from './tool-inputs';
import {ToolWorkflow,type ToolStep} from './tool-workflow';
import {BuiltinCapabilities} from './builtin-capabilities';
import {finalReceipts} from '../../core/result-output';
import './tools-page.css';
type Go=(screen:Screen)=>void;
export function ToolsPage({onBack,go,initialId}:{onBack:()=>void;go:Go;initialId?:string}){
 const runtime=useRuntime()!,snapshot=runtime.snapshot!;
 const [tab,setTab]=useState(text(snapshot.objects.skill.find(item=>item.id===initialId),'kind')||'Skill'),[archived,setArchived]=useState(false),[open,setOpen]=useState<Entity|null>(snapshot.objects.skill.find(item=>item.id===initialId)||null),[goal,setGoal]=useState(''),[preview,setPreview]=useState('');
 const [query,setQuery]=useState(''),[showAll,setShowAll]=useState(Boolean(initialId));
 const [sort,setSort]=useState<'recent'|'created'|'frequent'>('recent');
 const [selection,setSelection]=useState(0);
 const restoredTool=useRef<string|null>(null);
 const selectTool=(item:Entity)=>{restoredTool.current=initialId||null;setOpen(item);setGoal('');setSelection(value=>value+1)};
 const selectTab=(kind:string)=>{restoredTool.current=initialId||null;setTab(kind);setOpen(null)};
 const detail=useRef<HTMLElement>(null);
 const openedToolId=open?.id;
 useEffect(()=>{if(openedToolId)detail.current?.scrollIntoView({block:'start',behavior:'smooth'})},[openedToolId,selection]);
 const initialTool=snapshot.objects.skill.find(item=>item.id===initialId);
 useEffect(()=>{
  if(initialId&&initialTool&&restoredTool.current!==initialId){
   restoredTool.current=initialId;setOpen(initialTool);setTab(text(initialTool,'kind')||'Skill');setGoal('');
  }
 },[initialId,initialTool]);
 const pinned=(id:string)=>snapshot.objects.shortcut.some(item=>item.data.skill_id===id&&item.data.pinned);
 const tools=snapshot.objects.skill.filter(item=>(text(item,'title')+' '+text(item,'instructions')).toLowerCase().includes(query.toLowerCase())).filter(item=>(text(item,'kind')||'Skill')===tab&&(archived?item.data.status==='archived':item.data.status!=='archived')).slice().sort((a,b)=>sort==='frequent'?Number(b.data.uses||0)-Number(a.data.uses||0)||text(b,'last_used_at').localeCompare(text(a,'last_used_at')):sort==='created'?b.created.localeCompare(a.created):text(b,'last_used_at').localeCompare(text(a,'last_used_at'))||b.created.localeCompare(a.created));
 const recent=snapshot.objects.skill.filter(item=>item.data.status==='active'&&item.data.last_used_at).sort((a,b)=>text(b,'last_used_at').localeCompare(text(a,'last_used_at'))).slice(0,4);
 const pinnedTools=snapshot.objects.skill.filter(item=>item.data.status==='active'&&pinned(item.id)).slice(0,6);
 const common=tools.filter(item=>item.data.status==='active'&&(pinned(item.id)||['frequent','proficient'].includes(text(item,'mastery'))||Number(item.data.uses||0)>=3)).slice(0,6);
 const directoryVisible=showAll||Boolean(query.trim())||archived;
 return <main className="v277-page v281-tools-page elfred-tools-connected"><header><button aria-label="返回" onClick={onBack}><ArrowLeft size={26}/></button><h1>我的工具</h1><button aria-label="创建工具" style={{left:'auto',right:0}} onClick={()=>go({name:'create-tool'})}><Plus size={23}/></button></header>
 <button type="button" className="elfred-inbox-entry" onClick={()=>go({name:'inbox'})}><span>收件箱</span><small>{snapshot.objects.inbox.filter(item=>item.data.status==='pending').length} 项待整理</small><ChevronRight size={18}/></button>
 {snapshot.objects.skill.length>6&&<Field name="搜索工具" value={query} onChange={setQuery}/>}
 {pinnedTools.length>0&&<section className="v281-recent-tools"><header><h2>置顶工具</h2></header>{pinnedTools.map(item=><button key={item.id} className="v281-recent-card" onClick={()=>selectTool(item)}><span><Pin size={25}/></span><div><h3>{displayTitle(text(item,'title'),'')}</h3></div></button>)}</section>}
 <nav className="v281-tools-tabs">{['Skill','Mini App','Agent'].map(kind=><button key={kind} className={tab===kind?'active':''} onClick={()=>selectTab(kind)}>{kind}</button>)}</nav>
 {directoryVisible&&tab==='Skill'&&!archived&&!query.trim()&&<BuiltinCapabilities go={go} initialId={initialId?.startsWith('builtin:')?initialId.slice(8):undefined}/>}
 <section className="v281-recent-tools"><header><h2>最近使用</h2><button type="button" onClick={()=>setShowAll(true)}>查看全部<ChevronRight size={18}/></button></header>{recent.length?recent.map(item=><button key={item.id} className="v281-recent-card" onClick={()=>selectTool(item)}><span><Layers3 size={28}/></span><div><h3>{displayTitle(text(item,'title'),'')}</h3></div></button>):<p className="v277-empty">使用过的工具会出现在这里。</p>}</section>
 {!directoryVisible&&<section className="v281-all-tools"><h2>常用{tab}</h2><div>{common.map(item=><button key={item.id} onClick={()=>selectTool(item)}><span>{pinned(item.id)?<Pin size={27}/>:<Layers3 size={27}/>}</span><h3>{displayTitle(text(item,'title'),'')}</h3><p>{pinned(item.id)?'已固定':item.data.mastery==='proficient'?'熟练':'常用'}</p><ChevronRight size={20}/></button>)}</div>{!common.length&&<p className="v277-empty">还没有常用{tab}。使用后可在详情中固定到这里。</p>}<button type="button" className="v277-secondary elfred-tools-expand" onClick={()=>setShowAll(true)}>查看全部{tab}与管理</button></section>}
 {directoryVisible&&<section className="v281-all-tools"><h2>{archived?'已归档':'全部'+tab}</h2><label className="v277-field"><span>排序</span><select aria-label="工具排序" value={sort} onChange={event=>setSort(event.target.value as typeof sort)}><option value="recent">最近使用</option><option value="created">创建时间</option><option value="frequent">使用频率</option></select></label><button className="v277-secondary" onClick={()=>setArchived(!archived)}>{archived?'查看有效工具':'查看归档'}</button>{!query.trim()&&<button type="button" className="v277-secondary" onClick={()=>setShowAll(false)}>收起全部</button>}<div>{tools.map(item=><button key={item.id} onClick={()=>selectTool(item)}><span>{pinned(item.id)?<Pin size={27}/>:<Layers3 size={27}/>}</span><h3>{displayTitle(text(item,'title'),'')}</h3><p>{text(item,'status')==='active'?'已启用':text(item,'status')==='archived'?'已归档':'草稿'} · 使用 {Number(item.data.uses||0)} 次{item.data.activity==='idle'?' · 闲置':''}{item.data.mastery==='frequent'?' · 常用':item.data.mastery==='proficient'?' · 熟练':''}</p><ChevronRight size={20}/></button>)}</div>{!tools.length&&<button className="v277-secondary" onClick={()=>go({name:'create-tool'})}>创建第一个{tab}</button>}</section>}
 {open&&(()=>{const item=snapshot.objects.skill.find(item=>item.id===open.id);if(!item)return null;return <section ref={detail} className="v277-edit-card elfred-tool-detail" aria-label="工具详情"><h3>{displayTitle(text(item,'title'),'')}</h3><details><summary>使用说明</summary><p>{text(item,'instructions')}</p></details><ToolRunInputs key={item.id+':'+item.data.version_id} tool={item} goal={goal} setGoal={setGoal} go={go} onPreview={setPreview}/><ToolGovernance key={item.id+':'+item.version} tool={item}/><button className="v277-secondary" onClick={()=>go({name:'create-tool',id:item.id})}>编辑新版本</button><Action run={()=>runtime.command('shortcut.pin',{skill_id:item.id})}>{pinned(item.id)?'从我的工具移除':'固定到我的工具'}</Action><Action run={()=>runtime.command(item.data.status==='active'?'tool.archive':'tool.activate',entityRef(item))}>{item.data.status==='active'?'归档':'启用'}</Action><details><summary>版本与使用记录</summary>{snapshot.objects.skill_version.filter(version=>version.data.tool_id===item.id).map(version=><p key={version.id}>{new Date(version.created).toLocaleString('zh-CN')} · {text(version,'instructions').slice(0,100)}</p>)}</details></section>})()}
 {preview&&<section className="v277-edit-card"><h3>Mini App</h3><iframe title="Mini App 预览" sandbox="allow-scripts" src={`/api/elfred/preview/${preview}`} style={{width:'100%',height:400,border:0}}/><button onClick={()=>setPreview('')}>关闭预览</button></section>}
 </main>;
}
export function ToolEditor({id,onBack,go}:{id?:string;onBack:()=>void;go:Go}){
 const runtime=useRuntime()!,item=runtime.snapshot!.objects.skill.find(item=>item.id===id);
 const [base]=useState(item?.version),[kind,setKind]=useState(text(item,'kind')||'Skill'),[title,setTitle]=useState(text(item,'title')),[instructions,setInstructions]=useState(text(item,'instructions')),[system,setSystem]=useState(text(item,'system')||'execute'),[html,setHtml]=useState(text(item,'html'));
 const [generationTask,setGenerationTask]=useState('');
 const generatedTask=runtime.snapshot!.objects.task.find(task=>task.id===generationTask);
 const generatedRun=runtime.snapshot!.objects.run.find(run=>run.id===generatedTask?.data.run_id);
 const generatedOutput=finalReceipts((generatedRun?.data.receipts||[]) as {phase?:string;output?:unknown;provider?:string}[]).find(row=>typeof row.output==='string')?.output;
 useEffect(()=>{if(!html&&typeof generatedOutput==='string'){const source=generatedOutput.trim().replace(/^\`\`\`(?:html)?\s*/i,'').replace(/\s*\`\`\`$/,'');if(/<(?:html|body|main|div|section|button)\b/i.test(source))setHtml(source)}},[generatedOutput,html]);
 const [parameters,setParameters]=useState<ToolParameter[]>((item?.data.parameters||[]) as ToolParameter[]),[workflow,setWorkflow]=useState<ToolStep[]>((item?.data.workflow||[]) as ToolStep[]);
 const [step,setStep]=useState(id?3:0),[question,setQuestion]=useState(0),[mapNode,setMapNode]=useState(0),[confirmed,setConfirmed]=useState([false,false,false,false]),[problem,setProblem]=useState(''),[input,setInput]=useState(''),[output,setOutput]=useState(''),[scenario,setScenario]=useState(''),[rule,setRule]=useState(''),[process,setProcess]=useState(''),[resources,setResources]=useState(''),[criteria,setCriteria]=useState(''),[permission,setPermission]=useState('');
 const questions=[
  {name:'什么时候会用到它？',value:scenario,set:setScenario},
  {name:'最重要的判断规则是什么？',value:rule,set:setRule},
  {name:'它按什么步骤工作？',value:process,set:setProcess},
  {name:'需要哪些资料或工具？',value:resources,set:setResources},
  {name:'怎样验收结果？',value:criteria,set:setCriteria},
  {name:'哪些操作必须先问你？',value:permission,set:setPermission}
 ];
 const map=[['用户输入',input],['理解与判断',rule||scenario],['执行步骤',process],['检查结果',criteria],['输出成果',output]];
 const generated=[`解决的问题：${problem}`,`通常提供的输入：${input}`,`希望得到的结果：${output}`,`适用场景：${scenario||'每次使用前由本人核对'}`,`判断规则：${rule||'信息不足时保留未知'}`,`执行步骤：${process||'理解输入、执行、检查并交付'}`,`所需资料与工具：${resources||'仅使用本次提供的内容'}`,`验收标准：${criteria||'由本人核对输出'}`,`确认节点：${permission||'读取额外资料或对外操作前先询问'}`].join('\n');
 const save=async()=>{const result=await runtime.command('tool.save',{id,version:base,title:title||problem.slice(0,40),instructions:instructions.trim()||generated,kind,system,html,parameters:kind==='Mini App'?[]:parameters,workflow:kind==='Mini App'?[]:workflow,permissions:{read_scope:resources||'本次提供的资料',tool_scope:kind==='Mini App'?'仅页面内交互':'仅已授权的工具',external_access:false,confirm_steps:permission||'对外操作前确认'}});go({name:'tool-detail',id:result.id})};
 const generateMiniApp=async()=>{setGenerationTask('');setHtml('');const result=await runtime.command('tool.generate',{purpose:problem||title||instructions,source:input||'用户在页面输入',result:output||'页面展示处理结果',confirm:true,model_consent:true});setGenerationTask(result.task_id||'')};
 return <main className="v277-page v281-create-tool"><header><button aria-label="返回我的工具" onClick={onBack}><ArrowLeft size={24}/></button><h1>{id?'编辑工具':'创建工具'}</h1></header>
 <section className="v277-edit-card elfred-tool-wizard">
 {!id&&<p className="elfred-tool-step">{step+1} / 4 · {['选择类型','描述需求','逐项完善','预览与保存'][step]}</p>}
 {step===0&&<><h2>你想做什么工具？</h2><div className="elfred-tool-kind-cards">{[['Skill','可反复执行的一套方法'],['Mini App','带轻量交互界面的工具'],['Agent','长期负责一类目标的执行者']].map(([value,note])=><button type="button" key={value} aria-pressed={kind===value} onClick={()=>setKind(value)}><b>{value}</b><small>{note}</small></button>)}</div><h3>从常见方法开始</h3><div className="elfred-tool-sop-cards">{[['整理会议纪要','会议录音或文字','行动项与决策纪要'],['检索并汇总资料','问题与可访问资料','有来源的摘要'],['撰写内容','主题与目标读者','可修改的内容草稿'],['跟进任务','目标与当前进度','下一步和阻塞清单']].map(([name,source,result])=><button type="button" key={name} onClick={()=>{setTitle(name);setProblem(name);setInput(source);setOutput(result);setStep(1)}}>{name}</button>)}</div><button type="button" className="v277-primary" onClick={()=>setStep(1)}>从我的想法开始</button></>}
 {step===1&&<><h2>先说清三件事</h2><Field name="想解决什么问题" value={problem} onChange={setProblem} area/><Field name="通常会提供什么输入" value={input} onChange={setInput}/><Field name="希望得到什么结果" value={output} onChange={setOutput}/><button type="button" className="v277-primary" disabled={!problem.trim()||!input.trim()||!output.trim()} onClick={()=>{if(!title)setTitle(problem.slice(0,40));setStep(2)}}>继续补充规则</button></>}
 {step===2&&<><div className="elfred-tool-dialogue"><small>创建 Agent · {question+1} / {questions.length}</small><h2>{questions[question].name}</h2><Field name="你的回答" value={questions[question].value} onChange={questions[question].set} area/><div className="elfred-tool-dialogue-actions"><button type="button" className="v277-secondary" disabled={question===0} onClick={()=>setQuestion(question-1)}>上一题</button><button type="button" className="v277-primary" disabled={!questions[question].value.trim()} onClick={()=>{if(question<questions.length-1)setQuestion(question+1);else{setInstructions(generated);setStep(3)}}}>{question===questions.length-1?'查看结构':'继续'}</button></div></div><details className="elfred-tool-live-summary"><summary>实时摘要 · 点击修改</summary><Field name="问题" value={problem} onChange={setProblem}/><Field name="输入" value={input} onChange={setInput}/><Field name="结果" value={output} onChange={setOutput}/>{questions.map((item,index)=><Field key={index} name={item.name} value={item.value} onChange={item.set}/>)}</details></>}
 {step===3&&<><h2>结构预览</h2><div className="elfred-tool-map" aria-label="工具执行结构">{map.map(([name],index)=><button type="button" key={name} aria-pressed={mapNode===index} onClick={()=>setMapNode(index)}>{name}</button>)}</div><p className="elfred-tool-map-detail">{map[mapNode][1]||'保存后在测试中核对'}</p><Field name="工具名称" value={title} onChange={setTitle}/><details><summary>修改工具说明</summary><Field name="工具说明" value={instructions} onChange={setInstructions} area/></details><label className="v277-field"><span>负责 Agent</span><select value={system} onChange={e=>{setSystem(e.target.value);setWorkflow(old=>old.filter(s=>s.system!==e.target.value).map(s=>({...s,depends:s.depends.filter(id=>old.find(p=>p.id===id)?.system!==e.target.value)})))}}>{runtime.snapshot!.systems.map(value=><option value={value.id} key={value.id}>{value.name}</option>)}</select></label><div className="elfred-tool-permission"><h3>权限确认</h3>{[`读取：${resources||'本次提供的资料'}`,`工具：${kind==='Mini App'?'仅页面内交互':'仅已授权工具'}`,'不自动连接外部服务',`先确认：${permission||'对外操作'}`].map((label,index)=><label key={index}><input type="checkbox" checked={confirmed[index]} onChange={event=>setConfirmed(old=>old.map((value,i)=>i===index?event.target.checked:value))}/><span>{label}</span></label>)}</div><details><summary>输入与前置步骤</summary>{kind!=='Mini App'&&<><ParameterEditor value={parameters} onChange={setParameters}/><ToolWorkflow main={system} value={workflow} onChange={setWorkflow}/></>}</details>{kind==='Mini App'&&<div className="elfred-tool-generator"><Action disabled={Boolean(generationTask&&['queued','running'].includes(String(generatedTask?.data.status)))} run={generateMiniApp}>{html?'重新生成页面':'按描述生成页面'}</Action>{generationTask&&['queued','running'].includes(String(generatedTask?.data.status))&&<p role="status">正在生成页面…</p>}{generationTask&&['blocked','failed'].includes(String(generatedTask?.data.status))&&<p role="alert">页面生成未完成，请检查模型设置后重试。</p>}{html&&<p>页面已就绪，保存后可预览和测试。</p>}<details><summary>手动修改页面代码</summary><Field name="HTML 页面" area value={html} onChange={setHtml}/></details></div>}<Action disabled={!title.trim()||!instructions.trim()||confirmed.some(value=>!value)||(kind==='Mini App'&&!html.trim())} run={save}>保存并测试</Action></>}
 {step>0&&!id&&<button type="button" className="v277-secondary" onClick={()=>setStep(step-1)}>返回上一步</button>}
 </section></main>;
}
