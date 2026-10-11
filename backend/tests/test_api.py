import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.mktemp(suffix=".db")
from fastapi.testclient import TestClient
from app.main import app


def login(c, role="dispatcher"):
    r = c.post(
        "/api/v1/auth/login", json={"username": role, "password": "demo-" + role}
    )
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_end_to_end():
    with TestClient(app) as c:
        headers = login(c)
        n = c.get("/api/v1/network", headers=headers).json()
        assert n["geography"]["city"] == "Костанай"
        assert n["geography"]["district"] == "Юбилейный"
        r = c.post(
            "/api/v1/simulations",
            headers=headers,
            json={
                "network_version": n["version"],
                "incident": {"type": "pipe_break", "segment_id": n["pipes"][0]["id"]},
                "constraints": {"allow_backup_routes": False},
            },
        )
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["affected_consumers"]
        pdf = c.get("/api/v1/reports/" + s["simulation_id"], headers=headers)
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        assert (
            c.post(
                "/api/v1/incidents",
                headers=headers,
                json={"simulation_id": s["simulation_id"]},
            ).status_code
            == 200
        )
        assert c.get("/api/v1/incidents", headers=headers).json()
        assert (
            c.get("/api/v1/simulations/" + s["simulation_id"], headers=headers).json()
            == s
        )


def test_permissions_and_import():
    with TestClient(app) as c:
        assert c.get("/api/v1/network").status_code == 401
        observer = login(c, "observer")
        admin = login(c, "admin")
        n = c.get("/api/v1/network", headers=observer).json()
        assert (
            c.post("/api/v1/network/import", headers=observer, json=n).status_code
            == 403
        )
        assert (
            c.post(
                "/api/v1/simulations",
                headers=observer,
                json={
                    "network_version": n["version"],
                    "incident": {
                        "type": "pressure_drop",
                        "segment_id": n["pipes"][0]["id"],
                    },
                },
            ).status_code
            == 403
        )
        assert (
            c.post("/api/v1/network/import", headers=admin, json=n).status_code == 409
        )
        n["version"] = "import-test"
        n["pipes"][0]["end"] = "bad"
        assert (
            c.post("/api/v1/network/import", headers=admin, json=n).status_code == 422
        )
        assert c.get("/api/v1/audit", headers=admin).status_code == 200


def test_selected_variant_is_used_by_report_and_incident():
    from app.main import selected_result
    from app import store

    with TestClient(app) as client:
        headers = login(client)
        network = client.get("/api/v1/network", headers=headers).json()
        response = client.post(
            "/api/v1/simulations",
            headers=headers,
            json={
                "network_version": network["version"],
                "incident": {
                    "type": "pipe_break",
                    "segment_id": network["pipes"][0]["id"],
                },
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert len(result["variants"]) == 2
        saved = store.get(result["simulation_id"])
        chosen = selected_result(saved, 1)
        assert (
            chosen["affected_consumers"] == result["variants"][1]["affected_consumers"]
        )
        assert chosen["affected_segments"] == result["variants"][1]["affected_segments"]
        assert saved["affected_consumers"] == result["affected_consumers"]
        pdf = client.get(
            "/api/v1/reports/" + result["simulation_id"] + "?variant_index=1",
            headers=headers,
        )
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        incident = client.post(
            "/api/v1/incidents",
            headers=headers,
            json={"simulation_id": result["simulation_id"], "variant_index": 1},
        )
        assert incident.status_code == 200
        assert incident.json()["variant_index"] == 1
        assert incident.json()["affected_consumers"] == chosen["affected_consumers"]
        assert (
            client.get(
                "/api/v1/reports/" + result["simulation_id"] + "?variant_index=99",
                headers=headers,
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/incidents",
                headers=headers,
                json={"simulation_id": result["simulation_id"], "variant_index": 99},
            ).status_code
            == 422
        )
