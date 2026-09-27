import {taskCommand} from './runtime.mjs';
import {enumeration,string,DEFAULT_STOP} from './policy.mjs';
import {publicQuery,webIntent} from './public-web.mjs';
export function externalToolCommand(store,user,action,input,provider){
 if(action!=='external.prepare')return null;
 const operation=enumeration(input.operation,['web_search','image_generate'],'执行能力'),goal=string(input.goal,'本次问题或图片描述',3000);
 const publicResearch=operation==='web_search'&&provider?.status().web_search!=='configured'&&provider?.status().public_web==='available';
 const lookup=publicResearch?webIntent(publicQuery(goal),'web'):null;
 const task=taskCommand(store,user,'task.create',{goal,system:operation==='web_search'?'explore':'create',review_mode:'single',source_refs:[],constraints:operation==='web_search'?'仅将本次问题提交公开互联网检索，不读取私人库，不自动发送或发布。':'只生成一张 1024 × 1024 的低质量预览图，不发送或公开发布。',stop:{...DEFAULT_STOP,maxCalls:publicResearch?2:1,maxUnits:1000,maxTokens:publicResearch?50000:24000}});
 return {id:store.update(store.get(task.id),{...store.get(task.id).data,...(lookup?{web_lookup:lookup,public_research:true}:{media_operation:operation})},user).id};
}
