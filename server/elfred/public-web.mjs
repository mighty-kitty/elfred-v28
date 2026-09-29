import https from 'node:https';
import {lookup} from 'node:dns/promises';
import {readRss,validatedFeedUrl,publicIPv4} from './rss.mjs';
import {fail,now} from './store.mjs';

// Public, read-only tools. Never forward a transcript, memory or API credential.
export function publicQuery(value){
  if(typeof value!=='string'||!value.trim()||value.trim().length>300)fail('INVALID_WEB_QUERY','联网关键词需为 1—300 字，请缩短问题');
  if(/(?:sk-[\w-]{12,}|Bearer\s+\S+|(?:密码|口令|api\s*key|token)\s*[:：=]\s*\S+|[\w.+-]+@[\w.-]+\.[a-z]{2,}|\b1[3-9]\d{9}\b)/i.test(value))fail('PRIVATE_WEB_QUERY','联网关键词中含账号或凭据，请移除后再搜索');
  return value.trim();
}
export function webIntent(text,mode='auto'){
  if(!['auto','off','web'].includes(mode))fail('INVALID_INPUT','不支持的联网方式');
  // "不联网 / 不搜索"也算关掉。原来只认"不要/别/无需/不用/不能"这几种写法，
  // 于是"资料不够就写未知，不联网补充"这种句子会被当成"这一轮要联网"，整段消息还被当成关键词。
  if(mode==='off'||/(?:不要|别|无需|不用|不必|不能|不)\s*(?:联网|上网|搜索|搜)/.test(text))return null;
  const url=text.match(/https:\/\/[^\s<>"）)]+/i)?.[0];
  if(url&&(mode==='web'||/阅读|读一下|打开|看看|总结|查阅|网页|链接/.test(text))){const parsed=new URL(validatedFeedUrl(url));if(parsed.search)fail('PRIVATE_WEB_QUERY','读取网页请使用不含查询参数的公开链接');return {tool:'web.read',query:parsed.href};}
  if(mode==='web'||/联网|上网查|网上(?:查|搜)|搜索|搜一下|搜一搜|查(?:一下|找).*(?:最新|官网|新闻)|最新.*(?:资讯|新闻|价格|版本)/.test(text)){
    // 一条长消息（例如对话里带着一整份工具说明书）不该整段当联网关键词：
    // 自动模式下降级成普通对话，只有用户自己按了"本轮联网"才要求他缩短。
    if(mode!=='web'&&String(text).trim().length>300)return null;
    return {tool:'web.search',query:publicQuery(text)};
  }
  return null;
}
const decode=s=>s.replace(/&#(x[\da-f]+|\d+);/gi,(_,v)=>{const n=v[0].toLowerCase()==='x'?parseInt(v.slice(1),16):Number(v);return n>0&&n<=0x10ffff?String.fromCodePoint(n):'';}).replace(/&(amp|lt|gt|quot|apos|nbsp);/gi,(_,v)=>({amp:'&',lt:'<',gt:'>',quot:'"',apos:"'",nbsp:' '}[v.toLowerCase()]));
export function pageText(html){return decode(html.replace(/<(script|style|noscript|nav|footer)\b[^>]*>[\s\S]*?<\/\1>/gi,' ').replace(/<[^>]*>/g,' ')).replace(/\s+/g,' ').trim().slice(0,10000);}
export async function readPublicPage(value,{signal,redirects=0,resolver=lookup,requester=https.request}={}){
  const url=new URL(validatedFeedUrl(value));
  const records=await resolver(url.hostname,{family:4,all:true}),address=records.find(r=>publicIPv4(r.address))?.address;
  if(!address)fail('WEB_UNAVAILABLE','网页没有可用的公开地址');
  const result=await new Promise((resolve,reject)=>{
    const request=requester(url,{method:'GET',signal,timeout:10000,autoSelectFamily:false,headers:{Accept:'text/html, text/plain, application/xhtml+xml','Accept-Encoding':'identity','User-Agent':'ElfredPublicReader/1.0'},lookup:(_host,options,callback)=>options?.all?callback(null,[{address,family:4}]):callback(null,address,4)},response=>{
      if([301,302,303,307,308].includes(response.statusCode)&&response.headers.location){response.resume();resolve({redirect:new URL(response.headers.location,url).href});return;}
      if(response.statusCode!==200){response.resume();reject(new Error('HTTP '+response.statusCode));return;}
      if(!/^(text\/(html|plain)|application\/xhtml\+xml)\b/i.test(response.headers['content-type']||'')||response.headers['content-encoding']&&response.headers['content-encoding']!=='identity'){response.resume();reject(new Error('Unsupported webpage'));return;}
      const chunks=[];let size=0;
      response.on('data',chunk=>{size+=chunk.length;if(size>1000000){request.destroy(new Error('Page too large'));return;}chunks.push(chunk);});
      response.on('end',()=>resolve({html:Buffer.concat(chunks).toString('utf8')}));response.on('error',reject);
    });request.on('timeout',()=>request.destroy(new Error('Page timeout')));request.on('error',reject);request.end();
  });
  if(result.redirect){if(redirects>=2)fail('WEB_UNAVAILABLE','网页重定向次数过多');return readPublicPage(result.redirect,{signal,redirects:redirects+1,resolver,requester});}
  const content=pageText(result.html);if(content.length<30)fail('WEB_UNAVAILABLE','网页需要登录、脚本加载或未返回可读取正文');
  const title=pageText(result.html.match(/<title\b[^>]*>([\s\S]*?)<\/title>/i)?.[1]||url.hostname).slice(0,180);
  return {title,url:url.href,content,evidence:'page_text',retrieved_at:now()};
}
export class PublicWeb {
  constructor(config={},rssReader=readRss,pageReader=readPublicPage){this.enabled=config.ELFRED_PUBLIC_WEB!=='false';this.rssReader=rssReader;this.pageReader=pageReader;}
  async search(query,{signal}={}){
    if(!this.enabled)fail('PROVIDER_NOT_CONFIGURED','公开网页检索已关闭');
    query=publicQuery(query);const engines=[['bing-rss','https://www.bing.com/search?format=rss&q='],['google-news-rss','https://news.google.com/rss/search?hl=zh-CN&gl=CN&ceid=CN:zh-Hans&q=']];
    for(const [engine,base] of engines){try{const items=await this.rssReader(base+encodeURIComponent(query),0,signal);const hits=items.slice(0,6).map(item=>({title:item.title,url:item.url,summary:item.summary,published_at:item.published_at,evidence:'search_excerpt',retrieved_at:now()}));if(hits.length)return {engine,hits};}catch(error){if(signal?.aborted)throw error;}}
    fail('WEB_UNAVAILABLE','公开检索暂时不可用或没有结果，请更换关键词后重试');
  }
  async read(url,{signal}={}){if(!this.enabled)fail('PROVIDER_NOT_CONFIGURED','公开网页读取已关闭');try{return await this.pageReader(url,{signal});}catch(error){if(error.code)throw error;fail('WEB_UNAVAILABLE','网页暂时无法读取，可能需要登录或拒绝访问');}}
}
