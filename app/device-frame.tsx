"use client";

import { useEffect, useState, type CSSProperties, type ReactNode } from "react";

export function DeviceFrame({children,label,className=""}:{children:ReactNode;label:string;className?:string}) {
  const [scale,setScale]=useState(1);
  const isIphone17=className.split(/\s+/).includes("v277-device");
  const isResponsive=className.split(/\s+/).includes("v280-device");
  const [viewportStyle,setViewportStyle]=useState<CSSProperties>({});
  useEffect(()=>{
    const deviceWidth=isIphone17?422:393;
    const deviceHeight=isIphone17?894:852;
    const resize=()=>{
      if(isResponsive && window.matchMedia("(max-width: 600px), (pointer: coarse)").matches){
        const viewport=window.visualViewport;
        // Keep the composer inside Safari's visible viewport when the keyboard opens.
        const unzoomed=viewport && Math.abs(viewport.scale-1)<0.01;
        setViewportStyle({"--app-viewport-height":`${unzoomed?viewport.height:window.innerHeight}px`,"--app-viewport-top":`${unzoomed?viewport.offsetTop:0}px`} as CSSProperties);
        setScale(1);
        return;
      }
      setViewportStyle({});
      const gutter=window.innerWidth<=600?12:32;
      setScale(Math.min(1,(window.innerHeight-gutter)/deviceHeight,(window.innerWidth-gutter)/deviceWidth));
    };
    resize();window.addEventListener("resize",resize);
    window.visualViewport?.addEventListener("resize",resize);
    window.visualViewport?.addEventListener("scroll",resize);
    return()=>{window.removeEventListener("resize",resize);window.visualViewport?.removeEventListener("resize",resize);window.visualViewport?.removeEventListener("scroll",resize);};
  },[isIphone17,isResponsive]);
  return <main className={`app-shell ${className}`} style={{"--device-scale":scale,...viewportStyle} as CSSProperties}><div className={`device-frame${isIphone17?" iphone17-frame":""}`}>
    {isIphone17&&<><span className="iphone17-side-buttons" aria-hidden="true"/><span className="iphone17-power-button" aria-hidden="true"/><span className="iphone17-island" aria-hidden="true"><i/></span></>}
    <section className="phone-stage" aria-label={label}>{children}</section>
  </div></main>;
}
