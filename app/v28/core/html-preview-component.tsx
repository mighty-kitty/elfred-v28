"use client";
import {useState} from 'react';
import {MarkdownContent} from './markdown-content';
import {extractHtmlPreview} from './inline-html-preview.mjs';
import './inline-html-preview.css';

const CSP="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; media-src data: blob:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'";

export function InlineHtmlPreview({source,title='网页预览'}:{source:string;title?:string}){
 const [interactive,setInteractive]=useState(false);
 const preview=extractHtmlPreview(source);
 if(!preview)return <MarkdownContent text={source}/>;
 const document=`<meta http-equiv="Content-Security-Policy" content="${CSP}">${preview.html.replace(/^\s*<!doctype\s+html[^>]*>/i,'')}`;
 return <div className="elfred-inline-html">
  {preview.description&&<MarkdownContent text={preview.description}/>}
  <div className="elfred-inline-html-head"><b>{title}</b><button type="button" onClick={()=>setInteractive(value=>!value)}>{interactive?'停止交互':'运行交互'}</button></div>
  <iframe key={interactive?'interactive':'static'} title={title} sandbox={interactive?'allow-scripts':''} referrerPolicy="no-referrer" srcDoc={document}/>
  <details><summary>查看网页代码</summary><pre><code>{preview.code||preview.html}</code></pre></details>
 </div>;
}
