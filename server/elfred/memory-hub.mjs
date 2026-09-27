import {now,hash} from './store.mjs';
import {memoryUsable,projectMemory,memoryEvidenceActive} from './memory-validity.mjs';

// Versioned adapter contract, deliberately separate from any guessed EmoS API.
// A future EmoS bridge implements these endpoints; keys are server-only.
export function queueMemorySync(store,memory){
  const usable=memoryUsable(store,memory);
  const projected=projectMemory(store,memory);
  const stateHash=hash(JSON.stringify({version:memory.version,usable,alignment:projected.data.alignment,domain_alignment:projected.data.domain_alignment,evidence:(memory.data.evidence||[]).filter(e=>memoryEvidenceActive(store,memory,e))}));
  const latest=store.list('memory_bridge').filter(e=>e.data.memory_id===memory.id).sort((a,b)=>(b.data.intent_sequence||0)-(a.data.intent_sequence||0))[0];
  if(latest?.data.state_hash===stateHash)return latest;
  const sequence=(latest?.data.intent_sequence||0)+1;
  return store.unique('memory_bridge',`${memory.id}:${memory.version}:${stateHash}:${sequence}`,()=>store.add('memory_bridge',memory.owner,{memory_id:memory.id,revision:memory.version,usable,state_hash:stateHash,intent_sequence:sequence,status:'pending',attempts:0,next_at:0}));
}
export function memoryHubStatus(store,user,config=process.env){
  const events=store.list('memory_bridge').filter(e=>e.owner===user);
  return {configured:Boolean(config.ELFRED_MEMORY_HUB_URL&&config.ELFRED_MEMORY_HUB_TOKEN),mode:config.ELFRED_MEMORY_HUB_URL?'adapter':'local',pending:events.filter(e=>e.data.status==='pending').length,last_synced_at:events.find(e=>e.data.status==='synced')?.data.synced_at||null,contract:'elfred-memory-v1'};
}
export async function syncMemoryHub(store,config=process.env,fetcher=fetch){
  if(!config.ELFRED_MEMORY_HUB_URL||!config.ELFRED_MEMORY_HUB_TOKEN)return;
  const base=new URL(config.ELFRED_MEMORY_HUB_URL);
  if((base.protocol!=='https:'&&!(base.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(base.hostname)))||base.username||base.password||base.search||base.hash)return;
  for(const memory of store.list('memory'))queueMemorySync(store,memory);
  const event=store.list('memory_bridge').filter(e=>e.data.status==='pending'&&e.data.next_at<=Date.now()).sort((a,b)=>a.created.localeCompare(b.created))[0];
  if(!event)return;
  const memory=store.get(event.data.memory_id);
  if(!memory||memory.version!==event.data.revision){store.update(event,{...event.data,status:'superseded'},event.owner);return;}
  if(queueMemorySync(store,memory).id!==event.id){store.update(event,{...event.data,status:'superseded'},event.owner);return;}
  const usable=memoryUsable(store,memory);
  if(usable!==event.data.usable){store.update(event,{...event.data,status:'superseded'},event.owner);return;}
  const projected=projectMemory(store,memory);
  const payload=usable?{contract:'elfred-memory-v1',owner:memory.owner,id:memory.id,revision:memory.version,content:memory.data.content,scope:memory.data.scope,group:memory.data.group,kind:memory.data.kind||'user_understanding',risk:memory.data.risk,status:memory.data.status,learning_mode:memory.data.learning_mode||'owner_confirmed',allocation:memory.data.allocation||{holder:memory.data.scope,allowed_systems:[],contextual:true},professional_scope:memory.data.professional_scope||null,source_refs:memory.data.source_refs,alignment:projected.data.alignment,domain_alignment:projected.data.domain_alignment,evidence:(memory.data.evidence||[]).filter(e=>memoryEvidenceActive(store,memory,e)),expires_at:memory.data.expires_at||null,supersedes_id:memory.data.supersedes_id||null}:{contract:'elfred-memory-v1',owner:memory.owner,id:memory.id,revision:memory.version,action:'forget'};
  try{
    payload.state_hash=event.data.state_hash;
    const response=await fetcher(base.href.replace(/\/$/,'')+'/v1/memories/'+encodeURIComponent(memory.id),{method:usable?'PUT':'DELETE',redirect:'error',headers:{'Content-Type':'application/json',Authorization:`Bearer ${config.ELFRED_MEMORY_HUB_TOKEN}`,'Idempotency-Key':`${memory.id}:${memory.version}:${event.data.state_hash}:${event.data.intent_sequence}`},body:JSON.stringify(payload),signal:AbortSignal.timeout(4000)});
    if(!response.ok)throw new Error();
    const raw=await response.text();if(raw.length>4096)throw new Error();
    const receipt=JSON.parse(raw);
    if(receipt.id!==memory.id||receipt.revision!==memory.version||receipt.owner!==memory.owner||receipt.state_hash!==event.data.state_hash)throw new Error();
    store.update(event,{...event.data,status:'synced',synced_at:now()},event.owner);
  }catch{store.update(event,{...event.data,attempts:event.data.attempts+1,next_at:Date.now()+Math.min(3600000,30000*2**Math.min(event.data.attempts,7)),reason:'记忆中枢同步失败，保留本地记录等待重试'},event.owner);}
}
