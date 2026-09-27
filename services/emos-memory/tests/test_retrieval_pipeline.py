from src.memory_system.workflow import build_default_agent


def test_retrieval_backend_report_exposes_pipeline_profile():
    agent = build_default_agent()

    report = agent.repository.get_retrieval_backend_report()

    assert "pipeline_profile" in report
    assert "recall_stages" in report["pipeline_profile"]
    assert "control_plane" in report["pipeline_profile"]
    assert "recall" in report["pipeline_profile"]["control_plane"]
    assert "fusion" in report["pipeline_profile"]["control_plane"]
    assert "rerank" in report["pipeline_profile"]["control_plane"]
    assert "explainability_signals" in report["pipeline_profile"]
    assert "agent_contract" in report["pipeline_profile"]
    assert report["pipeline_profile"]["supports_embedding"] is True
    assert report["pipeline_profile"]["supports_rerank"] is True
    assert "validation_notes" in report
    assert "control_plane_status" in report
    assert report["control_plane_status"]["readiness"] in {"ready", "review"}
    assert "task_fit" in report
    assert "agent_recommendations" in report
    assert "runtime_advice" in report
    assert report["runtime_advice"]["advice_version"] == "retrieval-runtime-advice.v1"
    assert report["runtime_advice"]["candidate_pool"]["status"] in {"ready", "small"}
    assert report["runtime_advice"]["response_policy"]["mode"] in {
        "grounded_answer",
        "confirm_on_ambiguity",
        "avoid_strong_answer_on_thin_candidate_pool",
    }
    assert "anti_patterns" in report
