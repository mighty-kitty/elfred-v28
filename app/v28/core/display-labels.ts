import {fromMarkdown} from 'mdast-util-from-markdown';
import type {Entity} from '../features/live/types';

// Presentation only: stored names, IDs, versions and command inputs stay intact.
const uuid = /\b[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}\b/gi;
const opaque = /^(?:[\da-f]{32,}|(?:task|run|receipt|skill|document|knowledge|resource|outcome|attachment)[_-][\da-f-]{16,})$/i;
export const objectNames:Record<string,string>={skill:'工具',task:'任务',run:'执行记录',document:'文档',knowledge:'知识笔记',resource:'资料',attachment:'附件',outcome:'已验收成果',conversation:'会话',post:'社区动态',feed:'Agent 动态',project:'共创项目',release:'作品',copy:'工作副本',shared_record:'共享记录',memory:'记忆',inbox:'收件箱内容',message:'消息'};

export function displayTitle(value:unknown,fallback='未命名内容'){
  let title=String(value??'').trim();
  if(!title||opaque.test(title)||new RegExp('^'+uuid.source+'$','i').test(title))return fallback;
  // Old isolated QA fixtures appended a millisecond timestamp to their titles.
  // Do not remove dates, phones, order numbers or other numbers in user names.
  if(/^(?:延迟选择验收|延迟详情验收|隔离验收工具|隔离布局验收项目)(?:[\s_-]|[12]\d{12})/.test(title))title=title.replace(/[\s_-]*[12]\d{12}[A-Z]?(?:[\s_-]*[\da-f]{4,})?$/i,'').trim();
  const voice=title.match(/^语音-([12]\d{12})(\.[\w]+)$/);
  if(voice){const date=new Date(Number(voice[1]));title='语音 '+date.toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})+voice[2];}
  return title.replace(uuid,'相关记录')||fallback;
}

export function entityTitle(item:Entity|undefined,fallback?:string){
  return displayTitle(item?.data.title||item?.data.name,fallback||objectNames[item?.type||'']||'相关内容');
}

export function displayAnchor(anchor:string){
  return /^line:\d+$/.test(anchor)?`第 ${anchor.slice(5)} 行`:displayTitle(anchor,'原始内容');
}

export function displayError(message:string){
  if(/^(?:failed to fetch|networkerror when attempting to fetch resource\.?|network request failed|load failed)$/i.test(message.trim()))
    return '网络连接失败，请检查网络后重试';
  return message.replace(uuid,'相关记录').replace(/\b[\da-f]{32,}\b/gi,'校验信息');
}

// Produce readable card summaries from parsed Markdown without fetching links
// or exposing raw markup. Full content remains available in the read view.
export function markdownExcerpt(content:string,limit=200){
  const tree=fromMarkdown(content.slice(0,4000));
  const collect=(node:unknown):string=>{
    const value=node as {type:string;value?:string;alt?:string;children?:unknown[]};
    if(value.type==='html'||value.type==='definition')return '';
    if(value.type==='image')return value.alt||'';
    if(value.value!==undefined)return value.value;
    return (value.children||[]).map(collect).join(['root','list','listItem','blockquote'].includes(value.type)?' ':'');
  };
  return collect(tree).replace(/\s+/g,' ').trim().slice(0,limit);
}
