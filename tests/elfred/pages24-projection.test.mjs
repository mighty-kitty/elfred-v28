import test from 'node:test';
import assert from 'node:assert/strict';
import { projectSnapshot } from '../../app/v28/features/pages24/api/page2-projector.ts';

// 投影是纯函数（进来一个快照，出去一份视图），所以它能被 Node 直接 import 做单测 ——
// 页面上每个数字都从这里出来，这里钉住口径比在浏览器里点更早、更准。
// 需要 / 不需要的东西在 `tests/elfred/pages24-scoring.test.mjs`（公式本身）里也钉了一遍。

const SKILL_MARKDOWN = [
  '---', 'name: 会议纪要整理', '---', '',
  '## 什么时候用', '用户把一段会议记录交给你，需要整理成能直接执行的东西时。', '',
  '## 怎么做', '1. 通读记录，分出已决定的事和要做的事', '2. 每条待办写清负责人和截止时间', '',
  '## 交付什么', '一张待办表：事项 / 负责人 / 截止 / 依据哪句话',
].join('\n');

const ts = (minutesAgo) => new Date(Date.now() - minutesAgo * 60000).toISOString();
const entity = (id, type, data, created = ts(60)) => ({ id, type, owner: 'u1', space: null, visibility: 'private', version: 1, created, updated: created, data });

function snapshotWith({ skills = [], tasks = [], outcomes = [], knowledge = [], memories = [], friends = [], documents = [], resources = [] } = {}) {
  return {
    user: { id: 'u1', handle: 'me', name: '本人' },
    provider: { configured: true, model: 'deepseek-chat', judge: 'rule-baseline', jev: 'configured' },
    systems: [], definitions: [], budget: { limit_units: 0, reserved: 0, spent: 0 }, usage: [], server_time: ts(0),
    objects: {
      profile: [entity('p1', 'profile', { name: '本人', showLevel: true })],
      skill: skills, task: tasks, outcome: outcomes, knowledge, memory: memories, friend: friends,
      document: documents, resource: resources, forge_request: [], dimension_baseline: [],
    },
  };
}

test('能力卡：分数/等级/阶梯来自这张卡自己的成果，维度按归属系统给', () => {
  const skill = entity('s1', 'skill', { title: '会议纪要整理', kind: 'Skill', system: 'execute', instructions: SKILL_MARKDOWN });
  const tasks = [0, 1, 2].map((index) => entity(`t${index}`, 'task', { title: '整理会议纪要', goal: '整理会议纪要', skill_id: 's1', system: 'execute', satisfaction: 'satisfied', source_refs: [] }));
  const outcomes = [0, 1, 2].map((index) => entity(`o${index}`, 'outcome', { task_id: `t${index}`, verdict: 'accepted' }, ts(30 - index)));

  const data = projectSnapshot(snapshotWith({ skills: [skill], tasks, outcomes }));
  const card = data.capabilities[0];
  assert.equal(card.dimension, '交付', '说明书没写维度时按归属系统算，不是"未标注"');
  assert.equal(card.evidence, 3);
  assert.ok(card.score > 60, `三件验收过的成果要给出分数：${card.score}`);
  assert.equal(card.level, 2);
  assert.equal(card.stage, '有证据');
  assert.equal(card.copy, '用户把一段会议记录交给你，需要整理成能直接执行的东西时。');
  assert.deepEqual(card.ladder.map((rung) => rung.gate), [0, 3, 6, 10, 15]);
});

test('别人的成果不算这张卡的：没有成果就不给分，阶梯显示还差几件', () => {
  const skill = entity('s1', 'skill', { title: '没人用过的卡', kind: 'Skill', system: 'create', instructions: '' });
  const task = entity('t1', 'task', { title: '别的活', goal: '别的活', skill_id: 's2', system: 'create', satisfaction: 'satisfied' });
  const outcome = entity('o1', 'outcome', { task_id: 't1', verdict: 'accepted' });

  const card = projectSnapshot(snapshotWith({ skills: [skill], tasks: [task], outcomes: [outcome] })).capabilities[0];
  assert.equal(card.score, null);
  assert.equal(card.evidence, 0);
  assert.equal(card.verified, false);
  assert.match(card.gapLabel, /还差 3 项成果/);
});

test('任务验收产物只出现在成果里，不再混进"资料"', () => {
  const task = entity('t1', 'task', { title: '整理会议纪要', goal: '整理会议纪要', skill_id: 's1', system: 'execute', satisfaction: 'satisfied' });
  const outcome = entity('o1', 'outcome', { task_id: 't1', verdict: 'accepted' });
  const artifact = entity('k1', 'knowledge', { title: '整理会议纪要', content: '结果正文', outcome_id: 'o1', status: 'active' });
  const note = entity('k2', 'knowledge', { title: '本人记的笔记', content: '随手记', status: 'active' });
  const document = entity('d1', 'document', { title: '访谈.md', content: '访谈记录', status: 'active' });

  const data = projectSnapshot(snapshotWith({ tasks: [task], outcomes: [outcome], knowledge: [artifact, note], documents: [document] }));
  const names = data.documents.map((row) => row.name);
  assert.deepEqual(names.sort(), ['本人记的笔记', '访谈.md'], '资料 = 文档 + 本人记的知识');
  assert.equal(data.evidence.length, 1);
  assert.equal(data.evidence[0].title, '整理会议纪要');
});

test('理解度：页头那个百分比由成果/记忆/问卷算出来，不是恒 0', () => {
  const task = entity('t1', 'task', { title: '整理会议纪要', goal: '整理会议纪要', system: 'execute', satisfaction: 'satisfied', source_refs: [{ id: 'k1', version: 1 }] });
  const outcomes = [0, 1].map((index) => entity(`o${index}`, 'outcome', { task_id: 't1', verdict: 'accepted' }, ts(20 - index)));
  const memory = entity('m1', 'memory', { content: '我平时写方案喜欢先给结论', group: '偏好', scope: 'owner', status: 'validated', alignment: 'explicit', source_quote: '我平时写方案喜欢先给结论' });
  const baseline = entity('b1', 'dimension_baseline', { axes: { 洞察: 30, 判断: 52, 表达: 37, 链接: 37, 交付: 37 }, guard: 1, questionnaire_version: 2, taken_at: ts(100), status: 'active' });

  const snapshot = snapshotWith({ tasks: [task], outcomes, memories: [memory] });
  snapshot.objects.dimension_baseline = [baseline];
  const data = projectSnapshot(snapshot);
  assert.ok(data.alignment.alignment > 10, `做过问卷 + 两件外部核对，理解度应明显高于起点：${data.alignment.alignment}`);
  assert.equal(data.alignment.level >= 1, true);
  assert.equal(typeof data.alignment.nextGate, 'number');
  assert.equal(data.alignment.externalChecks, 2);
  assert.equal(data.alignment.confirmedMemories, 1);
});

test('说明书按 SKILL.md 拆开：能做到什么 / 步骤 / 交付 / 原文都在', () => {
  const skill = entity('s1', 'skill', { title: '会议纪要整理', kind: 'Skill', system: 'execute', instructions: SKILL_MARKDOWN });
  const live = projectSnapshot(snapshotWith({ skills: [skill] })).skills[0];
  assert.deepEqual(live.canDo, ['用户把一段会议记录交给你，需要整理成能直接执行的东西时。']);
  assert.equal(live.steps.length, 2);
  assert.match(live.outputs[0], /一张待办表/);
  assert.equal(live.stepCount, 2);
  assert.equal(live.instructions, SKILL_MARKDOWN, '"完整说明"要拿到原文');
  assert.equal(live.summary, '用户把一段会议记录交给你，需要整理成能直接执行的东西时。');
});

test('空账号：三块都是空数组/空值，界面据此走空态（不是拿演示数据顶上）', () => {
  const data = projectSnapshot(snapshotWith());
  assert.deepEqual(data.capabilities, []);
  assert.deepEqual(data.evidence, []);
  assert.deepEqual(data.documents, []);
  assert.equal(data.alignment.alignment, 10, '没见过你 = 一成的起点');
  assert.equal(data.alignment.level, 1);
});
