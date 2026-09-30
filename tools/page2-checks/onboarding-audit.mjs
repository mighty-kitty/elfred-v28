/**
 * 能力卡初始化的专项真机审计：模拟用户从空态走完三步，再核对"生成的是不是一张真能用的 skill"。
 *
 * 覆盖（每条都打印证据）：
 *   ① 空态：只留「暂时还没有能力卡 + 做一张能力卡」一颗按钮（说明小字与"去和 Elfred 说"都删了）
 *   ② 选择树：每页正好 3 个选项、选完决定下一页（第 1 页 → 资料范围 → 给谁看 → 确认页）；
 *      确认页复述刚才的选择；页面上不该再有"再细一点 / 看完整说明书 / 我自己说一句"
 *   ②b 结果核对：库里那张卡的说明书带着路径片段（没选的那条不会混进去）
 *   ③ 结果核对：库里是 active skill + source=onboarding + 说明书四小节 + 输入 + 前置步骤 + 任务草稿
 *   ④ 界面核对：卡组里出现新卡；卡详情渲染"能做到什么 / 步骤 / 交付"；输入问得出来；Lv.1 / 0 成果
 *   ④b 用它做一件事：说明书挂成输入框上方的附件（输入框留空），用户还能写自己的话；
 *      发出去的消息 = 那句话 + 说明书（功能没变）
 *   ⑤ 真能用：走 `tool.use`（带输入）→ 确认 → 启动 → 真的跑出回执
 *   ⑥ 三条边界路径：同一张卡换条路（内容必须不同）· 换一条完全不同的分支 ·
 *      已有卡时"再来一张"
 *
 * 用法（应用要在跑）：
 *   $env:NODE_PATH = "<装了 playwright 的 node_modules>"
 *   node tools/page2-checks/onboarding-audit.mjs
 */
import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
import { enterApp } from './_page.mjs';

const BASE = process.env.PAGE24_BASE || 'http://127.0.0.1:3000';
const OUT = path.join(process.env.TEMP || '.', 'pages24-onboarding-audit');
mkdirSync(OUT, { recursive: true });

const failures = [];
const expect = (ok, label, detail = '') => {
  console.log(`  ${ok ? '✓' : '✗'} ${label}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures.push(label);
};
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** 一个独立账号 + 它的 API 通道（每个用例一个，互不干扰） */
async function account(tag) {
  let cookie = '';
  let token = '';
  const call = async (p, opt = {}) => {
    const response = await fetch(`${BASE}/api/elfred${p}`, {
      ...opt,
      headers: { 'Content-Type': 'application/json', 'X-Elfred-Client': '1', Origin: BASE, ...(opt.headers || {}), ...(cookie ? { Cookie: cookie } : {}) },
    });
    const setCookie = response.headers.getSetCookie ? response.headers.getSetCookie() : [];
    if (setCookie.length) {
      cookie = setCookie.map((item) => item.split(';')[0]).join('; ');
      const session = setCookie.find((item) => item.startsWith('elfred_session='));
      if (session) token = session.slice('elfred_session='.length).split(';')[0];
    }
    const text = await response.text();
    try { return { status: response.status, body: JSON.parse(text) }; } catch { return { status: response.status, body: text }; }
  };
  const handle = `${tag}${Date.now()}`;
  await call('/auth/register', { method: 'POST', body: JSON.stringify({ handle, password: `${tag}-password-1`, name: '本人' }) });
  const csrf = (await call('/session')).body.csrf;
  const command = (action, input) => call('/commands', {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrf, 'Idempotency-Key': `${action}-${Math.random().toString(36).slice(2)}` },
    body: JSON.stringify({ action, input }),
  });
  const onboarding = (await call('/bootstrap')).body.objects.onboarding?.[0];
  await command('onboarding.choice.defer', { id: onboarding.id, version: onboarding.version });
  const snapshot = async () => (await call('/bootstrap')).body;
  return { handle, call, command, snapshot, cookieValue: () => cookie, token: () => token };
}

async function openApp(browser, acc) {
  const context = await browser.newContext({ viewport: { width: 430, height: 932 } });
  await context.addCookies([{ name: 'elfred_session', value: acc.token(), domain: new URL(BASE).hostname, path: '/' }]);
  const page = await context.newPage();
  const errors = [];
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text().slice(0, 160)); });
  page.on('pageerror', (error) => errors.push(String(error).slice(0, 160)));
  // 启动很慢（首帧是"正在恢复你的工作现场…"），统一走三个探针共用的入口：
  // 它等元素真的出现、必要时跳过首次对齐页，不用固定秒数（这里以前自己写了一份，偶发失败）。
  await enterApp(page, { tab: '知识', settle: 2500 });
  return { context, page, errors };
}

const openOnboarding = async (page) => {
  await page.getByRole('button', { name: '做一张能力卡', exact: true }).click();
  await sleep(1200);
};

/**
 * 可用性口径：**滚到底之后**，面板里的按钮一个都不能压在底部导航下面
 * （第一版就是被它盖住：按钮在，但点不到。中途被盖住是浮层导航的正常形态，滚动就能看全。）
 */
const uncoveredByNav = (page) => page.evaluate(() => {
  const nav = document.querySelector('.v277-bottom-wrap')?.getBoundingClientRect();
  const sheet = document.querySelector('.v279-setting-sheet');
  if (!nav || !sheet) return { ok: false, reason: '找不到导航或面板' };
  const scrollable = [...sheet.querySelectorAll('*')].find((el) => el.scrollHeight > el.clientHeight + 4);
  if (scrollable) scrollable.scrollTop = scrollable.scrollHeight;
  const covered = [...sheet.querySelectorAll('button')]
    .map((button) => ({ rect: button.getBoundingClientRect(), label: (button.textContent || '').trim().slice(0, 12) }))
    .filter(({ rect }) => rect.bottom > nav.top + 2 && rect.top < nav.bottom - 2);
  return { ok: covered.length === 0, reason: covered.map((item) => item.label).join('、') };
});

(async () => {
  const browser = await chromium.launch(process.env.PAGE24_CHROME ? { executablePath: process.env.PAGE24_CHROME } : {});

  // ── ① 空态 + ② 选择树 + ③④⑤ 结果与可用性 ──────────────────────────────
  console.log('① 空态与选择树');
  const main = await account('onb');
  const app = await openApp(browser, main);
  const empty = await app.page.evaluate(() => document.body.innerText);
  expect(/暂时还没有能力卡/.test(empty), '空态标题是"暂时还没有能力卡"');
  expect(/做一张能力卡/.test(empty), '主按钮在');
  // 空态只留标题与一颗按钮：原来的说明小字和"或者，直接跟 Elfred 说一句"都删掉了
  expect(!/直接跟 Elfred 说一句/.test(empty), '空态不再出现"直接跟 Elfred 说一句"');
  expect(!/30 秒/.test(empty), '空态不再出现"30 秒…"那行说明');
  await app.page.screenshot({ path: path.join(OUT, '1-empty.png'), fullPage: true });

  await openOnboarding(app.page);
  // 选项本身带 aria-pressed，用它数"这一页有几个选项"（页脚按钮没有这个属性）
  const optionCount = () => app.page.getByRole('dialog').locator('button[aria-pressed]').count();

  const q1 = await app.page.evaluate(() => document.body.innerText);
  expect(/第 1 步/.test(q1), '进到选择树第 1 页');
  expect(/你现在最想让它帮你做什么/.test(q1), '第 1 页问的是"最想做什么"');
  expect((await optionCount()) === 3, '第 1 页正好 3 个选项', `数到 ${await optionCount()}`);
  expect(!/我自己说一句/.test(q1), '答题页不再有"自己说一句"的出口（一页只有三个选项）');
  expect(!/选一条最接近的就行|下一页会跟着你的选择变/.test(q1), '答题页不再有那行解释小字');
  expect(!/查资料、盯变化、拿不准要我判断/.test(q1), '选项下面不再挂小字');
  expect(!/探索|参谋|创作|连接|执行/.test(q1.replace(/^[\s\S]*?你现在最想让它帮你做什么/, '')), '选项里不出现我们的系统名');
  const clear1 = await uncoveredByNav(app.page);
  expect(clear1.ok, '第 1 页的按钮没有被底部导航盖住', clear1.reason || '');
  await app.page.screenshot({ path: path.join(OUT, '2-q1.png'), fullPage: true });

  await app.page.getByRole('button', { name: /有一件事我想搞清楚/ }).click();
  await sleep(700);
  const q2 = await app.page.evaluate(() => document.body.innerText);
  expect(/这件事更像哪一种/.test(q2), '第 2 页跟着第 1 页变了');
  expect((await optionCount()) === 3, '第 2 页也是 3 个选项');
  await app.page.getByRole('button', { name: /把资料查全/ }).click();
  await sleep(700);
  const q3 = await app.page.evaluate(() => document.body.innerText);
  expect(/资料从哪来/.test(q3), '第 3 页问资料范围（随上一页变）');
  await app.page.screenshot({ path: path.join(OUT, '3-q3.png'), fullPage: true });
  await app.page.getByRole('button', { name: /^只用我给你的材料$/ }).click();
  await sleep(700);
  const q4 = await app.page.evaluate(() => document.body.innerText);
  expect(/给谁看/.test(q4), '第 4 页接着问给谁看');
  await app.page.getByRole('button', { name: /老师 \/ 上级/ }).click();
  await sleep(800);

  const preview = await app.page.evaluate(() => document.body.innerText);
  expect(/你要的是：/.test(preview), '预览页把刚才的选择复述了一遍');
  expect(/查资料并核实来源/.test(preview), '落到"查资料并核实来源"这张卡');
  expect(/要点摘要（正式、结论在前）/.test(preview), '交付里带着路径决定的那句');
  expect(/Lv\.1、0 项成果/.test(preview), '确认页写清"起点，不给分"');
  // 少解释：答题页不该再有大段说明与选项小字
  expect(!/选一条最接近的就行/.test(preview), '确认页不再有那行解释');
  // 确认页只留"是什么"：不再有「再细一点」和「看完整说明书」两颗开关
  expect(!/再细一点|看完整说明书/.test(preview), '确认页不再有"再细一点 / 看完整说明书"');
  await app.page.screenshot({ path: path.join(OUT, '4-preview.png'), fullPage: true });
  const clearPreview = await uncoveredByNav(app.page);
  expect(clearPreview.ok, '预览页的按钮没有被底部导航盖住', clearPreview.reason || '');
  await app.page.getByRole('button', { name: /生成这张卡/ }).click();
  // 生成要写 skill + 任务草稿（还可能顺带写记忆），别用固定秒数等界面
  let done = '';
  for (let i = 0; i < 20; i += 1) {
    await sleep(1000);
    done = await app.page.evaluate(() => document.body.innerText);
    if (/已经生成好了/.test(done)) break;
  }
  expect(/已经生成好了/.test(done), '生成成功，进到结果屏');
  expect(!/也记下了你的偏好/.test(done), '没改过偏好就不会记成理解');
  await app.page.screenshot({ path: path.join(OUT, '5-done.png'), fullPage: true });

  console.log('③ 结果核对（库里到底写了什么）');
  const snap = await main.snapshot();
  const skills = (snap.objects.skill || []).filter((item) => item.data.source === 'onboarding');
  expect(skills.length === 1, '只生成了这一张能力卡', `${skills.length} 张`);
  expect(skills.every((item) => item.data.status === 'active'), '都是 active（直接可用）');
  expect(skills.every((item) => item.data.parameters?.length >= 1), '每张卡都写了输入');
  expect(skills.some((item) => item.data.workflow?.length === 1) || skills.every((item) => (item.data.workflow || []).length === 0), '前置步骤合法（有就给一条）');
  const instructions = skills.map((item) => String(item.data.instructions || ''));
  expect(instructions.every((text) => /## 什么时候用/.test(text) && /## 怎么做/.test(text) && /## 交付什么/.test(text) && /## 注意/.test(text)), '说明书都是四小节');
  expect(instructions.some((text) => /只在本人提供的材料里查/.test(text)), '路径选的内容片段进了说明书');
  expect(instructions.some((text) => /要点摘要（正式、结论在前）/.test(text)), '路径选的交付形态进了说明书');
  expect(instructions.every((text) => !/允许联网/.test(text)), '没选的片段不会混进去');
  const tasks = (snap.objects.task || []).filter((item) => item.data.onboarding);
  expect(tasks.length === 1, '配了一条任务草稿', `${tasks.length} 条`);
  expect(tasks.every((item) => item.data.status === 'draft'), '草稿状态，没有自动跑');
  expect(tasks.every((item) => item.data.skill_id && item.data.skill_version_id), '草稿绑定了对应卡与版本');
  // 初始化记录是服务端账本，不进 /bootstrap 的客户端快照；这里按对象类型单独查一次
  const records = (await main.call('/objects?type=card_onboarding')).body;
  expect(Array.isArray(records) && records.length === 1, '留了一笔初始化记录', `${Array.isArray(records) ? records.length : '查询失败'}`);
  expect(Array.isArray(records[0]?.data.path) && records[0].data.path.length === 4, '记录里存下了整条路径', JSON.stringify(records[0]?.data.path));
  expect((records[0]?.data.fragment_ids || []).includes('scope-given'), '记录里存下了路径带来的内容片段');
  const memories = (snap.objects.memory || []).filter((item) => String(item.data.content || '').startsWith('用户希望：'));
  expect(memories.length === 0, '没改过偏好就不写记忆', `${memories.length} 条`);

  console.log('④ 界面核对（卡组与卡详情）');
  await app.page.getByRole('button', { name: '看我的能力卡组' }).click();
  await sleep(3000);
  const grid = await app.page.evaluate(() => document.body.innerText);
  expect(/查资料并核实来源/.test(grid), '这张卡出现在能力卡组里');
  expect(!/把目标拆成可执行步骤/.test(grid), '没选的那张没有一起生成');
  expect(/尚无成果|证据不足/.test(grid), '新卡是"尚无成果"（不白送分）');
  await app.page.getByRole('button', { name: /查资料并核实来源/ }).first().click();
  await sleep(1500);
  const sheet = await app.page.evaluate(() => document.querySelector('.v279-capability-sheet')?.innerText ?? '');
  expect(/它能替你做/.test(sheet) && /使用说明/.test(sheet), '卡详情两栏都在');
  expect(!/## 什么时候用/.test(sheet), '说明书不是压平的 markdown');
  expect(/完整说明/.test(sheet), '有"完整说明"可展开');
  expect(/Lv\.1/.test(sheet) && /待验证|发现/.test(sheet), '等级是 Lv.1 起点');
  await app.page.screenshot({ path: path.join(OUT, '6-card-sheet.png'), fullPage: true });

  // ── ④b 用它做一件事：说明书变成输入框上方的附件，输入框留给用户 ────────
  console.log('④b 用它做一件事：说明书挂成附件');
  await app.page.getByRole('button', { name: /用它做一件事/ }).first().click();
  await sleep(3000);
  const composerState = await app.page.evaluate(() => {
    const textarea = document.querySelector('.v283-agent-chat-composer textarea');
    const submit = document.querySelector('.v283-agent-chat-composer button[type=submit]');
    return {
      onChat: Boolean(textarea),
      chip: (document.querySelector('.v283-agent-attach-chip')?.textContent || '').trim(),
      input: textarea?.value ?? '(没有输入框)',
      sendDisabled: submit ? submit.hasAttribute('disabled') : null,
    };
  });
  expect(composerState.onChat, '进到对话界面');
  expect(/查资料并核实来源/.test(composerState.chip), '输入框上方挂着能力卡附件', composerState.chip.slice(0, 48));
  expect(composerState.input === '', '说明书没有倒进输入框（输入框是空的）', JSON.stringify(composerState.input).slice(0, 60));
  expect(composerState.sendDisabled === false, '只有附件、没打字时也能发送');
  await app.page.screenshot({ path: path.join(OUT, '7-composer-attach.png'), fullPage: true });

  // 用户还能在输入框里写自己的话；发出去的消息 = 那句话 + 说明书（功能没变）
  await app.page.locator('.v283-agent-chat-composer textarea').fill('帮我把范围收窄到国内高校');
  await sleep(400);
  await app.page.getByRole('button', { name: '发送消息' }).click();
  // 发送要等这一轮回复跑完才收尾（输入框与附件是那时才清的），所以轮询等，不用固定秒数
  let human = null;
  let afterSend = { input: '(还没清空)', chips: 1 };
  for (let i = 0; i < 40; i += 1) {
    await sleep(1500);
    const now = await main.snapshot();
    human = (now.objects.message || []).filter((item) => item.data.actor_type === 'human').pop() || human;
    afterSend = await app.page.evaluate(() => ({
      input: document.querySelector('.v283-agent-chat-composer textarea')?.value ?? '(没有输入框)',
      chips: document.querySelectorAll('.v283-agent-attach-chip').length,
    }));
    if (afterSend.input === '' && afterSend.chips === 0) break;
  }
  expect(afterSend.input === '', '发送后输入框清空');
  expect(afterSend.chips === 0, '发送后附件卡片收起');
  const sentText = String(human?.data.text || '');
  expect(/帮我把范围收窄到国内高校/.test(sentText), '用户自己写的那句话发出去了');
  expect(/已保存工具「查资料并核实来源」的说明/.test(sentText), '说明书随着这条消息一起发出（内容没变）', sentText.slice(0, 60));

  await app.page.getByRole('button', { name: '关闭', exact: true }).click().catch(() => {});
  await sleep(600);
  if (await app.page.locator('.v279-capability-sheet').count()) { await app.page.reload({ waitUntil: 'domcontentloaded' }); await sleep(2500); }

  console.log('⑤ 真能用：用它做一件事（带输入）→ 确认 → 启动 → 回执');
  const target = skills.find((item) => item.data.title === '查资料并核实来源');
  const version = snap.objects.skill_version.find((item) => item.id === target.data.version_id);
  const inputs = Object.fromEntries((version.data.parameters || []).map((item) => [item.name, '2026 年国内大学生 AI 工具使用情况']));
  const used = await main.command('tool.use', { id: target.id, version_id: version.id, goal: '查一下这个领域的公开资料', parameters: inputs });
  expect(used.status === 200 && used.body.task_id, 'tool.use 建出了任务', JSON.stringify(used.body).slice(0, 90));
  let task = (await main.snapshot()).objects.task.find((item) => item.id === used.body.task_id);
  expect(task.data.parameter_values?.['要查的问题'] === inputs['要查的问题'], '输入真的带进了任务');
  await main.command('task.confirm', { id: task.id, version: task.version, confirm: true, model_consent: true });
  task = (await main.snapshot()).objects.task.find((item) => item.id === used.body.task_id);
  const started = await main.command('run.start', { id: task.id, version: task.version });
  expect(started.status === 200, '能启动');
  let run = null;
  for (let i = 0; i < 60; i += 1) {
    await sleep(2000);
    run = (await main.snapshot()).objects.run.find((item) => item.id === started.body.id);
    if (run && ['completed', 'awaiting_review', 'failed', 'partial', 'blocked'].includes(run.data.status)) break;
  }
  expect(Boolean(run), '运行对象在');
  expect((run.data.receipts || []).length >= 1, '跑出了真回执（不是空跑）', (run.data.receipts || []).map((item) => item.step_id + ':' + item.status).join(','));
  expect(!['failed', 'blocked'].includes(run.data.status), '状态不是失败', run.data.status);
  const grown = (await main.snapshot()).objects.skill.find((item) => item.id === target.id);
  expect(grown.data.onboarding?.preset_id === 'explore-sources', '卡还是那张初始化卡（没被替换）');

  // ── ⑥ 四条边界路径 ──────────────────────────────────────────────────
  const mainMd = String(skills[0].data.instructions);

  // A：同一张卡换一条路 —— 卡名一样，内容必须不一样（这次改造的核心）
  console.log('⑥ 边界路径 A：同一张卡走另一条路，内容不同');
  const alt = await account('alt');
  const altApp = await openApp(browser, alt);
  await openOnboarding(altApp.page);
  await altApp.page.getByRole('button', { name: /有一件事我想搞清楚/ }).click();
  await sleep(600);
  await altApp.page.getByRole('button', { name: /把资料查全/ }).click();
  await sleep(600);
  await altApp.page.getByRole('button', { name: /允许上网找公开来源/ }).click();
  await sleep(600);
  await altApp.page.getByRole('button', { name: /队友 \/ 同事/ }).click();
  await sleep(700);
  await altApp.page.getByRole('button', { name: /生成这张卡/ }).click();
  await sleep(3000);
  const altSkill = ((await alt.snapshot()).objects.skill || [])[0];
  const altMd = String(altSkill?.data.instructions || '');
  expect(altSkill?.data.title === '查资料并核实来源', '还是同一张卡', altSkill?.data.title);
  expect(/允许联网/.test(altMd) && !/不联网补充/.test(altMd), '换了路径，说明书跟着变');
  expect(/转给队友的结论/.test(altMd), '交付也跟着路径变');
  expect(altMd !== mainMd, '两张卡标题一样、内容不一样');
  expect(altSkill?.data.onboarding?.fragments?.includes('scope-web'), '卡上记着这次的路径片段');

  // B：换个分支（做出来 → 从零写 → 队友）也能走通，而且不是同一张卡
  console.log('⑥ 边界路径 B：换一条完全不同的分支');
  const other = await account('other');
  const otherApp = await openApp(browser, other);
  await openOnboarding(otherApp.page);
  await otherApp.page.getByRole('button', { name: /有一份东西我想做出来/ }).click();
  await sleep(600);
  await otherApp.page.getByRole('button', { name: /从零写一份文稿/ }).click();
  await sleep(600);
  await otherApp.page.getByRole('button', { name: /队友 \/ 同事/ }).click();
  await sleep(700);
  await otherApp.page.getByRole('button', { name: /生成这张卡/ }).click();
  await sleep(3000);
  const otherSkill = ((await other.snapshot()).objects.skill || [])[0];
  const otherMd = String(otherSkill?.data.instructions || '');
  expect(otherSkill?.data.title === '写一份文档 / 文稿', '换分支落到"写一份文档 / 文稿"', otherSkill?.data.title);
  expect(otherSkill?.data.system === 'create', '归属跟着那条分支走');
  expect(/留出别人直接改的余地/.test(otherMd), '队友那句进了说明书');

  console.log('⑥ 边界路径 C：已有卡时从"我的工具"面板再来一张');
  await openApp(browser, main).then(async (second) => {
    await second.page.getByRole('button', { name: '导入内容' }).click();
    await sleep(1000);
    const panel = await second.page.evaluate(() => document.body.innerText);
    expect(/做一张能力卡/.test(panel), '面板里有"再来一张"的入口');
    await second.page.getByRole('button', { name: /做一张能力卡/ }).first().click();
    await sleep(1200);
    expect(/第 1 步/.test(await second.page.evaluate(() => document.body.innerText)), '从面板也能进初始化');
    // 走一条不一样的路：做出来 → 从零写一份文稿 → 队友 / 同事
    await second.page.getByRole('button', { name: /有一份东西我想做出来/ }).click();
    await sleep(700);
    await second.page.getByRole('button', { name: /从零写一份文稿/ }).click();
    await sleep(700);
    await second.page.getByRole('button', { name: /队友 \/ 同事/ }).click();
    await sleep(800);
    await second.page.getByRole('button', { name: /生成这张卡/ }).click();
    await sleep(3000);
    const all = (await main.snapshot()).objects.skill || [];
    expect(all.length === 2, '再来一张之后一共两张卡', `${all.length} 张`);
    expect(all.some((item) => item.data.title === '写一份文档 / 文稿'), '第二张是刚选的"写一份文档 / 文稿"');
    await second.context.close();
  });

  expect(app.errors.length === 0, '主路径没有控制台报错', app.errors.slice(0, 2).join(' / '));
  await app.context.close();
  await browser.close();

  console.log(`\n截图：${OUT}`);
  console.log(failures.length ? `✗ 有 ${failures.length} 项不符：${failures.join('；')}` : '✓ 全部符合');
  process.exit(failures.length ? 1 : 0);
})().catch((error) => { console.error('初始化审计失败：', error); process.exit(1); });
