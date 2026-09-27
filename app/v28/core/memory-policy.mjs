export const memoryGroups=['基础','社交','习惯','偏好'];
export const memorySystems=['owner','explore','advise','create','connect','execute'];
/** @type {Record<string,string>} */
export const systemNames={owner:'个人',explore:'探索',advise:'参谋',create:'创作',connect:'连接',execute:'执行'};
export const memoryAdmitted=item=>item.data.status==='validated'||item.data.status==='learned'&&item.data.risk==='low';
export function memoryActive(item,at=Date.now()){
  const d=item.data||{};
  return !d.hidden&&!['deleted','rejected','superseded','expired','deferred','needs_review'].includes(d.status)&&(!d.expires_at||Date.parse(d.expires_at)>Number(at));
}
export function memoryGroup(content){
  if(/身份|职业|工作是|我是|健康|财务|收入|住在|年龄/.test(content))return '基础';
  if(/同事|朋友|家人|关系|联系他人|公开发布|合作|社交/.test(content))return '社交';
  if(/习惯|每天|每周|节奏|作息|提醒|日程/.test(content))return '习惯';
  return '偏好';
}
