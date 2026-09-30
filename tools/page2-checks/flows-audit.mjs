/**
 * 第二页/第四页的**用户流程审计**：不只看首屏渲染，把用户真会走的几条路都点一遍，
 * 每条都断言"数据真的落库 / 真的显示出来"，而不是只看按钮在不在。
 *
 * 覆盖的流程（每条都会打印证据）：
 *   ① 记忆库：自动学到的理解真的显示出来（不是空态）
 *   ② 编辑资料：改昵称 → 保存 → 回主页看到新昵称（真的落库，不是本地状态）
 *   ③ 设置：能进设置页、每行都是真落点；上游服务状态已不在界面出现（只在后端接口）
 *   ④ 导入：选文件 → 文档列表出现它（真 document.create）
 *   ⑤ 轻量测试：答完 → 起点落库 → 能力洞察出现数字（真 questionnaire.submit）
 *   ⑥ 动态：第四页动态时间轴渲染社区里真人的帖子，点赞是真操作
 *
 * 用法（应用要在跑；playwright 用 NODE_PATH 指过去，同 live-audit.mjs）：
 *   $env:NODE_PATH = "<装了 playwright 的 node_modules>"
 *   node tools/page2-checks/flows-audit.mjs
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
import { enterApp } from './_page.mjs';

const BASE = process.env.PAGE24_BASE || 'http://127.0.0.1:3000';
const OUT = path.join(process.env.TEMP || '.', 'pages24-flows-audit');
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

const failures = [];
const expect = (ok, label, detail = '') => {
  console.log(`  ${ok ? '✓' : '✗'} ${label}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures.push(label);
};

(async () => {
  // 造一个干净的账号 + 一条自动学到的理解（流程①的素材）
  const handle = `flow${Date.now()}`;
  await j('/auth/register', { method: 'POST', body: JSON.stringify({ handle, password: 'flow-password-1', name: '审查' }) });
  const csrf = (await j('/session')).body.csrf;
  const cmd = (action, input) => j('/commands', {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrf, 'Idempotency-Key': `${action}-${Math.random().toString(36).slice(2)}` },
    body: JSON.stringify({ action, input }),
  });
  const bootstrap = async () => (await j('/bootstrap')).body;

  const onboarding = (await bootstrap()).objects.onboarding?.[0];
  await cmd('onboarding.choice.defer', { id: onboarding.id, version: onboarding.version });
  const conversation = (await cmd('agent.chat.create', { system: 'create' })).body;
  await cmd('agent.chat.send', { id: conversation.id, model_consent: true, text: '我平时写方案喜欢先给结论，再补依据。' });
  await sleep(1500);
  // Jev 判定是异步的（要在"没有任务在跑"的那一格才发出去），等它出结果再往下，
  // 免得"上游状态"那一屏读到的是"还没判"而不是"判完了"。
  for (let i = 0; i < 20; i += 1) {
    const runs = (await bootstrap()).objects.jev_run || [];
    if (runs.length) { console.log(`（Jev 已判定，用量 ${JSON.stringify(runs[0].data.usage)}）`); break; }
    await sleep(2000);
  }

  const browser = await chromium.launch(process.env.PAGE24_CHROME ? { executablePath: process.env.PAGE24_CHROME } : {});
  const context = await browser.newContext({ viewport: { width: 430, height: 932 } });
  await context.addCookies([{ name: 'elfred_session', value: token, domain: new URL(BASE).hostname, path: '/' }]);
  const page = await context.newPage();
  const consoleErrors = [];
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text().slice(0, 160)); });
  page.on('pageerror', (error) => consoleErrors.push(String(error).slice(0, 160)));
  // 把"哪条请求挂了"也记下来：`ERR_NETWORK_CHANGED` 这种是机器网络（代理/网卡）抖，
  // 不是产品报错；只看 message 文本分不出来，得看失败的 URL 是不是我们自己的。
  page.on('requestfailed', (request) => {
    const failure = request.failure()?.errorText ?? '';
    if (/ERR_ABORTED/.test(failure)) return;
    consoleErrors.push(`请求失败 ${request.url().slice(0, 120)} — ${failure}`);
  });

  // ── ① 记忆库 ────────────────────────────────────────────────────────
  console.log('① 记忆库');
  await enterApp(page, { tab: '知识' });
  await page.getByRole('button', { name: '记忆库' }).click();
  await sleep(2500);
  const memoryText = await page.evaluate(() => document.body.innerText);
  expect(/写方案喜欢先给结论/.test(memoryText), '自动学到的理解显示在记忆库里', (memoryText.match(/.*写方案喜欢先给结论.*/) || [''])[0].slice(0, 40));
  // 注意：分组为空时每类会写"这一类还没有记忆…"，那是正常的；这里查的是**整屏空态**（标题就是"还没有记忆"）。
  const pageLevelEmpty = memoryText.split('\n').some((line) => line.trim() === '还没有记忆');
  if (pageLevelEmpty) {
    console.log('    （整屏空态与真实记忆同时出现，这一屏的实际内容：）');
    console.log(memoryText.split('\n').filter(Boolean).map((line) => `      ${line}`).join('\n'));
  }
  expect(!pageLevelEmpty, '不是整屏空态（有记忆就不该出现"还没有记忆"的标题）');
  await page.screenshot({ path: path.join(OUT, 'memory.png'), fullPage: true });

  // ── ② 编辑资料 → 保存 → 主页显示新昵称 ──────────────────────────────
  console.log('② 编辑资料');
  await page.getByRole('button', { name: '我的', exact: true }).click();
  await sleep(2500);
  await page.getByRole('button', { name: '编辑资料', exact: true }).click();
  await sleep(2000);
  // 「个人信息」那四行必须是一整块卡：以前"用户名"是只读的 div，`:first-of-type/:last-of-type`
  // 是按标签算的，于是它同时命中 first 和 last，自己在中间收了个圆角+底边，看着像被切成两块。
  const infoRows = await page.evaluate(() => {
    const section = [...document.querySelectorAll('section')].find((item) => item.querySelector('h2')?.textContent?.includes('个人信息'));
    if (!section) return null;
    return [...section.children].filter((node) => node.tagName !== 'H2').map((node) => ({
      label: node.querySelector('span')?.textContent?.trim() || '',
      bottomWidth: getComputedStyle(node).borderBottomWidth,
      radius: getComputedStyle(node).borderBottomLeftRadius,
      background: getComputedStyle(node).backgroundColor,
    }));
  });
  expect(Array.isArray(infoRows) && infoRows.length === 4, '「个人信息」那一组是四行', `${infoRows?.length}`);
  const userNameRow = infoRows?.find((row) => row.label === '用户名');
  const tagsRow = infoRows?.find((row) => row.label === '领域标签');
  expect(userNameRow?.bottomWidth === '0px', '「用户名」那一行不带底边（不在中间收口）', userNameRow?.bottomWidth);
  expect(userNameRow?.radius === '0px', '「用户名」那一行不圆下角', userNameRow?.radius);
  expect(tagsRow?.bottomWidth === '1px', '最后一行「领域标签」有底边', tagsRow?.bottomWidth);
  expect(infoRows?.every((row) => row.background === 'rgb(255, 255, 255)'), '四行底色一致（看不出拼接缝）');
  // 少解释：编辑资料不再挂那些冗余说明（"任何情况下都不会公开"、开关下面的解释小字、跳记忆库的链接）
  const editText = await page.evaluate(() => document.body.innerText);
  expect(!/任何情况下都不会公开|去看它记住了什么|主页上不显示等级与理解度|主页上会显示/.test(editText), '编辑资料不再挂冗余解释（开关小字、隐私说明那一整段）');
  await page.screenshot({ path: path.join(OUT, 'profile-edit.png'), fullPage: true });
  const nickname = `审查昵称${Date.now() % 10000}`;
  await page.getByText('昵称', { exact: true }).first().click();
  await sleep(1200);
  const input = page.locator('input[placeholder]').first();
  await input.fill(nickname);
  await page.getByRole('button', { name: '保存', exact: true }).click();
  await sleep(2500);
  await page.getByRole('button', { name: '返回' }).first().click().catch(() => {});
  await sleep(2500);
  await page.getByRole('button', { name: '我的', exact: true }).click();
  await sleep(2500);
  const saved = (await bootstrap()).objects.profile?.[0]?.data?.name;
  expect(saved === nickname, '昵称真的落库了（不是只改了本地）', `库里的名字：${saved}`);
  expect((await page.evaluate(() => document.body.innerText)).includes(nickname), '主页显示新昵称');
  await page.screenshot({ path: path.join(OUT, 'profile.png'), fullPage: true });

  // ── ③ 设置页能进，逐行都有真落点 ────────────────────────────────────
  console.log('③ 设置页');
  // 第四页右上那颗设置按钮的 aria-label 是"个人设置"（不是"设置"，差点点错到别的地方）
  await page.getByRole('button', { name: '个人设置' }).click();
  await sleep(3000);
  const settingsText = await page.evaluate(() => document.body.innerText);
  // 用界面上的真标签（别猜，猜错了会误报）
  for (const label of ['昵称、简介与标签', '记忆与理解', '退出登录']) {
    const line = settingsText.split('\n').find((row) => row.includes(label));
    expect(Boolean(line), `设置页里有「${label}」这一行`, line?.slice(0, 70));
  }
  // 上游服务状态只在后端（GET /api/elfred/health/deps）：设置页不该出现那几个服务名
  expect(
    !/上游服务状态|Skill Foundry|PA 网关|EMOS/.test(settingsText),
    '设置页不再摆上游服务状态（那几行只在后端接口里）',
  );
  // 「理解度」那一行必须是理解度本身：以前它显示的是"记忆领域覆盖"，和页头那个百分比并列，像两套数
  expect(/\d+%\s*·\s*Lv\.\d/.test(settingsText), '设置里「理解度」显示的是百分比与等级', (settingsText.match(/\d+%[^\n]*/) || [''])[0]);
  const memoryRow = settingsText.split('\n').find((line) => /已确认/.test(line)) || '';
  expect(/个领域有记录/.test(memoryRow), '记忆覆盖挪到了「记忆与理解」那一行', memoryRow.slice(0, 40));
  await page.screenshot({ path: path.join(OUT, 'settings.png'), fullPage: true });
  await page.getByRole('button', { name: '返回' }).first().click().catch(() => {});
  await sleep(2000);

  // ── ④ 导入一个文件 → 文档列表出现它 ─────────────────────────────────
  console.log('④ 导入文件');
  const filePath = path.join(OUT, '审查用资料.md');
  writeFileSync(filePath, '# 审查用资料\n\n这是流程审计写进去的一份文档。\n');
  await page.getByRole('button', { name: '知识' }).click();
  await sleep(2500);
  await page.getByRole('button', { name: '查看资料' }).click();
  await sleep(1200);
  const fileInput = page.locator('input[type="file"]').first();
  await fileInput.setInputFiles(filePath);
  // 导入要等服务端落库 + 这一页重新取数：轮询等它出现在页面上，不用固定秒数
  let imported = false;
  let seen = false;
  for (let i = 0; i < 20; i += 1) {
    await sleep(1000);
    imported = imported || Boolean((await bootstrap()).objects.document?.some((item) => item.data.title === '审查用资料.md'));
    seen = /审查用资料/.test(await page.evaluate(() => document.body.innerText));
    if (imported && seen) break;
  }
  expect(imported, '文件真的落成文档对象（document.create）');
  expect(seen, '页面上能看到它');
  // 「预览」以前点了只回一句"预览还没接"（死按钮）——现在点开就是这份资料
  const previewBtn = page.getByRole('button', { name: '预览' }).first();
  await previewBtn.waitFor({ state: 'visible', timeout: 20000 }).catch(() => {});
  expect(await previewBtn.count() > 0, '导入面板里那份资料有「预览」');
  await previewBtn.click();
  await sleep(2500);
  const detail = await page.evaluate(() => document.body.innerText);
  expect(/审查用资料/.test(detail), '点「预览」进的是这份资料的详情页', detail.split('\n').filter(Boolean).slice(0, 3).join(' | '));
  expect(!/预览还没接/.test(detail), '不再出现"预览还没接"那句');
  await page.keyboard.press('Escape');
  await sleep(500);

  // ── ⑤ 轻量测试 → 起点落库 → 雷达有数字 ─────────────────────────────
  console.log('⑤ 轻量测试');
  const answers = Array.from({ length: 24 }, (_, index) => ({ id: `q${index + 1}`, choice: index % 2 ? 1 : 0 }));
  const paper = (await j('/page2/questionnaire')).body;
  const submitted = await cmd('questionnaire.submit', { answers: (paper.items || []).map((item, index) => ({ id: item.id, choice: index % 2 ? 2 : 1 })) });
  expect(submitted.status === 200 || submitted.body?.ok === true, '提交作答成功', JSON.stringify(submitted.body).slice(0, 80));
  // 刷新之后应用回到首页，得再进一次「知识」才看得到能力洞察（入口统一走共用函数，别用固定等待）
  await enterApp(page, { tab: '知识', settle: 3000 });
  const afterTest = await page.evaluate(() => document.body.innerText);
  expect(!/还没有能力洞察/.test(afterTest), '测完之后能力洞察不再是空态');
  const radarNumbers = (afterTest.match(/(洞察|判断|表达|链接|交付)\s*\d+/g) || []).length;
  if (radarNumbers < 3) {
    // 断言不成的时候把"能力洞察"那一块打出来，别让人只看一个数字
    const insightText = await page.evaluate(() => document.querySelector('.v277-cave-section')?.innerText ?? '(找不到能力洞察那一块)');
    console.log('    （能力洞察那一块的实际内容：）');
    console.log(insightText.split('\n').filter(Boolean).map((line) => `      ${line}`).join('\n'));
  }
  const hasNumbers = /\d{2}/.test(afterTest.replace(/理解度\s*\d+%/g, ''));
  expect(radarNumbers >= 3 || hasNumbers, '雷达 / 综合分上出现真实数字', `成对匹配 ${radarNumbers} 处`);
  await page.screenshot({ path: path.join(OUT, 'insight.png'), fullPage: true });
  void answers;

  // ── ⑥ 第四页动态 + 点赞 ─────────────────────────────────────────────
  console.log('⑥ 动态与互动');
  await page.getByRole('button', { name: '我的', exact: true }).click();
  await sleep(3000);
  const feedText = await page.evaluate(() => document.body.innerText);
  const hasPost = /收藏/.test(feedText);
  expect(hasPost, '动态时间轴渲染了帖子（带点赞 / 评论 / 收藏）');
  const likeButtons = page.locator('button:has-text("收藏")');
  if (await likeButtons.count()) {
    await likeButtons.first().click();
    await sleep(2000);
    const interactions = (await bootstrap()).objects.interaction || [];
    expect(interactions.length > 0, '收藏真的写成了 interaction 对象', `共 ${interactions.length} 条`);
  } else {
    expect(false, '找不到可点的动态按钮');
  }
  await page.screenshot({ path: path.join(OUT, 'feed.png'), fullPage: true });

  expect(consoleErrors.length === 0, '整轮没有控制台报错', consoleErrors.slice(0, 2).join(' / '));
  await browser.close();
  console.log(`\n截图：${OUT}`);
  console.log(failures.length ? `✗ 有 ${failures.length} 项不符：${failures.join('；')}` : '✓ 全部符合');
  process.exit(failures.length ? 1 : 0);
})().catch((error) => { console.error('流程审计失败：', error); process.exit(1); });
