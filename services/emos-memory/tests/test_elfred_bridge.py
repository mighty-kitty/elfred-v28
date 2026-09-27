import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from src.memory_system.api.elfred_bridge import Bridge, create_handler


def memory(owner="owner-a", revision=1, sequence=1, content="我喜欢简洁回答", state_hash="a" * 64):
    return {"contract": "elfred-memory-v1", "owner": owner, "id": "memory-a", "revision": revision, "intent_sequence": sequence, "state_hash": state_hash, "content": content, "scope": "advise", "allocation": {"holder": "advise", "allowed_systems": ["advise"], "contextual": True}, "learning_mode": "automatic", "source_refs": [{"id": "message-a"}], "alignment": "working"}


def test_native_storage_restart_update_owner_isolation_and_withdrawal(tmp_path):
    path = tmp_path / "emos.sqlite"
    bridge = Bridge(path)
    data = memory()
    receipt = bridge.apply("PUT", "memory-a", data)
    assert receipt["state_hash"] == data["state_hash"]
    assert bridge.apply("PUT", "memory-a", data) == receipt
    restarted = Bridge(path)
    assert restarted.read("owner-a", "memory-a")["content"] == data["content"]
    assert restarted.read("owner-b", "memory-a") is None
    restarted.apply("PUT", "memory-a", memory(owner="owner-b", content="另一个人的资料"))
    revised = memory(revision=2, sequence=2, content="请写详细说明", state_hash="b" * 64)
    restarted.apply("PUT", "memory-a", revised)
    with pytest.raises(ValueError):
        restarted.apply("PUT", "memory-a", data)
    assert restarted.read("owner-a", "memory-a")["allocation"]["allowed_systems"] == ["advise"]
    withdrawal = {**revised, "action": "forget", "intent_sequence": 3, "state_hash": "c" * 64}
    restarted.apply("DELETE", "memory-a", withdrawal)
    assert Bridge(path).read("owner-a", "memory-a") is None
    assert Bridge(path).read("owner-b", "memory-a")["content"] == "另一个人的资料"
    assert "请写详细说明" not in json.dumps(restarted.store.load({}), ensure_ascii=False)


def test_http_authentication_contract_and_unavailable_native_routes(tmp_path):
    token = "test-only-not-real-secret-" + "x" * 32
    server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(Bridge(tmp_path / "http.sqlite"), token))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:" + str(server.server_port)
    try:
        with urlopen(base + "/health") as response:
            assert json.load(response)["storage"] == "emos-native-sqlite"
        for method in ("PUT", "DELETE"):
            with pytest.raises(HTTPError) as error:
                urlopen(Request(base + "/v1/memories/memory-a", data=b"{}", method=method))
            assert error.value.code == 401
        with urlopen(Request(base + "/v1/memories/memory-a", data=json.dumps(memory()).encode(), method="PUT", headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})) as response:
            assert json.load(response)["owner"] == "owner-a"
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + "/memory/write", headers={"Authorization": "Bearer " + token}))
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()


def test_failed_persistence_never_returns_a_receipt(tmp_path):
    bridge = Bridge(tmp_path / "failure.sqlite")
    def fail_save(_payload):
        raise OSError("disk unavailable")
    bridge.store.save = fail_save
    with pytest.raises(OSError):
        bridge.apply("PUT", "memory-a", memory())
    assert Bridge(tmp_path / "failure.sqlite").read("owner-a", "memory-a") is None


def test_last_memory_tombstone_survives_restart_and_old_json_bootstrap(tmp_path):
    path = tmp_path / "last.sqlite"
    bridge = Bridge(path)
    original = memory()
    bridge.apply("PUT", "memory-a", original)
    stale_json = bridge.store.load({})
    bridge.apply("DELETE", "memory-a", {**original, "action": "forget", "intent_sequence": 2, "state_hash": "b" * 64})
    path.with_suffix(".json").write_text(json.dumps(stale_json), encoding="utf-8")
    restarted = Bridge(path)
    assert restarted.read("owner-a", "memory-a") is None
    with pytest.raises(ValueError):
        restarted.apply("PUT", "memory-a", original)
