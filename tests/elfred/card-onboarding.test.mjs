import test from 'node:test';
import assert from 'node:assert/strict';
import { Store, id } from '../../server/elfred/store.mjs';
import { authenticate } from '../../server/elfred/auth.mjs';
import { Service } from '../../server/elfred/service.mjs';
import { parseSkillMarkdown } from '../../app/v28/core/skill-markdown.mjs';
import {
  CARD_FRAGMENTS, CARD_PRESETS, CARD_QUESTIONS, MAX_CARDS_PER_RUN, PREFERENCE_GROUPS,
  composeSkillMarkdown, composeTaskDraft, composeToolParameters, composeToolWorkflow,
  customPreset, inferSystem, normalizePreferences, presetById, validateSelection,
  presetIdFromText, resolveFragments, resolvePath,
} from '../../app/v28/core/card-onboarding.mjs';

// 这块要证明的不是"能生成一张卡"，而是"生成的是一张真能用的 skill"：
// 说明书四小节、输入能被问出来、前置步骤合法、任务草稿绑得对、跑起来有回执。

const provider = { status: () => ({ configured: true, jev: 'unconfigured' }) };

function setup(t) {
  const store = new Store(':memory:');
  t.after(() => store.close());
  const service = new Service(store, provider);
  const user = authenticate(store, 'card' + Math.random().toString(36).slice(2, 8), 'card-password-1', true, '本人').user;
  service.initialize(user);
  const command = (action, input) => service.command(user.id, id(), action, input);
  return { store, service, user, command };
}

test('选项表本身能站得住：15 张预置卡、字段齐全、主责系统互不重复的前置步骤', () => {
  assert.equal(CARD_PRESETS.length, 15);
  assert.equal(new Set(CARD_PRESETS.map((item) => item.id)).size, 15, 'id 不能重复');
  assert.deepEqual([...new Set(CARD_PRESETS.map((item) => item.system))].sort(), ['advise', 'connect', 'create', 'execute', 'explore']);
  for (const preset of CARD_PRESETS) {
    assert.ok(preset.title && preset.canDo && preset.deliver, `${preset.id} 缺标题/能做什么/交付`);
    assert.equal(preset.steps.length, 3, `${preset.id} 的步骤定了三条`);
    assert.ok(preset.inputs?.length >= 1, `${preset.id} 至少要有一样输入`);
    assert.ok(preset.inputs.some((item) => item.required), `${preset.id} 至少要有一项必填输入`);
    if (preset.preStep) assert.notEqual(preset.preStep.system, preset.system, '前置步骤必须换一个系统');
  }
});

test('说明书是四小节，能被卡片详情解析出「能做到什么 / 步骤 / 交付」', () => {
  const preset = presetById('create-draft');
  const markdown = composeSkillMarkdown(preset, { preferences: { conclusion: 'process-first', length: 'detailed' } });
  const parsed = parseSkillMarkdown(markdown);
  assert.equal(parsed.canDo[0], preset.canDo, '第一节就是"它能替你做"');
  assert.equal(parsed.steps.length, 3);
  assert.equal(parsed.outputs[0], preset.deliver);
  assert.ok(parsed.limits.join('').includes('先交代过程'), '改过的偏好要落进"注意"');
  assert.ok(parsed.limits.join('').includes('把依据和取舍都写出来'));
  // 没动过的偏好不再往"注意"里塞套话（默认值不是用户表达的偏好）
  assert.equal(composeSkillMarkdown(preset, {}).includes('复核按任务情况自动决定'), false);
});

test('偏好：没选就用默认值；只有改了默认的才值得记成理解', () => {
  const all = normalizePreferences({});
  assert.deepEqual(all, Object.fromEntries(PREFERENCE_GROUPS.map((group) => [group.id, group.defaultValue])));
  const changed = normalizePreferences({ conclusion: 'process-first', length: 'detailed' });
  assert.equal(changed.conclusion, 'process-first');
  assert.equal(changed.sources, 'cite', '没答的保持默认');
});

test('选择校验：空选择、未知选项、一次多于一张、超长的"其它"都被挡住', () => {
  assert.equal(validateSelection({}).ok, false);
  assert.equal(validateSelection({ preset_ids: ['不存在'] }).ok, false);
  assert.equal(validateSelection({ preset_ids: CARD_PRESETS.slice(0, MAX_CARDS_PER_RUN + 1).map((item) => item.id) }).ok, false);
  assert.equal(validateSelection({ custom_text: 'x'.repeat(300) }).ok, false);
  // 一次只做一张：现成的和"其它"不能同时来（界面也做成二选一）
  assert.equal(validateSelection({ preset_ids: ['create-draft'], custom_text: '帮我把课程通知整理成三条待办' }).ok, false);
  assert.equal(validateSelection({ preset_ids: ['create-draft'] }).presets.length, 1);
  const ok = validateSelection({ custom_text: '帮我把课程通知整理成三条待办' });
  assert.equal(ok.ok, true);
  assert.equal(ok.presets.length, 1);
  assert.equal(ok.presets[0].id, 'custom');
  // 关键词判不出"整理成待办"这种，就归执行——反正第二屏允许用户改归属，不硬猜
  assert.equal(ok.presets[0].system, 'execute');
  assert.equal(inferSystem('帮我找人一起做项目'), 'connect');
  assert.equal(inferSystem('帮我写一份周报'), 'create');
});

test('生成：这张卡落成 active skill + 任务草稿，三处数据同源', async (t) => {
  const e = setup(t);
  const result = e.command('card.onboard', {
    preset_ids: ['explore-sources'],
    preferences: { conclusion: 'process-first' },
  });
  assert.equal(result.created.length, 1);
  assert.ok(result.id, '每次初始化都留一笔记录');

  const skills = e.store.list('skill').filter((item) => item.owner === e.user.id);
  assert.equal(skills.length, 1);
  for (const skill of skills) {
    assert.equal(skill.data.status, 'active', '卡必须直接可用');
    assert.equal(skill.data.source, 'onboarding');
    assert.ok(skill.data.version_id, '有版本才能被使用');
    assert.ok(skill.data.parameters.length >= 1, '要能被问出输入');
    assert.ok(skill.data.workflow.length <= 1, '前置步骤最多一条');
    const parsed = parseSkillMarkdown(skill.data.instructions);
    assert.equal(parsed.steps.length, 3);
    assert.ok(parsed.outputs[0]);
  }

  const tasks = e.store.list('task').filter((item) => item.owner === e.user.id);
  assert.equal(tasks.length, 1);
  for (const task of tasks) {
    assert.equal(task.data.status, 'draft', '草稿：不自动跑');
    assert.ok(task.data.skill_id, '草稿要绑到那张卡');
    assert.ok(task.data.skill_version_id);
    assert.ok(task.data.constraints.includes('先交代过程'), '第 2 屏的偏好要进任务约束');
    assert.equal(task.data.source_refs[0].id, task.data.skill_version_id);
  }

  const records = e.store.list('card_onboarding').filter((item) => item.owner === e.user.id);
  assert.equal(records.length, 1);
  assert.deepEqual(records[0].data.preset_ids, ['explore-sources']);
  assert.equal(records[0].data.preferences.conclusion, 'process-first');
});

test('偏好进记忆：只有非默认的那几条，来源指向这次初始化', async (t) => {
  const e = setup(t);
  const result = e.command('card.onboard', {
    preset_ids: ['advise-compare'],
    preferences: { length: 'detailed', review: 'independent' },
  });
  assert.equal(result.remembered.length, 2);
  const memories = e.store.list('memory').filter((item) => item.owner === e.user.id);
  assert.equal(memories.length, 2);
  assert.ok(memories.every((item) => item.data.content.startsWith('用户希望：')));
  assert.ok(memories.every((item) => item.data.source_refs[0].id === result.id), '来源是这次初始化的记录');
  assert.ok(memories.every((item) => item.data.risk === 'low'));
  // 全用默认值时不该产生记忆噪音
  const e2 = setup(t);
  assert.equal(e2.command('card.onboard', { preset_ids: ['advise-risk'] }).remembered.length, 0);
});

test('同一张卡不会生成第二张；重复调用只报"已经有了"', async (t) => {
  const e = setup(t);
  e.command('card.onboard', { preset_ids: ['explore-digest'] });
  const again = e.command('card.onboard', { preset_ids: ['explore-digest'] });
  assert.equal(again.created.length, 0, '重复选同一张，不再生成');
  assert.equal(again.skipped.length, 1);
  assert.equal(again.skipped[0].preset_id, 'explore-digest');
  assert.equal(e.store.list('skill').filter((item) => item.owner === e.user.id).length, 1);
  // 换一张新的 = "再来一张"那条路，一次仍然只加一张
  const next = e.command('card.onboard', { preset_ids: ['create-edit'] });
  assert.equal(next.created.length, 1);
  assert.equal(e.store.list('skill').filter((item) => item.owner === e.user.id).length, 2);
});

test('生成的卡是"真能用"：tool.use 带参数与前置步骤建出任务，跑完有回执', async (t) => {
  const e = setup(t);
  const result = e.command('card.onboard', { preset_ids: ['create-draft'] });
  const card = result.created[0];
  const skill = e.store.get(card.skill_id);
  const version = e.store.get(skill.data.version_id);
  assert.equal(version.data.workflow.length, 1, '写作卡配了"先收集资料"的前置步骤');

  const used = e.command('tool.use', {
    id: card.skill_id,
    version_id: skill.data.version_id,
    goal: '写一份课程项目报告',
    parameters: Object.fromEntries(version.data.parameters.map((item) => [item.name, item.name === '要写什么' ? '课程项目报告' : ''])),
  });
  const task = e.store.get(used.task_id);
  assert.equal(task.data.skill_id, card.skill_id);
  assert.equal(task.data.parameter_values['要写什么'], '课程项目报告', '输入真的进了任务');
  assert.equal((task.data.collaboration_steps || []).length, 1, '前置步骤变成协作步骤');

  // 走到能跑：确认授权 → 启动（模型未配置时会停在待配置，那就是环境问题，不是卡的问题）
  e.command('task.confirm', { id: task.id, version: task.version, confirm: true, model_consent: true });
  const ready = e.store.get(task.id);
  assert.equal(ready.data.status, 'ready');
  const started = e.command('run.start', { id: ready.id, version: ready.version });
  const run = e.store.get(started.id);
  assert.ok(run.data.plan.steps.length >= 1, '有可执行的计划');
  assert.equal(run.data.plan.steps.some((step) => step.phase === 'collaboration'), true, '前置步骤在计划里');
  assert.equal(run.data.plan.steps.some((step) => step.phase === 'work'), true);
});

test('老入口 preset_ids 仍能用；"其它"用原文当能做什么', async (t) => {
  const e = setup(t);
  // 界面上已经没有"我不知道选什么"这条捷径了，但 `preset_ids` 这个老入口仍然认
  // （脚本、测试与"再来一张"用它），这里把它钉住。
  const legacy = e.command('card.onboard', { preset_ids: ['explore-sources'] });
  assert.equal(legacy.created.length, 1);
  assert.deepEqual(legacy.created.map((item) => item.preset_id), ['explore-sources']);

  const e2 = setup(t);
  const custom = e2.command('card.onboard', { custom_text: '帮我把每周的会议记录整理成待办', custom_system: 'connect' });
  assert.equal(custom.created.length, 1);
  const skill = e2.store.get(custom.created[0].skill_id);
  assert.equal(skill.data.system, 'connect', '自己指定过归属就以他为准');
  const parsed = parseSkillMarkdown(skill.data.instructions);
  assert.equal(parsed.canDo[0], presetById('explore-digest').canDo, '这句话命中了现成卡，就用它的骨架');
  assert.ok(parsed.limits.join('').includes('本人原话：帮我把每周的会议记录整理成待办'), '本人那句话也进说明书');
  // 命不中任何现成卡，才造一张"其它"卡：原文就是它的"能做什么"
  const e3 = setup(t);
  const mine = e3.command('card.onboard', { custom_text: '帮我看看火星上有没有水' });
  const mineParsed = parseSkillMarkdown(e3.store.get(mine.created[0].skill_id).data.instructions);
  assert.equal(mineParsed.canDo[0], '帮我看看火星上有没有水');
  assert.equal(customPreset('').id, 'custom');
  assert.ok(composeToolParameters(presetById('create-draft')).length >= 1);
  assert.match(composeTaskDraft(presetById('create-draft'), {}).goal, /写一份文档/);
});

// ── 分支选择树（2026-09-29 改）───────────────────────────────────────────────

test('选择树本身站得住：每页 2~3 个选项、next 与片段都存在、每条路都能落到一张真卡', () => {
  assert.ok(Object.keys(CARD_QUESTIONS).length >= 4, '题目不止一页');
  for (const [id, node] of Object.entries(CARD_QUESTIONS)) {
    assert.ok(node.title, `${id} 缺标题`);
    assert.ok(node.options.length >= 2 && node.options.length <= 3, `${id} 每页 2~3 个选项（现在 ${node.options.length}）`);
    for (const option of node.options) {
      assert.ok(option.label.length <= 30, `${option.id} 的选项文案要短（现在 ${option.label.length} 字）`);
      if (option.next) assert.ok(CARD_QUESTIONS[option.next], `${option.id} 指向的下一题不存在：${option.next}`);
      if (option.preset) assert.ok(presetById(option.preset), `${option.id} 指向的卡不存在：${option.preset}`);
      for (const fragment of option.fragments || []) {
        assert.ok(CARD_FRAGMENTS.some((item) => item.id === fragment), `${option.id} 用了不存在的片段：${fragment}`);
      }
    }
  }

  // 把整棵树走一遍：每条路都要能解出一张卡
  const leaves = [];
  const walkAll = (nodeId, path) => {
    for (const option of CARD_QUESTIONS[nodeId].options) {
      const next = [...path, option.id];
      if (option.next) walkAll(option.next, next);
      else leaves.push(next);
    }
  };
  walkAll('root', []);
  assert.ok(leaves.length >= 8, `叶子够多（${leaves.length}）`);
  const reached = new Set();
  for (const leaf of leaves) {
    const resolved = resolvePath(leaf);
    assert.equal(resolved.ok, true, `这条路要能解出卡：${leaf.join(' > ')} — ${resolved.reason || ''}`);
    reached.add(resolved.preset.id);
  }
  // 15 张预置卡里，只有"核对交付物是否达标"留给"我自己说一句"那条路
  const missing = CARD_PRESETS.map((item) => item.id).filter((id) => !reached.has(id));
  assert.deepEqual(missing, ['execute-check'], `树覆盖不到的卡只能是这张（现在缺：${missing.join('、')}）`);
});

test('路径校验：不认识的选项、没答完、没落到卡，都要如实报错', () => {
  assert.equal(resolvePath(['不存在']).ok, false);
  assert.equal(resolvePath(['r1-clarify']).ok, false, '只答第一页不算完');
  assert.equal(resolvePath([]).ok, false);
});

test('同一张卡走不同路径 = 两份不同的 skill（交付和注意都不一样）', () => {
  const given = resolvePath(['r1-clarify', 'r2-clarify-sources', 'r3-scope-given', 'r4-aud-formal']);
  const web = resolvePath(['r1-clarify', 'r2-clarify-sources', 'r3-scope-web', 'r4-aud-peer']);
  assert.equal(given.preset.id, web.preset.id, '卡是同一张');
  const a = composeSkillMarkdown(given.preset, { fragments: given.fragments });
  const b = composeSkillMarkdown(web.preset, { fragments: web.fragments });
  assert.notEqual(a, b, '内容必须不同');
  assert.ok(a.includes('不联网补充') && !a.includes('允许联网'));
  assert.ok(b.includes('允许联网') && !b.includes('不联网补充'));
  assert.ok(a.includes('要点摘要（正式、结论在前）'), '交付跟着路径变');
  assert.ok(b.includes('转给队友的结论'), '交付跟着路径变');
  // 互斥组：同组只留最后选的那条
  assert.deepEqual(resolveFragments(['scope-given', 'scope-web']).map((item) => item.id), ['scope-web']);
});

test('自己说一句：能落到现成卡就落，落不到才造"其它"卡', () => {
  assert.equal(presetIdFromText('帮我把这周的会议记录整理成待办'), 'explore-digest');
  assert.equal(presetIdFromText('帮我核对一下这份交付达不达标'), 'execute-check');
  assert.equal(presetIdFromText('帮我看看火星上有没有水'), null);
  assert.equal(customPreset('帮我看看火星上有没有水').custom, true);
});
