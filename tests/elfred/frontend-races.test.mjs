import * as memoryPolicy from '../../app/v28/core/memory-policy.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import ts from 'typescript';
import {finalReceipts} from '../../app/v28/core/result-output.ts';
import {entityTitle,displayError} from '../../app/v28/core/display-labels.ts';
import {createClientId} from '../../app/v28/core/client-id.ts';

const response = value => ({ ok: true, status: 200, json: async () => value });
const deferred = () => {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
};
const flush = () => new Promise(setImmediate);

// Execute the actual TS hooks with persistent state/ref slots and controlled
// fetch promises. Effects are disabled so polling timers cannot hide the race.
// These tests cover async state transitions, not browser rendering or React QA.
function hookHarness(filename, imports = {}, fetcher = async () => { throw new Error('Unexpected fetch'); }) {
  const slots = [];
  let cursor = 0;
  const react = {
    createContext: () => ({ Provider: 'Provider' }),
    useContext: () => null,
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = typeof initial === 'function' ? initial() : initial;
      return [slots[index], value => {
        slots[index] = typeof value === 'function' ? value(slots[index]) : value;
      }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = { current: initial };
      return slots[index];
    },
    useCallback: callback => callback,
    useEffect: () => {},
  };
  const modules = {
    react,
    'react/jsx-runtime': { jsx: (type, props) => ({ type, props }) },
    '../../v27-7-state': {},
    './result-output': {finalReceipts},
    './client-id': {createClientId},
    './display-labels': {entityTitle,displayError},
    '../features/live/types': { text: (entity, key) => entity?.data?.[key] || '' },
    './memory-policy.mjs':memoryPolicy,
    ...imports,
  };
  const code = ts.transpileModule(readFileSync(new URL(filename, import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const loadedModule = { exports: {} };
  new Function('require', 'module', 'exports', 'fetch', 'crypto', code)(name => {
    assert.ok(Object.hasOwn(modules, name), `Unexpected import: ${name}`);
    return modules[name];
  }, loadedModule, loadedModule.exports, fetcher, { randomUUID });
  return {
    render(name, ...args) {
      cursor = 0;
      return loadedModule.exports[name](...args);
    },
  };
}

function runtimeHarness(fetcher) {
  const harness = hookHarness('../../app/v28/core/runtime-context.tsx', {}, fetcher);
  return () => harness.render('RuntimeProvider', { children: null }).props.value;
}

test('同步失败保留最后确认快照，恢复后更新时间，局部协作不作最终成果',async()=>{
 let offline=false;
 const runtime=runtimeHarness(async url=>{if(offline)throw new Error('offline');return response(url.endsWith('/session')?{user:{id:'alice'},csrf:'csrf'}:{user:{id:'alice'},server_time:'2026-09-23T08:00:00Z'});});
 await runtime().refresh();offline=true;await assert.rejects(runtime().refresh());assert.equal(runtime().syncStatus,'stale');assert.equal(runtime().lastSynced,'2026-09-23T08:00:00Z');assert.equal(runtime().snapshot.user.id,'alice');offline=false;await runtime().refresh();assert.equal(runtime().syncStatus,'current');
 assert.deepEqual(finalReceipts([{phase:'collaboration',output:'只有局部建议'}]),[]);
});

test('退出前和退出期间的迟到刷新都不能恢复旧账号快照', async () => {
  const bootstraps = [];
  const logoutResponse = deferred();
  const runtime = runtimeHarness(async url => {
    if (url.endsWith('/session')) return response({ user: { id: 'alice' }, csrf: 'alice-token' });
    if (url.endsWith('/bootstrap')) {
      const pending = deferred();
      bootstraps.push(pending);
      return pending.promise;
    }
    if (url.endsWith('/auth/logout')) return logoutResponse.promise;
    throw new Error(`Unexpected URL: ${url}`);
  });
  const beforeLogout = runtime().refresh();
  await flush();
  const logout = runtime().logout();
  const duringLogout = runtime().refresh();
  await flush();
  assert.equal(bootstraps.length, 2);
  logoutResponse.resolve(response({}));
  await logout;
  assert.equal(runtime().snapshot, null);
  for (const pending of bootstraps) pending.resolve(response({ user: { id: 'alice' }, private_content: 'ALICE SECRET' }));
  await Promise.all([beforeLogout, duringLogout]);
  assert.equal(runtime().snapshot, null);
});

test('乱序刷新只保留最新快照及对应CSRF令牌', async () => {
  const bootstraps = [];
  let sessions = 0;
  let sentToken;
  const runtime = runtimeHarness(async (url, options) => {
    if (url.endsWith('/session')) return response({ user: { id: 'alice' }, csrf: `token-${++sessions}` });
    if (url.endsWith('/bootstrap')) {
      const pending = deferred();
      bootstraps.push(pending);
      return pending.promise;
    }
    if (url.endsWith('/probe')) {
      sentToken = options.headers['X-CSRF-Token'];
      return response({});
    }
    throw new Error(`Unexpected URL: ${url}`);
  });
  const older = runtime().refresh();
  await flush();
  const newer = runtime().refresh();
  await flush();
  const current = { user: { id: 'alice' }, objects: { message: [] } };
  bootstraps[1].resolve(response(current));
  await newer;
  bootstraps[0].resolve(response({ user: { id: 'alice' }, objects: { message: ['REVOKED SECRET'] } }));
  await older;
  assert.deepEqual(runtime().snapshot, current);
  await runtime().request('/probe', {});
  assert.equal(sentToken, 'token-2');
});

test('草稿回填刷新采用同一次读取的正文和版本，不覆盖其他页面的新正文', async () => {
  let remote = { id: 'draft-id', version: 2, data: { conversation_id: 'room', text: '原稿' } };
  let writes = 0;
  const service = {
    snapshot: { objects: { draft: [structuredClone(remote)] } },
    request: async () => structuredClone(remote),
    command: async (_action, input) => {
      assert.equal(input.version, remote.version);
      writes++;
      remote = { ...remote, version: remote.version + 1, data: { ...remote.data, text: input.text } };
      return { id: remote.id, version: remote.version };
    },
  };
  const harness = hookHarness('../../app/v28/core/use-conversation-draft.ts', {
    './runtime-context': { useRuntime: () => service },
  });
  const draft = harness.render('useConversationDraft', 'room', true);
  // The fill caller obtained version 3; another page saved version 4 before reload.
  remote = { ...remote, version: 4, data: { ...remote.data, text: '另一页面刚保存的新正文' } };
  await draft.reload('版本3的辅助回填正文');
  assert.equal(harness.render('useConversationDraft', 'room', true).text, remote.data.text);
  await draft.save();
  assert.equal(writes, 0);
  assert.equal(remote.version, 4);
  assert.equal(remote.data.text, '另一页面刚保存的新正文');
});

test('业务提交成功但刷新失败仍返回成功，调用方不会重试已提交操作', async () => {
  let commands = 0;
  let refreshFails = true;
  const runtime = runtimeHarness(async (url, options) => {
    if (url.endsWith('/commands')) {
      commands++;
      assert.ok(options.headers['Idempotency-Key']);
      return response({ id: 'committed-message' });
    }
    if (url.endsWith('/session')) return response({ user: { id: 'alice' }, csrf: 'token' });
    if (url.endsWith('/bootstrap')) {
      if (refreshFails) throw new Error('Bootstrap connection interrupted');
      return response({ user: { id: 'alice' }, objects: { message: [{ id: 'committed-message' }] } });
    }
    throw new Error(`Unexpected URL: ${url}`);
  });
  const input = { id: 'room', text: '只发送一次' };
  let callerRetries = 0;
  const result = await runtime().command('message.send', input).catch(() => {
    callerRetries++;
    return runtime().command('message.send', input);
  });
  assert.deepEqual(result, { id: 'committed-message' });
  assert.equal(callerRetries, 0);
  assert.equal(commands, 1);
  assert.match(runtime().error, /操作已保存.*同步失败/);
  refreshFails = false;
  await runtime().refresh();
  assert.equal(runtime().snapshot.objects.message[0].id, result.id);
  assert.equal(commands, 1);
});
