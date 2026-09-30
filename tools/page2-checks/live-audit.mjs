/**
 * 第二页 / 第四页的实机检查（对着**现在这套**栈跑，不是旧的那套 8000 + 5182）。
 *
 * 它做四件事，每件事都打印证据，不看代码看渲染：
 *   ① 建一个干净的账号，往里放"真数据"：一张真 skill + 三件本人验收的成果 + 一条自动学到的理解；
 *   ② 用真浏览器打开第二页，读出页头理解度、能力卡的维度/小字/分数、今日成果条数；
 *   ③ 点开一张卡，读出"它能替你做 / 使用说明 / 输入输出 / 完整说明"渲染了什么；
 *   ④ 点开理解度面板，读出档位、还差多少、三格数字；顺手打开第四页与设置。
 *
 * 用法（应用要已经在跑，默认 127.0.0.1:3000）：
 *   $env:NODE_PATH = "<仓库外某个装了 playwright 的 node_modules>"
 *   node tools/page2-checks/live-audit.mjs
 * playwright 不在本仓库依赖里（它只用于这种实机检查），所以要给 NODE_PATH；
 * 本机可用 `C:\Users\35057\Desktop\纪念-Elfred历史版本\elfred-v28-integration\node_modules`。
 * 截图写到 %TEMP%\pages24-live-audit\。
 */
import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
import { enterApp } from './_page.mjs';

const BASE = process.env.PAGE24_BASE || 'http://127.0.0.1:3000';
const OUT = path.join(process.env.TEMP || '.', 'pages24-live-audit');
mkdirSync(OUT, { recursive: true });

let cookie = '';
let token = '';
const j = async (p, opt = {}) => {
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
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const SKILL_MD = [
  '---', 'name: 会议纪要整理', '---', '',
  '## 什么时候用', '用户把一段会议记录交给你，需要整理成能直接执行的东西时。', '',
  '## 怎么做', '1. 通读记录，分出"已决定的事"和"要做的事"', '2. 每条待办写清负责人和截止时间',
  '3. 记录里没写的人或时间，写"待确认"，不要自己补', '',
  '## 交付什么', '一张待办表：事项 / 负责人 / 截止 / 依据哪句话', '',
  '## 注意', '只整理记录里出现过的内容；推测要单独标出来。',
].join('\n');

const failures = [];
const expect = (ok, label, detail = '') => {
  console.log(`  ${ok ? '✓' : '✗'} ${label}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures.push(label);
};

(async () => {
  // ── ① 造真数据 ─────────────────────────────────────────────────────
  const handle = `audit${Date.now()}`;
  await j('/auth/register', { method: 'POST', body: JSON.stringify({ handle, password: 'audit-password-1', name: '审查' }) });
  const csrf = (await j('/session')).body.csrf;
  const cmd = (action, input) => j('/commands', {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrf, 'Idempotency-Key': `${action}-${Math.random().toString(36).slice(2)}` },
    body: JSON.stringify({ action, input }),
  });
  const obj = async (id) => (await j(`/objects/${id}`)).body;
  const bootstrap = async () => (await j('/bootstrap')).body;

  const onboarding = (await bootstrap()).objects.onboarding?.[0];
  await cmd('onboarding.choice.defer', { id: onboarding.id, version: onboarding.version });
  const conversation = (await cmd('agent.chat.create', { system: 'create' })).body;
  await cmd('agent.chat.send', { id: conversation.id, model_consent: true, text: '我平时写方案喜欢先给结论，再补依据。' });
  const saved = (await cmd('tool.save', { title: '会议纪要整理', instructions: SKILL_MD, kind: 'Skill', system: 'execute' })).body;
  await cmd('tool.activate', { id: saved.id, version: saved.version });
  for (const goal of ['整理一份会议纪要', '把访谈转成三条待办', '汇总本周的项目进展']) {
    const task = (await cmd('task.create', { goal, mode: 'manual', system: 'execute' })).body;
    let fresh = await obj(task.id);
    await cmd('task.confirm', { id: fresh.id, version: fresh.version, confirm: true });
    fresh = await obj(task.id);
    await cmd('task.complete_manual', { id: fresh.id, version: fresh.version, confirm: true, result: `${goal} 的结果`, satisfaction: 'satisfied' });
  }
  await sleep(1500);
  const snapshot = await bootstrap();
  console.log(`账号 ${handle}：能力卡 ${(snapshot.objects.skill || []).length} 张 · 已验收成果 ${(snapshot.objects.outcome || []).filter((item) => item.data.verdict === 'accepted').length} 件 · 记忆 ${(snapshot.objects.memory || []).length} 条\n`);

  // ── ② 真浏览器看第二页 ─────────────────────────────────────────────
  const browser = await chromium.launch(process.env.PAGE24_CHROME ? { executablePath: process.env.PAGE24_CHROME } : {});
  const context = await browser.newContext({ viewport: { width: 430, height: 932 } });
  await context.addCookies([{ name: 'elfred_session', value: token, domain: new URL(BASE).hostname, path: '/' }]);
  const page = await context.newPage();
  const consoleErrors = [];
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text().slice(0, 160)); });
  page.on('pageerror', (error) => consoleErrors.push(String(error).slice(0, 160)));

  // 入口统一走共用函数：应用启动慢或落在"首次对齐"页时它会自己等/跳过（固定 sleep 会偶发失败）
  await enterApp(page, { tab: '知识' });

  const header = await page.evaluate(() => document.querySelector('.v277-library-head')?.innerText?.replace(/\n/g, ' | ') ?? '');
  const cards = await page.evaluate(() => [...document.querySelectorAll('.v277-ability-cards button')].map((item) => item.innerText.replace(/\n/g, '｜')));
  const body = await page.evaluate(() => document.body.innerText);
  console.log('第二页：');
  console.log(`  页头：${header}`);
  console.log(`  能力卡：${cards.join('  ///  ') || '（没有卡）'}`);
  const percent = Number((header.match(/(\d+)%/) || [])[1] ?? -1);
  expect(percent > 10, '页头理解度是真数（> 10%，不是恒 0）', `读到 ${percent}%`);
  expect(cards.length >= 1 && !cards.join().includes('--- name:'), '卡面小字不是压平的 markdown', cards[0]?.slice(0, 60));
  expect(cards.join().includes('交付'), '卡片维度按归属系统给出（不是"未标注"）');
  // "知识库"那一排卡：这个账号没导入任何资料，所以**应该只有三件成果**。
  // 以前任务验收产物同时被当成"资料"，同一件东西会在这一排出现两遍（3 件变 5 张）。
  const progressCards = await page.evaluate(() => [...document.querySelectorAll('.v277-progress-cards > *')].map((item) => item.innerText.replace(/\n/g, '｜')));
  expect(progressCards.length === 3, '同一件验收产物不会在"资料"和"成果"里各显示一次', `这一排 ${progressCards.length} 张，成果 ${(snapshot.objects.outcome || []).length} 件`);
  await page.screenshot({ path: path.join(OUT, 'page2.png'), fullPage: true });

  // 能力库 / 记忆库两个页头的理解度必须是同一个数：以前能力库那边在空态硬写了 0，
  // 而记忆库用后端给的起点值（一成），同一个账号在同一页的两个标签下看到两个数。
  await page.getByRole('button', { name: '记忆库' }).first().click();
  await sleep(2500);
  const memoryHeader = await page.evaluate(() => document.querySelector('.v277-library-head')?.innerText?.replace(/\n/g, ' | ') ?? '');
  const memoryPercent = Number((memoryHeader.match(/(\d+)%/) || [])[1] ?? -1);
  expect(memoryPercent === percent, '记忆库页头的理解度和能力库一致', `能力库 ${percent}% / 记忆库 ${memoryPercent}%`);
  await page.getByRole('button', { name: '能力库' }).first().click();
  await sleep(2500);

  // ── ③ 点开一张卡看说明书 ──────────────────────────────────────────
  const card = page.locator('.v277-ability-cards button').first();
  if (await card.count()) {
    await card.click();
    await sleep(1200);
    const sheet = await page.evaluate(() => document.querySelector('.v279-capability-sheet')?.innerText ?? '');
    console.log('\n能力卡弹层：');
    console.log(sheet.split('\n').filter((line) => line.trim()).slice(0, 18).map((line) => `  ${line}`).join('\n'));
    expect(sheet.includes('它能替你做') && !sheet.includes('## 什么时候用'), '"它能替你做"是解析出来的人话，不是 markdown 原文');
    expect(sheet.includes('使用说明') && sheet.includes('完整说明'), '使用说明有流程图 + 可展开的完整说明');
    await page.screenshot({ path: path.join(OUT, 'card-sheet.png'), fullPage: true });
    await page.getByRole('button', { name: '关闭', exact: true }).click().catch(() => {});
    await sleep(600);
    if (await page.locator('.v279-capability-sheet').count()) { await page.reload({ waitUntil: 'domcontentloaded' }); await sleep(2500); }
  } else {
    expect(false, '这张账号应该有一张能力卡');
  }

  // ── ④ 理解度面板 + 第四页 ─────────────────────────────────────────
  // ── ③b 能力卡组右上那两颗圆钮：创建工具 / 查看我的工具 ─────────────
  // （中间那颗"让 Skill Foundry 生成"已按反馈删掉；这里同时反向断言它不会再出现）
  console.log('\n工具圆钮：');
  expect(await page.getByRole('button', { name: /Skill Foundry/ }).count() === 0, '中间那颗"让 Skill Foundry 生成"已经删掉');
  const createEntry = page.getByRole('button', { name: '创建工具' }).first();
  expect(await createEntry.count() > 0, '右上还有一颗「创建工具」');
  await createEntry.click();
  await sleep(2500);
  const editor = await page.evaluate(() => document.body.innerText);
  console.log(`  创建工具页：${editor.split('\n').filter(Boolean).slice(0, 4).join(' | ')}`);
  expect(/创建工具/.test(editor) && /工具名称/.test(editor), '点「创建工具」真的进了创建工具页');
  await page.screenshot({ path: path.join(OUT, 'create-tool.png'), fullPage: true });
  // 创建工具页是整屏的（没有底部导航），用它自己的返回键回去
  await page.getByRole('button', { name: '返回我的工具' }).click().catch(() => {});
  await sleep(2500);
  expect(/能力卡组/.test(await page.evaluate(() => document.body.innerText)), '从创建工具页返回后回到能力库');
  const toolsEntry = page.getByRole('button', { name: '查看我的工具' }).first();
  expect(await toolsEntry.count() > 0, '右上还有一颗「查看我的工具」');
  await toolsEntry.click();
  await sleep(2500);
  const toolsPage = await page.evaluate(() => document.body.innerText);
  console.log(`  我的工具页：${toolsPage.split('\n').filter(Boolean).slice(0, 4).join(' | ')}`);
  expect(/我的工具/.test(toolsPage), '点「查看我的工具」真的进了我的工具页');
  await page.screenshot({ path: path.join(OUT, 'my-tools.png'), fullPage: true });
  await page.getByRole('button', { name: '返回' }).first().click().catch(() => {});
  await sleep(2500);
  expect(/能力卡组/.test(await page.evaluate(() => document.body.innerText)), '从工具页返回后回到能力库');

  // ── ④ 理解度面板 + 第四页 ─────────────────────────────────────────
  const chip = page.locator('.v277-context-chip').first();
  if (await chip.count()) {
    await chip.click({ force: true });
    await sleep(1200);
    const levelSheet = await page.evaluate(() => document.querySelector('[aria-label="理解度详情"]')?.innerText ?? '');
    console.log('\n理解度弹层：');
    console.log(levelSheet.split('\n').filter((line) => line.trim()).slice(0, 14).map((line) => `  ${line}`).join('\n'));
    expect(/Lv\.\d/.test(levelSheet) && /当前理解度/.test(levelSheet), '理解度面板有档位与百分比');
    expect(/还差多少/.test(levelSheet), '理解度面板说清"到下一档还差多少"');
    await page.screenshot({ path: path.join(OUT, 'understanding.png'), fullPage: true });
    await page.getByRole('button', { name: '关闭', exact: true }).click().catch(() => {});
    await sleep(500);
    if (await page.locator('[aria-label="理解度详情"]').count()) { await page.reload({ waitUntil: 'domcontentloaded' }); await sleep(2500); }
  }
  await page.getByRole('button', { name: '我的', exact: true }).click();
  await sleep(2500);
  const profile = await page.evaluate(() => document.body.innerText);
  console.log('\n第四页：');
  console.log(profile.split('\n').filter((line) => line.trim()).slice(0, 10).map((line) => `  ${line}`).join('\n'));
  await page.screenshot({ path: path.join(OUT, 'page4.png'), fullPage: true });

  expect(consoleErrors.length === 0, '整轮没有控制台报错', consoleErrors.slice(0, 2).join(' / '));
  await browser.close();

  console.log(`\n截图：${OUT}`);
  console.log(failures.length ? `✗ 有 ${failures.length} 项不符：${failures.join('；')}` : '✓ 全部符合');
  process.exit(failures.length ? 1 : 0);
})().catch((error) => { console.error('实机检查失败：', error); process.exit(1); });
