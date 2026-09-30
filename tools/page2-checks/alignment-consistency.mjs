/**
 * 「理解度」口径一致性的真机审计（专门盯**空态新用户**那条路）。
 *
 * 为什么要单开一条：live-audit.mjs 造的账号有卡有成果，走的是"非空态"分支；
 * 用户截图里的问题（页头 10%、弹层 0%）只在"三块都空"的新账号上出现，
 * 所以那条探针一直没覆盖到 —— 这次把它补上。
 *
 * 做四件事，每件都打印读到的数：
 *   ① 能力库页头 vs 能力库弹层
 *   ② 记忆库页头 vs 记忆库弹层（且与能力库页头同数）
 *   ③ 第四页等级胶囊 vs 第四页弹层
 *   ④ 设置页「理解度」那一行
 * 五处必须是**同一个数**，否则判不合格。
 *
 * 用法（应用要在跑）：
 *   $env:NODE_PATH = "<装了 playwright 的 node_modules>"
 *   node tools/page2-checks/alignment-consistency.mjs
 */
import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
import { enterApp } from './_page.mjs';

const BASE = process.env.PAGE24_BASE || 'http://127.0.0.1:3000';
const OUT = path.join(process.env.TEMP || '.', 'pages24-alignment-audit');
mkdirSync(OUT, { recursive: true });

const failures = [];
const expect = (ok, label, detail = '') => {
  console.log(`  ${ok ? '✓' : '✗'} ${label}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures.push(label);
};
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const percentOf = (text) => Number((String(text).match(/(\d+)\s*%/) || [])[1] ?? -1);

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

(async () => {
  // ── 一个真正的新账号：什么都不做，三块都是空的 ────────────────────────
  const handle = `align${Date.now()}`;
  await j('/auth/register', { method: 'POST', body: JSON.stringify({ handle, password: 'align-password-1', name: '路人' }) });
  const csrf = (await j('/session')).body.csrf;
  const onboarding = (await j('/bootstrap')).body.objects.onboarding?.[0];
  if (onboarding) {
    await j('/commands', {
      method: 'POST',
      headers: { 'X-CSRF-Token': csrf, 'Idempotency-Key': `align-defer-${Math.random().toString(36).slice(2)}` },
      body: JSON.stringify({ action: 'onboarding.choice.defer', input: { id: onboarding.id, version: onboarding.version } }),
    });
  }
  const snapshot = await j('/bootstrap');
  const objects = snapshot.body.objects || {};
  console.log(`新账号 ${handle}：能力卡 ${(objects.skill || []).length} · 成果 ${(objects.outcome || []).length} · 记忆 ${(objects.memory || []).length}（三块都空 = 空态）\n`);

  const browser = await chromium.launch(process.env.PAGE24_CHROME ? { executablePath: process.env.PAGE24_CHROME } : {});
  const context = await browser.newContext({ viewport: { width: 430, height: 932 } });
  await context.addCookies([{ name: 'elfred_session', value: token, domain: new URL(BASE).hostname, path: '/' }]);
  const page = await context.newPage();
  const consoleErrors = [];
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text().slice(0, 160)); });
  page.on('pageerror', (error) => consoleErrors.push(String(error).slice(0, 160)));
  // 哪条请求挂了也记下来：`ERR_NETWORK_CHANGED` 是机器网络（代理 / 网卡）抖，不是产品报错，
  // 只看 message 文本分不出，得看失败的 URL 是不是我们自己的。
  page.on('requestfailed', (request) => {
    const failure = request.failure()?.errorText ?? '';
    if (/ERR_ABORTED/.test(failure)) return;
    consoleErrors.push(`请求失败 ${request.url().slice(0, 120)} — ${failure}`);
  });

  const headerText = () => page.evaluate(() => document.querySelector('.v277-library-head')?.innerText?.replace(/\n/g, ' | ') ?? '');
  const openSheet = async () => {
    await page.locator('.v277-context-chip').first().click({ force: true });
    await sleep(1400); // 弹层里的百分比是 700ms 缓动，等它走到终值再读
    return page.evaluate(() => document.querySelector('[aria-label="理解度详情"]')?.innerText ?? '');
  };
  const closeSheet = async () => {
    await page.getByRole('button', { name: '关闭', exact: true }).first().click().catch(() => {});
    await sleep(500);
    if (await page.locator('[aria-label="理解度详情"]').count()) {
      await page.reload({ waitUntil: 'domcontentloaded' });
      await sleep(2500);
    }
  };

  await enterApp(page, { tab: '知识' });

  // ── ① 能力库 ───────────────────────────────────────────────────────
  const knowledgeHeader = await headerText();
  const knowledgeHeaderPercent = percentOf(knowledgeHeader);
  const knowledgeSheet = await openSheet();
  const knowledgeSheetPercent = percentOf(knowledgeSheet);
  console.log('能力库：');
  console.log(`  页头：${knowledgeHeader}`);
  console.log(`  弹层：${knowledgeSheet.split('\n').filter((line) => line.trim()).slice(0, 3).join(' | ')}`);
  expect(knowledgeHeaderPercent >= 0, '能力库页头读到了理解度数值', `${knowledgeHeaderPercent}%`);
  expect(
    knowledgeSheetPercent === knowledgeHeaderPercent,
    '能力库：页头理解度 === 弹层「当前理解度」',
    `页头 ${knowledgeHeaderPercent}% / 弹层 ${knowledgeSheetPercent}%`,
  );
  expect(knowledgeSheetPercent > 0, '空态也不是 0%（后端给的起点值，不是硬写 0）', `弹层 ${knowledgeSheetPercent}%`);
  // 这两句是 2026-09-30 按反馈删掉的（标题下的小字 + 去看记忆库的出口），别再长回来
  expect(!/由已确认的记忆与反馈持续更新/.test(knowledgeSheet), '标题下那行小字已经删掉');
  expect(!/看它记住了什么/.test(knowledgeSheet), '「看它记住了什么」这个出口已经删掉');
  // 等级卡里那句「每个动作都要你点一下」也按反馈删掉了（展开的六档梯子里每档还留着说明）
  expect(!/每个动作都要你点一下/.test(knowledgeSheet), '等级卡里那行小字已经删掉');
  // 中间那块只说"离下一档还差多少"（百分数），不再重复写「10% → 40%」，也不再挂那句小字
  expect(/距离 Lv\.\d 还差\s*\d+%/.test(knowledgeSheet), '中间那块一句话说完「距离 Lv.N 还差 X%」', knowledgeSheet.split('\n').map((line) => line.trim()).filter((line) => /还差/.test(line)).join(' | '));
  expect(!/件你验收过的成果/.test(knowledgeSheet), '「再有 N 件…」那行小字已经删掉');
  // 另一栏（荣誉勋章）也得真画出来：两边共用 /page2/badges 和同一个 HonorGallery
  // 注意：`getByRole(name)` 默认是"包含"匹配 —— 页头那颗胶囊的 aria-label 里也有"荣誉勋章"，
  // 直接被点到就是点到弹层外面（会被遮罩拦下）。所以这里必须在弹层里找、而且用 exact。
  const sheetRoot = page.locator('[aria-label="理解度详情"]');
  await sheetRoot.getByRole('button', { name: '荣誉勋章', exact: true }).click();
  await sleep(1200);
  const honorsSheet = await page.evaluate(() => document.querySelector('[aria-label="理解度详情"]')?.innerText ?? '');
  expect(/勋章图鉴/.test(honorsSheet), '「荣誉勋章」那一栏能打开并画出图鉴', honorsSheet.split('\n').filter((line) => line.trim()).slice(0, 2).join(' | '));
  await page.screenshot({ path: path.join(OUT, 'knowledge-sheet-honors.png'), fullPage: true });
  await sheetRoot.getByRole('button', { name: '等级', exact: true }).click();
  await sleep(400);
  await page.screenshot({ path: path.join(OUT, 'knowledge-sheet.png'), fullPage: true });
  // 成长路径那一行以前是个点不动的 div（用户说"不通"）；现在点它 = 铺开六档
  await sheetRoot.getByRole('button', { name: '查看完整的成长路径' }).click();
  await sleep(700);
  const ladder = await page.evaluate(() => document.querySelector('[aria-label="理解度详情"]')?.innerText ?? '');
  expect(/Lv\.6/.test(ladder), '「成长路径」那一行点得动，会铺开六档', ladder.split('\n').filter((line) => /^Lv\.6/.test(line.trim())).join(''));
  await page.screenshot({ path: path.join(OUT, 'knowledge-sheet-path.png'), fullPage: true });
  await sheetRoot.getByRole('button', { name: '收起' }).click();
  await sleep(500);
  const collapsed = await page.evaluate(() => document.querySelector('[aria-label="理解度详情"]')?.innerText ?? '');
  expect(!/Lv\.6/.test(collapsed), '点「收起」能回到一行', collapsed.split('\n').filter((line) => /下一阶段/.test(line)).join(''));
  await closeSheet();

  // ── ② 记忆库（同一个组件，同一份数） ──────────────────────────────────
  await page.getByRole('button', { name: '记忆库' }).first().click();
  await sleep(2500);
  const memoryHeader = await headerText();
  const memoryHeaderPercent = percentOf(memoryHeader);
  const memorySheet = await openSheet();
  const memorySheetPercent = percentOf(memorySheet);
  console.log('\n记忆库：');
  console.log(`  页头：${memoryHeader}`);
  expect(memoryHeaderPercent === knowledgeHeaderPercent, '记忆库页头 === 能力库页头', `${knowledgeHeaderPercent}% / ${memoryHeaderPercent}%`);
  expect(memorySheetPercent === memoryHeaderPercent, '记忆库：页头 === 弹层', `${memoryHeaderPercent}% / ${memorySheetPercent}%`);
  await closeSheet();

  // ── ③ 第四页 ───────────────────────────────────────────────────────
  await page.getByRole('button', { name: '我的', exact: true }).click();
  await sleep(2500);
  const chip = page.locator('[aria-label^="理解度："]').first();
  const chipLabel = (await chip.count()) ? await chip.getAttribute('aria-label') : '';
  const chipLevel = Number((String(chipLabel).match(/Lv\.(\d+)/) || [])[1] ?? -1);
  await chip.click({ force: true });
  await sleep(1400);
  const profileSheet = await page.evaluate(() => document.querySelector('[aria-label="理解度详情"]')?.innerText ?? '');
  const profileSheetPercent = percentOf(profileSheet);
  console.log('\n第四页：');
  console.log(`  名字旁胶囊：${chipLabel}`);
  expect(chipLevel >= 1, '第四页有等级胶囊', chipLabel);
  expect(
    profileSheetPercent === knowledgeHeaderPercent,
    '第四页弹层 === 能力库页头',
    `第四页 ${profileSheetPercent}% / 能力库 ${knowledgeHeaderPercent}%`,
  );
  await page.screenshot({ path: path.join(OUT, 'profile-sheet.png'), fullPage: true });
  await closeSheet();

  // ── ④ 设置页那一行 ─────────────────────────────────────────────────
  await page.getByRole('button', { name: '个人设置' }).first().click();
  await sleep(2500);
  const settingsText = await page.evaluate(() => document.body.innerText);
  const settingsRow = settingsText.split('\n').map((line) => line.trim()).filter((line) => /% · Lv\./.test(line))[0] ?? '';
  const settingsPercent = percentOf(settingsRow);
  console.log('\n设置页：');
  console.log(`  理解度那一行：${settingsRow}`);
  expect(settingsPercent === knowledgeHeaderPercent, '设置页 === 能力库页头', `设置 ${settingsPercent}% / 能力库 ${knowledgeHeaderPercent}%`);
  expect(!/还没有数据/.test(settingsRow), '设置页不再因为"没接上"而显示占位句', settingsRow);
  await page.screenshot({ path: path.join(OUT, 'settings.png'), fullPage: true });

  expect(consoleErrors.length === 0, '整轮没有控制台报错', consoleErrors.slice(0, 2).join(' / '));
  await browser.close();

  const summary = [
    `能力库页头 ${knowledgeHeaderPercent}%`,
    `能力库弹层 ${knowledgeSheetPercent}%`,
    `记忆库页头 ${memoryHeaderPercent}%`,
    `记忆库弹层 ${memorySheetPercent}%`,
    `第四页弹层 ${profileSheetPercent}%`,
    `设置页 ${settingsPercent}%`,
  ].join(' · ');
  console.log(`\n读数：${summary}`);
  console.log(`截图：${OUT}`);
  console.log(failures.length ? `✗ 有 ${failures.length} 项不符：${failures.join('；')}` : '✓ 全部符合');
  process.exit(failures.length ? 1 : 0);
})().catch((error) => { console.error('实机检查失败：', error); process.exit(1); });
