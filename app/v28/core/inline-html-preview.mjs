import {fromMarkdown} from 'mdast-util-from-markdown';

// Only an explicit HTML code block (or a complete HTML document) becomes a preview.
// Other languages remain code so that we never pretend they can run in a browser.
export function extractHtmlPreview(source){
 if(typeof source!=='string'||!source.trim())return null;
 const tree=fromMarkdown(source);
 const blocks=tree.children.filter(node=>node.type==='code'&&['html','htm','css','js','javascript'].includes(String(node.lang||'').toLowerCase()));
 const main=blocks.find(node=>['html','htm'].includes(String(node.lang||'').toLowerCase()));
 if(main){
  const supporting=blocks.filter(node=>['css','js','javascript'].includes(String(node.lang||'').toLowerCase()));
  const previewBlocks=[main,...supporting];
  const css=supporting.filter(node=>String(node.lang).toLowerCase()==='css').map(node=>node.value).join('\n');
  const js=supporting.filter(node=>['js','javascript'].includes(String(node.lang).toLowerCase())).map(node=>node.value).join('\n');
  const html=main.value.trim()+(css?'\n<style>'+css.replace(/<\/style/gi,'<\\/style')+'</style>':'')+(js?'\n<script>'+js.replace(/<\/script/gi,'<\\/script')+'</script>':'');
  if(!html||html.length>80000||previewBlocks.some(node=>!Number.isInteger(node.position?.start.offset)||!Number.isInteger(node.position?.end.offset)))return null;
  let description=source;
  for(const node of [...previewBlocks].sort((a,b)=>b.position.start.offset-a.position.start.offset))description=description.slice(0,node.position.start.offset)+description.slice(node.position.end.offset);
  return {html,description:description.replace(/\n{3,}/g,'\n\n').trim(),code:previewBlocks.map(node=>'```'+node.lang+'\n'+node.value+'\n```').join('\n\n')};
 }
 if(source.length<=80000&&(/^\s*(?:<!doctype\s+html\b|<html[\s>])/i.test(source)||/^\s*<(?:div|main|section|article|button|header|footer|style|body|h[1-6]|p)\b/i.test(source)&&/<\/[a-z][\w-]*\s*>/i.test(source)))return {html:source.trim(),description:''};
 return null;
}
