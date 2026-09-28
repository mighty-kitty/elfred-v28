// Source: user's 2026-09-19 conversation, final question sequence (not the compressed M01 outline).
export const choiceVersion=3;
export const interestOptions=['AI 产品','科技','设计','编程','创业','商业','金融','教育','健康','科学','内容创作','摄影','游戏','旅行','本地生活','职业发展','文化','环保'];
export function interestLabels(value){
 const labels=Array.isArray(value)?value:String(value||'').split(/[，,、；;\n]+/u);
 return [...new Set(labels.map(label=>String(label).trim()).filter(Boolean))];
}
const fallback=[['none','都不符合'],['unsure','暂时不确定'],['skip','以后再说']];
const question=(id,agent,title,options)=>({id,agent,title,options:[...options,...fallback].map(([id,label])=>({id,label}))});
export const alignmentQuestions=[
 question('need','owner','你现在最需要解决什么？',[['direction','找到方向'],['compare','比较方向'],['make','做出成果'],['collaborate','找人合作'],['act','推进执行']]),
 question('direction','explore','你希望从哪里寻找项目方向？',[['interest','近期兴趣'],['ability','已有能力'],['problem','身边问题'],['opportunity','外部趋势与机会']]),
 question('interests','explore','你感兴趣的领域是什么？',[['specified','选择感兴趣的领域']]),
 question('criteria','advise','选择方向时，你最看重什么？',[['interest','感兴趣'],['feasible','能做出来'],['value','有实际价值'],['risk','风险低'],['growth','有发展空间']]),
 question('format','create','你希望先形成什么结果？',[['concept','概念方案'],['prototype','页面原型'],['content','内容作品'],['product','可运行的小产品']]),
 question('cooperation','connect','这个项目需要别人参与吗？',[['solo','自己完成'],['advice','先听取建议'],['partner','寻找合作者'],['resources','寻找用户或资源']]),
 question('pace','execute','你希望以什么节奏开始？',[['today','今天完成第一步'],['week','本周做出原型'],['research','先调研再决定'],['todo','暂时只建立待办']]),
 question('initiative','owner','Agent 可以主动到什么程度？',[['on_request','我问时再回应'],['important','重要时提醒'],['suggest','可以主动提出建议'],['low_risk','低风险事项可以先处理']]),
 question('external','owner','涉及联系他人或公开发布时，可以做到哪一步？',[['recommend','只向我推荐'],['research','整理资料'],['draft','生成待确认草稿'],['ask','每次先问我']]),
];
export const firstValueChoices=[
 {id:'outline',label:'帮我梳理项目起步方案',system:'create',questions:['need','direction','interests','criteria','format','pace','initiative','external'],goal:'给出一份轻量项目起步方案，列出可选择的方向、首个小成果与下一步。'},
 {id:'compare',label:'帮我比较几个方向',system:'advise',questions:['need','direction','interests','criteria','initiative','external'],goal:'给出三个轻量项目候选方向，按用户选择的标准比较取舍。'},
 {id:'plan',label:'帮我安排第一步',system:'execute',questions:['need','format','cooperation','pace','initiative','external'],goal:'为轻量项目拟定第一步行动与可检查的完成标准，不直接改动日程或执行外部行动。'},
];
export function alignmentSummary(answers={}){
 return alignmentQuestions.map(q=>{const option=q.options.find(o=>o.id===answers[q.id]?.option),detail=q.id==='interests'&&option?.id==='specified'?interestLabels(answers[q.id]?.tags||answers[q.id]?.detail).join('、'):'';return {question_id:q.id,agent:q.agent,question:q.title,label:detail||option?.label||'尚未选择',option:option?.id||'skip',certainty:!option||['none','unsure','skip'].includes(option.id)||q.id==='interests'&&option.id==='specified'&&!detail?'uncertain':'selected',at:answers[q.id]?.at||null};});
}
