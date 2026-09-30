import test from 'node:test';
import assert from 'node:assert/strict';
import {agentGrowth} from '../../app/v28/core/agent-growth.mjs';

const snapshot = (accepted=0, system='explore') => ({objects:{
  onboarding:[{data:{choice_confirmed_at:'2026-09-30T00:00:00Z'}}],
  task:Array.from({length:accepted},(_,i)=>({id:`t${i}`,data:{system,title:`真实任务 ${i+1}`}})),
  outcome:Array.from({length:accepted},(_,i)=>({created:`2026-09-${String(i+1).padStart(2,'0')}T00:00:00Z`,data:{task_id:`t${i}`,verdict:'accepted'}})),
  memory:[],
}});

test('five agents grow independently from their own accepted outcomes',()=>{
  const state=snapshot(3);
  assert.equal(agentGrowth(state,'explore').level>=3,true);
  assert.equal(agentGrowth(state,'create').level,2);
  assert.equal(agentGrowth(snapshot(1),'explore').level,3);
});

test('unverified statements cannot unlock the L6 evidence milestone',()=>{
  const state=snapshot(0);
  state.objects.memory=Array.from({length:40},(_,i)=>({id:`m${i}`,data:{scope:'explore',status:'learned',alignment:'scenario_verified'}}));
  assert.equal(agentGrowth(state,'explore').level<=5,true);
  assert.match(agentGrowth(state,'explore').nextCondition,/真实成果/);
});
