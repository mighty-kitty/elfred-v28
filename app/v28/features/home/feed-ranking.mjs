/**
 * Index once per snapshot. Menu toggles and filtering must not rescan the whole
 * feed for every pair compared by sort.
 * @param {import('../live/types').Snapshot} snapshot
 * @param {string} today
 */
export function indexPrivateFeed(snapshot, today) {
  const feeds = snapshot.objects.feed;
  /** @type {Record<string, {mode?: string, alias?: string, removed?: boolean}>} */
  const settings = snapshot.objects.settings[0]?.data.feed_topics || {};
  const canonicalTopic = value => settings[value]?.alias || value;
  const active = new Map();
  for (const interaction of snapshot.objects.interaction) {
    if (!interaction.data.active) continue;
    const id = interaction.data.object_id;
    if (!active.has(id)) active.set(id, new Set());
    active.get(id).add(interaction.data.kind);
  }
  const isActive = (id, kind) => active.get(id)?.has(kind) || false;
  const tasks = new Map(snapshot.objects.task.map(task => [task.id, task]));
  const likedTopics = new Map(), reducedTopics = new Map(), topics = new Map();
  for (const item of feeds) {
    const topic = canonicalTopic(String(item.data.topic ?? ''));
    topics.set(item.id, topic);
    if (isActive(item.id, 'like')) likedTopics.set(topic, (likedTopics.get(topic) || 0) + 1);
    if (isActive(item.id, 'less')) {
      if (!reducedTopics.has(topic)) reducedTopics.set(topic, new Set());
      reducedTopics.get(topic).add(item.data.system);
    }
  }
  const now = Date.parse(snapshot.server_time);
  const scores = new Map(feeds.map(item => {
    const topic = topics.get(item.id), mode = settings[topic]?.mode;
    const age = (now - Date.parse(item.created)) / 86400000;
    return [item.id, (tasks.get(item.data.task_id)?.data.focus_date === today ? 3 : 0)
      + (item.data.artifact_id ? 2 : 0) + Math.min(likedTopics.get(topic) || 0, 2)
      - age / 7 - (reducedTopics.get(topic)?.has(item.data.system) ? 8 : 0)
      + (mode === 'follow' ? 3 : 0) - (mode === 'mute' ? 20 : 0)];
  }));
  return {
    isActive, topics,
    topicOptions: [...new Set(topics.values())].filter(value => value && !settings[value]?.removed),
    recommended: feeds.slice().sort((a, b) => scores.get(b.id) - scores.get(a.id) || b.created.localeCompare(a.created)),
    latest: feeds.slice().sort((a, b) => b.created.localeCompare(a.created)),
  };
}
