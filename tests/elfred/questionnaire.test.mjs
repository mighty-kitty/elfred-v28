import test from 'node:test';
import assert from 'node:assert/strict';
import {Store,id} from '../../server/elfred/store.mjs';
import {authenticate} from '../../server/elfred/auth.mjs';
import {Service} from '../../server/elfred/service.mjs';
import {Runtime} from '../../server/elfred/runtime.mjs';
import {questionnaireView,questionnaireBaseline} from '../../server/elfred/questionnaire.mjs';
import {QUESTIONNAIRE_ITEMS,dimensionInsight,observationsFromOutcomes,scoreQuestionnaire} from '../../app/v28/core/dimensions.mjs';

function setup(t){
 const store=new Store(':memory:');t.after(()=>store.close());
 const provider={status:()=>({configured:true}),generate:async()=>({output:'结论：本次交付的真实结果。依据如下。',usage:{total_tokens:20}})};
 const service=new Service(store,provider),user=authenticate(store,'questionnaire-owner','questionnaire-password',true,'本人').user;service.initialize(user);
 const command=(a,i)=>service.command(user.id,id(),a,i),ref=o=>({id:o.id,version:store.get(o.id).version});
 return {store,provider,service,user,command,ref};
}

// 每题按自己的选项数取档（3 档的情境题没有第 5 档），choice 超过上限就取最高档。
const answerAll=choice=>QUESTIONNAIRE_ITEMS.map(item=>({id:item.id,choice:Math.min(choice,item.options.length-1)}));
const answerIdeal=()=>QUESTIONNAIRE_ITEMS.map(item=>({id:item.id,choice:item.key<0?0:item.options.length-1}));

test('题目与选项来自题库本身，给出去的题面不含内部字段',t=>{
 const e=setup(t),view=questionnaireView(e.store,e.user.id);
 assert.equal(view.items.length,22);
 assert.deepEqual(view.dimensions,['洞察','判断','表达','链接','交付']);
 for(const item of view.items)assert.deepEqual(Object.keys(item).sort(),['id','options','text']);
 assert.doesNotMatch(JSON.stringify(view.items),/"(key|guard|dimension)"/);
 assert.equal(view.taken,false);
});

test('起点落在低区间；一路点同意不会变成全都强',t=>{
 const e=setup(t),flat=scoreQuestionnaire(answerAll(4));
 for(const name of ['洞察','交付','表达','链接','判断']){
  const value=flat.axes[name];
  assert.ok(value>=22&&value<=52,`${name} 起点 ${value} 应落在 22—52`);
 }
 assert.equal(flat.axes['判断'],52);
 // 洞察在这份题库里是 1 正 3 反：一路点同意会把这一维压到低位（29.5），而不是抬到高位
 assert.equal(flat.axes['洞察'],29.5);
 assert.ok(flat.guard>0.5,`正反向项互相打架时 guard 应偏高，实际 ${flat.guard}`);
 const ideal=scoreQuestionnaire(answerIdeal());
 assert.equal(ideal.guard,0);
 for(const name of Object.keys(ideal.axes))assert.equal(ideal.axes[name],52);
});

test('提交落进当前会话的对象表；重测覆盖同一份起点',t=>{
 const e=setup(t);
 assert.throws(()=>e.command('questionnaire.submit',{answers:answerAll(3).slice(0,10)}),{code:'INVALID_INPUT'});
 const first=e.command('questionnaire.submit',{answers:answerAll(3)});
 assert.equal(first.ok,true);
 const rows=e.store.visible(e.user.id,'dimension_baseline');
 assert.equal(rows.length,1);
 assert.equal(rows[0].data.status,'active');
 assert.equal(rows[0].data.answers.length,22);
 const baseline=questionnaireBaseline(e.store,e.user.id);
 assert.deepEqual(baseline.axes,first.axes);
 assert.equal(questionnaireView(e.store,e.user.id).taken,true);
 assert.equal(e.service.bootstrap(e.user.id).objects.dimension_baseline.length,1);
 const again=e.command('questionnaire.submit',{answers:answerIdeal()});
 const rows2=e.store.visible(e.user.id,'dimension_baseline');
 assert.equal(rows2.length,1);
 assert.equal(rows2[0].id,rows[0].id);
 assert.equal(rows2[0].version,rows[0].version+1);
 assert.equal(again.axes['洞察'],52);
});

test('空态：没测过也没成果的维不给数字，不画全 0 的图',t=>{
 const e=setup(t),insight=dimensionInsight({});
 assert.equal(insight.started,false);
 assert.equal(insight.composite,null);
 assert.equal(insight.baseline,null);
 for(const axis of insight.axes){
  assert.equal(axis.value,null);
  assert.equal(axis.lower,null);
  assert.equal(axis.source,'insufficient');
 }
});

test('起点给一张偏低的图；一条成果只动对应那一维，不把综合分顶上去',t=>{
 const e=setup(t),scored=scoreQuestionnaire(answerAll(3));
 const baseline={axes:scored.axes,guard:scored.guard,version:2,takenAt:new Date().toISOString()};
 const started=dimensionInsight({baseline});
 assert.equal(started.started,true);
 assert.equal(started.axes.every(axis=>axis.source==='baseline'),true);
 assert.ok(started.composite!==null&&started.composite<60,`起点综合分应偏低，实际 ${started.composite}`);

 const at=new Date().toISOString();
 const one=dimensionInsight({baseline,observations:observationsFromOutcomes([{system:'advise',satisfaction:'satisfied',at}])});
 const judge=one.axes.find(axis=>axis.label==='判断');
 const insightAxis=one.axes.find(axis=>axis.label==='洞察');
 assert.equal(judge.samples,1);
 assert.equal(judge.source,'growing');
 assert.ok(judge.value>baseline.axes['判断'],'验收一件判断类的活，判断这一维应该往上走');
 assert.equal(insightAxis.value,baseline.axes['洞察']);
 assert.ok(one.composite<60,`一件成果不该把综合分顶到 60 以上，实际 ${one.composite}`);

 const three=dimensionInsight({baseline,observations:observationsFromOutcomes(
  Array.from({length:3},()=>({system:'advise',satisfaction:'satisfied',at}))) });
 assert.equal(three.axes.find(axis=>axis.label==='判断').source,'evidence');
 assert.equal(three.verifiedDimensions,1);
});

test('端到端：跑完一件活并本人验收，这一维按真实成果动；久不用的证据按半衰期回落',async t=>{
 const e=setup(t),scored=scoreQuestionnaire(answerAll(3));
 e.command('questionnaire.submit',{answers:answerAll(3)});
 const baseline=questionnaireBaseline(e.store,e.user.id);
 assert.deepEqual(baseline.axes,scored.axes);

 const task=e.command('task.create',{goal:'比较两个方案',system:'advise',review_mode:'single'});
 e.command('task.confirm',{...e.ref(task),confirm:true,model_consent:true});
 e.command('run.start',e.ref(task));
 await new Runtime(e.store,e.provider).tick();
 e.command('task.accept',{...e.ref(task),accept:true,satisfaction:'satisfied'});

 // 前端投影走的就是这一条：成果 → 观测 → 估计（按同一个 system/dimension 归属）
 const tasks=new Map(e.store.list('task').map(item=>[item.id,item]));
 const rows=e.store.list('outcome').filter(item=>item.data.verdict==='accepted').map(item=>({
  dimension:'',system:tasks.get(item.data.task_id)?.data.system,satisfaction:tasks.get(item.data.task_id)?.data.satisfaction,at:item.created}));
 const insight=dimensionInsight({baseline,observations:observationsFromOutcomes(rows),outcomeCount:rows.length});
 const judge=insight.axes.find(axis=>axis.label==='判断');
 assert.equal(insight.outcomeCount,1);
 assert.equal(judge.samples,1);
 assert.ok(judge.value>baseline.axes['判断']);
 assert.equal(insight.axes.find(axis=>axis.label==='交付').samples,0);

 const old=new Date(Date.now()-300*86400000).toISOString();
 const decayed=dimensionInsight({baseline,observations:observationsFromOutcomes([{system:'advise',satisfaction:'satisfied',at:old}])});
 const stale=decayed.axes.find(axis=>axis.label==='判断');
 assert.ok(Math.abs(stale.value-baseline.axes['判断'])<0.5,`半衰期之后旧证据应几乎不动分，实际 ${stale.value}`);
});
