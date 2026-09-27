import {spawn} from 'node:child_process';
import path from 'node:path';

export async function startEmos(root,data,config=process.env){
  if(config.ELFRED_MEMORY_HUB_AUTOSTART!=='true')return null;
  const base=new URL(config.ELFRED_MEMORY_HUB_URL||'');
  if(base.protocol!=='http:'||base.hostname!=='127.0.0.1'||!base.port||base.pathname!=='/'||base.search||base.hash||base.username||base.password||!config.ELFRED_MEMORY_HUB_TOKEN)throw new Error('EMOS 自动启动需使用带端口的本机服务地址和服务端令牌');
  const check=async()=>{try{const response=await fetch(base.href+'v1/status',{headers:{Authorization:'Bearer '+config.ELFRED_MEMORY_HUB_TOKEN},signal:AbortSignal.timeout(500)});const result=await response.json();return response.ok&&result.contract==='elfred-memory-v1';}catch{return false;}};
  if(await check())return null;
  const child=spawn(config.ELFRED_PYTHON||'python',['-m','src.memory_system.api.elfred_bridge'],{cwd:path.join(root,'services/emos-memory'),env:{...config,ELFRED_EMOS_DATABASE:path.join(data,'emos-memory.sqlite'),ELFRED_EMOS_PORT:base.port},windowsHide:true,stdio:'ignore'});
  let error=false;child.on('error',()=>{error=true;});
  for(let i=0;i<30;i++){if(error||child.exitCode!==null)break;if(await check())return child;await new Promise(resolve=>setTimeout(resolve,200));}
  child.kill();throw new Error('EMOS 启动失败：请检查 Python 版本、端口和数据库权限');
}
