import {observationCommand} from './observation.mjs';
import {discoveryInterests} from './discovery-policy.mjs';

export function discoveryGoal(summary){
  const selected=summary.filter(item=>item.certainty==='selected'&&['need','direction','interests','criteria','format','cooperation','pace'].includes(item.question_id));
  if(!selected.length)return null;
  return `根据本人初始化选择，持续寻找对当前方向有实际帮助的近期公开资料：${selected.map(item=>`${item.question} ${item.label}`).join('；')}。优先原始来源，说明与本人选择的关联；资料不足则标明未知，不编造机会或成果。`;
}

export function discoveryQuery(summary){
  const option=id=>summary.find(item=>item.question_id===id&&item.certainty==='selected')?.option;
  const direction={interest:'科技 产品',ability:'职业 技能',problem:'产品 用户问题',opportunity:'创业 市场机会'}[option('direction')]||'产品 创新';
  const format={concept:'创意',prototype:'原型',content:'内容创作',product:'产品开发'}[option('format')]||'项目实践';
  const interests=summary.find(item=>item.question_id==='interests'&&item.certainty==='selected')?.label?.slice(0,48)||'';
  return `${interests||direction} ${format}`;
}

function feedUrl(summary){
  const url=new URL('https://news.google.com/rss/search');
  url.searchParams.set('q',discoveryQuery(summary));url.searchParams.set('hl','zh-CN');url.searchParams.set('gl','CN');url.searchParams.set('ceid','CN:zh-Hans');
  return url.href;
}

export function provisionInitialDiscovery(store,user,summary,{start=false}={}){
  const key=`${user}:onboarding-discovery`;
  const existing=store.db.prepare('SELECT object_id FROM unique_keys WHERE namespace=? AND key=?').get('observation',key);
  const goal=discoveryGoal(summary);
  if(!goal){const prior=existing&&store.get(existing.object_id);if(prior?.data.auto_suggested&&prior.data.status==='active')store.update(prior,{...prior.data,status:'paused'},user);return null;}
  if(!existing&&store.visible(user,'observation').filter(item=>['draft','active','paused','blocked'].includes(item.data.status)).length>=20)return null;
  const watch=store.unique('observation',key,()=>{
    const created=observationCommand(store,user,'observation.create',{goal,source_url:feedUrl(summary),keywords:discoveryQuery(summary),system:'explore',interval_hours:24,max_checks:20,expires:new Date(Date.now()+30*86400000).toISOString()});
    return store.get(created.id);
  });
  // Migrate confirmed preferences on existing watches without overriding pause/stop decisions.
  let current=watch;
  if(['draft','active','paused','blocked'].includes(current.data.status)){
   const preferences={goal,title:goal.slice(0,80),source_url:feedUrl(summary),source_urls:[feedUrl(summary),'https://sspai.com/feed','https://www.ifanr.com/feed'],keywords:[discoveryQuery(summary)],interests:discoveryInterests(summary),auto_suggested:true};
   if(Object.entries(preferences).some(([key,value])=>JSON.stringify(current.data[key])!==JSON.stringify(value)))current=store.update(current,{...current.data,...preferences},user);
  }
  if(start&&current.data.status==='draft'){
   current=store.update(current,{...current.data,auto_managed:true,authorized_by:'onboarding.choice.confirm'},user);
   observationCommand(store,user,'observation.start',{id:current.id,version:current.version,confirm:true});
   current=store.get(current.id);
   current=store.update(current,{...current.data,auto_managed:true,authorized_by:'onboarding.choice.confirm'},user);
  }
  else if(start&&current.data.status==='active'&&!current.data.auto_managed)current=store.update(current,{...current.data,auto_managed:true,authorized_by:'onboarding.choice.confirm'},user);
  return current;
}
