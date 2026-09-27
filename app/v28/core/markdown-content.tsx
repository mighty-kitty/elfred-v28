"use client";
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type {Root,Element,Text,RootContent} from 'hast';

// Highlight only parsed text, never markup, URLs, or attributes.
function highlightText(needle:string){
  return ()=> (tree:Root)=>{
    function visit(node:Root|Element){
      node.children=node.children.flatMap(child=>{
        if(child.type==='element'){if(!['code','pre'].includes(child.tagName))visit(child);return [child];}
        if(child.type!=='text'||!needle||!child.value.includes(needle))return [child];
        const parts=child.value.split(needle),nodes:RootContent[]=[];
        parts.forEach((value,index)=>{if(index)nodes.push({type:'element',tagName:'mark',properties:{},children:[{type:'text',value:needle}]});if(value)nodes.push({type:'text',value} as Text)});
        return nodes;
      }) as typeof node.children;
    }
    visit(tree);
  };
}

export function MarkdownContent({text,highlight}:{text:string;highlight?:string}){
  return <div className="elfred-markdown"><Markdown remarkPlugins={[remarkGfm]} rehypePlugins={highlight?[highlightText(highlight)]:[]} skipHtml components={{
    a:({children,href})=>href?<a href={href} target="_blank" rel="noopener noreferrer">{children}</a>:<span>{children}</span>,
    // Previewing a draft must not automatically contact third-party image servers.
    img:({alt,src})=>typeof src==='string'&&src?<a href={src} target="_blank" rel="noopener noreferrer">{alt||'查看图片'}</a>:<span>{alt||'图片'}</span>,
    table:({children})=><div className="elfred-markdown-table"><table>{children}</table></div>,
  }}>{text}</Markdown></div>;
}
