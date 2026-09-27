// Calendar arithmetic uses the user's saved time zone, including DST boundaries.
function parts(at,zone){return Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(at).filter(p=>p.type!=='literal').map(p=>[p.type,Number(p.value)]));}
function midnight(day,zone){const target=Date.UTC(day.getUTCFullYear(),day.getUTCMonth(),day.getUTCDate());let guess=target;for(let i=0;i<4;i++){const p=parts(guess,zone),wall=Date.UTC(p.year,p.month-1,p.day,p.hour,p.minute,p.second),adjust=target-wall;if(!adjust)break;guess+=adjust;}return new Date(guess).toISOString();}
export function relativeRange(query,zone='Asia/Shanghai',at=new Date()){
 const words=['上周','本周','昨天','今天'].filter(w=>query.includes(w));
 if(words.length!==1)return {conflict:words.length>1};
 const p=parts(at,zone),day=new Date(Date.UTC(p.year,p.month-1,p.day)),word=words[0];
 if(word.includes('周'))day.setUTCDate(day.getUTCDate()-((day.getUTCDay()+6)%7)-(word==='上周'?7:0));else if(word==='昨天')day.setUTCDate(day.getUTCDate()-1);
 const end=new Date(day);end.setUTCDate(end.getUTCDate()+(word.includes('周')?7:1));
 return {after:midnight(day,zone),before:midnight(end,zone),label:`${word}按${word.includes('周')?'周一开始的自然周':'自然日'}，时区 ${zone}`};
}
export function resolveSearchContext(store,user,query,input){
 const resolved={...input},notes=[],uncertainties=[];let contentQuery=query;
 const settings=store.visible(user,'settings')[0],zone=settings?.data.timezone||'Asia/Shanghai';
 const range=relativeRange(query,zone);
 if(range.conflict)uncertainties.push('相对时间条件冲突，请明确一个时间范围');
 else if(range.after&&!input.after&&!input.before){resolved.after=range.after;resolved.before=range.before;notes.push(range.label);contentQuery=contentQuery.replace(/上周|本周|昨天|今天/g,' ');}
 const conversations=store.visible(user,'conversation');
 if(!input.space&&!/这个群|那个群/.test(query)){const mentioned=conversations.filter(c=>c.data.kind==='group'&&c.data.title&&query.includes(c.data.title));if(mentioned.length===1){resolved.space=mentioned[0].id;notes.push(`群聊：${mentioned[0].data.title}`);contentQuery=contentQuery.replace(mentioned[0].data.title,' ');}else if(mentioned.length>1)uncertainties.push('群名称不唯一，请选择具体会话');}
 if(!input.author&&/发的|发送的|分享的/.test(query)){
   const people=[...new Map(conversations.filter(c=>!resolved.space||c.id===resolved.space).flatMap(c=>store.members(c.id)).map(p=>[p.id,p])).values()];
   const matches=people.filter(p=>[p.name,p.handle].some(name=>name&&query.includes(name)&&new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'(?:在[^，。]{0,40})?(?:发的|发送的|分享的)').test(query)));
   if(matches.length===1){resolved.author=matches[0].id;notes.push(`发送者：${matches[0].name} · @${matches[0].handle}`);for(const name of [matches[0].name,matches[0].handle].filter(Boolean))contentQuery=contentQuery.replace(name,' ');}else uncertainties.push(matches.length?'存在同名发送者，请明确选择':'未能确定发送者，请从可访问的成员中选择');
 }
 resolved.content_query=contentQuery;return {resolved,notes,uncertainties};
}
