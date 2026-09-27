import { fail } from './store.mjs';

export const POLICY_VERSION = 'local-bounded-v1';
export const DEFAULT_STOP = Object.freeze({maxAttempts:3,maxReplans:1,maxSeconds:180,maxTokens:16384,maxCalls:8,maxUnits:6000});
export const TOOLS = Object.freeze({
  'search.local':{scope:'read',effect:'none',version:'1'},
  'context.read':{scope:'read',effect:'none',version:'1'},
  'document.read':{scope:'read',effect:'none',version:'1'},
  'web.search':{scope:'read_public',effect:'none',version:'1'},
  'web.read':{scope:'read_public',effect:'none',version:'1'},
  'text.compose':{scope:'model',effect:'generation',version:'1'},
});
export function string(value, name, max=10000, optional=false) {
  if (optional && (value === undefined || value === '')) return '';
  if (typeof value !== 'string' || !value.trim() || value.length>max) fail('INVALID_INPUT',`${name}需为 1—${max} 字文本`);
  return value.trim();
}
export function enumeration(value, values, name) {
  if (!values.includes(value)) fail('INVALID_INPUT',`${name}不支持此值`);
  return value;
}
export function bounded(value, name, min, max) {
  if (!Number.isSafeInteger(value) || value<min || value>max) fail('INVALID_INPUT',`${name}需在 ${min}—${max} 之间`);
  return value;
}
export function stopPolicy(input) {
  if (!input || typeof input!=='object') fail('STOP_POLICY_REQUIRED','运行必须具有有限停止条件');
  for (const key of Object.keys(DEFAULT_STOP)) bounded(input[key],key,1, key==='maxSeconds'?3600:key==='maxTokens'?100000:key==='maxUnits'?100000:key==='maxReplans'?5:20);
  return Object.fromEntries(Object.keys(DEFAULT_STOP).map(key=>[key,input[key]]));
}
export function planGate(plan, goal, grants) {
  stopPolicy(goal.stop);
  if (!Array.isArray(plan.steps) || !plan.steps.length || plan.steps.length>12) fail('INVALID_PLAN','计划需包含 1—12 步');
  const byId = new Map(plan.steps.map(step=>[step.id,step]));
  if (byId.size!==plan.steps.length) fail('INVALID_PLAN','步骤 ID 不得重复');
  const done=new Set(), visiting=new Set();
  const visit=step=>{
    if (visiting.has(step.id)) fail('INVALID_PLAN','计划存在循环依赖');
    if (done.has(step.id)) return;
    if (!TOOLS[step.tool]) fail('TOOL_FORBIDDEN','工具未在白名单注册',403);
    if (!grants.includes(TOOLS[step.tool].scope)) fail('GRANT_REQUIRED','缺少当前工具授权',403);
    if (!Array.isArray(step.depends)) fail('INVALID_PLAN','缺少步骤依赖');
    visiting.add(step.id);
    for (const dependency of step.depends) {
      if (!byId.has(dependency)) fail('INVALID_PLAN','步骤依赖不存在');
      visit(byId.get(dependency));
    }
    visiting.delete(step.id); done.add(step.id);
  };
  plan.steps.forEach(visit);
  return {decision:'permit',policy_version:POLICY_VERSION,checked_at:new Date().toISOString()};
}
export function verify(goal, steps, receipts) {
  const failures=[];
  for (const step of steps) {
    const receipt=receipts.find(item=>item.step_id===step.id && item.status==='succeeded');
    if (!receipt || !receipt.output_hash || receipt.effect_status!=='verified') failures.push({step_id:step.id,kind:'missing_evidence'});
  }
  if (failures.length) return {verdict:'unknown',decision:'targeted_repair',failures};
  // Generated prose cannot establish semantic goal acceptance by itself.
  if (steps.some(step=>step.tool==='text.compose')) return {verdict:'unknown',decision:'pause_for_human',failures:[{kind:'human_review_required',criterion:goal.criteria}]};
  if (!receipts.some(receipt=>receipt.output?.length)) return {verdict:'not_satisfied',decision:'pause_for_human',failures:[{kind:'no_results'}]};
  return {verdict:'satisfied',decision:'accept',failures:[]};
}
