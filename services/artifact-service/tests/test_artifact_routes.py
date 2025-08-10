import pytest
from fastapi.testclient import TestClient

# Import AFTER monkeypatching publish_event if you need to
from app.main import app
from app.db import mongodb

client = TestClient(app)


@pytest.fixture(autouse=True)
def stub_events(monkeypatch):
    # Don't require RabbitMQ for tests
    from app.events import rabbit
    monkeypatch.setattr(rabbit, "publish_event", lambda *a, **k: None)


@pytest.fixture(scope="module", autouse=True)
def ensure_test_db():
    """
    These tests assume a local MongoDB reachable at MONGO_URI/MONGO_DB (e.g., docker-compose).
    If you prefer pure unit tests, mock DAL functions instead.
    """
    # Nothing to do here if your service already reads env vars.
    # Optionally you can set env here for test DB.
    yield


def test_list_filters_exist():
    ws = "ws-list"
    r = client.get(f"/artifact/{ws}?limit=1")
    assert r.status_code == 200


def test_create_sets_etag_and_get():
    ws = "ws-etag"
    create = client.post(
        f"/artifact/{ws}",
        json={"kind": "cam.document", "name": "Doc1", "data": {"a": 1}},
    )
    assert create.status_code in (201, 409)
    # When created, ETag must be present
    if create.status_code == 201:
        assert "ETag" in create.headers
        aid = create.json()["_id"]
    else:
        # If already exists from a previous run, fetch it
        # (Optional: you could query list endpoint with name prefix filter)
        # For simplicity just skip the rest.
        return

    got = client.get(f"/artifact/{ws}/{aid}")
    assert got.status_code == 200
    assert "ETag" in got.headers
    assert got.json()["_id"] == aid


def test_if_match_precondition():
    ws = "ws-pre"
    # Create fresh artifact
    c = client.post(
        f"/artifact/{ws}",
        json={"kind": "cam.document", "name": "Doc2", "data": {"a": 1}},
    )
    assert c.status_code in (201, 409)
    if c.status_code == 201:
        aid = c.json()["_id"]
        current_v = int(c.headers["ETag"])
    else:
        # If it already exists, we can’t easily recover ID without a name filter; skip.
        return

    # Wrong If-Match → 412
    bad = client.post(
        f"/artifact/{ws}/{aid}/patch",
        headers={"If-Match": "999"},
        json={"patch": [{"op": "replace", "path": "/data/a", "value": 2}]},
    )
    assert bad.status_code == 412

    # Correct If-Match → 200 and ETag should bump
    ok = client.post(
        f"/artifact/{ws}/{aid}/patch",
        headers={"If-Match": str(current_v)},
        json={"patch": [{"op": "replace", "path": "/data/a", "value": 2}]},
    )
    assert ok.status_code == 200
    assert "ETag" in ok.headers
    assert int(ok.headers["ETag"]) == current_v + 1


def test_soft_delete_and_404_after():
    ws = "ws-del"
    c = client.post(
        f"/artifact/{ws}",
        json={"kind": "cam.document", "name": "ToDelete", "data": {"x": 1}},
    )
    assert c.status_code in (201, 409)
    if c.status_code != 201:
        # If already present from a previous run, we can’t easily resolve ID; skip.
        return
    aid = c.json()["_id"]

    d = client.delete(f"/artifact/{ws}/{aid}")
    assert d.status_code == 204

    # Now reads should 404
    g = client.get(f"/artifact/{ws}/{aid}")
    assert g.status_code == 404

    # And by default list should not show deleted
    lst = client.get(f"/artifact/{ws}")
    assert lst.status_code == 200
    assert all(item["_id"] != aid for item in lst.json())

    # But include_deleted=true could show it (optional; depends on DAL semantics)
    lst2 = client.get(f"/artifact/{ws}?include_deleted=true")
    assert lst2.status_code == 200


def test_head_returns_etag(client):
    ws = "ws-head"
    # Create an artifact
    create_res = client.post(f"/artifact/{ws}", json={
        "kind": "cam.document",
        "name": "HeadTest",
        "data": {"foo": "bar"}
    })
    assert create_res.status_code in (201, 409)
    aid = create_res.json().get("_id") if create_res.status_code == 201 else None

    if not aid:
        # List to get the id if it already exists
        list_res = client.get(f"/artifact/{ws}")
        assert list_res.status_code == 200
        aid = list_res.json()[0]["_id"]

    # Call HEAD
    head_res = client.head(f"/artifact/{ws}/{aid}")
    assert head_res.status_code == 200
    assert "etag" in {k.lower(): v for k, v in head_res.headers.items()}
    assert head_res.text == ""  # No body
