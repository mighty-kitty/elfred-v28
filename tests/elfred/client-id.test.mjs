import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {createClientId} from '../../app/v28/core/client-id.ts';

test('HTTP 浏览器只有 getRandomValues 时也能生成唯一 RFC UUID 操作编号',()=>{
  const source={getRandomValues:array=>webcrypto.getRandomValues(array)};
  const ids=Array.from({length:1000},()=>createClientId(source));
  assert.equal(new Set(ids).size,1000);
  assert.ok(ids.every(id=>/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(id)));
});
test('HTTPS 使用原生 UUID，没有安全随机数能力时明确失败',()=>{
  assert.equal(createClientId({randomUUID:()=> 'native-uuid'}),'native-uuid');
  assert.throws(()=>createClientId({}),/更新浏览器/);
});
