// Render the recorded history, never planned future steps, as execution logs.
const statuses={queued:'进入执行队列',running:'开始执行',pause_requested:'请求暂停',paused:'已暂停',cancel_requested:'请求停止',cancelled:'已停止',awaiting_review:'成果已生成，等待本人核对',needs_review:'成果已生成，等待本人核对',completed:'任务已完成',blocked:'运行受阻',partial:'部分步骤已完成',failed:'执行失败',reconciliation_required:'用量待核对'};
const phases={work:'生成成果',review:'核对结果',repair:'按反馈修订',collaboration:'协作准备',context:'读取资料'};
const tools={'document.read':'读取资料','search.local':'查找资料','owner.report':'记录本人完成结果','text.compose':'生成内容'};
export function playerLogs(store,user,id){
 const run=store.read(user,id,'run'),rows=store.db.prepare('SELECT data,at FROM object_versions WHERE object_id=? ORDER BY version').all(run.id);
 const logs=[],seen=new Set();let previousStatus='';
 for(const row of rows){
  const data=JSON.parse(row.data);
  if(data.status!==previousStatus){
   if(statuses[data.status])logs.push({at:row.at,message:statuses[data.status]});
   previousStatus=data.status;
  }
  for(const receipt of data.receipts||[]){
   const key=receipt.id||receipt.step_id;if(seen.has(key))continue;seen.add(key);
   const step=data.plan?.steps?.find(step=>step.id===receipt.step_id);
   const name=phases[receipt.phase||step?.phase||receipt.step_id]||tools[step?.tool]||'执行步骤';
   logs.push({at:receipt.at||row.at,message:name+' · '+(receipt.provider==='conditional-skip'||receipt.status==='skipped'?'无需修订，已跳过':'已记录结果')});
  }
 }
 return {items:logs.sort((a,b)=>a.at.localeCompare(b.at))};
}
