import {sourceRefs} from './knowledge.mjs';
import {projectActive,mergeFiles} from './project-work.mjs';
import { fail, hash, now } from './store.mjs';
import { string, enumeration } from './policy.mjs';
import {attachmentRefs} from './attachments.mjs';
import {validateWebArtifact} from './preview.mjs';
import {slotCommand,publicSlots,checkSlot,requiresApproval} from './project-slots.mjs';

export function communityCommand(store,user,action,input) {
  if(/^(post|project|claim|copy|contribution)\./.test(action)&&(!store.user(user)||input.actor_type==='agent'||input.auto_publish===true))fail('HUMAN_REQUIRED','社区内容只能由登录用户主动发布',403);
  const slotResult=slotCommand(store,user,action,input);if(slotResult)return slotResult;
  const member=projectId=>{const project=projectActive(store,user,projectId);if(!store.role(projectId,user)) fail('FORBIDDEN','需要项目成员权限',403);return project;};
  if(action==='post.follow_author'){
    const post=store.read(user,input.id);if(!['post','release'].includes(post.type)||post.visibility!=='public'||post.owner===user)fail('INVALID_INPUT','请选择其他真人公开发表的内容');
    const interaction=store.unique('interaction',`${user}:author:${post.owner}`,()=>store.add('interaction',user,{object_id:post.owner,kind:'follow_author',active:false}));return {id:store.update(interaction,{...interaction.data,active:!interaction.data.active},user).id};
  }
  if(action==='post.create'||action==='post.edit') {
    const existing=action==='post.edit'?store.expect(store.owned(user,input.id,'post'),input.version):null;
    if(existing?.data.project_id) fail('INVALID_INPUT','共创招募请从项目管理更新');
    if(input.confirm!==true) fail('CONFIRMATION_REQUIRED','请确认将正文公开到社区');
    const data={title:string(input.title,'标题',200),content:string(input.content,'正文',12000),author_name:store.user(user).name,kind:'discussion',author_type:'human',published_by:user,attachments:attachmentRefs(store,user,input.attachment_ids??existing?.data.attachments?.map(item=>item.id)??[]),status:'published'};
    return {id:existing?store.update(existing,{...existing.data,...data},user).id:store.add('post',user,data,{visibility:'public'}).id};
  }
  if(action==='post.withdraw') {
    const post=store.expect(store.owned(user,input.id,'post'),input.version);
    if(input.confirm!==true) fail('CONFIRMATION_REQUIRED','请确认撤下公开帖子');
    if(post.data.project_id) fail('INVALID_INPUT','共创招募请从项目管理停止招募');
    return {id:store.update(post,{...post.data,status:'withdrawn'},user).id};
  }
  if(action==='project.recruiting') {
    const project=store.expect(store.owned(user,input.id,'project'),input.version);
    if(project.data.status==='ended')fail('PROJECT_CLOSED','项目已结束');
    const recruiting=input.enabled===true;
    for(const post of store.list('post').filter(item=>item.data.project_id===project.id))store.update(post,{...post.data,status:recruiting?'recruiting':'closed'},user);
    return {id:store.update(project,{...project.data,recruiting},user).id};
  }
  if(action==='project.create') {
    const project=store.add('project',user,{title:string(input.title,'项目名',200),goal:string(input.goal,'项目目标',3000),criteria:string(input.criteria,'验收标准',2000),task:string(input.task,'开放任务',2000),basis:input.basis?string(input.basis,'已有基础',3000):'',public_scope:input.public_scope?enumeration(input.public_scope,['brief'],'公开范围'):'',reviewer_id:input.reviewer_id===user?user:null,fee_terms:input.fee_terms?string(input.fee_terms,'费用说明',1000):'',deadline_mode:input.deadline_mode?enumeration(input.deadline_mode,['none','date'],'截止设置'):'',deadline:input.deadline_mode==='date'?string(input.deadline,'截止日期',40):null,participation:enumeration(input.participation||'open',['open','application'],'参与方式'),status:'active',recruiting:false,revision:0,content:'',release_id:null},{visibility:'members'});
    store.join(project.id,user,'owner');return {id:project.id};
  }
  if(action==='project.brief.update') {
    const project=store.expect(store.owned(user,input.id,'project'),input.version);
    if(project.data.status==='ended')fail('PROJECT_CLOSED','项目已结束');
    const deadline_mode=enumeration(input.deadline_mode,['none','date'],'截止设置');
    const deadline=deadline_mode==='date'?string(input.deadline,'截止日期',40):null;
    if(deadline&&(!Number.isFinite(Date.parse(deadline))||Date.parse(deadline)<=Date.now()))fail('INVALID_DEADLINE','截止日期必须晚于现在');
    const data={...project.data,title:string(input.title,'项目名',200),goal:string(input.goal,'项目目标',3000),criteria:string(input.criteria,'验收标准',2000),task:string(input.task,'开放任务',2000),basis:string(input.basis,'已有基础',3000),public_scope:enumeration(input.public_scope,['brief'],'公开范围'),reviewer_id:input.reviewer_id===user?user:null,fee_terms:string(input.fee_terms,'费用说明',1000),deadline_mode,deadline,participation:enumeration(input.participation,['open','application'],'参与方式')};
    if(!data.reviewer_id)fail('INVALID_REVIEWER','当前需由项目发起者本人负责最终审核');
    const updated=store.update(project,data,user);
    const autoSlot=store.list('project_slot').find(slot=>slot.space===project.id&&slot.data.auto_brief);
    if(autoSlot&&(autoSlot.data.title!==data.task||autoSlot.data.criteria!==data.criteria||autoSlot.data.participation!==data.participation)){
      slotCommand(store,user,'project.slot.save',{id:autoSlot.id,version:autoSlot.version,project_id:project.id,title:data.task,criteria:data.criteria,participation:data.participation,capacity:null,risk:autoSlot.data.risk,deadline:autoSlot.data.deadline,depends_on:autoSlot.data.depends_on||[]});
    }
    return {id:updated.id,version:updated.version};
  }
  if(action==='project.publish_post') {
    const project=store.expect(store.owned(user,input.id,'project'),input.version);
    if(input.confirm!==true) fail('CONFIRMATION_REQUIRED','请确认公开文字和参与范围');
    const missing=['title','goal','basis','task','criteria','participation','public_scope','reviewer_id','fee_terms','deadline_mode'].filter(key=>!project.data[key]);
    if(missing.length)fail('BRIEF_INCOMPLETE','公开前请补齐：'+missing.join('、'));
    if(project.data.deadline_mode==='date'&&(!project.data.deadline||Date.parse(project.data.deadline)<=Date.now()))fail('INVALID_DEADLINE','截止日期必须晚于现在');
    if(project.data.reviewer_id!==project.owner)fail('INVALID_REVIEWER','当前需由发起者本人负责最终审核');
    // The first brief task is a real claimable task, even when the owner has not
    // split the work into more detailed slots yet.
    if(!store.list('project_slot').some(slot=>slot.space===project.id)){
      const created=slotCommand(store,user,'project.slot.save',{project_id:project.id,title:project.data.task,criteria:project.data.criteria,capacity:null,participation:project.data.participation});
      const slot=store.get(created.id);store.update(slot,{...slot.data,auto_brief:true},user);
    }
    const existing=store.list('post').find(item=>item.data.project_id===project.id);
    const recruiting=existing?project.data.recruiting:true;
    const data={kind:'cocreation',author_type:'human',published_by:user,slots:publicSlots(store,project.id),title:project.data.title,author_name:store.user(user).name,content:project.data.goal,basis:project.data.basis,public_scope:project.data.public_scope,reviewer_name:store.user(project.owner).name,fee_terms:project.data.fee_terms,deadline_mode:project.data.deadline_mode,deadline:project.data.deadline,criteria:project.data.criteria,task:project.data.task,project_id:project.id,status:recruiting?'recruiting':'closed',participation:project.data.participation};
    if(!existing)store.update(project,{...project.data,recruiting:true},user);
    return {id:existing?store.update(existing,data,user).id:store.add('post',user,data,{visibility:'public'}).id};
  }
  if(action==='project.claim') {
    const post=store.read(user,input.post_id,'post'),project=store.get(post.data.project_id);
    if(!project?.data.recruiting || post.data.status!=='recruiting') fail('CLOSED','项目已停止招募');
    if(input.confirm!==true) fail('CONFIRMATION_REQUIRED','请确认本人参与承诺');
    if(store.list('claim').some(item=>item.owner===user&&item.data.project_id===project.id&&item.data.status==='removed'))fail('MEMBERSHIP_REVOKED','参与资格已撤销，需要发起者重新批准',403);
    const publishedSlots=post.data.slots||[];
    const implicit=publishedSlots.length===1&&publishedSlots[0].auto_brief?publishedSlots[0]:null;
    const slot=input.slot_id?store.get(input.slot_id):implicit?store.get(implicit.id):null;
    if(!slot&&store.list('project_slot').some(s=>s.space===project.id))fail('SLOT_REQUIRED','请选择具体任务位，并按其名额与审批规则参与');
    if(slot&&!(post.data.slots||[]).some(item=>item.id===slot.id))fail('INVALID_SLOT','任务位尚未公开');
    const previous=store.list('claim').find(item=>item.owner===user&&item.data.project_id===project.id&&(item.data.slot_id||null)===(slot?.id||null));
    if(previous&&['accepted','pending','needs_reconfirmation'].includes(previous.data.status))return {id:previous.id,project_id:project.id};
    checkSlot(store,project,slot,slot?.id);
    if(slot)store.expect(slot,input.slot_version??implicit?.rules_version);
    if(slot&&(post.data.slots||[]).find(published=>published.id===slot.id)?.rules_version!==slot.version)fail('SLOT_RULES_CHANGED','任务约定正在更新，请等待发起者重新公开后再确认');
    if(previous){const status=requiresApproval(project,slot)?'pending':'accepted';store.update(previous,{...previous.data,status,withdrawn_at:null,rules_version:slot?.version||null,rules_snapshot:slot?.data||{criteria:project.data.criteria}},user);if(status==='accepted')store.join(project.id,user);return {id:previous.id,project_id:project.id};}
    const claim=store.unique('claim',`${project.id}:${user}:${slot?.id||'general'}`,()=>store.add('claim',user,{project_id:project.id,slot_id:slot?.id||null,status:requiresApproval(project,slot)?'pending':'accepted',goal:slot?.data.title||project.data.task,rules_version:slot?.version||null,rules_snapshot:slot?.data||{criteria:project.data.criteria}}));
    if(claim.data.status==='accepted') store.join(project.id,user);
    return {id:claim.id,project_id:project.id};
  }
  if(action==='claim.review') {
    const claim=store.get(input.id);if(!claim || claim.type!=='claim') fail('NOT_FOUND','申请不存在',404);
    const project=store.owned(user,claim.data.project_id,'project');store.expect(claim,input.version);
    if(input.accept===true&&!project.data.recruiting)fail('CLOSED','项目已停止招募');
    if(claim.data.status!=='pending') fail('INVALID_STATE','申请已处理',409);
    if(input.accept===true){const slot=claim.data.slot_id?store.get(claim.data.slot_id):null;if(slot&&claim.data.rules_version!==slot.version)fail('SLOT_RULES_CHANGED','任务约定已变化，请由申请人重新确认');checkSlot(store,project,slot,claim.data.slot_id);store.join(claim.data.project_id,claim.owner);}
    return {id:store.update(claim,{...claim.data,status:input.accept===true?'accepted':'declined',review_note:string(input.note||(input.accept===true?'发起者已批准':'本次申请未获接纳，可调整后重新申请'),'审核说明',1000)},user).id};
  }
  if(action==='project.remove_member') {
    const project=store.expect(store.owned(user,input.id,'project'),input.version);
    if(input.user_id===project.owner) fail('INVALID_INPUT','不能移除项目发起者');
    store.db.prepare('DELETE FROM members WHERE space=? AND user_id=?').run(project.id,input.user_id);
    for(const claim of store.list('claim').filter(item=>item.owner===input.user_id&&item.data.project_id===project.id)) store.update(claim,{...claim.data,status:'removed'},user);
    return {id:store.update(project,{...project.data,membership_updated:now()},user).id};
  }
  if(action==='copy.create') {
    const project=member(input.project_id);
    const implicit=user!==project.owner&&!input.slot_id?store.list('claim').find(c=>c.owner===user&&c.data.project_id===project.id&&c.data.status==='accepted'&&store.get(c.data.slot_id)?.data.auto_brief):null;
    if(user!==project.owner&&!input.slot_id&&!implicit&&store.list('project_slot').some(s=>s.space===project.id))fail('SLOT_REQUIRED','请选择已认领的具体任务位创建副本');
    const slot=input.slot_id||implicit?.data.slot_id?store.read(user,input.slot_id||implicit.data.slot_id,'project_slot'):null;
    if(slot&&(slot.space!==project.id||user!==project.owner&&!store.list('claim').some(c=>c.owner===user&&c.data.slot_id===slot.id&&c.data.status==='accepted')))fail('FORBIDDEN','请先认领此任务位',403);
    return {id:store.add('copy',user,{project_id:project.id,slot_id:slot?.id||null,format:project.data.format||'text',access_space:project.id,base_revision:project.data.revision,content:project.data.content,files:project.data.files||{},base_files:project.data.files||{},rules_snapshot:slot?.data||{criteria:project.data.criteria},status:'draft'}).id};
  }
  if(action==='copy.save') {
    const copy=store.expect(store.owned(user,input.id,'copy'),input.version);member(copy.data.project_id);
    if(copy.data.status!=='draft') fail('INVALID_STATE','该副本已提交；请创建新的工作副本',409);
    const format=enumeration(input.format||copy.data.format||'text',['text','web'],'成果格式'),content=string(input.content,'成果正文',200000);
    const build=format==='web'?validateWebArtifact(content,copy.data.files||{}):null;
    const updated=store.update(copy,{...copy.data,content,format,build,files:{...(copy.data.files||{}),[format==='web'?'index.html':'成果.md']:content}},user);
    return {id:updated.id,version:updated.version};
  }
  if(action==='copy.revise') {
    const copy=store.expect(store.owned(user,input.id,'copy'),input.version),project=member(copy.data.project_id);
    const rebased=mergeFiles(copy.data.base_files||{},project.data.files||{},copy.data.files||{});
    const files={...rebased.files};for(const path of rebased.conflicts)if(copy.data.files?.[path]!==undefined)files[path]=copy.data.files[path];else delete files[path];
    const primary=copy.data.format==='web'?'index.html':'成果.md';
    return {id:store.add('copy',user,{project_id:project.id,access_space:project.id,base_revision:project.data.revision,content:files[primary]??copy.data.content,format:copy.data.format||'text',slot_id:copy.data.slot_id||null,upstream_content:project.data.content,origin_copy:copy.id,stage_refs:copy.data.stage_refs||[],files,base_files:project.data.files||{},unresolved_conflicts:rebased.conflicts,rules_snapshot:copy.data.rules_snapshot,status:'draft'}).id};
  }
  if(action==='copy.submit') {
    const copy=store.expect(store.owned(user,input.id,'copy'),input.version);member(copy.data.project_id);
    if(copy.data.status!=='draft'||!copy.data.content) fail('INVALID_STATE','需要未提交的非空副本',409);
    if(input.reviewed!==true) fail('REVIEW_REQUIRED','本人审核后才能提交贡献');
    if(copy.data.unresolved_conflicts?.length)fail('CONFLICT_UNRESOLVED','请先逐文件核对并确认解决冲突');
    sourceRefs(store,user,copy.data.stage_refs||[]);
    for(const ref of copy.data.stage_refs||[]){if(!store.role(copy.data.project_id,store.get(ref.id)?.owner))fail('DEPENDENCY_CHANGED','阶段贡献者已退出，请重新选择工作依据');}
    const contribution=store.add('contribution',user,{project_id:copy.data.project_id,copy_id:copy.id,files:copy.data.files||{[copy.data.format==='web'?'index.html':'成果.md']:copy.data.content},base_files:copy.data.base_files||{},rules_snapshot:copy.data.rules_snapshot,stage_refs:copy.data.stage_refs||[],content:copy.data.content,format:copy.data.format||'text',slot_id:copy.data.slot_id||null,content_hash:hash(copy.data.content),base_revision:copy.data.base_revision,status:'submitted',reviewed_by:user},{space:copy.data.project_id,visibility:'members'});
    store.update(copy,{...copy.data,status:'submitted',contribution_id:contribution.id},user);
    return {id:contribution.id};
  }
  if(action==='contribution.review') {
    const contribution=store.expect(store.read(user,input.id,'contribution'),input.version);
    const project=store.owned(user,contribution.data.project_id,'project');
    if(contribution.data.status!=='submitted') fail('INVALID_STATE','贡献已处理',409);
    const decision=enumeration(input.decision,['accept','reject','changes'],'审查决定');
    let status={accept:'accepted',reject:'rejected',changes:'changes_requested'}[decision];
    const merged=mergeFiles(contribution.data.base_files||{},project.data.files||{},contribution.data.files||{});
    if(decision==='accept' && contribution.data.base_revision!==project.data.revision&&merged.conflicts.length) status='conflicted';
    if(status==='accepted') store.update(project,{...project.data,revision:project.data.revision+1,content:contribution.data.content,format:contribution.data.format||'text',files:merged.files,accepted_contributions:[...(project.data.accepted_contributions||[]),contribution.id],accepted_contribution:contribution.id},user);
    if(status==='accepted'&&contribution.data.slot_id){const slot=store.get(contribution.data.slot_id);if(slot)store.update(slot,{...slot.data,status:'completed'},user);}
    return {id:store.update(contribution,{...contribution.data,status,conflict_files:merged.conflicts,feedback:string(input.feedback||'已审核','反馈',2000),reviewer:user},user).id};
  }
  if(action==='project.feedback') {
    const project=member(input.id);
    const stage=input.stage_id?store.read(user,input.stage_id,'project_stage'):null;
    if(stage&&(stage.space!==project.id||!['shared','superseded'].includes(stage.data.status)||!Number.isInteger(input.stage_version)||stage.version!==input.stage_version))fail('STAGE_CHANGED','所选阶段版本已变化，请重新核对',409);
    return {id:store.add('feedback',user,{content:string(input.content,'阶段反馈',5000),kind:enumeration(input.kind||'progress',['progress','blocked','dependency','review'],'反馈类型'),stage_ref:stage?{id:stage.id,version:stage.version}:null},{space:project.id,visibility:'members'}).id};
  }
  if(action==='project.release') {
    const project=store.expect(store.owned(user,input.id,'project'),input.version);
    if(input.confirm!==true || !project.data.accepted_contribution) fail('REVIEW_REQUIRED','需已有采纳成果并由本人确认发布');
    if(input.execute===true&&project.data.format!=='web') fail('SANDBOX_UNAVAILABLE','当前环境仅支持静态文本成果，未开放用户代码执行',503);
    const build=project.data.format==='web'?validateWebArtifact(project.data.content,project.data.files||{}):null;
    const release=store.unique('release',`${project.id}:${project.data.revision}`,()=>store.add('release',user,{title:project.data.title,purpose:project.data.goal,author_name:store.user(user).name,tool_description:string(input.tool_description||'真人审核并发布；未另附工具说明','工具说明',1000),content:project.data.content,files:project.data.files||{},origin_release:project.data.origin_release||null,contributors:(project.data.accepted_contributions||[project.data.accepted_contribution]).map(id=>{const c=store.get(id);return {contribution_id:id,user_id:c.owner,name:store.user(c.owner).name}}),revision:project.data.revision,project_id:project.id,contribution_id:project.data.accepted_contribution,content_hash:hash(project.data.content),status:'published',author_type:'human',published_by:user,format:project.data.format||'text',build,preview:build?'sandboxed-web':'escaped-text-only',license:input.allow_fork===true?'copy-with-attribution':'view-only'},{visibility:'public'}));
    store.update(project,{...project.data,release_id:release.id},user);for(const post of store.list('post').filter(x=>x.data.project_id===project.id))store.update(post,{...post.data,release_id:release.id},user);return {id:release.id};
  }
  if(action==='project.rollback') {
    const project=store.expect(store.owned(user,input.id,'project'),input.version),release=store.read(user,input.release_id,'release');
    if(release.data.project_id!==project.id) fail('INVALID_INPUT','版本不属于此项目');
    for(const post of store.list('post').filter(x=>x.data.project_id===project.id))store.update(post,{...post.data,release_id:release.id},user);
    return {id:store.update(project,{...project.data,release_id:release.id},user,'project.rollback').id};
  }
  if(action==='project.fork') {
    const release=store.read(user,input.release_id,'release');
    if(release.data.license!=='copy-with-attribution') fail('LICENSE_REQUIRED','发布者尚未授予复制许可',403);
    const project=store.add('project',user,{title:release.data.title+' · 再创作',goal:string(input.goal,'新目标',3000),criteria:'由本人审核新成果',task:'继续创作',participation:'open',status:'active',recruiting:false,revision:0,content:release.data.content,format:release.data.format||'text',release_id:null,origin_release:release.id,origin_author:release.owner,files:release.data.files||{}},{visibility:'members'});
    store.join(project.id,user,'owner');return {id:project.id};
  }
  if(action==='post.interact') {
    const post=store.read(user,input.id);if(!['post','release'].includes(post.type))fail('INVALID_INPUT','仅能对社区内容互动');
    const kind=enumeration(input.kind,['like','save','hide','report'],'互动');
    const item=store.unique('interaction',`${user}:${post.id}:${kind}`,()=>store.add('interaction',user,{object_id:post.id,kind,active:false}));
    return {id:store.update(item,{...item.data,active:!item.data.active},user).id};
  }
  if(action==='post.comment') {
    const post=store.read(user,input.id);if(!['post','release'].includes(post.type))fail('INVALID_INPUT','仅能对社区内容评论');
    return {id:store.add('comment',user,{post_id:post.id,author_type:'human',published_by:user,author_name:store.user(user).name,content:string(input.content,'评论',5000),status:'published'},{visibility:'public'}).id};
  }
  return null;
}
