import {fail,now} from './store.mjs';
import {string,enumeration,DEFAULT_STOP} from './policy.mjs';
import {validateWebArtifact} from './preview.mjs';
import {taskCommand} from './runtime.mjs';
import {parameterSchema,parameterValues,toolWorkflow} from './tool-parameters.mjs';
import {contextCommand} from './context-request.mjs';
function toolPermissions(input,previous){
  if(input===undefined)return previous||{read_scope:'本次提供的资料',tool_scope:'仅已授权的工具',external_access:false,confirm_steps:'对外操作前确认'};
  if(!input||typeof input!=='object'||Array.isArray(input))fail('INVALID_INPUT','权限卡格式无效');
  if(input.external_access!==false)fail('EXTERNAL_ACCESS_UNAVAILABLE','外部服务须在实际任务中单独连接并授权');
  return {read_scope:string(input.read_scope,'可读取的资料',500),tool_scope:string(input.tool_scope,'可使用的工具',500),external_access:false,confirm_steps:string(input.confirm_steps,'确认节点',500)};
}
export function toolLibraryCommand(store,user,action,input){
  if(action==='tool.generate'){
    if(input.confirm!==true||input.model_consent!==true)fail('CONSENT_REQUIRED','请确认调用模型生成 Mini App 页面');
    const purpose=string(input.purpose,'工具用途',1000),source=string(input.source,'输入',500),result=string(input.result,'输出',500);
    const created=taskCommand(store,user,'task.create',{goal:`生成一个可直接运行的单文件 Mini App。只输出完整 HTML，不要 Markdown 代码围栏或解释。页面应包含内联 CSS 和必要的内联 JavaScript，不能引用外部网址、脚本、样式或网络服务。用户需求：${purpose}。输入：${source}。输出：${result}。界面以手机优先，输入必须可操作，结果须真实由页面逻辑计算或整理；不能伪装为已调用外部服务。`,system:'create',mode:'compose',review_mode:'single',source_refs:[]});
    let task=store.get(created.id);task=store.update(task,{...task.data,title:'生成 Mini App 页面',internal_tool_generation:true,internal_search:true},user);
    taskCommand(store,user,'task.confirm',{id:task.id,version:task.version,confirm:true,model_consent:true});
    task=store.get(task.id);taskCommand(store,user,'run.start',{id:task.id,version:task.version});
    return {task_id:task.id};
  }
  if(action==='tool.governance'){
    const tool=store.expect(store.owned(user,input.id,'skill'),input.version);
    if(input.confirm!==true)fail('CONFIRMATION_REQUIRED','请核对工具使用证据与闲置规则');
    const ranks=['unrated','frequent','proficient'],mastery=enumeration(input.mastery||tool.data.mastery||'unrated',ranks,'熟练状态');
    if(ranks.indexOf(mastery)<ranks.indexOf(tool.data.mastery||'unrated'))fail('MASTERY_PRESERVED','常用与熟练证据不会因闲置或一次失败扣除');
    const accepted=store.list('task').filter(t=>t.owner===user&&t.data.skill_id===tool.id&&!t.data.test_run&&t.data.status==='completed');
    if(mastery==='frequent'&&Number(tool.data.uses||0)<2||mastery==='proficient'&&tool.data.mastery!=='proficient'&&!accepted.length)fail('EVIDENCE_REQUIRED','常用需重复实际使用，熟练需至少一项本人验收的成果');
    const idle=input.idle_days??null;if(idle!==null&&(!Number.isInteger(idle)||idle<1||idle>3650))fail('INVALID_INPUT','闲置提醒需为 1—3650 天，留空表示关闭');
    return {id:store.update(tool,{...tool.data,mastery,idle_days:idle,mastery_evidence:{uses:tool.data.uses||0,accepted_task_ids:accepted.map(t=>t.id),confirmed_at:now()}},user).id};
  }
  if(action==='tool.save'){
    const previous=input.id?store.expect(store.owned(user,input.id,'skill'),input.version):null;
    const data={title:string(input.title,'名称',100),instructions:string(input.instructions,'使用说明',12000),kind:enumeration(input.kind||'Skill',['Skill','Mini App','Agent'],'工具类型'),system:enumeration(input.system||'execute',['explore','advise','create','connect','execute'],'负责系统'),html:typeof input.html==='string'?input.html.slice(0,200000):'',status:'draft'};
    if(data.kind==='Mini App'&&!data.html.trim())fail('INVALID_INPUT','Mini App 需要 HTML/CSS/JavaScript 页面');
    if(data.kind==='Mini App')data.build=validateWebArtifact(data.html);
    data.parameters=parameterSchema(input.parameters??previous?.data.parameters??[]);
    data.workflow=toolWorkflow(input.workflow??previous?.data.workflow??[],data.system);
    data.permissions=toolPermissions(input.permissions,previous?.data.permissions);
    if(data.kind==='Mini App'&&data.workflow.length)fail('INVALID_WORKFLOW','网页工具在自身页面中运行，不启动前置模型步骤');
    if(data.kind==='Mini App'&&data.parameters.length)fail('INVALID_PARAMETERS','Mini App 的输入请在页面内定义');
    const tool=previous?store.update(previous,{...previous.data,...data},user):store.add('skill',user,{...data,uses:0});
    const version=store.add('skill_version',user,{tool_id:tool.id,...data,revision:(previous?.data.revision||0)+1});
    const saved=store.update(tool,{...tool.data,version_id:version.id,revision:version.data.revision},user);
    return {id:saved.id,version:saved.version};
  }
  if(action==='tool.activate'||action==='tool.archive'){
    const tool=store.expect(store.owned(user,input.id,'skill'),input.version);
    if(action==='tool.activate'&&!tool.data.version_id)fail('VERSION_REQUIRED','请先编辑并保存一个工具版本');
    return {id:store.update(tool,{...tool.data,status:action==='tool.activate'?'active':'archived'},user).id};
  }
  if(action==='tool.use'||action==='tool.test'){
    const tool=store.owned(user,input.id,'skill');
    if(action==='tool.use'&&tool.data.status!=='active')fail('TOOL_DISABLED','请先启用工具');
    const version=store.owned(user,tool.data.version_id,'skill_version');
    if(input.version_id!==version.id)fail('VERSION_CONFLICT','工具版本已变化，请核对新输入后再使用');
    const parameters=parameterValues(version.data.parameters||[],input.parameters||{});
    let task;
    if(version.data.kind!=='Mini App'){
      const goal=string(input.goal||('按已选工具完成本次工作：'+version.data.title),'本次目标',8000);
      task=taskCommand(store,user,'task.create',{goal,constraints:`资料范围：${version.data.permissions?.read_scope||'本次提供的资料'}；可用工具：${version.data.permissions?.tool_scope||'仅已授权的工具'}；不得自动连接外部服务；${version.data.permissions?.confirm_steps||'对外操作前确认'}。`,mode:'compose',system:version.data.system,stop:{...DEFAULT_STOP,maxUnits:Math.max(DEFAULT_STOP.maxUnits,((version.data.workflow?.length||0)+2)*1000)},source_refs:[{id:version.id,version:version.version}]});
      const created=store.get(task.id);store.update(created,{...created.data,skill_id:tool.id,skill_version_id:version.id,parameter_values:parameters,test_run:action==='tool.test'},user);
      if(version.data.workflow?.length){contextCommand(store,user,'task.collaboration',{id:task.id,version:store.get(task.id).version,confirm:true,steps:version.data.workflow.map(step=>({...step,source_refs:[{id:version.id,version:version.version}]}))});const configured=store.get(task.id);store.update(configured,{...configured.data,collaboration_steps:configured.data.collaboration_steps.map(step=>({...step,parameter_values:parameters}))},user);}
    }
    store.add('tool_use',user,{tool_id:tool.id,version_id:version.id,task_id:task?.id||null,kind:action==='tool.test'?'test':'use'});
    if(version.data.kind==='Mini App'&&action==='tool.use')store.update(tool,{...tool.data,uses:(tool.data.uses||0)+1,last_used_at:now()},user);
    return {id:tool.id,task_id:task?.id,version_id:version.id};
  }
  return null;
}
