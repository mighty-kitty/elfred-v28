import test from 'node:test';
import assert from 'node:assert/strict';
import { safeBase, callJson, joinUrl } from '../../server/elfred/upstream.mjs';

// 这两个零件被四个上游共用（记忆中枢 / 能力服务 / 规划网关 / 依赖状态），
// 所以规矩只在这里钉一次，改的时候不会漏掉某一家。

test('地址白名单：只收 https 与本机回环的 http', () => {
  assert.equal(safeBase('https://api.example.com/v1').hostname, 'api.example.com');
  assert.equal(safeBase('http://127.0.0.1:8200').port, '8200');
  assert.equal(safeBase('http://localhost:8765').hostname, 'localhost');
  assert.equal(safeBase('http://[::1]:8790').hostname, '[::1]');
  assert.equal(safeBase('http://example.com'), null, '明文 http 只允许本机');
  assert.equal(safeBase('https://user:pass@api.example.com'), null, '不许把账号密码写进地址');
  assert.equal(safeBase('https://api.example.com/?token=x'), null);
  assert.equal(safeBase('https://api.example.com/#frag'), null);
  assert.equal(safeBase('不是地址'), null);
  assert.equal(safeBase(undefined), null);
});

test('callJson：正常返回解析后的对象，空响应体返回 null', async () => {
  const fetcher = async () => ({ ok: true, status: 200, text: async () => '{"status":"ok"}' });
  assert.deepEqual(await callJson(fetcher, 'https://api.example.com/health'), { status: 'ok' });
  const empty = async () => ({ ok: true, status: 204, text: async () => '' });
  assert.equal(await callJson(empty, 'https://api.example.com/x'), null);
});

test('callJson：非 2xx / 超大 / 不是 JSON 都抛错，且带上状态码与片段', async () => {
  const bad = async () => ({ ok: false, status: 503, text: async () => 'upstream down' });
  await assert.rejects(() => callJson(bad, 'https://api.example.com/x'), /HTTP 503/);

  const huge = async () => ({ ok: true, status: 200, text: async () => 'x'.repeat(50) });
  await assert.rejects(() => callJson(huge, 'https://api.example.com/x', { limit: 10 }), /响应过大/);

  const notJson = async () => ({ ok: true, status: 200, text: async () => '<html>' });
  await assert.rejects(() => callJson(notJson, 'https://api.example.com/x'), /不是有效的 JSON/);
});

test('callJson：方法、头、体与超时都递给了 fetch', async () => {
  let seen = null;
  const fetcher = async (url, init) => { seen = { url, init }; return { ok: true, status: 200, text: async () => '{}' }; };
  await callJson(fetcher, 'https://api.example.com/v1/memories/m1', {
    method: 'PUT',
    headers: { Authorization: 'Bearer t', 'Idempotency-Key': 'k1' },
    body: '{"a":1}',
    timeout: 1234,
  });
  assert.equal(seen.url, 'https://api.example.com/v1/memories/m1');
  assert.equal(seen.init.method, 'PUT');
  assert.equal(seen.init.redirect, 'error');
  assert.equal(seen.init.headers.Authorization, 'Bearer t');
  assert.equal(seen.init.headers['Idempotency-Key'], 'k1');
  assert.equal(seen.init.body, '{"a":1}');
  assert.equal(typeof seen.init.signal?.addEventListener, 'function', '每个调用都带超时信号');
});

test('joinUrl：拼路径时不会出现两个斜杠', () => {
  assert.equal(joinUrl(safeBase('https://api.example.com/v1'), '/skills'), 'https://api.example.com/v1/skills');
  assert.equal(joinUrl(safeBase('http://127.0.0.1:8765/'), '/skills'), 'http://127.0.0.1:8765/skills');
});

test('四个上游都从这一个模块取零件（不再各写一份）', async () => {
  const modules = [
    '../../server/elfred/memory-hub.mjs',
    '../../server/elfred/skill-forge/index.mjs',
    '../../server/elfred/pa-gateway/index.mjs',
    '../../server/elfred/dependency-health.mjs',
  ];
  for (const specifier of modules) {
    const source = await import('node:fs').then((fs) => fs.readFileSync(new URL(specifier, import.meta.url), 'utf8'));
    assert.match(source, /from '\.\.?\/upstream\.mjs'|from '\.\.\/upstream\.mjs'/, `${specifier} 应当 import 公共零件`);
    assert.doesNotMatch(source, /^function safeBase/m, `${specifier} 不该再自带一份 safeBase`);
  }
});
