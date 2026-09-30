// 三个真机探针共用的入口：把"进主界面并切到某一页"这件事写一次，
// 免得每条探针各自 sleep 一个固定秒数（应用启动慢时会偶发失败，实测踩过两次）。
const APP = process.env.PAGE24_BASE || 'http://127.0.0.1:3000';

/**
 * 打开应用并切到目标页。
 * @param {import('playwright').Page} page
 * @param {{tab?: '知识'|'我的', settle?: number}} options
 */
export async function enterApp(page, { tab = '知识', settle = 2500 } = {}) {
  const nav = page.getByRole('button', { name: tab });
  // dev 模式下首次编译 + 首屏很慢（实测 45 秒以上），goto 的默认 30 秒会先超时；给足时间再等元素。
  // 等不到就重开一次页面（连跑多个账号时服务端会被前面那些请求拖慢，重开一次比干等有效）。
  for (let attempt = 1; attempt <= 2; attempt += 1) {
    await page.goto(`${APP}/v28`, { waitUntil: 'domcontentloaded', timeout: 90000 });
    try {
      await nav.waitFor({ state: 'visible', timeout: 90000 });
    } catch {
      // 新账号有时首屏落在"首次对齐"引导页（没有底部导航），先跳过再进主界面
      const labels = await page.evaluate(() => [...document.querySelectorAll('button[aria-label]')].map((item) => item.getAttribute('aria-label')));
      const text = await page.evaluate(() => document.body.innerText);
      console.log(`    （还没进主界面：${text.split('\n').filter(Boolean).slice(0, 3).join(' | ')}）`);
      console.log(`    （可点的：${labels.slice(0, 10).join(' / ') || '（没有按钮）'}）`);
      const skip = page.getByRole('button', { name: /稍后再说|稍后继续|跳过|进入首页|保存并返回首页/ }).first();
      if (await skip.count()) { await skip.click().catch(() => {}); }
      else console.log('    （没找到"稍后"类按钮，继续等）');
      try {
        await nav.waitFor({ state: 'visible', timeout: 60000 });
      } catch (error) {
        if (attempt === 2) throw error;
        console.log('    （这一轮没等到，重开一次页面）');
        continue;
      }
    }
    await nav.click();
    await page.waitForTimeout(settle);
    return;
  }
}
