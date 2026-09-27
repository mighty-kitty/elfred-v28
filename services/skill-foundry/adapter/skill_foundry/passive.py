from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

from adapter.contracts import canonical_json, payload_hash
from adapter.skill_foundry.classification import PROFILE_VERSION
from adapter.skill_foundry.distiller import semantic_terms
from adapter.storage.store import now_iso


TASK_TYPE_LABELS = {
    "document_summary": "文档摘要",
    "software_development": "软件开发",
    "research": "调研分析",
    "data_analysis": "数据分析",
    "task_planning": "计划整理",
    "communication": "沟通写作",
    "unknown": "相似任务",
}

TASK_TYPE_KEYWORDS = {
    "document_summary": {
        "摘要", "总结", "要点", "概括", "阅读", "文档", "网页", "pdf",
        "summary", "summarize", "document",
    },
    "software_development": {
        "开发", "代码", "编程", "修复", "测试", "接口", "重构", "bug",
        "code", "implement", "refactor", "test",
    },
    "research": {
        "调研", "研究", "检索", "文献", "竞品", "资料", "分析报告",
        "research", "survey", "literature",
    },
    "data_analysis": {
        "数据", "统计", "图表", "报表", "指标", "可视化", "csv", "excel",
        "analysis", "dataset", "chart",
    },
    "task_planning": {
        "计划", "规划", "拆解", "排期", "清单", "路线图", "安排",
        "plan", "roadmap", "schedule",
    },
    "communication": {
        "邮件", "消息", "回复", "沟通", "通知", "文案", "汇报",
        "email", "message", "reply", "draft",
    },
}


def infer_task_type(text: str) -> str:
    normalized = str(text or "").casefold()
    scores = {
        task_type: sum(1 for keyword in keywords if keyword in normalized)
        for task_type, keywords in TASK_TYPE_KEYWORDS.items()
    }
    task_type, score = max(scores.items(), key=lambda item: item[1])
    return task_type if score else "unknown"


class PassiveSkillFoundry:
    """Continuously group completed work and prepare reviewable Skill drafts."""

    def __init__(self, service: Any) -> None:
        self.service = service
        self.store = service.store
        self.client = service.client
        settings = service.settings
        self.min_tasks = max(2, int(settings.skill_passive_min_tasks))
        self.max_tasks = max(self.min_tasks, int(settings.skill_passive_max_tasks))
        self.similarity_threshold = max(
            0.1, min(0.95, float(settings.skill_passive_similarity_threshold))
        )
        self._scan_lock = threading.Lock()

    def scan_once(self) -> dict[str, Any]:
        if not self._scan_lock.acquire(blocking=False):
            return {"status": "busy", "groups": 0, "draftsCreated": 0}
        try:
            profiles = [
                profile
                for todo in self.client.list_todos()
                if (profile := self._profile(todo)) is not None
            ]
            groups = self._cluster(profiles)
            drafts_created = 0
            observed = 0
            for group in groups:
                observed += 1
                record = self._upsert_group(group)
                if not group["eligible"]:
                    continue
                task_ids = group["taskIds"][-self.max_tasks :]
                build_hash = payload_hash(
                    {
                        "taskIds": task_ids,
                        "distillerVersion": self.service.distiller.VERSION,
                        "maturityVersion": (
                            self.service.maturity_assessor.VERSION
                        ),
                        "semanticProfileVersion": PROFILE_VERSION,
                        "profileEvidenceHashes": group.get(
                            "profileEvidenceHashes"
                        )
                        or [],
                    }
                )
                existing_skill = record.get("skill_id") or self._related_skill(
                    task_ids
                )
                if record.get("last_build_hash") == build_hash:
                    stored_profile = json.loads(
                        record.get("profile_json") or "{}"
                    )
                    if existing_skill and not stored_profile.get("maturity"):
                        skill = self.service.registry.get(str(existing_skill))
                        maturity = (
                            (
                                (skill or {}).get("current_version") or {}
                            ).get("workflow")
                            or {}
                        ).get("maturity")
                        if maturity:
                            self._update_group(
                                record["group_id"],
                                status=(
                                    "draft_ready"
                                    if maturity.get("ready")
                                    else str(
                                        maturity.get("stage") or "observing"
                                    )
                                ),
                                task_ids=task_ids,
                                profile={**group, "maturity": maturity},
                                skill_id=str(existing_skill),
                                error=None,
                            )
                    continue
                self._update_group(
                    record["group_id"],
                    status="building",
                    task_ids=task_ids,
                    profile=group,
                    skill_id=existing_skill,
                    error=None,
                )
                try:
                    result = self.service.create_draft(
                        task_ids,
                        skill_id=str(existing_skill) if existing_skill else None,
                    )
                    maturity = result.get("maturity") or {}
                    group_profile = {
                        **group,
                        "maturity": maturity,
                    }
                    self._update_group(
                        record["group_id"],
                        status=(
                            "draft_ready"
                            if maturity.get("ready")
                            else str(maturity.get("stage") or "observing")
                        ),
                        task_ids=task_ids,
                        profile=group_profile,
                        skill_id=result["skill"]["skill_id"],
                        last_build_hash=build_hash,
                        last_build_id=result["build"]["build_id"],
                        error=None,
                    )
                    drafts_created += 1
                except Exception as error:
                    self._update_group(
                        record["group_id"],
                        status="failed",
                        task_ids=task_ids,
                        profile=group,
                        skill_id=existing_skill,
                        error=str(error)[:1000],
                    )
            return {
                "status": "completed",
                "completedTasks": len(profiles),
                "groups": observed,
                "draftsCreated": drafts_created,
            }
        finally:
            self._scan_lock.release()

    def groups(self) -> list[dict[str, Any]]:
        with self.store.connect() as conn:
            rows = conn.execute(
                """SELECT * FROM skill_candidate_groups
                ORDER BY updated_at DESC"""
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["task_ids"] = json.loads(item.pop("task_ids_json"))
            item["profile"] = json.loads(item.pop("profile_json"))
            output.append(item)
        return output

    def _profile(self, todo: dict[str, Any]) -> dict[str, Any] | None:
        if str(todo.get("status") or "").casefold() != "completed":
            return None
        todo_id = todo.get("id")
        if todo_id is None:
            return None
        text = " ".join(
            str(todo.get(key) or "")
            for key in ("name", "summary", "description", "user_notes")
        ).strip()
        if len(text) < 8:
            return None
        canonical = self.store.canonical_task_by_freetodo_id(int(todo_id)) or {}
        metadata = canonical.get("metadata") or {}
        trajectory = self._captured_trajectory(
            str(canonical.get("task_id") or "")
        )
        explicit_type = str(metadata.get("task_type") or "").strip()
        if not explicit_type:
            explicit_type = str(trajectory.get("taskType") or "").strip()
        task_type = explicit_type or infer_task_type(text)
        category = self._normalize_label(todo.get("categories"))
        project = self._normalize_label(canonical.get("project"))
        semantic_profile = self.service.semantic_profiler.profile_task(
            task_id=str(canonical.get("task_id") or f"freetodo_{todo_id}"),
            todo_id=int(todo_id),
            text=text,
            explicit_type=task_type if explicit_type else "",
            trajectory=trajectory,
            category=category,
            project=project,
        )
        return {
            "todoId": int(todo_id),
            "taskId": str(canonical.get("task_id") or f"freetodo_{todo_id}"),
            "title": str(todo.get("name") or "未命名任务"),
            "taskType": semantic_profile["taskType"],
            "taskFamily": semantic_profile["taskFamily"],
            "goalClass": semantic_profile["goalClass"],
            "inputKinds": semantic_profile["inputKinds"],
            "outputKinds": semantic_profile["outputKinds"],
            "workflowFingerprint": semantic_profile[
                "workflowFingerprint"
            ],
            "classification": semantic_profile["classification"],
            "explicitType": bool(explicit_type),
            "category": category,
            "project": project,
            "terms": sorted(semantic_terms(text)),
            "workflowSignature": [
                (
                    str(step.get("actionType") or step.get("action") or ""),
                    str(step.get("tool") or ""),
                )
                for step in trajectory.get("steps") or []
                if isinstance(step, dict)
            ],
            "completedAt": str(
                todo.get("completed_at") or todo.get("updated_at") or ""
            ),
        }

    def _captured_trajectory(self, task_id: str) -> dict[str, Any]:
        if not task_id:
            return {}
        for item in self.store.task_evidence(task_id=task_id, limit=100):
            trajectory = (item.get("evidence") or {}).get("trajectory")
            if isinstance(trajectory, dict):
                return trajectory
        return {}

    def _cluster(self, profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        profiles.sort(
            key=lambda item: (item.get("completedAt") or "", item["todoId"])
        )
        clusters: list[list[dict[str, Any]]] = []
        for profile in profiles:
            best: list[dict[str, Any]] | None = None
            best_score = 0.0
            for cluster in clusters:
                score = self._similarity(profile, cluster)
                if score >= self.similarity_threshold and score > best_score:
                    best = cluster
                    best_score = score
            if best is None:
                clusters.append([profile])
            else:
                best.append(profile)

        output = []
        for cluster in clusters:
            types = [
                item["taskType"]
                for item in cluster
                if item["taskType"] != "unknown"
            ]
            task_type = max(set(types), key=types.count) if types else "unknown"
            families = [
                item["taskFamily"]
                for item in cluster
                if item.get("taskFamily")
            ]
            task_family = (
                max(set(families), key=families.count)
                if families
                else task_type
            )
            explicit_count = sum(
                1
                for item in cluster
                if item["explicitType"] and item["taskType"] == task_type
            )
            common_terms = set(cluster[0]["terms"])
            for item in cluster[1:]:
                common_terms.intersection_update(item["terms"])
            eligible = len(cluster) >= (
                self.min_tasks if explicit_count >= self.min_tasks else max(3, self.min_tasks)
            )
            representative = cluster[0]
            fingerprint = str(
                representative.get("workflowFingerprint") or ""
            )[:16]
            if not fingerprint:
                fingerprint_source = canonical_json(
                    representative.get("workflowSignature")
                    or representative.get("terms")
                    or [representative["taskId"]]
                )
                fingerprint = hashlib.sha256(
                    fingerprint_source.encode("utf-8")
                ).hexdigest()[:16]
            classifications = [
                item.get("classification") or {} for item in cluster
            ]
            model_count = sum(
                str(item.get("mode") or "") in {"model", "codex", "hermes"}
                for item in classifications
            )
            confidence = round(
                sum(
                    float(item.get("confidence") or 0)
                    for item in classifications
                )
                / max(1, len(classifications))
                * 100
            )
            group_key = (
                f"type:{task_type}:family:{task_family}:pattern:{fingerprint}"
            )
            output.append(
                {
                    "groupKey": group_key,
                    "label": TASK_TYPE_LABELS.get(task_type, task_type),
                    "taskType": task_type,
                    "taskFamily": task_family,
                    "workflowFingerprint": fingerprint,
                    "classification": {
                        "mode": (
                            "codex"
                            if model_count == len(classifications)
                            and classifications
                            else (
                                "mixed"
                                if model_count
                                else "deterministic"
                            )
                        ),
                        "confidence": confidence,
                        "modelProfiles": model_count,
                        "totalProfiles": len(classifications),
                        "cacheHits": sum(
                            bool(item.get("cacheHit"))
                            for item in classifications
                        ),
                    },
                    "profileEvidenceHashes": sorted(
                        str(item.get("evidenceHash") or "")
                        for item in classifications
                        if item.get("evidenceHash")
                    ),
                    "taskIds": [item["todoId"] for item in cluster],
                    "taskCount": len(cluster),
                    "eligible": eligible,
                    "commonTerms": sorted(common_terms)[:20],
                    "tasks": [
                        {
                            "todoId": item["todoId"],
                            "title": item["title"],
                            "completedAt": item["completedAt"],
                        }
                        for item in cluster
                    ],
                }
            )
        return output

    def _similarity(
        self, profile: dict[str, Any], cluster: list[dict[str, Any]]
    ) -> float:
        task_type = profile["taskType"]
        cluster_types = {item["taskType"] for item in cluster}
        family = str(profile.get("taskFamily") or "")
        cluster_families = {
            str(item.get("taskFamily") or "") for item in cluster
        }
        family_confident = float(
            (profile.get("classification") or {}).get("confidence") or 0
        ) >= 0.75
        cluster_family_confident = all(
            float(
                (item.get("classification") or {}).get("confidence") or 0
            )
            >= 0.75
            for item in cluster
        )
        if (
            family
            and family != "unknown_workflow"
            and cluster_families
            and family not in cluster_families
            and family_confident
            and cluster_family_confident
        ):
            return 0.0
        type_score = (
            0.25
            if task_type != "unknown" and task_type in cluster_types
            else 0.0
        )
        workflow = profile.get("workflowSignature") or []
        workflow_scores = [
            SequenceMatcher(
                None,
                workflow,
                item.get("workflowSignature") or [],
                autojunk=False,
            ).ratio()
            for item in cluster
            if workflow and item.get("workflowSignature")
        ]
        workflow_score = max(workflow_scores) if workflow_scores else 0.0
        if workflow_scores and workflow_score < 0.45:
            return 0.0
        terms = set(profile["terms"])
        cluster_terms = set().union(*(set(item["terms"]) for item in cluster))
        semantic = (
            len(terms & cluster_terms) / len(terms | cluster_terms)
            if terms and cluster_terms
            else 0.0
        )
        same_category = bool(
            profile["category"]
            and any(profile["category"] == item["category"] for item in cluster)
        )
        same_project = bool(
            profile["project"]
            and any(profile["project"] == item["project"] for item in cluster)
        )
        return min(
            1.0,
            type_score
            + (0.12 if family and family in cluster_families else 0.0)
            + workflow_score * 0.50
            + semantic * 0.05
            + (0.04 if same_category else 0.0)
            + (0.04 if same_project else 0.0),
        )

    def _upsert_group(self, group: dict[str, Any]) -> dict[str, Any]:
        timestamp = now_iso()
        group_key = str(group["groupKey"])
        group_id = "skillgroup_" + hashlib.sha256(
            group_key.encode("utf-8")
        ).hexdigest()[:24]
        status = "ready" if group["eligible"] else "observing"
        with self.store.transaction() as conn:
            legacy_key = f"type:{group.get('taskType') or 'unknown'}"
            previous_key = (
                f"type:{group.get('taskType') or 'unknown'}:"
                f"pattern:{str(group.get('workflowFingerprint') or '')[:12]}"
            )
            current = conn.execute(
                "SELECT group_id FROM skill_candidate_groups WHERE group_key=?",
                (group_key,),
            ).fetchone()
            legacy = conn.execute(
                """SELECT group_id FROM skill_candidate_groups
                WHERE group_key IN (?,?) ORDER BY
                CASE WHEN group_key=? THEN 0 ELSE 1 END LIMIT 1""",
                (previous_key, legacy_key, previous_key),
            ).fetchone()
            if current is None and legacy is not None:
                conn.execute(
                    """UPDATE skill_candidate_groups
                    SET group_key=?,updated_at=? WHERE group_id=?""",
                    (group_key, timestamp, legacy["group_id"]),
                )
            stored = conn.execute(
                """SELECT profile_json FROM skill_candidate_groups
                WHERE group_key=?""",
                (group_key,),
            ).fetchone()
            profile_payload = dict(group)
            if stored is not None:
                stored_profile = json.loads(stored["profile_json"])
                if stored_profile.get("maturity"):
                    profile_payload["maturity"] = stored_profile["maturity"]
            conn.execute(
                """INSERT INTO skill_candidate_groups
                (group_id,group_key,label,status,skill_id,task_ids_json,
                 profile_json,last_build_hash,last_build_id,error,created_at,updated_at)
                VALUES(?,?,?,?,NULL,?,?,NULL,NULL,NULL,?,?)
                ON CONFLICT(group_key) DO UPDATE SET
                label=excluded.label,
                status=CASE
                  WHEN skill_candidate_groups.status IN (
                    'building','draft_ready','evidence_gap',
                    'pattern_forming','validating_reproduction'
                  )
                    THEN skill_candidate_groups.status
                  ELSE excluded.status
                END,
                task_ids_json=excluded.task_ids_json,
                profile_json=excluded.profile_json,
                updated_at=excluded.updated_at""",
                (
                    group_id,
                    group_key,
                    group["label"],
                    status,
                    canonical_json(group["taskIds"]),
                    canonical_json(profile_payload),
                    timestamp,
                    timestamp,
                ),
            )
            row = conn.execute(
                "SELECT * FROM skill_candidate_groups WHERE group_key=?",
                (group_key,),
            ).fetchone()
        return dict(row)

    def _update_group(
        self,
        group_id: str,
        *,
        status: str,
        task_ids: list[int],
        profile: dict[str, Any],
        skill_id: str | None,
        error: str | None,
        last_build_hash: str | None = None,
        last_build_id: str | None = None,
    ) -> None:
        with self.store.transaction() as conn:
            conn.execute(
                """UPDATE skill_candidate_groups SET status=?,skill_id=?,
                task_ids_json=?,profile_json=?,
                last_build_hash=COALESCE(?,last_build_hash),
                last_build_id=COALESCE(?,last_build_id),
                error=?,updated_at=? WHERE group_id=?""",
                (
                    status,
                    skill_id,
                    canonical_json(task_ids),
                    canonical_json(profile),
                    last_build_hash,
                    last_build_id,
                    error,
                    now_iso(),
                    group_id,
                ),
            )

    def _related_skill(self, task_ids: list[int]) -> str | None:
        wanted = set(task_ids)
        best_skill: str | None = None
        best_overlap = 0.0
        for skill in self.service.registry.list():
            source_ids = {
                int(item["freetodo_todo_id"])
                for item in skill.get("source_tasks") or []
            }
            if not source_ids:
                continue
            overlap = len(wanted & source_ids) / len(source_ids)
            if overlap > best_overlap:
                best_overlap = overlap
                best_skill = str(skill["skill_id"])
        return best_skill if best_overlap >= 0.5 else None

    @staticmethod
    def _normalize_label(value: Any) -> str:
        label = re.sub(r"\s+", " ", str(value or "")).strip().casefold()
        return "" if label in {"未分类", "none", "null"} else label


class PassiveSkillFoundryWorker:
    def __init__(self, service: Any) -> None:
        self.engine = PassiveSkillFoundry(service.skill_foundry)
        self.interval = max(
            1.0, float(service.settings.skill_passive_interval_seconds)
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._status: dict[str, Any] = {
            "state": "created",
            "scanCount": 0,
            "draftsCreated": 0,
            "lastResult": None,
            "lastError": None,
            "lastScanAt": None,
        }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run,
            name="elfred-passive-skill-foundry",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5.0)

    def status(self) -> dict[str, Any]:
        with self._lock:
            result = dict(self._status)
        result["groups"] = self.engine.groups()
        return result

    def process_once(self) -> dict[str, Any]:
        result = self.engine.scan_once()
        task_matching = self.engine.service.scan_active_task_matches()
        result["taskMatching"] = task_matching
        with self._lock:
            self._status.update(
                {
                    "state": "watching",
                    "scanCount": self._status["scanCount"] + 1,
                    "draftsCreated": self._status["draftsCreated"]
                    + int(result.get("draftsCreated") or 0),
                    "lastResult": result,
                    "lastError": None,
                    "lastScanAt": datetime.now().astimezone().isoformat(),
                }
            )
        return result

    def _run(self) -> None:
        with self._lock:
            self._status["state"] = "starting"
        while not self._stop.is_set():
            try:
                self.process_once()
            except Exception as error:
                with self._lock:
                    self._status.update(
                        {
                            "state": "degraded",
                            "lastError": str(error),
                            "lastScanAt": datetime.now().astimezone().isoformat(),
                        }
                    )
            self._stop.wait(self.interval)
        with self._lock:
            self._status["state"] = "stopped"
