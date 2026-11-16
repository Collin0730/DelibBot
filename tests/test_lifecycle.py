"""One deliberation from creation to debrief, through the public API."""
import time


def wait_for(fn, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        out = fn()
        if out:
            return out
        time.sleep(0.2)
    raise AssertionError("timed out")


BRIEFING = b"""Library budget briefing

The council must save 400,000 next year. Option one is to shorten opening hours at every branch.
Shorter hours would save about 250,000 and affect evening users most.

Option two is to close the Northgate branch, which has the fewest visits.
Closing Northgate would save about 300,000 but leave the north of the town without a library.

Some residents have suggested charging for room hire to raise new income.
"""


def test_full_lifecycle(client):
    assert client.get("/api/deliberations").status_code == 401
    assert client.post("/api/auth/login", json={"email": "lucy@example.org", "password": "nope"}).status_code == 401
    token = client.post("/api/auth/login", json={"email": "lucy@example.org", "password": "test-password"}).json()["token"]
    org = {"Authorization": f"Bearer {token}"}

    # moderator, deliberation, options
    mods = client.post("/api/moderators", json={"name": "River", "email": "river@example.org"}, headers=org).json()
    mod = mods[0]
    assert client.post("/api/moderators", json={"name": "River", "email": "river@example.org"}, headers=org).status_code == 409
    d = client.post("/api/deliberations", json={"title": "Library budget", "framing_question": "Shorter hours or close a branch?", "moderator_id": mod["id"]}, headers=org).json()
    did = d["id"]
    assert d["stage"] == "none" and d["moderator"]["name"] == "River"
    for label in ("Shorten opening hours", "Close the Northgate branch"):
        d = client.post(f"/api/deliberations/{did}/concepts", json={"label": label}, headers=org).json()
    hours, close = d["options"]

    # materials and evaluation
    assert client.post(f"/api/deliberations/{did}/eval", headers=org).status_code == 409
    up = client.post(f"/api/deliberations/{did}/documents", files=[("files", ("briefing.txt", BRIEFING, "text/plain")), ("files", ("notes.xlsx", b"x", "application/octet-stream"))], headers=org).json()
    assert up["added"] == ["briefing.txt"] and len(up["skipped"]) == 1
    client.post(f"/api/deliberations/{did}/participants", json={"name": "Dana", "email": "dana@example.org"}, headers=org)
    assert client.post(f"/api/deliberations/{did}/invites", headers=org).status_code == 409  # no evaluation yet
    client.post(f"/api/deliberations/{did}/eval", headers=org)
    d = wait_for(lambda: (lambda x: x if x["eval"]["status"] != "running" else None)(client.get(f"/api/deliberations/{did}", headers=org).json()), 60)
    assert d["eval"]["status"] in ("passed", "below_goal"), d["eval"]
    assert d["eval"]["health"] > 50 and len(d["eval"]["metrics"]) >= 6

    # people and invites
    d = client.post(f"/api/deliberations/{did}/participants", json={"name": "Sam", "email": "sam@example.org"}, headers=org).json()
    d = client.post(f"/api/deliberations/{did}/standins", json={"count": 2}, headers=org).json()
    assert d["counts"] == {**d["counts"], "people": 2, "standins": 2}
    dana = next(p for p in d["participants"] if p["name"] == "Dana")
    sam = next(p for p in d["participants"] if p["name"] == "Sam")
    p_dana = {"Authorization": "Bearer p." + dana["link"].split("/")[-1]}
    assert client.get("/api/p/state", headers=p_dana).status_code == 401  # link is not live until invites go out
    d = client.post(f"/api/deliberations/{did}/invites", headers=org).json()
    assert d["stage"] == "invited"
    d = client.post(f"/api/participants/{sam['id']}/cancel", headers=org).json()
    assert d["counts"]["cancelled"] == 1
    assert client.get("/api/p/state", headers={"Authorization": "Bearer p." + sam["link"].split("/")[-1]}).status_code == 401

    # participant: accept, pre-survey, partner
    st = client.post("/api/p/accept", json={"consent_research": True}, headers=p_dana).json()
    assert st["status"] == "accepted" and len(st["options"]) == 2
    st = client.post("/api/p/pre-survey", json={"knowledge_level": "novice", "hopes": "Understand the numbers", "stances": [{"concept_id": hours["id"], "value": "support", "certainty": 2}, {"concept_id": close["id"], "value": "oppose", "certainty": 4}]}, headers=p_dana).json()
    assert st["pre_done"]
    reply = client.post("/api/p/partner", json={"message": "How much would closing Northgate save?"}, headers=p_dana).json()
    assert reply["role"] == "assistant" and reply["body"]
    assert len(client.get("/api/p/partner", headers=p_dana).json()) == 2

    # schedule and start
    assert client.post(f"/api/deliberations/{did}/messages", json={"body": "hi"}, headers=p_dana).status_code == 409
    d = client.post(f"/api/deliberations/{did}/schedule", json={"scheduled_start": "2026-12-05T10:00:00Z", "duration_minutes": 90, "format": "online"}, headers=org).json()
    assert d["stage"] == "scheduled"
    m_tok = "m." + mod["link"].split("/")[-1]
    mod_h = {"Authorization": "Bearer " + m_tok}
    assert [x["id"] for x in client.get("/api/deliberations", headers=mod_h).json()] == [did]
    assert client.post(f"/api/deliberations/{did}/start", headers=mod_h).json()["stage"] == "in_progress"

    # live room
    with client.websocket_connect(f"/api/ws/deliberations/{did}?token=p.{dana['link'].split('/')[-1]}") as ws:
        assert ws.receive_json()["type"] == "presence"
        client.post(f"/api/deliberations/{did}/messages", json={"body": "Welcome everyone. Let's start with opening hours."}, headers=mod_h)
        sent = client.post(f"/api/deliberations/{did}/messages", json={"body": "I support the plan to shorten opening hours, it seems fair."}, headers=p_dana).json()
        seen = []
        wait_for(lambda: seen.append(ws.receive_json()) or any(e["type"] == "message" and e["message"]["id"] == sent["id"] for e in seen))
    room = wait_for(lambda: (lambda r: r if any(e["message_id"] == sent["id"] for e in r["flow"]["entries"]) else None)(client.get(f"/api/deliberations/{did}/room", headers=mod_h).json()))
    entry = next(e for e in room["flow"]["entries"] if e["message_id"] == sent["id"])
    assert entry["concept_id"] == hours["id"] and entry["position"] == "support" and entry["speaker"] == dana["id"]
    wait_for(lambda: any(next((p for p in room["people"] if p["id"] == x["speaker"] and p["simulated"]), None) for x in client.get(f"/api/deliberations/{did}/room", headers=mod_h).json()["messages"]))

    # a new idea becomes a proposed row; the moderator confirms it, then corrects a tag
    idea = client.post(f"/api/deliberations/{did}/messages", json={"body": "What about charging for room hire to raise new income?"}, headers=p_dana).json()
    room = wait_for(lambda: (lambda r: r if any(c["raised_in_message"] == idea["id"] for c in r["flow"]["concepts"]) else None)(client.get(f"/api/deliberations/{did}/room", headers=mod_h).json()))
    new = next(c for c in room["flow"]["concepts"] if c["raised_in_message"] == idea["id"])
    assert new["status"] == "proposed" and new["raised_by"] == dana["id"]
    assert new["id"] not in [c["id"] for c in client.get(f"/api/deliberations/{did}/room", headers=p_dana).json()["flow"]["concepts"]]
    assert client.post(f"/api/concepts/{new['id']}/review", json={"status": "confirmed"}, headers=p_dana).status_code == 403
    client.post(f"/api/concepts/{new['id']}/review", json={"status": "confirmed"}, headers=mod_h)
    flow = client.post(f"/api/entries/{entry['id']}/correct", json={"position": "clarify", "paraphrase": "Shorter hours seem fair"}, headers=mod_h).json()
    assert entry["id"] not in [e["id"] for e in flow["entries"]]
    fixed = next(e for e in flow["entries"] if e["message_id"] == sent["id"])
    assert fixed["position"] == "clarify" and fixed["tagged_by"] == "moderator"
    client.post(f"/api/deliberations/{did}/stance", json={"concept_id": hours["id"], "value": "undecided", "certainty": 3}, headers=p_dana)
    assert client.post(f"/api/deliberations/{did}/standins/speak", headers=mod_h).status_code == 200

    # end, reflect, review, export
    assert client.post(f"/api/deliberations/{did}/end", headers=mod_h).json()["stage"] == "pending_debrief"
    form = client.get("/api/p/reflection", headers=p_dana).json()
    assert form["open"] and form["topics"][0]["view_before"] == "support"
    topic = next(t for t in form["topics"] if t["points"])
    body = {"topics": [{"concept_id": t["concept_id"], "view_after": "undecided", "certainty_after": 3, "moved_note": "Cost", "points": ([{"entry_id": topic["points"][0]["entry_id"], "effect": "moved"}] if t is topic else [])} for t in form["topics"]],
            "answers": {"felt_heard": 4, "partner_helpful": 5}}
    assert client.post("/api/p/reflection", json=body, headers=p_dana).status_code == 200
    assert client.post("/api/p/reflection", json=body, headers=p_dana).status_code == 409
    rv = client.get(f"/api/deliberations/{did}/review", headers=org).json()
    t0 = next(t for t in rv["topics"] if t["concept_id"] == hours["id"])
    assert t0["before"]["support"] == 1 and t0["after"]["undecided"] == 1
    assert sum(e["moved"] for t in rv["topics"] for e in t["entries"]) == 1
    assert client.post(f"/api/deliberations/{did}/complete", headers=org).json()["stage"] == "complete"
    ex = client.get(f"/api/deliberations/{did}/export", headers=org).json()
    assert ex["pseudonymous"] and "full_name" not in ex["participants"][0] and len(ex["flow_entries"]) >= 2
    assert any(e["supersedes_id"] for e in ex["flow_entries"])
    assert "full_name" in client.get(f"/api/deliberations/{did}/export?names=true", headers=org).json()["participants"][0]

    # removing the moderator keeps them on the finished deliberation
    out = client.delete(f"/api/moderators/{mod['id']}", headers=org).json()
    assert out["unassigned"] == 0 and out["moderators"] == []
    assert client.get(f"/api/deliberations/{did}", headers=org).json()["moderator"]["name"] == "River"
    assert client.get("/api/deliberations", headers=mod_h).status_code == 401
