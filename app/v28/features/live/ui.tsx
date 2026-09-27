"use client";
import {MarkdownContent} from '../../core/markdown-content';
import {useState,type FormEvent,type ReactNode} from 'react';
import {text,statuses,type Entity} from './types';
export function Card({children,className=''}:{children:ReactNode;className?:string}){return <section className={`live-card ${className}`}>{children}</section>}
export function Empty({children}:{children:ReactNode}){return <div className="live-empty">{children}</div>}
export function Badge({value}:{value:string}){return <span className={`live-badge state-${value}`}>{statuses[value]||value}</span>}
export function Item({item,onClick}:{item:Entity;onClick?:()=>void}){return <button type="button" className="live-item" onClick={onClick}><span><strong>{text(item,'title')||text(item,'goal')||text(item,'content').slice(0,50)||text(item,'summary')||text(item,'purpose')}</strong><small>{new Date(item.updated).toLocaleString('zh-CN')} · v{item.version}</small></span><Badge value={text(item,'status')}/></button>}
export function Action({children,onClick,secondary=false,disabled=false}:{children:ReactNode;onClick:()=>unknown;secondary?:boolean;disabled?:boolean}){return <button type="button" disabled={disabled} className={secondary?'live-secondary':'live-primary'} onClick={()=>{void onClick()}}>{children}</button>}
export type Field={name:string;label:string;type?:'textarea'|'password'|'number'|'select'|'checkbox';options?:{value:string;label:string}[];value?:string;required?:boolean;placeholder?:string};
export function Form({fields,submit,onSubmit,children}:{fields:Field[];submit:string;onSubmit:(values:Record<string,string>,form:HTMLFormElement)=>Promise<unknown>;children?:ReactNode}){
  const [busy,setBusy]=useState(false);
  async function send(event:FormEvent<HTMLFormElement>){event.preventDefault();if(busy)return;setBusy(true);const form=event.currentTarget;try{await onSubmit(Object.fromEntries(new FormData(form).entries()) as Record<string,string>,form);}finally{setBusy(false)}}
  return <form className="live-form" onSubmit={send}>{fields.map(field=><label key={field.name} className={field.type==='checkbox'?'live-check':''}>{field.type==='checkbox'?<><input type="checkbox" name={field.name} required={field.required}/><span>{field.label}</span></>:<><span>{field.label}</span>{field.type==='textarea'?<textarea name={field.name} defaultValue={field.value} required={field.required!==false} placeholder={field.placeholder} rows={4}/>:field.type==='select'?<select name={field.name} defaultValue={field.value}>{field.options?.map(option=><option key={option.value} value={option.value}>{option.label}</option>)}</select>:<input name={field.name} type={field.type||'text'} defaultValue={field.value} required={field.required!==false} placeholder={field.placeholder}/>}</>}</label>)}{children}<button className="live-primary" disabled={busy}>{busy?'正在保存…':submit}</button></form>
}
export function Content({value}:{value:unknown}){return typeof value==='string'?<MarkdownContent text={value}/>:<pre className="live-content">{JSON.stringify(value,null,2)}</pre>}
