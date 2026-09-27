import {semanticPreview,semanticResults} from './semantic-search.mjs';
import {searchJudgment} from './search-commands.mjs';
import { authenticate, session } from './auth.mjs';
import {parseFile} from './file-parser.mjs';
import {PREVIEW_CSP,validateWebArtifact,renderWebArtifact} from './preview.mjs';
import { DomainError, fail, hash } from './store.mjs';
import {playerLogs} from './player-logs.mjs';
import {dependencyHealth} from './dependency-health.mjs';
import {recallMemories} from './memory-learning.mjs';
import {memoryHubStatus} from './memory-hub.mjs';
import {memorySystems} from '../../app/v28/core/memory-policy.mjs';

async function readBody(request) {
  if(!String(request.headers['content-type']||'').startsWith('application/json')) fail('CONTENT_TYPE','仅支持 JSON 请求',415);
  let size=0;const chunks=[];
  for await(const chunk of request) {size+=chunk.length;if(size>12000000) fail('BODY_TOO_LARGE','请求内容过大',413);chunks.push(chunk);}
  try {const value=JSON.parse(Buffer.concat(chunks).toString('utf8'));if(!value||typeof value!=='object'||Array.isArray(value)) throw new Error();return value;}catch {fail('INVALID_JSON','请求格式不正确');}
}
export function apiHandler(service,{origin='http://127.0.0.1:3000'}={}) {
  const s=service.store;
  return async(request,response)=>{
    const url=new URL(request.url,origin);
    if(!url.pathname.startsWith('/api/elfred')) return false;
    const headers={'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'};
    const send=(status,data,extra={})=>{response.writeHead(status,{...headers,...extra});response.end(JSON.stringify(data));};
    try {
      if(request.headers.host!==new URL(origin).host) fail('INVALID_HOST','无效主机',403);
      const method=request.method,route=url.pathname.slice('/api/elfred'.length)||'/';
      const token=String(request.headers.cookie||'').split(';').map(part=>part.trim()).find(part=>part.startsWith('elfred_session='))?.slice(15);
      const user=session(s,token);
      if(method!=='GET') {
        if(request.headers.origin!==origin || request.headers['x-elfred-client']!=='1') fail('CSRF_REJECTED','请从当前应用发起操作',403);
        if(!['/auth/login','/auth/register'].includes(route) && (!user||request.headers['x-csrf-token']!==hash(token+':csrf'))) fail('CSRF_REJECTED','会话已变化，请刷新后重试',403);
      }
      if(method==='GET' && route==='/health') {send(200,{status:'ok',storage:'sqlite',mode:'local'});return true;}
      if(method==='GET' && route==='/session') {send(200,{user:user||null,csrf:user?hash(token+':csrf'):null});return true;}
      if(method==='POST' && ['/auth/login','/auth/register'].includes(route)) {
        const input=await readBody(request);
        const key=hash('ip:'+request.socket.remoteAddress),time=Date.now();
        const limit=s.db.prepare('SELECT * FROM login_attempts WHERE key=?').get(key);
        if(limit && limit.until>time && limit.count>=50) fail('RATE_LIMIT','登录请求过多，请稍后再试',429);
        s.db.prepare('INSERT INTO login_attempts VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=CASE WHEN until<? THEN 1 ELSE count+1 END,until=CASE WHEN until<? THEN excluded.until ELSE until END').run(key,time+900000,time,time);
        const result=authenticate(s,input.handle,input.password,route==='/auth/register',input.name,request.socket.remoteAddress);
        service.initialize(result.user);
        send(200,{user:result.user,csrf:hash(result.token+':csrf')},{'Set-Cookie':`elfred_session=${result.token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=604800${origin.startsWith('https:')?'; Secure':''}`});return true;
      }
      if(method==='GET' && route.startsWith('/profiles/')) {send(200,service.publicProfile(decodeURIComponent(route.slice(10))));return true;}
      if(!user) fail('UNAUTHENTICATED','请先登录',401);
      if(method==='POST' && route==='/auth/logout') {s.db.prepare('DELETE FROM sessions WHERE token=?').run(hash(token));send(200,{ok:true},{'Set-Cookie':'elfred_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0'});return true;}
      if(method==='GET'&&route.startsWith('/preview/')){
        const object=s.read(user.id,route.slice(9));
        if(!['copy','release','skill_version','contribution'].includes(object.type))fail('NOT_FOUND','预览不存在',404);
        const html=object.type==='skill_version'?object.data.html:object.data.format==='web'?object.data.content:null;
        validateWebArtifact(html,object.data.files||{});
        response.writeHead(200,{...headers,'Content-Type':'text/html; charset=utf-8','Content-Security-Policy':PREVIEW_CSP,'X-Frame-Options':'SAMEORIGIN'});response.end(renderWebArtifact(html,object.data.files||{}));return true;
      }
      if(method==='GET'&&route.startsWith('/attachments/')){
        const object=s.read(user.id,route.slice(13),'attachment'),inline=/^(image|audio|video)\//.test(object.data.mime);
        response.writeHead(200,{...headers,'Content-Type':object.data.mime,'Content-Security-Policy':"default-src 'none'; sandbox",'Content-Disposition':`${inline?'inline':'attachment'}; filename*=UTF-8''${encodeURIComponent(object.data.name)}`});response.end(Buffer.from(object.data.base64,'base64'));return true;
      }
      if(method==='GET'&&/^\/conversations\/[^/]+\/messages$/.test(route)){
        const conversation=s.read(user.id,route.split('/')[2],'conversation'),before=Number(url.searchParams.get('before')||Number.MAX_SAFE_INTEGER),limit=Number(url.searchParams.get('limit')||50),query=(url.searchParams.get('query')||'').slice(0,300).toLocaleLowerCase();
        if(!Number.isSafeInteger(before)||before<1||!Number.isInteger(limit)||limit<1||limit>100)fail('INVALID_CURSOR','消息分页参数不正确');
        const all=s.visible(user.id,'message').filter(item=>item.space===conversation.id&&item.data.seq<before&&(!query||item.data.text.toLocaleLowerCase().includes(query))).sort((a,b)=>b.data.seq-a.data.seq),items=all.slice(0,limit);
        send(200,{items:items.reverse(),has_more:all.length>limit,next_before:items.length?Math.min(...items.map(item=>item.data.seq)):null});return true;
      }
      if(method==='GET' && route==='/bootstrap') {send(200,service.bootstrap(user.id));return true;}
      if(method==='GET'&&route==='/memory/hub'){send(200,memoryHubStatus(s,user.id,service.provider.config||process.env));return true;}
      if(method==='GET'&&route==='/memory/recall'){
        const scope=url.searchParams.get('scope'),query=url.searchParams.get('q')||'';
        if(!memorySystems.includes(scope)||query.length>1000)fail('INVALID_INPUT','请选择理解领域，并缩短检索描述');
        send(200,{scope,items:recallMemories(s,user.id,scope,query).map(m=>({id:m.id,revision:m.version,content:m.data.content,scope:m.data.scope,usage_purpose:m.data.usage_purpose,source_refs:m.data.source_refs,alignment:m.data.alignment})),status:'local-authorized-cache'});return true;
      }
      if(method==='GET'&&route==='/models'){send(200,await service.provider.models());return true;}
      if(method==='GET'&&route==='/health/deps'){send(200,await dependencyHealth(s,service.provider,user.id));return true;}
      if(method==='GET'&&/^\/runs\/[^/]+\/logs$/.test(route)){send(200,playerLogs(s,user.id,route.split('/')[2]));return true;}
      if(method==='GET' && route==='/objects') {send(200,service.list(user.id,url.searchParams.get('type')));return true;}
      if(method==='GET' && route.startsWith('/objects/')) {send(200,service.read(user.id,route.slice(9)));return true;}
      if(method==='POST' && route==='/commands') {
        const {action,input}=await readBody(request);
        if(typeof action!=='string'||!input||typeof input!=='object'||Array.isArray(input)) fail('INVALID_INPUT','缺少业务操作参数');
        send(200,service.command(user.id,request.headers['idempotency-key'],action,input));return true;
      }
      if(method==='POST'&&route==='/attachment-parse'){
        const input=await readBody(request),file=s.read(user.id,input.id,'attachment');
        const existing=s.visible(user.id,'document').find(item=>item.data.attachment_id===file.id);
        if(existing){send(200,{id:existing.id});return true;}
        const content=await parseFile(file);s.read(user.id,file.id,'attachment');
        if(!content?.trim()||content.includes('\ufffd')||content.includes('\u0000'))fail('PARSE_EMPTY','未提取到有效文字；扫描件请使用图片识别');
        const doc=s.transaction(()=>s.unique('parsed_attachment',`${user.id}:${file.id}`,()=>s.add('document',user.id,{title:file.data.name,content,status:'ready',parser:'local-office-pdf-text-v1',attachment_id:file.id,source_refs:[{id:file.id,version:file.version}],content_hash:hash(content),line_count:content.split('\n').length})));
        send(200,{id:doc.id});return true;
      }
      if(method==='POST'&&route==='/search-input'){
        const input=await readBody(request),file=s.read(user.id,input.id,'attachment');
        const content=await parseFile(file);s.read(user.id,file.id,'attachment');
        if(!content?.trim())fail('PARSE_EMPTY','未提取到文字，请改用图片识别或手动输入');
        send(200,{text:content.slice(0,input.preview===true?500000:12000),stored_as_knowledge:false});return true;
      }
      if(method==='POST'&&route==='/search-scope'){send(200,semanticPreview(s,user.id,await readBody(request)));return true;}
      if(method==='POST'&&route==='/search-semantic'){send(200,semanticResults(s,user.id,await readBody(request)));return true;}
      if(method==='POST'&&route==='/search-judgment'){send(200,searchJudgment(s,user.id,await readBody(request)));return true;}
      if(method==='POST' && route==='/search') {send(200,service.search(user.id,await readBody(request)));return true;}
      if(method==='GET' && route==='/events') {
        const after=Number(request.headers['last-event-id']||url.searchParams.get('after')||0);
        if(!Number.isSafeInteger(after)||after<0) fail('INVALID_CURSOR','事件游标不正确');
        const events=service.events(user.id,after);
        if(String(request.headers.accept).includes('text/event-stream')) {
          response.writeHead(200,{...headers,'Content-Type':'text/event-stream','Connection':'keep-alive'});
          let cursor=after;response.write('retry: 3000\n\n');
          const flush=()=>{if(!session(s,token)){response.end();return;}const batch=service.events(user.id,cursor);for(const event of batch){cursor=event.seq;response.write(`id: ${event.seq}\nevent: changed\ndata: ${JSON.stringify({id:event.object_id,kind:event.kind})}\n\n`);}if(batch.length<300)cursor=Number(s.db.prepare('SELECT COALESCE(MAX(seq),0) AS seq FROM events').get().seq);response.write(`id: ${cursor}\n: heartbeat\n\n`);};
          flush();const interval=setInterval(()=>{try{flush()}catch{response.end()}},2500);interval.unref();response.on('close',()=>clearInterval(interval));
        } else send(200,{events});
        return true;
      }
      if(method==='GET' && route==='/export') {send(200,service.export(user.id),{'Content-Disposition':'attachment; filename="elfred-export.json"'});return true;}
      fail('NOT_FOUND','接口不存在',404);
    } catch(error) {
      // A failed or disconnected event stream cannot be changed into a JSON response.
      if(response.headersSent){response.end();return true;}
      send(error instanceof DomainError?error.status:500,{error:{code:error instanceof DomainError?error.code:'INTERNAL_ERROR',message:error instanceof DomainError?error.message:'内部错误，操作未完成'}});
      return true;
    }
  };
}
