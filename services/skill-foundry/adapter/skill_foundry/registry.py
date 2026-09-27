from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from adapter.contracts import canonical_json
from adapter.skill_foundry.models import BUILD_STATES, SKILL_STATES
from adapter.storage.store import now_iso


class SkillRegistry:
    """Versioned SQLite registry plus an Agent Skills-compatible file projection."""

    def __init__(self, store: Any, skill_root: Path) -> None:
        self.store = store
        self.skill_root = Path(skill_root)
        self.skill_root.mkdir(parents=True, exist_ok=True)

    def create_build(self, task_ids: list[int]) -> dict[str, Any]:
        build_id = "build_" + uuid.uuid4().hex
        timestamp = now_iso()
        history = [
            {
                "status": "fusing",
                "progress": 4,
                "detail": "已接收来源任务，准备读取证据",
                "at": timestamp,
            }
        ]
        with self.store.transaction() as conn:
            conn.execute(
                """INSERT INTO skill_builds
                (build_id,status,source_task_ids_json,status_history_json,
                 skill_id,version_id,error,created_at,updated_at)
                VALUES(?,'fusing',?,?,NULL,NULL,NULL,?,?)""",
                (
                    build_id,
                    canonical_json(task_ids),
                    canonical_json(history),
                    timestamp,
                    timestamp,
                ),
            )
        return self.build(build_id) or {}

    def update_build(
        self,
        build_id: str,
        status: str,
        *,
        skill_id: str | None = None,
        version_id: str | None = None,
        error: str | None = None,
        progress: int | None = None,
        detail: str | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if status not in BUILD_STATES:
            raise ValueError(f"invalid build state: {status}")
        timestamp = now_iso()
        with self.store.transaction() as conn:
            current = conn.execute(
                "SELECT * FROM skill_builds WHERE build_id=?", (build_id,)
            ).fetchone()
            if current is None:
                raise KeyError(build_id)
            history = json.loads(current["status_history_json"])
            previous = history[-1] if history else {}
            history.append(
                {
                    "status": status,
                    "progress": max(
                        0,
                        min(
                            100,
                            int(
                                progress
                                if progress is not None
                                else previous.get("progress") or 0
                            ),
                        ),
                    ),
                    "detail": detail or previous.get("detail") or status,
                    "metrics": metrics or previous.get("metrics") or {},
                    "at": timestamp,
                }
            )
            conn.execute(
                """UPDATE skill_builds SET status=?,status_history_json=?,
                skill_id=COALESCE(?,skill_id),version_id=COALESCE(?,version_id),
                error=?,updated_at=? WHERE build_id=?""",
                (
                    status,
                    canonical_json(history),
                    skill_id,
                    version_id,
                    error,
                    timestamp,
                    build_id,
                ),
            )
        return self.build(build_id) or {}

    def build(self, build_id: str) -> dict[str, Any] | None:
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT * FROM skill_builds WHERE build_id=?", (build_id,)
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["source_task_ids"] = json.loads(
            item.pop("source_task_ids_json")
        )
        item["status_history"] = json.loads(item.pop("status_history_json"))
        latest = item["status_history"][-1] if item["status_history"] else {}
        item["progress"] = int(latest.get("progress") or 0)
        item["stage_detail"] = str(latest.get("detail") or item["status"])
        item["metrics"] = latest.get("metrics") or {}
        return item

    def next_version(self, skill_id: str | None) -> str:
        if not skill_id:
            return "0.1.0"
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT version FROM skill_versions WHERE skill_id=?",
                (skill_id,),
            ).fetchall()
        versions = []
        for row in rows:
            try:
                versions.append(tuple(int(part) for part in row["version"].split(".")))
            except (TypeError, ValueError):
                continue
        if not versions:
            return "0.1.0"
        major, minor, patch = max(versions)
        return f"{major}.{minor}.{patch + 1}"

    def register_draft(
        self,
        *,
        compiled: dict[str, Any],
        distilled: dict[str, Any],
        validation: dict[str, Any],
        trajectories: list[dict[str, Any]],
        version: str,
        skill_id: str | None = None,
    ) -> dict[str, Any]:
        timestamp = now_iso()
        current = self.get(skill_id) if skill_id else None
        if skill_id and current is None:
            raise KeyError(skill_id)
        if current and current["status"] == "deprecated":
            raise ValueError("deprecated skills cannot be regenerated")
        if current:
            slug = str(current["slug"])
            name = str(current["name"])
            skill_id = str(current["skill_id"])
        else:
            slug = self._unique_slug(str(compiled["slug"]))
            name = str(distilled["name"])
            skill_id = "skill_" + uuid.uuid4().hex
        version_id = "skillver_" + uuid.uuid4().hex
        artifact_path = self._write_artifacts(
            slug=slug,
            version=version,
            compiled=compiled,
            validation=validation,
        )
        with self.store.transaction() as conn:
            conn.execute(
                """INSERT INTO skills
                (skill_id,slug,name,description,status,current_version_id,
                 published_version_id,trigger_terms_json,created_at,updated_at)
                VALUES(?,?,?,?, 'draft',?,NULL,?,?,?)
                ON CONFLICT(skill_id) DO UPDATE SET
                description=excluded.description,
                status=CASE
                  WHEN skills.status IN ('approved','active')
                    THEN skills.status
                  ELSE 'draft'
                END,
                current_version_id=excluded.current_version_id,
                trigger_terms_json=excluded.trigger_terms_json,
                updated_at=excluded.updated_at""",
                (
                    skill_id,
                    slug,
                    name,
                    str(distilled["description"]),
                    version_id,
                    canonical_json(distilled.get("triggers") or []),
                    timestamp,
                    timestamp,
                ),
            )
            conn.execute(
                """INSERT INTO skill_versions
                (version_id,skill_id,version,status,skill_markdown,workflow_json,
                 distilled_json,validation_json,artifact_path,created_at)
                VALUES(?,?,?,'draft',?,?,?,?,?,?)""",
                (
                    version_id,
                    skill_id,
                    version,
                    compiled["skillMarkdown"],
                    canonical_json(compiled["workflow"]),
                    canonical_json(distilled),
                    canonical_json(validation),
                    str(artifact_path),
                    timestamp,
                ),
            )
            for trajectory in trajectories:
                conn.execute(
                    """INSERT INTO skill_source_tasks
                    (skill_id,version_id,task_id,freetodo_todo_id,
                     evidence_refs_json,created_at)
                    VALUES(?,?,?,?,?,?)""",
                    (
                        skill_id,
                        version_id,
                        trajectory["taskId"],
                        int(trajectory["freetodoTodoId"]),
                        canonical_json(trajectory.get("evidenceRefs") or []),
                        timestamp,
                    ),
                )
            conn.execute(
                "INSERT INTO audit_logs(created_at,action,target,detail_json) VALUES(?,?,?,?)",
                (
                    timestamp,
                    "skill_draft_registered",
                    skill_id,
                    canonical_json(
                        {
                            "version": version,
                            "source_task_ids": [
                                item["taskId"] for item in trajectories
                            ],
                        }
                    ),
                ),
            )
        return self.get(skill_id) or {}

    def approve(
        self, skill_id: str, *, allow_heuristic: bool = False
    ) -> dict[str, Any]:
        timestamp = now_iso()
        with self.store.transaction() as conn:
            skill = conn.execute(
                "SELECT * FROM skills WHERE skill_id=?", (skill_id,)
            ).fetchone()
            if skill is None:
                raise KeyError(skill_id)
            if skill["status"] not in {"draft", "pending_review", "approved"}:
                raise ValueError(
                    f"skill in state {skill['status']} cannot be approved"
                )
            version = conn.execute(
                "SELECT * FROM skill_versions WHERE version_id=?",
                (skill["current_version_id"],),
            ).fetchone()
            if version is None:
                raise ValueError("skill current version is missing")
            validation = json.loads(version["validation_json"])
            if not validation.get("valid"):
                raise ValueError("invalid skill draft cannot be approved")
            workflow = json.loads(version["workflow_json"])
            evidence = workflow.get("evidenceRequirements") or {}
            if not evidence.get("complete"):
                missing = ", ".join(evidence.get("missing") or [])
                raise ValueError(
                    "incomplete evidence cannot be approved"
                    + (f": {missing}" if missing else "")
                )
            maturity = workflow.get("maturity") or {}
            if not maturity.get("ready"):
                blockers = ", ".join(
                    str(item.get("code") or "")
                    for item in maturity.get("blockers") or []
                    if isinstance(item, dict)
                )
                raise ValueError(
                    "immature skill cannot be approved"
                    + (f": {blockers}" if blockers else "")
                )
            distilled = json.loads(version["distilled_json"])
            generation = distilled.get("generation") or {}
            if (
                generation.get("mode") not in {"model", "codex", "hermes"}
                and not allow_heuristic
            ):
                raise ValueError(
                    "heuristic draft requires an explicit approval waiver"
                )
            conn.execute(
                """UPDATE skills SET status='approved',
                published_version_id=current_version_id,updated_at=?
                WHERE skill_id=?""",
                (timestamp, skill_id),
            )
            conn.execute(
                "UPDATE skill_versions SET status='approved' WHERE version_id=?",
                (skill["current_version_id"],),
            )
            conn.execute(
                "INSERT INTO audit_logs(created_at,action,target,detail_json) VALUES(?,?,?,?)",
                (
                    timestamp,
                    "skill_approved",
                    skill_id,
                    canonical_json({"version_id": skill["current_version_id"]}),
                ),
            )
        return self.get(skill_id) or {}

    def get(self, skill_id: str | None) -> dict[str, Any] | None:
        if not skill_id:
            return None
        with self.store.connect() as conn:
            skill = conn.execute(
                "SELECT * FROM skills WHERE skill_id=?", (skill_id,)
            ).fetchone()
            if skill is None:
                return None
            version = conn.execute(
                "SELECT * FROM skill_versions WHERE version_id=?",
                (skill["current_version_id"],),
            ).fetchone()
            published_version = (
                conn.execute(
                    "SELECT * FROM skill_versions WHERE version_id=?",
                    (skill["published_version_id"],),
                ).fetchone()
                if skill["published_version_id"]
                else None
            )
            versions = conn.execute(
                "SELECT version_id,version,status,artifact_path,created_at "
                "FROM skill_versions WHERE skill_id=? ORDER BY created_at",
                (skill_id,),
            ).fetchall()
            sources = conn.execute(
                "SELECT * FROM skill_source_tasks WHERE version_id=? "
                "ORDER BY created_at,task_id",
                (skill["current_version_id"],),
            ).fetchall()
            published_sources = (
                conn.execute(
                    "SELECT * FROM skill_source_tasks WHERE version_id=? "
                    "ORDER BY created_at,task_id",
                    (skill["published_version_id"],),
                ).fetchall()
                if skill["published_version_id"]
                else []
            )
        item = dict(skill)
        item["trigger_terms"] = json.loads(item.pop("trigger_terms_json"))
        item["auto_execute_enabled"] = bool(
            item.get("auto_execute_enabled")
        )
        item["current_version"] = self._decode_version(version)
        item["published_version"] = self._decode_version(published_version)
        item["has_pending_update"] = bool(
            item.get("published_version_id")
            and item.get("current_version_id")
            != item.get("published_version_id")
        )
        item["versions"] = [dict(row) for row in versions]
        item["source_tasks"] = []
        for row in sources:
            source = dict(row)
            source["evidence_refs"] = json.loads(
                source.pop("evidence_refs_json")
            )
            item["source_tasks"].append(source)
        item["published_source_tasks"] = []
        for row in published_sources:
            source = dict(row)
            source["evidence_refs"] = json.loads(
                source.pop("evidence_refs_json")
            )
            item["published_source_tasks"].append(source)
        return item

    def list(self, statuses: set[str] | None = None) -> list[dict[str, Any]]:
        query = "SELECT skill_id FROM skills"
        params: list[Any] = []
        if statuses:
            invalid = statuses.difference(SKILL_STATES)
            if invalid:
                raise ValueError(f"invalid skill states: {sorted(invalid)}")
            marks = ",".join("?" for _ in statuses)
            query += f" WHERE status IN ({marks})"
            params.extend(sorted(statuses))
        query += " ORDER BY updated_at DESC"
        with self.store.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            item
            for row in rows
            if (item := self.get(str(row["skill_id"]))) is not None
        ]

    def set_auto_execute(
        self,
        skill_id: str,
        enabled: bool,
    ) -> dict[str, Any]:
        timestamp = now_iso()
        with self.store.transaction() as conn:
            cursor = conn.execute(
                """UPDATE skills SET auto_execute_enabled=?,updated_at=?
                WHERE skill_id=?""",
                (int(enabled), timestamp, skill_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(skill_id)
            conn.execute(
                """UPDATE skill_task_matches
                SET auto_execute=?,updated_at=?
                WHERE skill_id=? AND status='suggested'""",
                (int(enabled), timestamp, skill_id),
            )
            conn.execute(
                """INSERT INTO audit_logs
                (created_at,action,target,detail_json) VALUES(?,?,?,?)""",
                (
                    timestamp,
                    "skill_auto_execute_changed",
                    skill_id,
                    canonical_json({"enabled": bool(enabled)}),
                ),
            )
        return self.get(skill_id) or {}

    def upsert_task_matches(
        self,
        *,
        freetodo_todo_id: int,
        task_id: str | None,
        task_context: dict[str, Any],
        matches: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        timestamp = now_iso()
        active_skill_ids: list[str] = []
        with self.store.transaction() as conn:
            for match in matches:
                skill_id = str(match["skillId"])
                version_id = str(match["versionId"])
                active_skill_ids.append(skill_id)
                conn.execute(
                    """INSERT INTO skill_task_matches
                    (match_id,freetodo_todo_id,task_id,skill_id,version_id,
                     score,reasons_json,task_context_json,status,auto_execute,
                     last_run_id,error,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,'suggested',?,NULL,NULL,?,?)
                    ON CONFLICT(freetodo_todo_id,skill_id) DO UPDATE SET
                      task_id=excluded.task_id,
                      version_id=excluded.version_id,
                      score=excluded.score,
                      reasons_json=excluded.reasons_json,
                      task_context_json=excluded.task_context_json,
                      status=CASE
                        WHEN skill_task_matches.version_id=excluded.version_id
                         AND skill_task_matches.status IN (
                           'completed','failed','dismissed',
                           'confirmation_required'
                         )
                        THEN skill_task_matches.status
                        ELSE 'suggested'
                      END,
                      auto_execute=excluded.auto_execute,
                      last_run_id=CASE
                        WHEN skill_task_matches.version_id=excluded.version_id
                        THEN skill_task_matches.last_run_id
                        ELSE NULL
                      END,
                      error=CASE
                        WHEN skill_task_matches.version_id=excluded.version_id
                        THEN skill_task_matches.error
                        ELSE NULL
                      END,
                      updated_at=excluded.updated_at""",
                    (
                        "skillmatch_" + uuid.uuid4().hex,
                        int(freetodo_todo_id),
                        task_id,
                        skill_id,
                        version_id,
                        float(match.get("score") or 0),
                        canonical_json(match.get("whyMatched") or []),
                        canonical_json(task_context),
                        int(bool(match.get("autoExecuteEnabled"))),
                        timestamp,
                        timestamp,
                    ),
                )
            if active_skill_ids:
                marks = ",".join("?" for _ in active_skill_ids)
                conn.execute(
                    f"""UPDATE skill_task_matches SET status='stale',
                    updated_at=? WHERE freetodo_todo_id=?
                    AND status='suggested' AND skill_id NOT IN ({marks})""",
                    (timestamp, int(freetodo_todo_id), *active_skill_ids),
                )
            else:
                conn.execute(
                    """UPDATE skill_task_matches SET status='stale',
                    updated_at=? WHERE freetodo_todo_id=?
                    AND status='suggested'""",
                    (timestamp, int(freetodo_todo_id)),
                )
        return self.task_matches(freetodo_todo_id=freetodo_todo_id)

    def task_matches(
        self,
        *,
        freetodo_todo_id: int | None = None,
        statuses: set[str] | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT m.*,s.name,s.description,s.slug "
            "FROM skill_task_matches m JOIN skills s ON s.skill_id=m.skill_id"
        )
        clauses: list[str] = []
        params: list[Any] = []
        if freetodo_todo_id is not None:
            clauses.append("m.freetodo_todo_id=?")
            params.append(int(freetodo_todo_id))
        if statuses:
            marks = ",".join("?" for _ in statuses)
            clauses.append(f"m.status IN ({marks})")
            params.extend(sorted(statuses))
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY m.score DESC,m.updated_at DESC LIMIT ?"
        params.append(max(1, min(5000, int(limit))))
        with self.store.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._decode_match(row) for row in rows]

    def update_task_match(
        self,
        *,
        freetodo_todo_id: int,
        skill_id: str,
        status: str,
        run_id: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        with self.store.transaction() as conn:
            conn.execute(
                """UPDATE skill_task_matches SET status=?,
                last_run_id=COALESCE(?,last_run_id),error=?,updated_at=?
                WHERE freetodo_todo_id=? AND skill_id=?""",
                (
                    status,
                    run_id,
                    str(error)[:2000] if error else None,
                    now_iso(),
                    int(freetodo_todo_id),
                    skill_id,
                ),
            )
        matches = self.task_matches(
            freetodo_todo_id=freetodo_todo_id,
            limit=50,
        )
        return next(
            (item for item in matches if item["skill_id"] == skill_id),
            None,
        )

    def stale_missing_task_matches(
        self,
        freetodo_todo_ids: set[int],
    ) -> int:
        timestamp = now_iso()
        with self.store.transaction() as conn:
            if freetodo_todo_ids:
                marks = ",".join("?" for _ in freetodo_todo_ids)
                cursor = conn.execute(
                    f"""UPDATE skill_task_matches SET status='stale',
                    updated_at=? WHERE status='suggested'
                    AND freetodo_todo_id NOT IN ({marks})""",
                    (timestamp, *sorted(freetodo_todo_ids)),
                )
            else:
                cursor = conn.execute(
                    """UPDATE skill_task_matches SET status='stale',
                    updated_at=? WHERE status='suggested'""",
                    (timestamp,),
                )
        return int(cursor.rowcount)

    def create_run(
        self,
        *,
        skill_id: str,
        version_id: str,
        task_id: str | None,
        freetodo_todo_id: int | None,
        inputs: dict[str, Any],
        plan: dict[str, Any],
        requires_confirmation: bool,
    ) -> dict[str, Any]:
        run_id = "skillrun_" + uuid.uuid4().hex
        with self.store.transaction() as conn:
            conn.execute(
                """INSERT INTO skill_runs
                (run_id,skill_id,version_id,task_id,freetodo_todo_id,status,
                 inputs_json,plan_json,result_json,error,requires_confirmation,
                 started_at,finished_at)
                VALUES(?,?,?,?,?,'running',?,?,'{}',NULL,?,?,NULL)""",
                (
                    run_id,
                    skill_id,
                    version_id,
                    task_id,
                    freetodo_todo_id,
                    canonical_json(inputs),
                    canonical_json(plan),
                    int(requires_confirmation),
                    now_iso(),
                ),
            )
        return self.run(run_id) or {}

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        with self.store.transaction() as conn:
            cursor = conn.execute(
                """UPDATE skill_runs SET status=?,result_json=?,error=?,
                finished_at=? WHERE run_id=?""",
                (
                    status,
                    canonical_json(result or {}),
                    str(error)[:2000] if error else None,
                    now_iso(),
                    run_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(run_id)
        return self.run(run_id) or {}

    def run(self, run_id: str) -> dict[str, Any] | None:
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT * FROM skill_runs WHERE run_id=?", (run_id,)
            ).fetchone()
        return self._decode_run(row)

    def runs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM skill_runs ORDER BY started_at DESC LIMIT ?",
                (max(1, min(1000, int(limit))),),
            ).fetchall()
        return [
            item for row in rows if (item := self._decode_run(row)) is not None
        ]

    def record_feedback(
        self,
        run_id: str,
        *,
        rating: int | None,
        outcome: str | None,
        comment: str | None,
        corrections: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if self.run(run_id) is None:
            raise KeyError(run_id)
        if rating is not None and not 1 <= int(rating) <= 5:
            raise ValueError("rating must be between 1 and 5")
        feedback_id = "feedback_" + uuid.uuid4().hex
        timestamp = now_iso()
        with self.store.transaction() as conn:
            conn.execute(
                """INSERT INTO skill_feedback
                (feedback_id,run_id,rating,outcome,comment,corrections_json,created_at)
                VALUES(?,?,?,?,?,?,?)""",
                (
                    feedback_id,
                    run_id,
                    int(rating) if rating is not None else None,
                    outcome,
                    comment,
                    canonical_json(corrections),
                    timestamp,
                ),
            )
        return {
            "feedback_id": feedback_id,
            "run_id": run_id,
            "rating": rating,
            "outcome": outcome,
            "comment": comment,
            "corrections": corrections,
            "created_at": timestamp,
        }

    def feedback_for_run(self, run_id: str) -> list[dict[str, Any]]:
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM skill_feedback WHERE run_id=? ORDER BY created_at",
                (run_id,),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["corrections"] = json.loads(item.pop("corrections_json"))
            output.append(item)
        return output

    def _unique_slug(self, slug: str) -> str:
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT slug FROM skills WHERE slug=? OR slug LIKE ?",
                (slug, f"{slug}-%"),
            ).fetchall()
        existing = {str(row["slug"]) for row in rows}
        if slug not in existing:
            return slug
        index = 2
        while f"{slug}-{index}" in existing:
            index += 1
        return f"{slug}-{index}"

    def _write_artifacts(
        self,
        *,
        slug: str,
        version: str,
        compiled: dict[str, Any],
        validation: dict[str, Any],
    ) -> Path:
        root = self.skill_root / slug
        version_root = root / "versions" / version
        files = {
            "SKILL.md": compiled["skillMarkdown"],
            "workflow.json": self._pretty(compiled["workflow"]),
            "references/provenance.json": self._pretty(
                {
                    **compiled["provenance"],
                    "validationResult": validation,
                }
            ),
            "references/evidence_manifest.json": self._pretty(
                compiled.get("evidenceManifest") or {}
            ),
            "examples/input.json": self._pretty(compiled["exampleInput"]),
            "examples/output.json": self._pretty(compiled["exampleOutput"]),
            "tests/cases.json": self._pretty(compiled["testCases"]),
        }
        for relative, content in files.items():
            self._atomic_write(version_root / relative, content)
            self._atomic_write(root / relative, content)
        return version_root

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _pretty(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, indent=2) + "\n"

    @staticmethod
    def _decode_version(row: Any) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["workflow"] = json.loads(item.pop("workflow_json"))
        item["distilled"] = json.loads(item.pop("distilled_json"))
        item["validation"] = json.loads(item.pop("validation_json"))
        return item

    @staticmethod
    def _decode_run(row: Any) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["inputs"] = json.loads(item.pop("inputs_json"))
        item["plan"] = json.loads(item.pop("plan_json"))
        item["result"] = json.loads(item.pop("result_json"))
        item["requires_confirmation"] = bool(item["requires_confirmation"])
        return item

    @staticmethod
    def _decode_match(row: Any) -> dict[str, Any]:
        item = dict(row)
        item["why_matched"] = json.loads(item.pop("reasons_json"))
        item["task_context"] = json.loads(item.pop("task_context_json"))
        item["auto_execute"] = bool(item["auto_execute"])
        return item
