import https from 'node:https';
import {lookup} from 'node:dns/promises';
import {isIP} from 'node:net';
import {fail} from './store.mjs';

export function validatedFeedUrl(value){
  let url;
  try { url=new URL(value); } catch { fail('INVALID_FEED_URL','请输入有效的 HTTPS RSS 或 Atom 地址'); }
  if(url.protocol!=='https:'||url.username||url.password||url.hash||url.port&&url.port!=='443'||isIP(url.hostname)||!url.hostname.includes('.')||/\.(local|internal|localhost|test)$/i.test(url.hostname))
    fail('INVALID_FEED_URL','订阅源必须是公开 HTTPS 域名，不能使用内网地址或自定义端口');
  return url.href;
}

export function publicIPv4(address){
  if(isIP(address)!==4)return false;
  const [a,b,c]=address.split('.').map(Number);
  if(a===0||a===10||a===127||a>=224||a===169&&b===254||a===172&&b>=16&&b<=31||a===100&&b>=64&&b<=127)return false;
  // Some managed outbound networks map verified public hostnames into 198.18/15.
  // TLS hostname verification still applies to the pinned connection.
  if(a===192&&(b===168||b===0)||a===198&&b===51&&c===100||a===203&&b===0&&c===113)return false;
  return true;
}

function decode(value){
  return String(value||'').replace(/^<!\[CDATA\[|\]\]>$/g,'').replace(/&#(x[0-9a-f]+|\d+);/gi,(_,code)=>{
    const n=code[0].toLowerCase()==='x'?parseInt(code.slice(1),16):Number(code);
    return n>0&&n<=0x10ffff?String.fromCodePoint(n):'';
  }).replace(/&(?:amp|lt|gt|quot|apos|nbsp);/gi,entity=>({amp:'&',lt:'<',gt:'>',quot:'"',apos:"'",nbsp:' '}[entity.slice(1,-1).toLowerCase()]));
}
function plain(value){return decode(value).replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim();}
function tag(block,name){const match=block.match(new RegExp(`<${name}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${name}>`,'i'));return match?.[1]||'';}
function safeLink(raw,base){
  try{const url=new URL(decode(raw.trim()),base);return ['https:','http:'].includes(url.protocol)&&!url.username&&!url.password?url.href:null}catch{return null}
}

export function parseRss(xml,sourceUrl){
  if(typeof xml!=='string'||xml.length>1200000||/<!DOCTYPE|<!ENTITY/i.test(xml))fail('INVALID_FEED','订阅源格式不受支持');
  const atom=/<feed(?:\s|>)/i.test(xml),blocks=[...xml.matchAll(atom?/<entry(?:\s[^>]*)?>([\s\S]*?)<\/entry>/gi:/<item(?:\s[^>]*)?>([\s\S]*?)<\/item>/gi)].slice(0,60);
  if(!blocks.length&&!/<(?:rss|feed|rdf:RDF)(?:\s|>)/i.test(xml))fail('INVALID_FEED','没有识别到 RSS 或 Atom 内容');
  return blocks.map(([,block])=>{
    const link=atom?block.match(/<link\b[^>]*\bhref=["']([^"']+)["'][^>]*\/?>/i)?.[1]||tag(block,'link'):tag(block,'link');
    const url=safeLink(link,sourceUrl),title=plain(tag(block,'title')).slice(0,180),description=plain(tag(block,'description')||tag(block,'summary')||tag(block,'content:encoded')||tag(block,'content')).slice(0,1200);
    const identifier=plain(tag(block,'guid')||tag(block,'id'))||url;
    if(!title||!identifier||!url)return null;
    const date=Date.parse(plain(tag(block,'pubDate')||tag(block,'published')||tag(block,'updated')));
    return {id:identifier,title,summary:description,url,published_at:Number.isFinite(date)?new Date(date).toISOString():null};
  }).filter(Boolean);
}

export async function readRss(sourceUrl,redirects=0,signal){
  const url=new URL(validatedFeedUrl(sourceUrl));
  const records=await lookup(url.hostname,{family:4,all:true});
  const address=records.find(record=>publicIPv4(record.address))?.address;
  if(!address)fail('FEED_UNAVAILABLE','订阅源没有可用的公开 IPv4 地址');
  const result=await new Promise((resolve,reject)=>{
    const request=https.request(url,{method:'GET',signal,timeout:10000,autoSelectFamily:false,headers:{Accept:'application/rss+xml, application/atom+xml, application/xml, text/xml','User-Agent':'ElfredRSS/1.0'},lookup:(_host,options,callback)=>options?.all?callback(null,[{address,family:4}]):callback(null,address,4)},response=>{
      if([301,302,307,308].includes(response.statusCode)&&response.headers.location){response.resume();resolve({redirect:new URL(response.headers.location,url).href});return;}
      if(response.statusCode!==200){response.resume();reject(new Error('HTTP '+response.statusCode));return;}
      if(response.headers['content-encoding']&&response.headers['content-encoding']!=='identity'){response.resume();reject(new Error('Unsupported encoding'));return;}
      const chunks=[];let size=0;
      response.on('data',chunk=>{size+=chunk.length;if(size>1000000){request.destroy(new Error('Feed too large'));return;}chunks.push(chunk)});
      response.on('end',()=>resolve({xml:Buffer.concat(chunks).toString('utf8')}));
      response.on('error',reject);
    });
    request.on('timeout',()=>request.destroy(new Error('Feed timeout')));
    request.on('error',reject);request.end();
  });
  if(result.redirect){
    if(redirects>=2)fail('FEED_UNAVAILABLE','RSS 重定向次数过多');
    return readRss(validatedFeedUrl(result.redirect),redirects+1,signal);
  }
  return parseRss(result.xml,url.href);
}
