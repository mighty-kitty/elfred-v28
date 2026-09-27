import {memoryGroup} from '../../app/v28/core/memory-policy.mjs';

export const memoryRisk=content=>/我是|我叫|职业|住在|年龄|身份|在读|学生|大学|价值观|我.*(?:认为|相信|信奉)|健康|疾病|患有|患了|诊断|抑郁|焦虑症|糖尿病|过敏|用药|服药|服用.*药|财务|收入|工资|月薪|负债|贷款|资产|存款|投资|密码|密钥|api.?key|银行卡|身份证|住址|性取向|宗教|关系|家人|朋友|公开发布|联系他人|长期目标|人生目标|自动发送|自动支付/i.test(content)?'high':'low';
const domains=[
 ['connect',/沟通|协作|合作|社交|同事|朋友|家人|关系|联系|人际|团队交流/],
 ['execute',/提醒|日程|作息|安排|执行|截止|期限|任务拆解|每天|每周|早起|熬夜|工作节奏/],
 ['explore',/资讯|信息源|新闻|检索|搜索|核实|核验|来源|查证|订阅|关注.*(?:科技|行业|比赛|资讯)/],
 ['advise',/决策|选择方案|选方案|比较|取舍|风险分析|建议方案|优先级|权衡/],
 ['create',/写作|写.*(?:方案|文章|文案|代码|报告)|文档|产品方案|文章|文案|代码|表达风格|段落|结论|背景|问题定义|写方案/],
];
export function memoryTopic(content){
 if(/结论|背景|问题定义|结构|顺序/.test(content))return '结构顺序';
 if(/语气|口吻|正式|随意/.test(content))return '表达语气';
 if(/简短|简洁|详细|长文|字数|篇幅/.test(content))return '内容篇幅';
 if(/中文|英文|语言/.test(content))return '回复语言';
 if(/提醒|作息|日程|每天|每周|节奏/.test(content))return '安排习惯';
 if(/信息源|来源|核验|核实|查证/.test(content))return '来源要求';
 if(/健康|疾病|熬夜/.test(content))return '健康限制';
 if(/职业|身份|我是/.test(content))return '身份信息';
 return null;
}
export function allocateMemory(content,originSystem,{scope=null,contextual=false}={}){
 const risk=memoryRisk(content),group=memoryGroup(content);
 const scenario=memoryScenario(content);
 const explicitGlobal=/所有.*(?:Agent|助手)|任何.*(?:回答|回复|解释)|无论.*(?:任务|场景)/i.test(content);
 const replyStyle=/(?:回答|回复|解释|和我说话).*(?:中文|英文|简短|简洁|详细)/.test(content);
 const identity=/我是|我叫|职业|住在|年龄|身份|在读|学生|大学|健康|疾病|患有|患了|服用.*药|财务|收入|工资|资产|我.*(?:认为|相信|信奉)|价值观|长期目标|人生目标/.test(content);
 const matching=domains.filter(([,rule])=>rule.test(content));
 const global=!scenario&&(explicitGlobal||replyStyle&&matching.length===0);
 const target=scope||(identity||global?'owner':matching[0]?.[0]||originSystem);
 const allowed=target==='owner'&&risk==='low'&&global?['explore','advise','create','connect','execute']:[];
 return {scope:target,group,risk,topic:memoryTopic(content),allocation:{version:1,holder:target,origin_system:originSystem,reason:scope?'本人或原初始化题目指定领域':identity?'个人高影响理解':global?'通用工作偏好':matching.length?'内容与职责匹配':'当前领域限定理解',allowed_systems:allowed,contextual:contextual||Boolean(scenario),scenario}};
}
export function memoryScenario(content){
 const action=String(content).match(/(?:写|撰写|生成|起草|整理|修改)([^，。；\n]{1,24}?)(?:时|先|都|要|需|改成|改为|回复|[，。；]|$)/)?.[1]?.trim();
 if(!action||/^(作|代码的风格|东西)$/.test(action))return null;
 const recipient=String(content).match(/(?:给|向)([^，。；\n]{1,12}?)(?:写|发|汇报|沟通)/)?.[1]?.trim();
 return recipient?`${recipient}:${action}`:action;
}
export function memoryScenarioApplies(memory,query){
 const scenario=memory.data.allocation?.scenario;
 return !scenario||scenario.split(':').every(part=>String(query).includes(part));
}
export function memoryApplies(memory,system,query=''){
 if(memory.data.scope===system)return true;
 if(memory.data.scope!=='owner'||!memory.data.allocation?.allowed_systems?.includes(system))return false;
 if(memory.data.risk==='low')return true;
 return memory.data.status==='validated'&&semanticOverlap(memory.data.content,query)>=2;
}
export function semanticOverlap(a,b){
 const text=String(a).toLowerCase(),other=String(b).toLowerCase();
 const terms=new Set(text.match(/[a-z0-9]{2,}/g)||[]);
 for(const phrase of text.match(/[\u4e00-\u9fff]{2,}/g)||[])for(let i=0;i<phrase.length-1;i++)terms.add(phrase.slice(i,i+2));
 return [...terms].reduce((n,t)=>n+Number(other.includes(t)),0);
}
