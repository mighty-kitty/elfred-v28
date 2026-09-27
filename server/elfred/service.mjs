import { fail, now, hash } from './store.mjs';
import { string, enumeration, bounded } from './policy.mjs';
import { knowledgeCommand, search } from './knowledge.mjs';
import { taskCommand } from './runtime.mjs';
import { socialCommand } from './social.mjs';
import {agentChatCommand} from './agent-chat.mjs';
import { communityCommand } from './community.mjs';
import { SYSTEMS, DEFINITIONS } from './catalog.mjs';
import { improvementCommand } from './improvement.mjs';
import {groupCommand} from './group-records.mjs';
import {attachmentCommand,attachmentMetadata} from './attachments.mjs';
import {toolLibraryCommand} from './tool-library.mjs';
import {onboardingChoiceCommand,materializeInitialMemories} from './onboarding-choice.mjs';
import {onboardingCommand} from './onboarding.mjs';
import {projectWorkCommand} from './project-work.mjs';
import {searchCommand} from './search-commands.mjs';
import { homeCommand } from './home.mjs';
import {publicSlots,publishedSlots} from './project-slots.mjs';
import {handoffCommand} from './handoffs.mjs';
import {toolActivity} from './tool-parameters.mjs';
import {projectProgress} from './project-progress.mjs';
import {semanticCommand} from './semantic-search.mjs';
import {contextCommand} from './context-request.mjs';
import {reflectionCommand} from './reflection.mjs';
import {externalToolCommand} from './external-tools.mjs';
import {feedCommand} from './feed.mjs';
import {observationCommand} from './observation.mjs';
import {provisionInitialDiscovery} from './auto-discovery.mjs';
import {swarmCommand} from './swarm.mjs';
import {memoryHubStatus,queueMemorySync} from './memory-hub.mjs';
import {projectMemory} from './memory-validity.mjs';
import {migrateAutomaticMemories} from './memory-learning.mjs';

export const READ_TYPES=['observation','context_request','context_grant','handoff','project_stage','attachment','skill_version','tool_use','shared_record','project_slot','profile','settings','onboarding','task','run','attempt','approval','document','knowledge','memory','outcome','feed','interaction','inbox','notification','friend','conversation','message','draft','assist','commitment','project','post','comment','claim','copy','contribution','release','feedback','resource','connector','data_request','brief','skill','shortcut','trace','candidate','evaluation','method','rollout'];
export class Service {
  constructor(store,provider) {this.store=store;this.provider=provider;}
  initialize(user) {
    const s=this.store;
    s.transaction(()=>{
      s.unique('profile',user.id,()=>s.add('profile',user.id,{name:user.name,bio:'',public:false}));
      s.unique('settings',user.id,()=>s.add('settings',user.id,{timezone:'Asia/Shanghai',notifications:true,quiet:false,model_allowed:false}));
      const onboarding=s.unique('onboarding',user.id,()=>s.add('onboarding',user.id,{status:'collecting',intent:'',skipped:[]}));
      if(onboarding.data.choice_confirmed_at&&Array.isArray(onboarding.data.choice_summary)){provisionInitialDiscovery(s,user.id,onboarding.data.choice_summary);materializeInitialMemories(s,user.id,onboarding.data.choice_summary);}
      migrateAutomaticMemories(s,user.id);
      for(const memory of s.list('memory').filter(m=>m.owner===user.id))queueMemorySync(s,memory);
      s.db.prepare('INSERT OR IGNORE INTO budget_accounts(owner,limit_units) VALUES(?,?)').run(user.id,10000);
    });
  }
  list(user,type) {
    if(!READ_TYPES.includes(type)) fail('INVALID_TYPE','对象类型不可查询');
    const s=this.store;
    if(type==='claim') return s.list(type).filter(item=>item.owner===user||s.get(item.data.project_id)?.owner===user).map(item=>{if(s.role(item.data.project_id,user))return item;const {new_rules,...data}=item.data;return {...item,data};});
    return s.visible(user,type).filter(item=>!['deleted'].includes(item.data.status)&&(type!=='memory'||item.data.kind!=='method_experience')).map(item=>{
      if(type==='context_request'){const task=s.get(item.data.task_id);return {...item,data:{...item.data,recovery_task:task?.owner===user&&s.canRead(user,{...task,data:{...task.data,source_refs:[]}})?{id:task.id,version:task.version,status:task.data.status,source_invalid:!s.canRead(user,task)}:null}};}
      if(type==='memory')return projectMemory(s,item);
      if(type==='skill')return {...item,data:{...item.data,activity:toolActivity(item)}};
      if(type==='attachment')return attachmentMetadata(item);
      if(type==='conversation') {const members=s.members(item.id);return {...item,data:{...item.data,title:item.data.kind==='direct'?members.find(member=>member.id!==user)?.name||item.data.title:item.data.title},members,unread:Math.max(0,item.data.seq-(s.db.prepare('SELECT seq FROM read_cursors WHERE space=? AND user_id=?').get(item.id,user)?.seq||0))};}
      if(type==='assist'&&item.data.task_id){const task=s.get(item.data.task_id);return {...item,data:{...item.data,status:task?.data.status||item.data.status}};}
      if(type==='release')return {...item,data:{...item.data,is_current:s.get(item.data.project_id)?.data.release_id===item.id}};
      if(type==='project_slot')return {...item,data:{...item.data,filled:publicSlots(s,item.space).find(slot=>slot.id===item.id)?.filled||0}};
      if(type==='project') return {...item,data:{...item.data,progress:projectProgress(s,user,item),public_budget_used:s.list('task').filter(t=>t.data.project_id===item.id&&t.data.budget_source==='project').reduce((sum,t)=>sum+(t.data.units||0),0)},members:s.members(item.id)};
      if(type==='friend') {const other=s.user(item.owner===user?item.data.recipient:item.owner);return {...item,data:{...item.data,other_name:other.name,other_handle:other.handle}};}
      if(type==='brief'){const valid=!item.data.reflection||(item.data.reflection.facts||[]).every(f=>{const task=s.get(f.task_id);return task?.version===f.version&&s.canRead(user,task)});return {...item,data:{...item.data,...(!valid?{reflection:null,review:null,reflection_unavailable:true}:{}),facts:(item.data.facts||[]).filter(fact=>s.canRead(user,s.get(fact.task_id)))}};}
      if(type==='post') return {...item,data:{...item.data,...(item.data.project_id?{slots:publishedSlots(s,item)}:{}),likes:s.list('interaction').filter(interaction=>interaction.data.object_id===item.id&&interaction.data.kind==='like'&&interaction.data.active).length,comments:s.list('comment').filter(comment=>comment.data.post_id===item.id&&comment.data.status==='published').length}};
      return item;
    });
  }
  read(user,objectId) {
    const object=this.store.get(objectId);
    if(object?.type==='attachment'){this.store.read(user,objectId);return attachmentMetadata(object);}
    if(object?.type==='claim'){const result=this.list(user,'claim').find(item=>item.id===objectId);if(!result)fail('NOT_FOUND','申请不可访问',404);return result;}
    if(object && !READ_TYPES.includes(object.type)) fail('NOT_FOUND','内容不存在',404);
    if(object?.type==='brief'){this.store.read(user,objectId);return this.list(user,'brief').find(item=>item.id===objectId);}
    const result=this.store.read(user,objectId);return result.type==='memory'?projectMemory(this.store,result):result;
  }
  bootstrap(user) {
    const onboarding=this.store.visible(user,'onboarding')[0];
    if(onboarding?.data.choice_confirmed_at&&Array.isArray(onboarding.data.choice_summary)&&!this.store.visible(user,'observation').some(item=>item.data.auto_suggested))this.store.transaction(()=>provisionInitialDiscovery(this.store,user,onboarding.data.choice_summary));
    if(onboarding?.data.choice_confirmed_at&&Array.isArray(onboarding.data.choice_summary))this.store.transaction(()=>materializeInitialMemories(this.store,user,onboarding.data.choice_summary));
    this.store.transaction(()=>migrateAutomaticMemories(this.store,user));
    const types=['observation','context_request','context_grant','handoff','project_stage','attachment','skill_version','tool_use','shared_record','project_slot','profile','settings','onboarding','task','run','knowledge','document','memory','feed','notification','friend','conversation','message','post','comment','project','draft','assist','commitment','copy','contribution','release','feedback','claim','interaction','approval','resource','connector','brief','skill','shortcut','inbox','candidate','evaluation','outcome','method','rollout','trace'];
    const module_errors={},objects=Object.fromEntries(types.map(type=>{try{return [type,this.list(user,type)];}catch(error){if(['profile','settings','onboarding'].includes(type))throw error;module_errors[type]='此模块暂时加载失败，请重试';return [type,[]];}}));
    return {memory_hub:memoryHubStatus(this.store,user,this.provider.config||process.env),user:this.store.user(user),provider:this.provider.status(),systems:SYSTEMS,definitions:DEFINITIONS,objects,module_errors,budget:this.store.db.prepare('SELECT * FROM budget_accounts WHERE owner=?').get(user),usage:this.store.db.prepare('SELECT * FROM usage WHERE owner=? ORDER BY created DESC LIMIT 100').all(user),server_time:now(),storage:'local-sqlite',production_ready:false};
  }
  command(user,key,action,input) {
    const s=this.store;
    return s.command(user,key,{action,input},()=>{
      if(input.evaluation_candidate_id) fail('INTERNAL_ONLY','候选方法仅能通过离线评估入口运行',403);
      if(action==='task.model_settings'){
        const task=s.expect(s.owned(user,input.id,'task'),input.version);
        if(!['draft','ready','blocked','failed','partial','paused','cancelled'].includes(task.data.status)||task.data.mode!=='compose'||task.data.media_operation)fail('INVALID_STATE','当前任务不能修改模型，请先停止运行并核对现有成果',409);
        const model=string(input.model,'模型',120),reviewMode=enumeration(input.review_mode,['auto','single','independent'],'复核方式');
        if(!(this.provider.allowedModels?.()||[this.provider.status().model]).includes(model))fail('MODEL_NOT_AVAILABLE','模型不在当前服务可用列表中，请重新打开模型设置',409);
        if(task.data.model_name===model&&task.data.review_mode===reviewMode)return {id:task.id};
        for(const approval of s.visible(user,'approval').filter(item=>item.data.task_id===task.id&&item.data.status==='approved'))s.update(approval,{...approval.data,status:'revoked'},user);
        return {id:s.update(task,{...task.data,model_name:model,review_mode:reviewMode,status:'draft',execution_revision:Number(task.data.execution_revision||0)+1},user).id};
      }
      for(const handler of [swarmCommand,agentChatCommand,observationCommand,externalToolCommand,feedCommand,reflectionCommand,semanticCommand,contextCommand,handoffCommand,projectWorkCommand,searchCommand,taskCommand,knowledgeCommand,socialCommand,communityCommand,improvementCommand,homeCommand,onboardingChoiceCommand,onboardingCommand,attachmentCommand,toolLibraryCommand,groupCommand]) {const result=handler(s,user,action,input,this.provider);if(result) return result;}
      const owned=(type)=>s.expect(s.owned(user,input.id,type),input.version);
      if(action==='onboarding.save' || action==='onboarding.complete') {
        const object=owned('onboarding');
        return {id:s.update(object,{...object.data,intent:typeof input.intent==='string'?input.intent.slice(0,8000):object.data.intent,status:action.endsWith('complete')?'completed':'collecting',skipped:input.skip===true?['optional_profile','optional_skill']:object.data.skipped},user).id};
      }
      if(action==='profile.save') {
        const profile=owned('profile');
        const name=string(input.name,'称呼',60),bio=typeof input.bio==='string'?input.bio.slice(0,2000):'';
        const media={};for(const key of ['avatar','cover'])if(input[key]!==undefined){
          const value=input[key];if(typeof value!=='string'||value.length>360000)fail('INVALID_IMAGE','头像或封面需小于 250 KB');
          if(value){const match=/^data:image\/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)$/.exec(value);if(!match)fail('INVALID_IMAGE','仅支持 PNG、JPEG 或 WebP 图片');const bytes=Buffer.from(match[2],'base64');const valid=match[1]==='png'?bytes.subarray(0,8).toString('hex')==='89504e470d0a1a0a':match[1]==='jpeg'?bytes.subarray(0,3).toString('hex')==='ffd8ff':bytes.subarray(0,4).toString()==='RIFF'&&bytes.subarray(8,12).toString()==='WEBP';if(!valid)fail('INVALID_IMAGE','图片格式不正确');}media[key]=value;
        }
        s.db.prepare('UPDATE users SET name=? WHERE id=?').run(name,user);
        return {id:s.update(profile,{...profile.data,...media,name,bio,showLevel:input.showLevel===undefined?profile.data.showLevel:input.showLevel===true,role:typeof input.role==='string'?input.role.slice(0,100):profile.data.role||'',tags:Array.isArray(input.tags)?input.tags.filter(item=>typeof item==='string').slice(0,20):profile.data.tags||[]},user).id};
      }
      if(action==='profile.publish') {
        const profile=owned('profile');
        if(input.confirm!==true) fail('CONFIRMATION_REQUIRED','请确认公开称呼与简介');
        return {id:s.update(profile,{...profile.data,public:input.publish===true,published:input.publish===true?{name:profile.data.name,bio:profile.data.bio}:null},user).id};
      }
      if(action==='settings.save') {
        const settings=owned('settings'),timezone=string(input.timezone||settings.data.timezone,'时区',80);
        try {new Intl.DateTimeFormat('zh-CN',{timeZone:timezone}).format();} catch {fail('INVALID_TIMEZONE','时区格式不正确');}
        return {id:s.update(settings,{...settings.data,timezone,notifications:input.notifications===true,quiet:input.quiet===true},user).id};
      }
      if(action==='agent.preferences') {
        const settings=owned('settings'),system=enumeration(input.system,['explore','advise','create','connect','execute'],'系统');
        const preferences={enabled:input.enabled!==false,name:string(input.name||system,'名称',100),duty:string(input.duty||'按目标与验收标准完成授权任务','职责',1000),focus:string(input.focus||'仅当前目标','关注范围',1000)};
        return {id:s.update(settings,{...settings.data,agents:{...settings.data.agents,[system]:preferences}},user).id};
      }
      if(action==='agent.publish_preferences') {
        const settings=owned('settings'),system=enumeration(input.system,['explore','advise','create','connect','execute'],'系统');
        const preferences={topic:string(input.topic,'发布主题',100),length:enumeration(input.length,['简洁摘要','标准摘要','详细说明'],'内容长度'),format:enumeration(input.format||'图文',['纯文字','图文'],'内容形式'),format_version:2,frequency:'事件触发'};
        return {id:s.update(settings,{...settings.data,agent_publish:{...settings.data.agent_publish,[system]:preferences}},user).id};
      }
      if(action==='brief.preferences') {
        const settings=owned('settings'),preferences=input.preferences;
        if(!preferences||typeof preferences!=='object'||Array.isArray(preferences)||JSON.stringify(preferences).length>3000) fail('INVALID_INPUT','简报偏好格式不正确');
        const clean={};for(const [key,value] of Object.entries(preferences)) {if(typeof value!=='string'||value.length>100)fail('INVALID_INPUT','简报偏好格式不正确');clean[key]=value;}
        return {id:s.update(settings,{...settings.data,brief_preferences:clean},user).id};
      }
      if(action==='budget.set') {
        const units=bounded(input.limit_units,'本地调用额度',0,100000);
        const account=s.db.prepare('SELECT * FROM budget_accounts WHERE owner=?').get(user);
        if(units<account.reserved+account.spent) fail('BUDGET_RESERVED','额度不能低于已用与预留之和');
        s.db.prepare('UPDATE budget_accounts SET limit_units=? WHERE owner=?').run(units,user);s.event(user,'budget.changed',user,{limit_units:units});return {id:user};
      }
      if(action==='usage.reconcile') {
        const entry=s.db.prepare('SELECT * FROM usage WHERE id=? AND owner=?').get(input.id,user);
        if(!entry||entry.status!=='unknown') fail('NOT_FOUND','没有待核对用量',404);
        if(input.confirm!==true) fail('CONFIRMATION_REQUIRED','需核对供应商记录后确认');
        const actual=bounded(input.actual_units,'实际调用额度',0,entry.reserved);
        const note=string(input.note,'对账依据',1000);
        s.db.prepare('UPDATE budget_accounts SET reserved=reserved-?,spent=spent+? WHERE owner=?').run(entry.reserved,actual,user);
        s.db.prepare("UPDATE usage SET status='settled',actual=?,receipt=? WHERE id=?").run(actual,JSON.stringify({reconciled_by:user,note,at:now(),monetary_cost:'not_reconciled'}),entry.id);
        const task=s.get(entry.task_id);if(task?.data.status==='reconciliation_required') s.update(task,{...task.data,status:'blocked'},user);
        s.event(entry.run_id,'usage.reconciled',user);return {id:entry.id};
      }
      if(action==='notification.read') {const notification=owned('notification');return {id:s.update(notification,{...notification.data,status:'read'},user).id};}
      if(action==='feed.interact') {
        const feed=s.read(user,input.id,'feed'),kind=enumeration(input.kind,['like','save','hide','less'],'互动');
        const item=s.unique('interaction',`${user}:${feed.id}:${kind}`,()=>s.add('interaction',user,{object_id:feed.id,kind,active:false}));
        return {id:s.update(item,{...item.data,active:!item.data.active},user).id};
      }
      if(action==='inbox.create') {
        const object=s.read(user,input.object_id);
        const item=s.unique('inbox',`${user}:${object.id}`,()=>s.add('inbox',user,{object_id:object.id,status:'pending',source_refs:[{id:object.id,version:object.version}]}));
        if(item.data.status==='dismissed')s.update(item,{...item.data,status:item.data.task_id?'processed':'pending',source_refs:[{id:object.id,version:object.version}]},user);
        return {id:item.id};
      }
      if(action==='inbox.task'){
        const item=owned('inbox'),source=s.read(user,item.data.object_id);
        if(item.data.task_id)return {id:item.data.task_id};
        const result=taskCommand(s,user,'task.create',{goal:string(input.goal||source.data.title||source.data.content||source.data.summary||'处理已保存事项','目标',8000),source_refs:[{id:source.id,version:source.version}],mode:'compose',system:enumeration(input.system||'execute',['execute','explore','create'],'处理方向')});
        s.update(item,{...item.data,status:'processed',task_id:result.id},user);return result;
      }
      if(action==='inbox.dismiss') {const item=owned('inbox');return {id:s.update(item,{...item.data,status:'dismissed'},user).id};}
      if(action==='brief.review') {
        const brief=owned('brief'),decision=enumeration(input.decision,['confirmed','corrected','deferred','denied'],'反思决定');
        if(['confirmed','corrected'].includes(decision))for(const fact of brief.data.reflection?.facts||[])s.expect(s.read(user,fact.task_id,'task'),fact.version);
        return {id:s.update(brief,{...brief.data,review:{decision,correction:decision==='corrected'?string(input.correction,'修正内容',4000):'',reviewed_at:now()},status:'reviewed'},user).id};
      }
      if(action==='resource.create') return {id:s.add('resource',user,{title:string(input.title,'资源名称',200),content:string(input.content,'公开或授权依据',5000),willingness:'unknown',status:'active'}).id};
      if(action==='connector.create') {
        const provider=enumeration(input.provider,['model'],'服务');
        return {id:s.unique('connector',`${user}:${provider}`,()=>s.add('connector',user,{provider,scope:'selected-task-context',status:'active',purpose:string(input.purpose||'所选任务生成','用途',500)})).id};
      }
      if(action==='connector.revoke') {const connector=owned('connector');for(const approval of this.list(user,'approval').filter(item=>item.data.scopes.includes('model')&&item.data.status==='approved'))s.update(approval,{...approval.data,status:'revoked'},user);return {id:s.update(connector,{...connector.data,status:'revoked'},user).id};}
      if(action==='skill.create') {
        const task=s.owned(user,input.task_id,'task');if(task.data.status!=='completed') fail('OUTCOME_REQUIRED','先验收真实任务结果');
        return {id:s.add('skill',user,{title:string(input.title,'方法名',100),instructions:string(input.instructions,'复用方法',4000),task_id:task.id,outcome_id:task.data.outcome_id,status:'draft',permissions:['read'],uses:0}).id};
      }
      if(action==='shortcut.pin') {
        const skill=s.owned(user,input.skill_id,'skill');const shortcut=s.unique('shortcut',`${user}:${skill.id}`,()=>s.add('shortcut',user,{skill_id:skill.id,pinned:false}));
        return {id:s.update(shortcut,{...shortcut.data,pinned:!shortcut.data.pinned},user).id};
      }
      if(action==='data.request') {
        const kind=enumeration(input.kind,['export','delete'],'数据请求');
        if(input.confirm!==true) fail('CONFIRMATION_REQUIRED','请确认数据请求');
        return {id:s.add('data_request',user,{kind,status:kind==='export'?'ready':'pending_policy',note:kind==='delete'?'已登记。生产保留/删除政策尚待确定；本地管理员按备份恢复手册处理。':'仅导出本人当前有权读取的对象'}).id};
      }
      fail('UNKNOWN_COMMAND','未知业务操作',404);
    });
  }
  search(user,input) {return search(this.store,user,input);}
  events(user,after=0) {
    const visible=[];
    let cursor=after;
    // Materialize bounded batches: Node 22's SQLite iterator can outlive its statement.
    const statement=this.store.db.prepare('SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT 300');
    while(true){
      const batch=statement.all(cursor);
      for(const event of batch){
        cursor=event.seq;
        if(this.store.canRead(user,this.store.get(event.object_id)))visible.push({...event,metadata:JSON.parse(event.metadata)});
        if(visible.length===300)return visible;
      }
      if(batch.length<300)break;
    }
    return visible;
  }
  publicProfile(handle) {
    const user=this.store.db.prepare('SELECT id FROM users WHERE handle=?').get(handle);
    const profile=user&&this.store.list('profile').find(item=>item.owner===user.id&&item.data.public);
    if(!profile) fail('NOT_FOUND','该用户尚未公开资料',404);
    return profile.data.published;
  }
  export(user) {return {exported_at:now(),user:this.store.user(user),objects:Object.fromEntries(READ_TYPES.map(type=>[type,this.list(user,type)])),checksum:hash(user+now())};}
}
