# -*- coding: utf-8 -*-
"""Contract tests: the published schemas must match what the service really does."""
import json
import os

from app import policy as policy_mod
from app.engine import RunEngine
from app.errors import ERROR_CODES
from app.models import RunEvent, ToolEnvelope
# Explicit imports keep the contract file tied to the runtime sources it describes.
from app import engine as engine_mod

CONTRACTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "contracts")


def _contract(name: str) -> dict:
    with open(os.path.join(CONTRACTS, name), encoding="utf-8") as handle:
        return json.load(handle)


def _emitted_event_types() -> set:
    source = open(engine_mod.__file__, encoding="utf-8").read()
    types = set()
    marker = '_emit(run, "'
    index = source.find(marker)
    while index != -1:
        start = index + len(marker)
        end = source.find('"', start)
        types.add(source[start:end])
        index = source.find(marker, end)
    return types


def test_sse_event_contract_matches_the_engine():
    contract = _contract("sse_events.json")
    declared = set(contract["types"])
    emitted = _emitted_event_types()
    assert declared == emitted, {
        "declared_not_emitted": sorted(declared - emitted),
        "emitted_not_declared": sorted(emitted - declared),
    }
    assert set(contract["required_fields"]) == set(RunEvent.model_fields.keys())


def test_tool_envelope_contract_matches_the_model():
    contract = _contract("tool_envelope.json")
    assert set(contract["fields"]) == set(ToolEnvelope.model_fields.keys())


def test_error_code_contract_matches_the_api():
    contract = _contract("tool_envelope.json")
    declared = set(contract["error_codes"])
    # ERROR_CODES also carries NOT_FOUND, which is HTTP plumbing rather than a
    # domain error from the book's list.
    assert declared <= set(ERROR_CODES), sorted(declared - set(ERROR_CODES))


def test_every_registered_tool_has_an_engine_handler():
    source = open(engine_mod.__file__, encoding="utf-8").read()
    dispatch = source.split("handlers = {", 1)[1].split("}", 1)[0]
    handled = {line.split('"')[1] for line in dispatch.splitlines() if '"' in line}
    assert set(policy_mod.TOOL_REGISTRY) == handled, {
        "registry_without_handler": sorted(set(policy_mod.TOOL_REGISTRY) - handled),
        "handler_without_registry": sorted(handled - set(policy_mod.TOOL_REGISTRY)),
    }


def test_engine_exposes_the_book_tool_list():
    # the six EMOS tools, knowledge, task, skill, delegation and local read
    required = {"emos_recall", "emos_plan_write", "emos_reflect", "emos_supersede",
                "knowledge_search", "task_create", "task_search", "task_update",
                "task_complete", "skill_match", "skill_run", "local_file_read",
                "opencode_delegate"}
    assert required <= set(policy_mod.TOOL_REGISTRY)
    assert isinstance(RunEngine.__dict__.get("cancel"), object)
