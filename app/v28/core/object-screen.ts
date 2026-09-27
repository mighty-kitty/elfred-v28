import type {Entity} from '../features/live/types';
import type {Screen} from './screen';
export function objectScreen(object:Entity,anchor?:string,conversations:Entity[]=[]):Screen {
  const conversation=object.type==='conversation'?object:object.type==='message'?conversations.find(c=>c.id===object.data.conversation_id):undefined;
  if(conversation?.data.kind==='agent'){const system=String(conversation.data.system),id=system==='advise'?'advisor':system;if(['explore','advisor','create','connect','execute'].includes(id))return {name:'agent',id:id as 'explore'|'advisor'|'create'|'connect'|'execute',conversationId:conversation.id,messageId:object.type==='message'?object.id:undefined};}
  if(object.type==='skill')return {name:'tool-detail',id:object.id};
  if(object.type==='message')return {name:'chat',id:String(object.data.conversation_id),messageId:object.id};
  if(object.type==='conversation')return {name:'chat',id:object.id};
  if(object.type==='task')return {name:'task',id:object.id};
  if(object.type==='post'||object.type==='project'||object.type==='release')return {name:'community-post',id:object.id};
  if(object.type==='feed')return {name:'feed-detail',id:object.id};
  if(object.type==='friend')return {name:'utility',kind:'relationships'};
  if(object.type==='memory')return {name:'memory-detail',id:object.id};
  return {name:'search-source',id:object.id,anchor};
}
