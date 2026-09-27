PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS ingested_events (
  event_id TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL,
  producer TEXT NOT NULL,
  received_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  source TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL,
  deleted_at TEXT,
  last_error TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_payload_versions (
  version_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  disposition TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(event_id, payload_hash)
);

CREATE TABLE IF NOT EXISTS sync_jobs (
  job_id TEXT PRIMARY KEY,
  event_id TEXT,
  job_type TEXT NOT NULL,
  status TEXT NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  detail_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_attempts (
  attempt_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  target TEXT NOT NULL,
  operation TEXT NOT NULL,
  status TEXT NOT NULL,
  error TEXT,
  request_hash TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS privacy_decisions (
  decision_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  local_allowed INTEGER NOT NULL,
  cloud_allowed INTEGER NOT NULL,
  reason TEXT NOT NULL,
  redactions_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_task_analyses (
  event_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  source_hash TEXT NOT NULL,
  cloud_consent INTEGER NOT NULL,
  analysis_json TEXT NOT NULL,
  error TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT,
  lease_until TEXT,
  prompt_version TEXT NOT NULL DEFAULT 'task-analysis-v1',
  schema_version TEXT NOT NULL DEFAULT '1.0',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical_tasks (
  task_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT,
  domain TEXT NOT NULL DEFAULT 'uncategorized',
  project TEXT,
  stage TEXT NOT NULL DEFAULT 'unknown',
  progress_percent INTEGER,
  priority TEXT NOT NULL DEFAULT 'none',
  due_at TEXT,
  confidence REAL NOT NULL DEFAULT 0,
  record_status TEXT NOT NULL DEFAULT 'active',
  freetodo_todo_id INTEGER UNIQUE,
  freetodo_uid TEXT NOT NULL UNIQUE,
  last_remote_hash TEXT,
  last_remote_json TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK(progress_percent IS NULL OR (progress_percent >= 0 AND progress_percent <= 100)),
  CHECK(confidence >= 0 AND confidence <= 1)
);

CREATE TABLE IF NOT EXISTS task_evidence (
  evidence_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  observation_key TEXT NOT NULL,
  relation TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0,
  evidence_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(task_id, event_id, observation_key),
  FOREIGN KEY(task_id) REFERENCES canonical_tasks(task_id) ON DELETE CASCADE,
  CHECK(confidence >= 0 AND confidence <= 1)
);

CREATE TABLE IF NOT EXISTS freetodo_todo_links (
  link_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  local_key TEXT NOT NULL,
  freetodo_todo_id INTEGER,
  freetodo_uid TEXT NOT NULL,
  status TEXT NOT NULL,
  last_remote_hash TEXT,
  last_remote_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(event_id, local_key),
  UNIQUE(freetodo_uid)
);

CREATE TABLE IF NOT EXISTS freetodo_journal_links (
  link_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  local_key TEXT NOT NULL,
  freetodo_journal_id INTEGER,
  freetodo_uid TEXT NOT NULL,
  status TEXT NOT NULL,
  last_remote_hash TEXT,
  last_remote_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(event_id, local_key)
);

CREATE TABLE IF NOT EXISTS journal_sync_state (
  journal_date TEXT PRIMARY KEY,
  uid TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL,
  trigger_name TEXT NOT NULL,
  source_hash TEXT,
  candidate_hash TEXT,
  candidate_status TEXT,
  candidate_json TEXT,
  remote_id INTEGER,
  last_remote_hash TEXT,
  last_remote_json TEXT,
  source_event_count INTEGER NOT NULL DEFAULT 0,
  included_event_count INTEGER NOT NULL DEFAULT 0,
  excluded_event_count INTEGER NOT NULL DEFAULT 0,
  requested_generation INTEGER NOT NULL DEFAULT 1,
  processed_generation INTEGER NOT NULL DEFAULT 0,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT,
  lease_until TEXT,
  lease_token TEXT,
  last_error TEXT,
  prompt_version TEXT NOT NULL DEFAULT 'journal-v2',
  privacy_version TEXT NOT NULL DEFAULT 'journal-auto-v1',
  hardware_status TEXT NOT NULL DEFAULT 'disabled',
  hardware_error TEXT,
  remote_managed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS freetodo_activity_links (
  link_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL UNIQUE,
  local_activity_id TEXT NOT NULL,
  freetodo_activity_id INTEGER,
  status TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topic_registry (
  topic_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  aliases_json TEXT NOT NULL,
  parent_topic_id TEXT,
  status TEXT NOT NULL,
  source_event_ids_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topic_aliases (
  normalized_alias TEXT PRIMARY KEY,
  alias TEXT NOT NULL,
  topic_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_topic_links (
  event_id TEXT NOT NULL,
  topic_id TEXT NOT NULL,
  confidence REAL NOT NULL,
  PRIMARY KEY(event_id, topic_id)
);

CREATE TABLE IF NOT EXISTS memory_outbox (
  item_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  contract_version TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  status TEXT NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TEXT NOT NULL,
  acknowledged_at TEXT
);

CREATE TABLE IF NOT EXISTS personal_agent_outbox (
  item_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  contract_version TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  status TEXT NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TEXT NOT NULL,
  acknowledged_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
  log_id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  action TEXT NOT NULL,
  target TEXT,
  detail_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS migration_batches (
  batch_id TEXT PRIMARY KEY,
  source_path TEXT NOT NULL,
  dry_run INTEGER NOT NULL,
  status TEXT NOT NULL,
  imported_event_ids_json TEXT NOT NULL,
  report_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  rolled_back_at TEXT
);

CREATE TABLE IF NOT EXISTS skill_builds (
  build_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  source_task_ids_json TEXT NOT NULL,
  status_history_json TEXT NOT NULL,
  skill_id TEXT,
  version_id TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skills (
  skill_id TEXT PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  status TEXT NOT NULL,
  current_version_id TEXT,
  published_version_id TEXT,
  auto_execute_enabled INTEGER NOT NULL DEFAULT 0,
  trigger_terms_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK(status IN ('draft','pending_review','approved','active','deprecated'))
);

CREATE TABLE IF NOT EXISTS skill_versions (
  version_id TEXT PRIMARY KEY,
  skill_id TEXT NOT NULL,
  version TEXT NOT NULL,
  status TEXT NOT NULL,
  skill_markdown TEXT NOT NULL,
  workflow_json TEXT NOT NULL,
  distilled_json TEXT NOT NULL,
  validation_json TEXT NOT NULL,
  artifact_path TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(skill_id, version),
  FOREIGN KEY(skill_id) REFERENCES skills(skill_id) ON DELETE CASCADE,
  CHECK(status IN ('draft','pending_review','approved','active','deprecated'))
);

CREATE TABLE IF NOT EXISTS skill_source_tasks (
  skill_id TEXT NOT NULL,
  version_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  freetodo_todo_id INTEGER NOT NULL,
  evidence_refs_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(version_id, task_id),
  FOREIGN KEY(skill_id) REFERENCES skills(skill_id) ON DELETE CASCADE,
  FOREIGN KEY(version_id) REFERENCES skill_versions(version_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS skill_runs (
  run_id TEXT PRIMARY KEY,
  skill_id TEXT NOT NULL,
  version_id TEXT NOT NULL,
  task_id TEXT,
  freetodo_todo_id INTEGER,
  status TEXT NOT NULL,
  inputs_json TEXT NOT NULL,
  plan_json TEXT NOT NULL,
  result_json TEXT NOT NULL,
  error TEXT,
  requires_confirmation INTEGER NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  FOREIGN KEY(skill_id) REFERENCES skills(skill_id),
  FOREIGN KEY(version_id) REFERENCES skill_versions(version_id)
);

CREATE TABLE IF NOT EXISTS skill_feedback (
  feedback_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  rating INTEGER,
  outcome TEXT,
  comment TEXT,
  corrections_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES skill_runs(run_id) ON DELETE CASCADE,
  CHECK(rating IS NULL OR (rating >= 1 AND rating <= 5))
);

CREATE TABLE IF NOT EXISTS skill_candidate_groups (
  group_id TEXT PRIMARY KEY,
  group_key TEXT NOT NULL UNIQUE,
  label TEXT NOT NULL,
  status TEXT NOT NULL,
  skill_id TEXT,
  task_ids_json TEXT NOT NULL,
  profile_json TEXT NOT NULL,
  last_build_hash TEXT,
  last_build_id TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK(status IN (
    'observing','ready','building','draft_ready','evidence_gap',
    'pattern_forming','validating_reproduction','failed','ignored'
  )),
  FOREIGN KEY(skill_id) REFERENCES skills(skill_id)
);

CREATE TABLE IF NOT EXISTS skill_task_profiles (
  task_id TEXT PRIMARY KEY,
  freetodo_todo_id INTEGER NOT NULL,
  evidence_hash TEXT NOT NULL,
  profile_json TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK(mode IN ('model','hermes','deterministic')),
  CHECK(status IN ('classified','fallback'))
);

CREATE TABLE IF NOT EXISTS skill_task_matches (
  match_id TEXT PRIMARY KEY,
  freetodo_todo_id INTEGER NOT NULL,
  task_id TEXT,
  skill_id TEXT NOT NULL,
  version_id TEXT NOT NULL,
  score REAL NOT NULL,
  reasons_json TEXT NOT NULL,
  task_context_json TEXT NOT NULL,
  status TEXT NOT NULL,
  auto_execute INTEGER NOT NULL DEFAULT 0,
  last_run_id TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(freetodo_todo_id, skill_id),
  FOREIGN KEY(skill_id) REFERENCES skills(skill_id) ON DELETE CASCADE,
  FOREIGN KEY(version_id) REFERENCES skill_versions(version_id),
  FOREIGN KEY(last_run_id) REFERENCES skill_runs(run_id),
  CHECK(status IN (
    'suggested','running','completed','failed','dismissed','stale',
    'confirmation_required'
  ))
);

CREATE TABLE IF NOT EXISTS hardware_output_plans (
  plan_id TEXT PRIMARY KEY,
  journal_id TEXT NOT NULL,
  journal_version TEXT NOT NULL,
  journal_date TEXT NOT NULL,
  journal_hash TEXT NOT NULL,
  status TEXT NOT NULL,
  requested_mode TEXT NOT NULL,
  effective_mode TEXT NOT NULL,
  journal_json TEXT NOT NULL,
  warnings_json TEXT NOT NULL,
  model_detail_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK(status IN (
    'draft','ready','awaiting_confirmation','running','partial',
    'completed','failed','canceled'
  ))
);

CREATE TABLE IF NOT EXISTS hardware_output_actions (
  action_id TEXT PRIMARY KEY,
  plan_id TEXT NOT NULL,
  position INTEGER NOT NULL,
  adapter_id TEXT NOT NULL,
  command TEXT NOT NULL,
  preset TEXT NOT NULL,
  parameters_json TEXT NOT NULL,
  summary TEXT NOT NULL,
  rationale TEXT NOT NULL,
  risk_level TEXT NOT NULL,
  requires_confirmation INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  last_run_id TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(plan_id, position),
  FOREIGN KEY(plan_id) REFERENCES hardware_output_plans(plan_id) ON DELETE CASCADE,
  CHECK(adapter_id IN ('pendant','base','arm','printer')),
  CHECK(risk_level IN ('low','medium','high')),
  CHECK(status IN (
    'pending','queued','running','confirmation_required','completed',
    'failed','skipped','canceled'
  ))
);

CREATE TABLE IF NOT EXISTS hardware_output_runs (
  run_id TEXT PRIMARY KEY,
  plan_id TEXT NOT NULL,
  status TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,
  requested_action_ids_json TEXT NOT NULL,
  confirmed_action_ids_json TEXT NOT NULL,
  blocked_action_ids_json TEXT NOT NULL,
  force INTEGER NOT NULL DEFAULT 0,
  result_json TEXT NOT NULL,
  error TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  FOREIGN KEY(plan_id) REFERENCES hardware_output_plans(plan_id) ON DELETE CASCADE,
  CHECK(status IN (
    'queued','running','awaiting_confirmation','completed','partial',
    'failed','canceled'
  ))
);

CREATE TABLE IF NOT EXISTS hardware_output_attempts (
  attempt_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  action_id TEXT NOT NULL,
  adapter_id TEXT NOT NULL,
  attempt_number INTEGER NOT NULL,
  status TEXT NOT NULL,
  request_json TEXT NOT NULL,
  response_json TEXT NOT NULL,
  error TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES hardware_output_runs(run_id) ON DELETE CASCADE,
  FOREIGN KEY(action_id) REFERENCES hardware_output_actions(action_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS k3_execution_log_outbox (
  log_id TEXT PRIMARY KEY,
  attempt_id TEXT NOT NULL UNIQUE,
  run_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  send_attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL,
  sent_at TEXT,
  FOREIGN KEY(attempt_id) REFERENCES hardware_output_attempts(attempt_id) ON DELETE CASCADE,
  FOREIGN KEY(run_id) REFERENCES hardware_output_runs(run_id) ON DELETE CASCADE,
  CHECK(status IN ('pending','sent'))
);

CREATE TABLE IF NOT EXISTS hardware_device_events (
  event_id TEXT PRIMARY KEY,
  adapter_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  status TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  CHECK(adapter_id IN ('pendant','base','arm','printer'))
);

CREATE TABLE IF NOT EXISTS k3_execution_log_outbox (
  log_id TEXT PRIMARY KEY,
  attempt_id TEXT NOT NULL UNIQUE,
  run_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  send_attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL,
  sent_at TEXT,
  FOREIGN KEY(attempt_id) REFERENCES hardware_output_attempts(attempt_id)
    ON DELETE CASCADE,
  FOREIGN KEY(run_id) REFERENCES hardware_output_runs(run_id)
    ON DELETE CASCADE,
  CHECK(status IN ('pending','sent'))
);

CREATE INDEX IF NOT EXISTS idx_events_status ON ingested_events(status);
CREATE INDEX IF NOT EXISTS idx_k3_log_outbox_ready
ON k3_execution_log_outbox(status,next_attempt_at,created_at);
CREATE INDEX IF NOT EXISTS idx_events_created ON ingested_events(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON sync_jobs(status);
CREATE INDEX IF NOT EXISTS idx_task_analyses_status ON event_task_analyses(status);
CREATE INDEX IF NOT EXISTS idx_canonical_tasks_candidates ON canonical_tasks(record_status,last_seen_at);
CREATE INDEX IF NOT EXISTS idx_canonical_tasks_project ON canonical_tasks(domain,project,stage);
CREATE INDEX IF NOT EXISTS idx_task_evidence_task ON task_evidence(task_id,created_at);
CREATE INDEX IF NOT EXISTS idx_task_evidence_event ON task_evidence(event_id,created_at);
CREATE INDEX IF NOT EXISTS idx_todo_event ON freetodo_todo_links(event_id);
CREATE INDEX IF NOT EXISTS idx_journal_event ON freetodo_journal_links(event_id);
CREATE INDEX IF NOT EXISTS idx_journal_sync_ready
ON journal_sync_state(status,next_attempt_at,lease_until);
CREATE INDEX IF NOT EXISTS idx_memory_status ON memory_outbox(status);
CREATE INDEX IF NOT EXISTS idx_pa_status ON personal_agent_outbox(status);
CREATE INDEX IF NOT EXISTS idx_skill_builds_status ON skill_builds(status,updated_at);
CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(status,updated_at);
CREATE INDEX IF NOT EXISTS idx_skill_versions_skill ON skill_versions(skill_id,created_at);
CREATE INDEX IF NOT EXISTS idx_skill_source_tasks_task ON skill_source_tasks(task_id,freetodo_todo_id);
CREATE INDEX IF NOT EXISTS idx_skill_runs_skill ON skill_runs(skill_id,started_at);
CREATE INDEX IF NOT EXISTS idx_skill_runs_task ON skill_runs(freetodo_todo_id,started_at);
CREATE INDEX IF NOT EXISTS idx_skill_feedback_run ON skill_feedback(run_id,created_at);
CREATE INDEX IF NOT EXISTS idx_skill_candidate_groups_status
ON skill_candidate_groups(status,updated_at);
CREATE INDEX IF NOT EXISTS idx_skill_task_profiles_todo
ON skill_task_profiles(freetodo_todo_id,updated_at);
CREATE INDEX IF NOT EXISTS idx_skill_task_matches_todo
ON skill_task_matches(freetodo_todo_id,status,score);
CREATE INDEX IF NOT EXISTS idx_skill_task_matches_skill
ON skill_task_matches(skill_id,status,updated_at);
CREATE INDEX IF NOT EXISTS idx_hardware_plans_journal
ON hardware_output_plans(journal_id,journal_version,created_at);
CREATE INDEX IF NOT EXISTS idx_hardware_plans_status
ON hardware_output_plans(status,updated_at);
CREATE INDEX IF NOT EXISTS idx_hardware_actions_plan
ON hardware_output_actions(plan_id,position);
CREATE INDEX IF NOT EXISTS idx_hardware_runs_status
ON hardware_output_runs(status,created_at);
CREATE INDEX IF NOT EXISTS idx_hardware_attempts_run
ON hardware_output_attempts(run_id,started_at);
CREATE INDEX IF NOT EXISTS idx_hardware_device_events
ON hardware_device_events(adapter_id,created_at);
CREATE INDEX IF NOT EXISTS idx_k3_execution_log_outbox
ON k3_execution_log_outbox(status,next_attempt_at,created_at);

