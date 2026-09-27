from __future__ import annotations

from typing import Any


SPECS: list[dict[str, Any]] = [
    {"app": "Feishu", "category": "im_collaboration", "summary": "确认 Elfred 演示范围和联调顺序", "text": "决定先走独立 Adapter。下一步：准备联调清单，截止：明天。", "tasks": [("准备 Elfred 联调清单", "明天", 0.92, "Elfred")]},
    {"app": "Zotero", "category": "research", "summary": "整理科研资料中的关键论据", "text": "发现 Topic Registry 需要稳定别名，决定记录来源索引。", "tasks": [("整理实验论据与来源", None, 0.84, "科研")]},
    {"app": "Codex", "category": "development", "summary": "实现 ContextEvent 到 Todo 的映射", "text": "风险：同 ID 不同 payload 可能覆盖数据。决定使用 payload hash。", "tasks": [("实现 payload hash 冲突检测", "明天", 0.95, "开发")]},
    {"app": "Edge", "category": "browser_research", "summary": "浏览 FreeTodo API 文档", "text": "新想法：用 uid 和 Adapter link 双重保证幂等。", "tasks": []},
    {"app": "Calendar", "category": "life", "summary": "安排明天演示前的准备", "text": "下一步：演示前检查投屏和网络。", "tasks": [("检查演示投屏和网络", "明天", 0.90, "生活")]},
    {"app": "Notes", "category": "work", "summary": "也许需要优化演示讲稿", "text": "待确认：演示讲稿是否需要再压缩。", "tasks": [("优化演示讲稿", None, 0.42, "Elfred")]},
    {"app": "Feishu", "category": "im_collaboration", "summary": "技术路线评审", "text": "决定保留 legacy 作为回退，不删除旧 Organizer。", "tasks": []},
    {"app": "Terminal", "category": "development", "summary": "运行 FreeTodo 基线", "text": "风险：全局 Python 的 pth 编码错误会影响启动。", "tasks": [("记录 Python pth 环境风险", None, 0.81, "开发")]},
    {"app": "Observer", "category": "work", "summary": "重复截图被 Observer 去重", "text": "重复截图只记录诊断，不产生新任务。", "tasks": []},
    {"app": "PasswordManager", "category": "private", "summary": "私密凭据页面", "text": "password=DEMO-SECRET-MUST-NOT-LEAVE", "tasks": [("复制私密 token", None, 0.99, "工作")], "sensitive": True, "sensitivity_types": ["credential", "token"]},
    {"app": "Feishu", "category": "im_collaboration", "summary": "联系演示同事 13800138000", "text": "把日程发给 demo.owner@example.com。", "tasks": [("发送演示日程给 demo.owner@example.com", None, 0.88, "Elfred")]},
    {"app": "GitHub", "category": "development", "summary": "核对上游 commit", "text": "依赖：等待接口合同最终确认。", "tasks": [("固定 FreeTodo commit", None, 0.94, "开发")]},
    {"app": "Teams", "category": "im_collaboration", "summary": "Memory 接口讨论", "text": "等待 Memory 团队提供正式 endpoint 和认证方式。", "tasks": []},
    {"app": "VSCode", "category": "development", "summary": "补齐 Adapter API", "text": "下一步包含 forget 和 reconcile。", "tasks": [("实现 forget", None, 0.96, "Elfred"), ("实现 reconcile", None, 0.95, "Elfred")]},
    {"app": "Notes", "category": "work", "summary": "阿福项目名称统一", "text": "决定阿福、Elfred项目都归并为 Elfred。", "tasks": [("核对阿福 Topic alias", None, 0.86, "阿福")]},
    {"app": "Agent", "category": "work", "summary": "Personal Agent 上下文出口", "text": "新想法：通过版本化 Outbox 解耦。", "tasks": [("验证 Personal Agent Outbox", None, 0.91, "Personal Agent项目")]},
    {"app": "PowerShell", "category": "development", "summary": "导出 OpenAPI 和依赖清单", "text": "已完成 94 paths 的审计。", "tasks": []},
    {"app": "Calendar", "category": "work", "summary": "安排验收会议", "text": "下一步：在 2026-07-14T10:00:00+08:00 前完成检查。", "tasks": [("完成演示验收检查", "2026-07-14T10:00:00+08:00", 0.93, "Elfred")]},
    {"app": "FreeTodo", "category": "work", "summary": "验证手工修改保护", "text": "风险：不能悄悄覆盖用户在 Todo 中的手工修改。", "tasks": [("测试手工修改保护", None, 0.97, "开发")]},
    {"app": "Observer", "category": "work", "summary": "完成当天上下文回顾", "text": "发现日报需要突出 idea、决策、风险和下一步。", "tasks": [("检查 idea 导向日报", None, 0.89, "Elfred")], "memory_allowed": True},
]


def build_demo_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for index, spec in enumerate(SPECS):
        tasks = [
            {
                "task": title,
                "deadline": deadline,
                "assignee": "unknown",
                "project": project,
                "confidence": confidence,
            }
            for title, deadline, confidence, project in spec["tasks"]
        ]
        events.append({
            "event_id": f"demo-20260713-{index + 1:03d}",
            "created_at": f"2026-07-13T{8 + index // 3:02d}:{(index * 7) % 60:02d}:00+08:00",
            "source": "desktop_observer",
            "app": {
                "name": spec["app"],
                "process_name": f"{spec['app']}.exe",
                "window_title": spec["summary"],
                "category": spec["category"],
            },
            "trigger": {"type": "demo", "level": 3, "score": 8, "reasons": ["acceptance_demo"]},
            "content": {
                "content_type": "important",
                "raw_text": spec["text"],
                "clean_text": spec["text"],
                "summary": spec["summary"],
                "entities": [{"type": "project", "text": task["project"]} for task in tasks if task.get("project")],
                "tasks": tasks,
            },
            "privacy": {
                "is_sensitive": bool(spec.get("sensitive")),
                "sensitivity_types": spec.get("sensitivity_types") or [],
                "action": "block" if spec.get("sensitive") else "allow",
                "allowed_to_upload": False,
                "allowed_to_write_long_term_memory": bool(spec.get("memory_allowed")),
                "requires_user_confirmation": False,
            },
            "artifacts": {"screenshot_id": f"demo-shot-{index + 1:03d}"},
            "suggestions": {"memory_write_suggestions": [], "task_card_suggestions": tasks, "skill_candidate_suggestions": []},
            "status": "temporary_context",
            "demo_unknown_field": {"preserved": True, "index": index},
        })
    return events
