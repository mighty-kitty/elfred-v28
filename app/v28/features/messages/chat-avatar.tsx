"use client";
import {UsersRound} from 'lucide-react';
import './chat-avatar.css';

const sampleAvatars:Record<string,string>={
  'person-linjia':'avatar-lin',
  'person-chenkai':'avatar-kevin',
  'person-aya':'avatar-aya',
  'person-duming':'avatar-du',
  'person-zhaoya':'avatar-zhao',
};

export function ChatAvatar({name,id,group=false,live=false,small=false}:{name:string;id?:string;group?:boolean;live?:boolean;small?:boolean}){
  const sample=!live&&(group?'avatar-group':sampleAvatars[id||'']);
  if(sample)return <i className={`${sample} v277-sprite-community elfred-chat-avatar ${small?'is-small':''}`} aria-label={name}/>;
  return <span className={`elfred-chat-avatar elfred-chat-avatar-fallback ${small?'is-small':''}`} aria-label={name}>{group?<UsersRound size={small?16:20}/>:name.trim().slice(0,1)||'人'}</span>;
}
