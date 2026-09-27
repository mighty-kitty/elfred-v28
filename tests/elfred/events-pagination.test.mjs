import test from 'node:test';
import assert from 'node:assert/strict';
import {Store,id} from '../../server/elfred/store.mjs';
import {Service} from '../../server/elfred/service.mjs';

test('事件跨过大量不可读记录后仍按序分页，重复读取不会失去 SQLite 语句',()=>{
  const store=new Store(':memory:'),service=new Service(store,{}),alice=id(),bob=id();
  try{
    for(const user of [alice,bob])store.db.prepare('INSERT INTO users VALUES(?,?,?,?,?)').run(user,user,'unused',user,new Date().toISOString());
    store.transaction(()=>{
      for(let i=0;i<650;i++)store.add('knowledge',bob,{title:'别人的私有资讯'});
      for(let i=0;i<340;i++)store.add('knowledge',alice,{title:'我的资讯 '+i});
    });
    const first=service.events(alice,0);assert.equal(first.length,300);
    const rest=service.events(alice,first.at(-1).seq);assert.equal(rest.length,40);
    const all=[...first,...rest];assert.equal(new Set(all.map(e=>e.object_id)).size,340);
    assert.ok(all.every(e=>e.actor===alice));assert.ok(all.every((e,i)=>i===0||e.seq>all[i-1].seq));
    for(let i=0;i<20;i++)assert.deepEqual(service.events(alice,0),first);
    assert.deepEqual(service.events(alice,rest.at(-1).seq),[]);
  }finally{store.close()}
});
