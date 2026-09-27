// Only a service health check crosses this boundary. Private memories are never
// forwarded to an unshipped backend with a client-selected identity header.
export async function dependencyHealth(store,provider,user,config=process.env,fetcher=fetch){
 const memories=store.visible(user,'memory');store.db.prepare('SELECT 1').get();
 const result={allGreen:false,memory:{ok:true,count:memories.length,reason:'应用记忆库已连接'},
  emos:{ok:false,reason:'尚未配置独立记忆服务',impact:'当前记忆保存在应用数据库，未同步到 EmoS'},
  skill_foundry:{ok:false,reason:'尚未配置独立能力服务',impact:'当前使用应用内已保存的工具与专业能力'},
  gateway:{ok:true,reason:'当前登录会话已连接',impact:''},
  jev:{configured:provider.status().jev==='configured',baseUrl:'',model:'',hint:'以真实服务端配置为准'}};
 if(!config.ELFRED_PAGE2_API_URL)return result;
 try{
  const base=new URL(config.ELFRED_PAGE2_API_URL);
  if(base.username||base.password||base.search||base.hash||(base.protocol!=='https:'&&!(base.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(base.hostname))))throw new Error();
  const response=await fetcher(base.href.replace(/\/$/,'')+'/health/deps',{redirect:'error',signal:AbortSignal.timeout(4000),headers:config.ELFRED_PAGE2_API_TOKEN?{Authorization:`Bearer ${config.ELFRED_PAGE2_API_TOKEN}`}:{}});
  if(!response.ok)throw new Error();const raw=await response.text();if(raw.length>100000)throw new Error();const health=JSON.parse(raw);
  if(!health.emos||typeof health.emos.ok!=='boolean')throw new Error();
  result.emos={ok:health.emos.ok,reason:health.emos.ok?'独立记忆服务可达':'独立记忆服务不可用',impact:'服务连通性已检测；当前应用记忆仍在本地，跨服务同步尚未配置'};
  if(typeof health.skill_foundry?.ok==='boolean')result.skill_foundry={ok:health.skill_foundry.ok,reason:health.skill_foundry.ok?'独立能力服务可达':'独立能力服务不可用',impact:'当前仍使用应用内能力'};
 }catch{result.emos={ok:false,reason:'独立服务连接失败或接口不匹配',impact:'应用内记忆仍可使用，未同步到 EmoS'};}
 result.allGreen=result.emos.ok&&result.skill_foundry.ok&&result.gateway.ok;return result;
}
