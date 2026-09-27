export type Capability={id:string;system:string;name:string;version:number;kind:'skill'|'check'|'monitor'|'tool';purpose:string;steps:string[];outputs:string[];checks:string[];limitations:string|null};
export type Entity={id:string;type:string;owner:string;space:string|null;visibility:'private'|'members'|'public';version:number;created:string;updated:string;data:Record<string,unknown>;members?:{id:string;name:string;handle:string;role:string}[];unread?:number};
export type User={id:string;handle:string;name:string};
export type Snapshot={memory_hub?:{configured:boolean;mode:string;pending:number;last_synced_at:string|null;contract:string};module_errors?:Record<string,string>;user:User;provider:{public_web?:string;web_search?:string;image_generate?:string;embedding?:string;embedding_model?:string;configured:boolean;model:string|null;judge:string;jev:string};systems:{id:string;name:string;roles:string[]}[];definitions:Capability[];objects:Record<string,Entity[]>;budget:{limit_units:number;reserved:number;spent:number};usage:{id:string;run_id:string;reserved:number;actual:number|null;status:string;created:string}[];server_time:string};
export type Result={id:string;version_id?:string;version?:number;task_id?:string;run_id?:string;artifact_id?:string;conversation_id?:string;project_id?:string};
export type Command=(action:string,input:Record<string,unknown>)=>Promise<Result|undefined>;
export const text=(item:Entity|undefined,key:string)=>String(item?.data[key]??'');
export const assetText=(item:Entity)=>{
  const content=text(item,'content')||text(item,'instructions')||text(item,'text')||text(item,'goal');
  if(content.trim().startsWith('['))try{const hits=JSON.parse(content);if(Array.isArray(hits)&&hits.every(hit=>typeof hit.title==='string'&&typeof hit.excerpt==='string'))return hits.map(hit=>hit.title+'\n'+hit.excerpt+'\n定位：'+(hit.anchor||'')).join('\n\n')}catch{}
  return content;
};
export const ref=(item:Entity)=>({id:item.id,version:item.version});
export const statuses:Record<string,string>={draft:'草稿',ready:'待启动',queued:'排队中',running:'运行中',blocked:'待配置或补充',failed:'失败',partial:'部分完成',paused:'已暂停',cancelled:'已取消',cancel_requested:'正在取消',pause_requested:'正在暂停',completed:'已完成',awaiting_acceptance:'待验收',awaiting_review:'待核对',reconciliation_required:'待对账',pending:'待处理',accepted:'已接受',declined:'已拒绝',validated:'已确认',learned:'自动记录',candidate:'待验证',pending_confirmation:'待本人确认',superseded:'已被修正',needs_review:'待重评',rejected:'已否认',deferred:'已搁置',submitted:'待审查',changes_requested:'请修改',conflicted:'版本冲突',published:'已发布',recruiting:'招募中',active:'有效',revoked:'已撤销',approved:'已批准',insufficient:'理解不足',explicit:'明确表达',hypothesis:'待验证理解',scenario_verified:'情境验证',stable_over_time:'跨时间稳定'};
