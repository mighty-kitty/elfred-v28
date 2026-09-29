import test from 'node:test';
import assert from 'node:assert/strict';
import {understandingScore,ALIGNMENT_GATE} from '../../app/v28/core/agent-alignment.mjs';
import {cardRating,LEVEL_GATE,CARD_PERFORMANCE} from '../../app/v28/core/capability-score.mjs';
import {parseSkillMarkdown,skillCardCopy,readFrontmatter} from '../../app/v28/core/skill-markdown.mjs';

const day = 86400000;
const at = (daysAgo) => new Date(Date.now() - daysAgo * day).toISOString();
const accepted = (daysAgo, external = false, satisfaction = 'satisfied') => ({ satisfaction, external, at: at(daysAgo) });

// ── 理解度 ────────────────────────────────────────────────────────────
// 期望值来自旧后端的实测口径（`elfred-page2-api/smoke_test.py`：理解度 45 / Lv.2；
// 新用户 10%，做过问卷 15%），不是"跑出来多少写多少"。

test('新用户：理解度 10%、Lv.1、它自己很不确定', () => {
  const result = understandingScore({ outcomes: [] });
  assert.equal(result.alignment, 10);
  assert.equal(result.level, 1);
  assert.equal(result.stage, '初见');
  assert.equal(result.uncertainty, 100);
  assert.equal(result.nextGate, ALIGNMENT_GATE[2]);
  assert.equal(result.externalChecks, 0);
});

test('做过问卷给一次弱加分：新用户 10% → 15%（重测不累加，因为只有一份有效起点）', () => {
  assert.equal(understandingScore({ outcomes: [], hasBaseline: true }).alignment, 15);
});

test('三件外部可核对的结果 → 45% / Lv.2（与旧后端实测值一致）', () => {
  const result = understandingScore({ outcomes: [accepted(3, true), accepted(2, true), accepted(1, true)] });
  assert.equal(result.alignment, 45);
  assert.equal(result.level, 2);
  assert.equal(result.stage, '认识你');
  assert.equal(result.externalChecks, 3);
});

test('本人点一下验收的权重低于外部核对：同样条数，分数更低', () => {
  const five = [accepted(5), accepted(4), accepted(3), accepted(2), accepted(1)];
  const owned = understandingScore({ outcomes: five }).alignment;
  const external = understandingScore({ outcomes: five.map((row) => ({ ...row, external: true })) }).alignment;
  assert.ok(external > owned, `外部 ${external} 应高于本人验收 ${owned}`);
});

test('它会掉：30 天没有新证据减半；被指正再往下扣', () => {
  const fresh = understandingScore({ outcomes: [accepted(1, true), accepted(1, true), accepted(1, true)] }).alignment;
  const stale = understandingScore({ outcomes: [accepted(31, true), accepted(31, true), accepted(31, true)] }).alignment;
  assert.ok(stale < fresh, `闲置应更低：${stale} < ${fresh}`);
  const corrected = understandingScore({ outcomes: [accepted(1, true), accepted(1, true), accepted(1, true), accepted(1, false, 'unsatisfied')] }).alignment;
  assert.ok(corrected < fresh, `被指正应更低：${corrected} < ${fresh}`);
  // 被本人打回、还没重新验收的任务不产成果对象，条数由调用方单独传（第二页就是这么用的）
  const fromTasks = understandingScore({ outcomes: [accepted(1, true), accepted(1, true), accepted(1, true)], extraCorrections: 1 }).alignment;
  assert.ok(fromTasks < fresh, `打回也要扣：${fromTasks} < ${fresh}`);
  // 被新理解顶掉的旧理解同样算指正
  const superseded = understandingScore({ outcomes: [accepted(1, true), accepted(1, true), accepted(1, true)], memories: [{ data: { status: 'superseded', superseded_by: 'm2' } }] }).alignment;
  assert.ok(superseded < fresh, `旧理解被顶掉要扣：${superseded} < ${fresh}`);
});

test('还差几件成果由公式算，不是拍脑袋：nextEvidence 能让分数真的够到下一档', () => {
  const outcomes = [accepted(2, true)];
  const before = understandingScore({ outcomes });
  assert.equal(before.level, 1);
  assert.ok(before.nextEvidence > 0);
  const after = understandingScore({ outcomes: [...outcomes, ...Array.from({ length: before.nextEvidence }, () => accepted(1))] });
  assert.ok(after.alignment >= before.nextGate, `${after.alignment} 应够到 ${before.nextGate}`);
});

// ── 能力分与等级 ──────────────────────────────────────────────────────

test('0 项成果的能力卡不给分，也不给等级结论', () => {
  const rating = cardRating([]);
  assert.equal(rating.score, null);
  assert.equal(rating.evidence, 0);
  assert.equal(rating.level, 1);
  assert.equal(rating.stage, '发现');
  assert.equal(rating.verified, false);
  assert.match(rating.gapLabel, /还差 3 项成果/);
});

test('三件本人验收的成果：分数往上走、门槛按成果数升到 Lv.2', () => {
  const rating = cardRating([accepted(3), accepted(2), accepted(1)]);
  assert.equal(rating.evidence, 3);
  assert.ok(rating.score > 60 && rating.score <= 100, `分数应在量表之上：${rating.score}`);
  assert.equal(rating.level, 2);
  assert.equal(rating.stage, '有证据');
  assert.equal(rating.gap.goal, LEVEL_GATE[3]);
  assert.equal(rating.gap.need, 3);
});

test('没给满意度的验收照旧算数，但表现分比"本人满意"低', () => {
  const satisfied = cardRating([accepted(1), accepted(1), accepted(1)]).score;
  const unknown = cardRating([accepted(1, false, 'unknown'), accepted(1, false, 'unknown'), accepted(1, false, 'unknown')]).score;
  assert.ok(unknown < satisfied, `没给满意度 ${unknown} 应低于满意 ${satisfied}`);
});

test('"这条不对"会把分数拉下来（分数可落，不是只涨）', () => {
  const good = cardRating([accepted(3), accepted(2), accepted(1)]).score;
  const bad = cardRating([accepted(3), accepted(2), accepted(1, false, 'unsatisfied')]).score;
  assert.ok(bad < good, `被否定的成果应更低：${bad} < ${good}`);
});

test('外部可核对的那一档权重更高，但不越过 100', () => {
  const rows = Array.from({ length: 6 }, () => accepted(1, true));
  const rating = cardRating(rows);
  assert.ok(rating.score <= 100 && rating.score > 0);
  assert.equal(rating.external, 6);
  assert.equal(rating.level >= 2, true);
  assert.deepEqual(rating.ladder.map((rung) => rung.gate), LEVEL_GATE.slice(1));
});

test('表现分只认三种验收结论，别的值不参与（不编数据）', () => {
  const rating = cardRating([{ satisfaction: 'nonsense', at: at(1) }, accepted(1)]);
  assert.equal(rating.evidence, 1);
  assert.equal(CARD_PERFORMANCE.satisfied, 92);
});

// ── SKILL.md 解析 ─────────────────────────────────────────────────────

const HAND_WRITTEN = [
  '---', 'name: 会议纪要整理', '---', '',
  '## 什么时候用', '用户把一段会议记录交给你，需要整理成能直接执行的东西时。', '',
  '## 怎么做', '1. 通读记录，分出"已决定的事"和"要做的事"', '2. 每条待办写清负责人和截止时间', '',
  '## 交付什么', '一张待办表：事项 / 负责人 / 截止 / 依据哪句话', '',
  '## 注意', '只整理记录里出现过的内容；推测要单独标出来。',
].join('\n');

const FOUNDRY = [
  '---', 'name: communication', 'description: "复用 告知前端改动涉及的本地文件路径 的已验证 Elfred 工作流。"', '---', '',
  '# 告知前端改动涉及的本地文件路径', '',
  '## When to Use', '', '- 用户需要按既有语气和结构起草同类沟通内容。', '',
  '## Inputs', '',
  '- `documentTitle` (string, required): 每次运行可替换的 documentTitle',
  '- `outputLanguage` (string, optional): 用户偏好', '',
  '## Procedure', '', '1. `read_code` — use `code_editor`。该动作在 3/3 条成功轨迹中出现。', '',
  '## Verification', '', '- 任务状态为 completed', '',
  '## Pitfalls', '', '- source_text_too_short: 停止运行并请求更完整的文本',
].join('\n');

test('手写中文说明书：分得出"什么时候用 / 怎么做 / 交付什么 / 注意"', () => {
  const parsed = parseSkillMarkdown(HAND_WRITTEN);
  assert.equal(parsed.title, '会议纪要整理');
  assert.deepEqual(parsed.canDo, ['用户把一段会议记录交给你，需要整理成能直接执行的东西时。']);
  assert.equal(parsed.steps.length, 2);
  assert.match(parsed.steps[0], /通读记录/);
  assert.match(parsed.outputs[0], /一张待办表/);
  assert.match(parsed.limits[0], /只整理记录里出现过/);
  assert.equal(skillCardCopy(HAND_WRITTEN), '用户把一段会议记录交给你，需要整理成能直接执行的东西时。');
});

test('Skill Foundry 的英文说明书也认：输入带必填标记，步骤取自 Procedure', () => {
  const parsed = parseSkillMarkdown(FOUNDRY);
  assert.equal(parsed.description, '复用 告知前端改动涉及的本地文件路径 的已验证 Elfred 工作流。');
  assert.deepEqual(parsed.canDo, ['用户需要按既有语气和结构起草同类沟通内容。']);
  assert.equal(parsed.inputs.length, 2);
  assert.match(parsed.inputs[0], /^documentTitle（必填）/);
  assert.match(parsed.inputs[1], /^outputLanguage/);
  assert.equal(parsed.steps.length, 1);
  assert.match(parsed.steps[0], /read_code/);
  assert.match(parsed.checks[0], /任务状态为 completed/);
  assert.equal(skillCardCopy(FOUNDRY).startsWith('复用 告知前端改动'), true);
});

test('frontmatter 只认单层键值；小节认不出来就原样留着，不编内容', () => {
  const frontmatter = readFrontmatter(HAND_WRITTEN);
  assert.equal(frontmatter.data.name, '会议纪要整理');
  assert.equal(frontmatter.body.startsWith('## 什么时候用'), true);
  const parsed = parseSkillMarkdown('## 随便写的小节\n- 一句话');
  assert.deepEqual(parsed.canDo, []);
  assert.deepEqual(parsed.steps, []);
  assert.deepEqual(parsed.inputs, []);
  assert.equal(parsed.sections.length, 1);
  assert.equal(skillCardCopy('## 随便写的小节\n- 一句话'), '');
});
