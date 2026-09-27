import { createServer } from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {writeFileSync,readFileSync,existsSync,unlinkSync} from 'node:fs';
import next from 'next';
import { Store } from '../server/elfred/store.mjs';
import { ModelProvider } from '../server/elfred/providers.mjs';
import { Service } from '../server/elfred/service.mjs';
import { Runtime } from '../server/elfred/runtime.mjs';
import { apiHandler } from '../server/elfred/http.mjs';
import {serverConfig} from '../server/elfred/server-config.mjs';
import {startEmos} from './emos-process.mjs';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {port,localOrigin:origin,publicOrigin}=serverConfig();
const data=path.resolve(process.env.ELFRED_DATA_DIR||path.join(root,'.elfred-data'));
const store=new Store(path.join(data,'elfred.sqlite'));
const emosProcess=await startEmos(root,data);
const provider=new ModelProvider();
const service=new Service(store,provider);
const runtime=new Runtime(store,provider);
const handler=apiHandler(service,{origin:publicOrigin});
const app=next({dev:!process.argv.includes('--production'),dir:root,hostname:'127.0.0.1',port});
await app.prepare();
const nextHandler=app.getRequestHandler();
const server=createServer(async(req,res)=>{
  if(process.argv.includes('--production') && req.url==='/') {
    res.writeHead(302,{Location:'/v28','Cache-Control':'no-store'});res.end();return;
  }
  if(!await handler(req,res)) await nextHandler(req,res);
});
server.requestTimeout=60000;
const pidFile=path.join(data,'server.pid');
server.listen(port,'127.0.0.1',()=>{writeFileSync(pidFile,String(process.pid));runtime.start();console.log(`Elfred 本地运行：${origin}/v28\n数据目录：${data}\n模型：${provider.status().configured?'已配置，等待实际调用验证':'未配置；本地任务、知识、消息与共创仍可使用'}`);});
let stopping=false;
async function shutdown(){if(stopping)return;stopping=true;server.close();await runtime.stop();await app.close();store.close();emosProcess?.kill();if(existsSync(pidFile)&&readFileSync(pidFile,'utf8')===String(process.pid))unlinkSync(pidFile);process.exit(0);}
process.on('SIGINT',shutdown);process.on('SIGTERM',shutdown);
