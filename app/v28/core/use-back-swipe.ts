"use client";

import {useEffect,useLayoutEffect,useRef,type RefObject} from 'react';

/** One-finger back gesture; horizontal scrollers and text editing keep their own gestures. */
export function useBackSwipe(root:RefObject<HTMLElement|null>,back:()=>void,enabled:boolean,accountKey:string){
 const latest=useRef({back,enabled});useLayoutEffect(()=>{latest.current={back,enabled}},[back,enabled]);
 useEffect(()=>{
  const element=root.current?.closest<HTMLElement>('.phone-stage')||root.current;if(!element)return;
  let start:{x:number;y:number;dialog:HTMLElement|null;locked:boolean}|null=null,suppressUntil=0;
  const begin=(event:TouchEvent)=>{
   start=null;if(event.touches.length!==1)return;
   const target=event.target instanceof Element?(event.target instanceof HTMLElement?event.target:event.target.parentElement):null;
   if(!target||target.closest('input,textarea,select,[contenteditable="true"],.v283-brief-deck'))return;
   for(let node:HTMLElement|null=target;node&&node!==element;node=node.parentElement){
    const style=getComputedStyle(node);
    if(node.scrollWidth>node.clientWidth+2&&['auto','scroll'].includes(style.overflowX))return;
   }
   const dialogs=[...element.querySelectorAll<HTMLElement>('[role="dialog"][aria-modal="true"]')].filter(node=>node.getClientRects().length).sort((a,b)=>(Number.parseInt(getComputedStyle(a).zIndex)||0)-(Number.parseInt(getComputedStyle(b).zIndex)||0));
   const dialog=dialogs.at(-1)||null;
   if(!latest.current.enabled&&!dialog)return;
   start={x:event.touches[0].clientX,y:event.touches[0].clientY,dialog,locked:false};
  };
  const move=(event:TouchEvent)=>{
   if(!start)return;if(event.touches.length!==1){start=null;return;}
   const dx=event.touches[0].clientX-start.x,dy=event.touches[0].clientY-start.y;
   if(!start.locked&&Math.abs(dy)>12&&Math.abs(dy)>=Math.abs(dx)){start=null;return;}
   if(dx>12&&dx>Math.abs(dy)*1.4){start.locked=true;if(event.cancelable)event.preventDefault();}
  };
  const end=(event:TouchEvent)=>{
   const origin=start;start=null;if(!origin?.locked||!event.changedTouches.length)return;
   const dx=event.changedTouches[0].clientX-origin.x,dy=event.changedTouches[0].clientY-origin.y;
   if(dx<75||dx<Math.abs(dy)*1.4)return;
   const dialog=origin.dialog;
   if(dialog){
    if(!dialog.isConnected)return;
    const ownClose=[...dialog.querySelectorAll<HTMLButtonElement>('button')].find(button=>/^(关闭|返回)/.test(button.getAttribute('aria-label')||button.innerText));
    const backdrop=dialog.previousElementSibling;
    const close=ownClose||(backdrop instanceof HTMLButtonElement&&/^关闭/.test(backdrop.getAttribute('aria-label')||'')?backdrop:null);
    if(!close)return;close.click();
   }else latest.current.back();
   suppressUntil=Date.now()+450;
  };
  const cancel=()=>{start=null;};
  const click=(event:MouseEvent)=>{if(Date.now()<suppressUntil){event.preventDefault();event.stopPropagation();}};
  element.addEventListener('touchstart',begin,{passive:true});element.addEventListener('touchmove',move,{passive:false});
  element.addEventListener('touchend',end);element.addEventListener('touchcancel',cancel);element.addEventListener('click',click,true);
  return()=>{element.removeEventListener('touchstart',begin);element.removeEventListener('touchmove',move);element.removeEventListener('touchend',end);element.removeEventListener('touchcancel',cancel);element.removeEventListener('click',click,true);};
 // The account-keyed page provider replaces its DOM after session restoration.
 },[root,enabled,accountKey]);
}
