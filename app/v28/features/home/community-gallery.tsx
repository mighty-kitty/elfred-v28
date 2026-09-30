"use client";
import {useEffect,useState} from 'react';
import {createPortal} from 'react-dom';
import {ChevronLeft,ChevronRight,X} from 'lucide-react';
import {displayTitle} from '../../core/display-labels';
import type {FileRef} from '../live/attachments';
import './community-gallery.css';

export function CommunityImageGallery({files,onOpen,detail=false}:{files:FileRef[];onOpen?:()=>void;detail?:boolean}){
 const images=files.filter(file=>file.mime.startsWith('image/'));
 const [selected,setSelected]=useState<number|null>(null);
 const [touchStart,setTouchStart]=useState<number|null>(null);
 useEffect(()=>{
  if(selected===null)return;
  const key=(event:KeyboardEvent)=>{
   if(event.key==='Escape')setSelected(null);
   if(event.key==='ArrowLeft')setSelected(value=>value===null?null:(value-1+images.length)%images.length);
   if(event.key==='ArrowRight')setSelected(value=>value===null?null:(value+1)%images.length);
  };
  window.addEventListener('keydown',key);
  return()=>window.removeEventListener('keydown',key);
 },[selected,images.length]);
 if(!images.length)return null;
 return <>
  <div className={`community-image-gallery ${images.length===1?'is-single':images.length===2?'is-pair':'is-grid'} ${detail?'is-detail':''}`} aria-label={`${images.length} 张动态图片`}>
   {images.map((file,index)=><button type="button" key={file.id} aria-label={`查看第 ${index+1} 张图片，共 ${images.length} 张`} onClick={()=>detail?setSelected(index):onOpen?.()}><img src={`/api/elfred/attachments/${file.id}`} alt={displayTitle(file.name,`图片 ${index+1}`)} loading="lazy"/></button>)}
  </div>
  {selected!==null&&typeof document!=='undefined'&&createPortal(<div className="community-image-viewer" role="dialog" aria-modal="true" aria-label={`图片 ${selected+1} / ${images.length}`} onTouchStart={event=>setTouchStart(event.touches[0]?.clientX??null)} onTouchEnd={event=>{if(touchStart===null)return;const delta=(event.changedTouches[0]?.clientX??touchStart)-touchStart;if(Math.abs(delta)>45)setSelected(value=>value===null?null:(value+(delta<0?1:-1)+images.length)%images.length);setTouchStart(null)}}>
   <button type="button" className="community-image-viewer-backdrop" aria-label="关闭图片" onClick={()=>setSelected(null)}/>
   <div className="community-image-viewer-content"><button type="button" className="community-image-viewer-close" aria-label="关闭图片" onClick={()=>setSelected(null)}><X size={24}/></button><img src={`/api/elfred/attachments/${images[selected].id}`} alt={displayTitle(images[selected].name,`图片 ${selected+1}`)}/><span>{selected+1} / {images.length}</span>{images.length>1&&<><button type="button" className="community-image-viewer-prev" aria-label="上一张" onClick={()=>setSelected((selected-1+images.length)%images.length)}><ChevronLeft size={28}/></button><button type="button" className="community-image-viewer-next" aria-label="下一张" onClick={()=>setSelected((selected+1)%images.length)}><ChevronRight size={28}/></button></>}</div>
  </div>,document.querySelector('.phone-stage')||document.body)}
 </>;
}
