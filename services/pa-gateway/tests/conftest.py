# -*- coding: utf-8 -*-
"""Keep the test suite hermetic.

Tests must never call a real model and must never inherit local .env values:
the deterministic planner is part of the contract under test.
"""
import os

os.environ["PA_PLAN_PROVIDER"] = "deterministic"
os.environ["LLM_BASE_URL"] = ""
os.environ["LLM_API_KEY"] = ""
os.environ["LLM_MODEL"] = ""
os.environ["LETTA_AGENT_ID"] = ""
os.environ["LETTA_MODEL"] = ""
os.environ["LETTA_URL"] = ""
os.environ["LETTA_API_KEY"] = ""
# never spawn a real coding harness from a test
os.environ["PA_DELEGATE_CMD"] = ""
os.environ["PA_DELEGATE_WORKSPACE"] = ""
# a test must never read the developer's real desktop capture
os.environ["OBSERVER_URL"] = ""
# ... nor the developer's real knowledge index
os.environ["PA_KNOWLEDGE_LOCAL"] = "0"
# Approvals execute inline in tests so their assertions can read the final state
# straight off the response; the async worker is covered by test_async_execution.py.
os.environ["PA_APPROVAL_MODE"] = "sync"
