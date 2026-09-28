const directions = {
 interest: ['科技','产品','设计','创意','兴趣'], ability: ['职业','技能','学习','能力','实践'],
 problem: ['产品','用户','需求','问题','解决'], opportunity: ['创业','市场','机会','创新','产品'],
};
const formats = {
 concept: ['方案','创意','设计','概念'], prototype: ['原型','设计','界面','产品'],
 content: ['内容','创作','写作','作品'], product: ['产品','开发','软件','应用','工具'],
};
export function discoveryInterests(summary) {
 const option=id=>summary.find(item=>item.question_id===id&&item.certainty==='selected')?.option;
 const specific=summary.find(item=>item.question_id==='interests'&&item.certainty==='selected')?.label||'';
 return [...new Set([...specific.split(/[，,、；;\s]+/u).map(word=>word.trim()).filter(word=>word.length>=2&&word.length<=30).slice(0,8),...(directions[option('direction')]||[]),...(formats[option('format')]||[])])];
}
export function discoveryRelevance(item, interests=[]) {
 const content=(String(item.title||'')+' '+String(item.summary||'')).toLocaleLowerCase();
 return interests.reduce((score,word)=>score+(content.includes(word.toLocaleLowerCase())?1:0),0);
}
