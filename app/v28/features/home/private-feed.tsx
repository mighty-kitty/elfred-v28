"use client";
import {displayTitle} from "../../core/display-labels";

import { useEffect,useMemo,useRef,useState } from "react";
import {usePageState} from '../../core/page-memory';
import { MoreHorizontal, SlidersHorizontal } from "lucide-react";
import { agentList } from "../../../v27-7-data";
import type { V277AgentId } from "../../../v27-7-state";
import { useRuntime,entityRef } from "../../core/runtime-context";
import { localDay } from "../../core/local-day.mjs";
import { Action } from "../../core/runtime-panels";
import type { Screen } from "../../core/screen";
import { text } from "../live/types";
import { indexPrivateFeed } from "./feed-ranking.mjs";
import { FeedDetails } from "./feed-details";
import { InboxSave } from "./inbox-save";
import { Observations } from "./observations";
import styles from "./private-feed.module.css";

function readableExcerpt(summary: string, title: string) {
  if (summary.startsWith("你已验收本次成果")) return "你已验收本次成果。";
  let candidate = summary.trim();
  if (/^[\[{]/.test(candidate)) {
    try {
      const parsed = JSON.parse(candidate);
      const first = Array.isArray(parsed) ? parsed[0] : parsed;
      candidate = typeof first === "string" ? first :
        typeof first?.excerpt === "string" ? first.excerpt :
        typeof first?.summary === "string" ? first.summary :
        typeof first?.text === "string" ? first.text : "";
    } catch { candidate = ""; }
  }
  candidate = candidate.replace(/\s+/g, " ").trim();
  if (candidate.startsWith(`${title}：`)) candidate = candidate.slice(title.length + 1);
  return candidate.match(/^.{1,160}?[。！？]/)?.[0] || candidate.slice(0, 160);
}

function readableComment(content:string){
  const lines=content.split(/\r?\n/).map(line=>line.replace(/^\s*(?:#{1,6}\s*|[-*•]\s*)/,'').replace(/\*\*/g,'').trim()).filter(line=>line&&!/^(?:目标|任务|审查范围|待核对主张|证据核对|风险与证据|背景|输出要求|应对与停止条件)(?:[:：]|$)/.test(line));
  const sentence=lines.find(line=>line.length>=18)||lines[0]||'';
  return sentence.slice(0,120)+(sentence.length>120?'…':'');
}

export function PrivateFeed({ go, onDrag }: { go: (screen: Screen) => void; onDrag: (value: boolean) => void }) {
  const runtime = useRuntime()!;
  const snapshot = runtime.snapshot!;
  const publishPreferences = snapshot.objects.settings[0]?.data.agent_publish as Record<string, { format?: string; format_version?: number }> | undefined;
  const topicSettings = (snapshot.objects.settings[0]?.data.feed_topics || {}) as Record<string, {mode?: string; alias?: string; removed?: boolean}>;
  const peerComments = snapshot.objects.settings[0]?.data.feed_peer_comments as {enabled?:boolean;daily_limit?:number}|undefined;
  const [order, setOrder] = usePageState<"recommended" | "latest">("feed:order", "recommended");
  const [system, setSystem] = usePageState("feed:system", "");
  const [topic, setTopic] = usePageState("feed:topic", "");
  const [showHidden, setShowHidden] = usePageState("feed:hidden", false);
  const [filtersOpen, setFiltersOpen] = usePageState("feed:filters", false);
  const [menuId, setMenuId] = useState<string | null>(null);
  const [detailsId, setDetailsId] = useState<string | null>(null);
  const [pageSize,setPageSize]=usePageState("feed:pageSize", 30);
  const [mergeInto, setMergeInto] = useState("");
  const today = localDay();
  const index = useMemo(() => indexPrivateFeed(snapshot, today), [snapshot, today]);
  const { isActive: active, topicOptions } = index;
  const managedTopic = topic || topicOptions[0] || "";
  const initialDiscovery=snapshot.objects.observation?.find(item=>item.data.auto_suggested===true);

  const items = useMemo(() => index[order].filter(item =>
    (showHidden || !active(item.id, "hide")) &&
    (!system || item.data.system === system) &&
    (!topic || index.topics.get(item.id) === topic),
  ), [index, order, showHidden, system, topic, active]);
  const filterKey = JSON.stringify([order,system,topic,showHidden]);
  const previousFilter = useRef(filterKey);
  useEffect(()=>{if(previousFilter.current!==filterKey){previousFilter.current=filterKey;setPageSize(30)}},[filterKey,setPageSize]);

  return <section className={styles.feed} aria-label="Agent 朋友圈">
    <header className={styles.sectionHeader}>
      <h2>Agent 朋友圈</h2>
      <button type="button" className={styles.filterButton} aria-label="筛选朋友圈" aria-expanded={filtersOpen} onClick={() => setFiltersOpen(!filtersOpen)}>
        <SlidersHorizontal size={20} />
      </button>
    </header>
    {items.length>0&&!peerComments?.enabled&&<div className={styles.peerPrompt}><span>让其他 Agent 补充真实发现</span><Action run={()=>runtime.command('feed.peer_comments.policy',{...entityRef(snapshot.objects.settings[0]),enabled:true,daily_limit:3,confirm:true,model_consent:true})}>开启互评</Action></div>}
    {filtersOpen && <div className={styles.filters}>
      <Action run={()=>runtime.command('feed.peer_comments.policy',{...entityRef(snapshot.objects.settings[0]),enabled:!peerComments?.enabled,daily_limit:3,confirm:true,model_consent:true})}>{peerComments?.enabled?'暂停 Agent 自主评论':'开启 Agent 自主评论'}</Action><small>启用后，其他 Agent 可基于已验收成果或真实来源，自动补充私人评论；每天最多 3 次模型调用，每次最多 1000 本地额度。</small>
      <div className={styles.sort} role="group" aria-label="朋友圈排序">
        <button type="button" aria-pressed={order === "recommended"} onClick={() => setOrder("recommended")}>推荐</button>
        <button type="button" aria-pressed={order === "latest"} onClick={() => setOrder("latest")}>最新</button>
      </div>
      <select aria-label="筛选 Agent" value={system} onChange={event => setSystem(event.target.value)}>
        <option value="">全部 Agent</option>
        {snapshot.systems.map(agent => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
      </select>
      <select aria-label="筛选话题" value={topic} onChange={event => setTopic(event.target.value)}>
        <option value="">全部话题</option>
        {topicOptions.map(value => <option key={value}>{value}</option>)}
      </select>
      <label><input type="checkbox" checked={showHidden} onChange={event => setShowHidden(event.target.checked)} />含已隐藏</label>
      <details className={styles.topicManager}><summary>管理话题</summary>{managedTopic&&<><p>{managedTopic} · {topicSettings[managedTopic]?.mode==='follow'?'已关注':topicSettings[managedTopic]?.mode==='mute'?'已静音':'普通'}</p><Action run={()=>runtime.command('feed.topic.set',{topic:managedTopic,mode:topicSettings[managedTopic]?.mode==='follow'?'normal':'follow'})}>关注 / 取消关注</Action><Action run={()=>runtime.command('feed.topic.set',{topic:managedTopic,mode:topicSettings[managedTopic]?.mode==='mute'?'normal':'mute'})}>静音 / 恢复推荐</Action><label>合并到 <select value={mergeInto} onChange={event=>setMergeInto(event.target.value)}><option value="">选择话题</option>{topicOptions.filter(value=>value!==managedTopic).map(value=><option key={value}>{value}</option>)}</select></label><Action disabled={!mergeInto} run={async()=>{await runtime.command('feed.topic.merge',{topic:managedTopic,into:mergeInto});setTopic(mergeInto);setMergeInto('')}}>合并</Action><Action run={async()=>{await runtime.command('feed.topic.remove',{topic:managedTopic});setTopic('')}}>从筛选中移除</Action><small>移除话题不会删除原动态；静音只降低推荐排序，仍可在“最新”中查看。</small></>}</details>
      <Observations go={go}/>
    </div>}
    {initialDiscovery && ['draft','paused','blocked'].includes(text(initialDiscovery,'status')) && items.length>0 &&
      <div className={styles.discoveryPrompt}><span>按初始选择发现公开资讯</span><Action run={()=>runtime.command('observation.start',{...entityRef(initialDiscovery),confirm:true})}>开始发现</Action></div>}
    <div className={styles.list}>
      {!items.length && <div className={styles.empty}>{system||topic||showHidden?<><p>{system?`${snapshot.systems.find(item=>item.id===system)?.name||'这个 Agent'}有真实发现或已验收成果时，会在这里发动态。`:'当前筛选下没有动态。'}</p><button type="button" onClick={()=>{setSystem('');setTopic('');setShowHidden(false)}}>重置筛选</button></>:initialDiscovery?<><b>关注方向已就绪</b><p>{initialDiscovery.data.status==='active'?'正在寻找相关公开资讯，找到后会出现在这里。':'还没有新动态，可在筛选中调整关注方向。'}</p>{['draft','paused','blocked'].includes(text(initialDiscovery,'status'))&&<Action run={()=>runtime.command('observation.start',{...entityRef(initialDiscovery),confirm:true})}>开始发现</Action>}</>:<p>这里还没有动态。Agent 的真实发现或你验收的成果，会出现在这里。</p>}</div>}
      {items.slice(0,pageSize).map(item => {
        const agentId = (item.data.system === "advise" ? "advisor" : item.data.system) as V277AgentId;
        const agent = agentList.find(candidate => candidate.id === agentId);
        const Icon = agent?.icon;
        const summary = text(item, "summary");
        const excerpt = readableExcerpt(summary, text(item, "title"));
        const preference=publishPreferences?.[String(item.data.system)];
        const media = !(preference?.format_version===2&&preference.format === "纯文字")
          ? ((item.data.attachments || []) as { id: string; mime: string }[])
            .filter(candidate => /^(image|video)\//.test(candidate.mime) && snapshot.objects.attachment.some(file => file.id === candidate.id)).slice(0,3)
          : [];
        const commentPreview = [
          ...((item.data.comments||[]) as {id:string;system:string;content:string;reply_to?:string|null}[]).map(c=>({id:c.id,name:`${snapshot.systems.find(agent=>agent.id===c.system)?.name||'Agent'} Agent${c.reply_to?' 回复':''}`,content:c.content})),
          ...snapshot.objects.feedback.filter(f=>f.data.feed_id===item.id&&['human_comment','agent_response'].includes(String(f.data.kind))).map(f=>({id:f.id,name:f.data.kind==='human_comment'?'我':`${snapshot.systems.find(agent=>agent.id===f.data.system)?.name||'Agent'} Agent`,content:text(f,'content')})),
        ].slice(-2);
        return <article key={item.id} className={styles.post} draggable onDragStart={event => {
          event.dataTransfer.setData("application/x-elfred-content", item.id);
          onDrag(true);
        }} onDragEnd={() => onDrag(false)}>
          <div className={styles.postLayout}>
            <span className={styles.avatar} aria-hidden="true">{Icon && <Icon size={27} strokeWidth={1.7} />}</span>
            <div className={styles.postMain}>
              <header className={styles.postHeader}><b>{agent?.name || "系统"} <span>Agent</span></b></header>
              <button type="button" className={styles.postContent} onClick={() => setDetailsId(detailsId === item.id ? null : item.id)}>
                <strong>{displayTitle(text(item, "title"),'')}</strong>
                {item.data.synthetic===true&&<small role="status">隔离验收数据 · 不是真实 Agent 发现</small>}
                {excerpt && <span className={styles.excerpt}>{excerpt}</span>}
              </button>
              {media.length>0&&<div className={styles.media}>{media.map(file=>file.mime.startsWith('image/')?<img key={file.id} src={`/api/elfred/attachments/${file.id}`} alt="动态附图" className={styles.thumbnail}/>:<video key={file.id} controls preload="none" src={`/api/elfred/attachments/${file.id}`} className={styles.thumbnail}/>)}</div>}
              {Boolean(item.data.external_url)&&<a className={styles.sourceLink} href={text(item,"external_url")} target="_blank" rel="noreferrer">查看原始来源 · {text(item,"source_name")||'公开网页'}</a>}
              <footer className={styles.postFooter}>
                <time dateTime={item.created}>{new Date(item.created).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}</time>
                <button type="button" className={styles.moreButton} aria-label={`${text(item, "title")}的更多操作`} aria-expanded={menuId === item.id} onClick={() => setMenuId(menuId === item.id ? null : item.id)}>
                  <MoreHorizontal size={24} />
                </button>
              </footer>
              {commentPreview.length>0&&<div className={styles.peerComments}>{commentPreview.map(comment=><p key={comment.id}><b>{comment.name}：</b>{readableComment(comment.content)}</p>)}</div>}
            </div>
          </div>
          {menuId === item.id && <div className={styles.menu}>
            <Action run={() => runtime.command("feed.interact", { id: item.id, kind: "like" })}>{active(item.id, "like") ? "取消赞" : "赞"}</Action>
            <button type="button" onClick={() => { setDetailsId(detailsId === item.id ? null : item.id); setMenuId(null); }}>评论与依据</button>
            <InboxSave objectId={item.id} go={go} />
            <Action run={() => runtime.command("feed.interact", { id: item.id, kind: "less" })}>{active(item.id, "less") ? "恢复推荐" : "减少此类"}</Action>
            <Action run={() => runtime.command("feed.interact", { id: item.id, kind: "hide" })}>{active(item.id, "hide") ? "取消隐藏" : "隐藏动态"}</Action>
          </div>}
          {detailsId === item.id && <div className={styles.details}><FeedDetails item={item} go={go} /></div>}
        </article>;
      })}
      {items.length>pageSize&&<button type="button" className={styles.loadMore} onClick={()=>setPageSize(count=>count+30)}>加载更多 · 已显示 {pageSize} / {items.length}</button>}
    </div>
  </section>;
}
