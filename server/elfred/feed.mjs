import {fail,now} from './store.mjs';
import {string,bounded,enumeration} from './policy.mjs';
import {FEED_DENSITY} from './feed-density.mjs';
import {taskCommand} from './runtime.mjs';
export function feedCommand(store,user,action,input){
 if(action==='feed.density.set'){
  const settings=store.expect(store.owned(user,input.id,'settings'),input.version);
  const modes=Object.keys(FEED_DENSITY),system=input.system?enumeration(input.system,['explore','advise','create','connect','execute'],'Agent'):null;
  const mode=enumeration(input.mode,system?[...modes,'inherit']:modes,'信息密度');
  const current=settings.data.feed_density||{global:'standard',agents:{}};
  const agents={...current.agents};
  if(system){if(mode==='inherit')delete agents[system];else agents[system]=mode;}
  return {id:store.update(settings,{...settings.data,feed_density:{global:system?current.global||'standard':mode,agents}},user).id};
 }
 if(action==='feed.peer_comments.policy'){
  const settings=store.expect(store.owned(user,input.id,'settings'),input.version);
  if(input.confirm!==true||input.enabled===true&&input.model_consent!==true)fail('CONSENT_REQUIRED','请确认私人朋友圈自动评论的模型使用和每日上限');
  const daily_limit=bounded(input.daily_limit,'每日评论上限',1,5);
  return {id:store.update(settings,{...settings.data,feed_peer_comments:{enabled:input.enabled===true,daily_limit,consented_at:input.enabled===true?now():settings.data.feed_peer_comments?.consented_at||null}},user).id};
 }
 if(action==='feed.topic.set'||action==='feed.topic.merge'||action==='feed.topic.remove'){
  const settings=store.visible(user,'settings')[0];
  if(!settings)fail('NOT_FOUND','设置不存在',404);
  const topic=string(input.topic,'话题',100),topics={...(settings.data.feed_topics||{})};
  if(action==='feed.topic.merge'){
   const into=string(input.into,'合并到话题',100);
   if(topic===into)fail('INVALID_INPUT','请选择不同的话题');
   if(!store.visible(user,'feed').some(item=>item.data.topic===topic)||!store.visible(user,'feed').some(item=>item.data.topic===into))fail('INVALID_INPUT','只能合并已有话题');
   topics[topic]={...(topics[topic]||{}),alias:into,removed:true};
  }else if(action==='feed.topic.remove'){
   topics[topic]={...(topics[topic]||{}),removed:true};
  }else{
   if(!store.visible(user,'feed').some(item=>item.data.topic===topic))fail('INVALID_INPUT','只能管理已有话题');
   const mode=String(input.mode||'normal');
   if(!['normal','follow','mute'].includes(mode))fail('INVALID_INPUT','话题状态不支持');
   topics[topic]={...(topics[topic]||{}),mode,removed:false};
  }
  store.update(settings,{...settings.data,feed_topics:topics},user);
  return {id:settings.id};
 }
 if(action==='feed.question'){
  const feed=store.expect(store.owned(user,input.id,'feed'),input.version),goal=string(input.goal,'追问',3000);
  const comment=input.comment_id?store.read(user,input.comment_id,'feedback'):null;
  if(comment&&(comment.data.feed_id!==feed.id||comment.data.kind!=='human_comment'))fail('INVALID_INPUT','只能回复此动态下本人的评论');
  const artifact=feed.data.artifact_id?store.read(user,feed.data.artifact_id):null,replies=store.visible(user,'feedback').filter(f=>f.data.feed_id===feed.id&&f.data.kind==='agent_response').slice(-3),sources=[feed,...(artifact?[artifact]:[]),...replies,...(comment?[comment]:[])];
  const content=JSON.stringify({title:feed.data.title,summary:feed.data.summary,original_url:feed.data.external_url||null,original_result:artifact?.data.content?.slice(0,1600)||'',human_comment:comment?.data.content||null,collaboration:(feed.data.comments||[]).slice(0,3).map(c=>({system:c.system,content:c.content.slice(0,400)})),recent_responses:replies.map(r=>({system:r.data.system,content:r.data.content.slice(0,400)})),scope_note:'本次为原成果、本人评论、协作意见及最近三条补充的有限摘录；长内容可能截断，不代替完整原文'});
  const context=store.add('resource',user,{title:'本次追问的事件与讨论摘录',content,source_refs:sources.map(s=>({id:s.id,version:s.version})),status:'active',internal_search:true});
  const result=taskCommand(store,user,'task.create',{goal,system:input.system||feed.data.system,source_refs:[{id:context.id,version:context.version}],review_mode:'single'});
  const task=store.get(result.id);store.update(task,{...task.data,feed_event_id:feed.id,...(comment?{feed_comment_id:comment.id}:{})},user);return result;
 }
 if(action==='feed.comment'){
  const feed=store.expect(store.owned(user,input.id,'feed'),input.version),content=string(input.content,'评论',2000);
  if(feed.data.status!=='active')fail('INVALID_INPUT','这条动态暂不能评论');
  return {id:store.add('feedback',user,{feed_id:feed.id,kind:'human_comment',content,status:'posted',source_refs:[{id:feed.id,version:feed.version}],created_at:now()}).id};
 }
 if(action==='feed.feedback'){
  const feed=store.expect(store.owned(user,input.id,'feed'),input.version),note=string(input.note,'内容反馈',2000);
  if(!['content_error','understanding_correction','direction'].includes(input.kind))fail('INVALID_INPUT','反馈类型不支持');
  return {id:store.add('feedback',user,{feed_id:feed.id,system:feed.data.system,kind:input.kind,content:note,status:'recorded',source_refs:[{id:feed.id,version:feed.version}],created_at:now()}).id};
 }
 return null;
}
export function feedEvidence(store,user,task,run){
 const generated=(run.data.receipts||[]).filter(r=>r.attachment_id).map(r=>({id:r.attachment_id}));
 const media=[...(task.data.source_refs||[]),...generated].map(ref=>store.get(ref.id)).filter(o=>o?.type==='attachment'&&store.canRead(user,o)).map(o=>({id:o.id,name:o.data.name,mime:o.data.mime,size:o.data.size}));
 const comments=(run.data.receipts||[]).filter(r=>r.phase==='collaboration'&&typeof r.output==='string').map(r=>({id:r.id,system:run.data.plan.steps.find(s=>s.id===r.step_id)?.system,content:r.output,run_id:run.id,step_id:r.step_id,at:r.at,status:'模型协作建议，随主责成果由本人核对'}));
 return {attachments:media,comments,reason:'来自本人实际验收的任务成果',personal_value:task.data.goal,uncertainty:'验收代表本人采用；模型意见仍需结合原始来源核对'};
}
