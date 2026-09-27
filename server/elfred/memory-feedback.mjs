import {now} from './store.mjs';
import {queueMemorySync} from './memory-hub.mjs';
import {memoryUsable,memoryEvidenceActive,memoryCounterevidenceActive} from './memory-validity.mjs';
import {memoryApplies,memoryTopic,semanticOverlap} from './memory-allocation.mjs';

const positive=/符合我的(?:偏好|习惯|要求)|符合预期|(?:这次|这个|这样的).*(?:结构|格式|顺序|语气|安排|来源|中文|篇幅).*(?:合适|满意|喜欢|正确)|(?:结构|格式|顺序|语气|安排|来源|篇幅).*(?:正合适|符合|满意)|就按这个(?:结构|格式|顺序|方式)/;
const negative=/不符合|不合适|不合我的|不满意|不正确|不喜欢|没.*满意|不是我的|不要再|别再|不对|太长|太短|不要.*(?:结论|背景)/;
const topicWords={结构顺序:/结论|背景|结构|顺序|问题定义/,表达语气:/语气|口吻|正式|随意/,内容篇幅:/篇幅|长度|长|短|详细|简洁/,回复语言:/中文|英文|语言/,安排习惯:/安排|提醒|日程|节奏|作息/,来源要求:/来源|核验|查证|核实/};
function linkedFeedback(memory,text,single){
 const topic=memory.data.topic||memoryTopic(memory.data.content);
 return single&&/符合我的(?:偏好|习惯|要求)/.test(text)||Boolean(topic&&topicWords[topic]?.test(text))||semanticOverlap(memory.data.content,text)>=2;
}
export function recordNaturalMemoryFeedback(store,user,{text,source,refs,system,scenario,outcome=null,reply=null}){
 if(/^(以后|今后|每次|请记住|我(?:喜欢|偏好|习惯|更喜欢))/.test(String(scenario)))return;
 if(positive.test(String(scenario))||negative.test(String(scenario))||/^(好[的啊呀吧]?|谢谢|收到)[。！!\s]*$/.test(String(scenario)))return;
 if(!source||source.owner!==user||source.data.actor_type==='agent'||!store.canRead(user,source)||(!positive.test(text)&&!negative.test(text)))return;
 for(const ref of refs||[]){
  const memory=store.get(ref.id);
  if(!memory||memory.owner!==user||memory.data.kind==='method_experience'||memory.version!==ref.version||!memoryUsable(store,memory)||!memoryApplies(memory,system,text)||!linkedFeedback(memory,text,(refs||[]).length===1))continue;
  const entry={...(outcome?{outcome_id:outcome.id,outcome_version:outcome.version}:{}),source_id:source.id,source_version:source.version,reply_id:reply?.id||null,reply_version:reply?.version||null,system,scenario:String(scenario).slice(0,200),note:text,observed_at:source.created,confirmed_at:source.created,automatic:true};
  if(negative.test(text)){
   if((memory.data.counterevidence||[]).some(e=>e.source_id===source.id))continue;
   queueMemorySync(store,store.update(memory,{...memory.data,alignment:'hypothesis',counterevidence:[...(memory.data.counterevidence||[]),{...entry,at:source.created}]},user));continue;
  }
  if((memory.data.evidence||[]).some(e=>e.source_id===source.id))continue;
  const evidence=[...(memory.data.evidence||[]),entry];
  const valid=evidence.filter(e=>memoryEvidenceActive(store,memory,e)&&(!e.system||e.system===system));
  const counter=(memory.data.counterevidence||[]).some(e=>memoryCounterevidenceActive(store,memory,e)&&(!e.system||e.system===system));
  const stable=valid.length>=2&&new Set(valid.map(e=>e.observed_at.slice(0,10))).size>=2&&new Set(valid.map(e=>e.scenario)).size>=2;
  const alignment=counter?'hypothesis':stable?'stable_over_time':'scenario_verified';
  queueMemorySync(store,store.update(memory,{...memory.data,evidence,alignment,automatic_review:{system,at:now(),reason:counter?'仍有未解决反证':stable?'不同日期与场景的真实反馈持续支持':'本次真实反馈支持'},...(stable?{stability_review:{at:now(),automatic:true,evidence_ids:valid.map(e=>e.source_id||e.outcome_id)}}:{})},user));
 }
}
export function dialogueMemoryFeedback(store,user,conversation,message){
 const reply=store.visible(user,'message').filter(m=>m.data.conversation_id===conversation.id&&m.data.actor_type==='agent'&&m.data.seq<message.data.seq).sort((a,b)=>b.data.seq-a.data.seq)[0];
 const run=reply&&store.get(reply.data.run_id),task=run&&store.get(run.data.task_id);
 if(!run||!task||task.owner!==user||!['completed','awaiting_review'].includes(run.data.status))return;
 recordNaturalMemoryFeedback(store,user,{text:message.data.text,source:message,refs:run.data.memory_refs,system:conversation.data.system,scenario:task.data.goal,reply});
}
export function taskMemoryFeedback(store,user,task,run,outcome,text){
 if(task.data.project_id||task.data.access_space||task.data.group_agent||!text)return;
 const source=store.add('feedback',user,{kind:'memory_validation',task_id:task.id,content:text,status:'recorded'});
 recordNaturalMemoryFeedback(store,user,{text,source,refs:run.data.memory_refs,system:task.data.system,scenario:task.data.goal,outcome});
}
