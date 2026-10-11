import asyncio
import hashlib
import io
import json
import os
import secrets
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    Query,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, ValidationError
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from . import store
from .kostanay import make_kostanay
from .models import Network, SimulationInput, Reading
from .engine import simulate
from .telemetry import generate, PROFILES

pool = None
clients = set()
telemetry = {}
telemetry_profile = "normal"
telemetry_counter = 0


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return str(uuid.uuid4())


def audit(actor, action, target):
    id = uid()
    store.put(
        id,
        "audit",
        dict(
            id=id, user=actor["username"], timestamp=now(), action=action, target=target
        ),
    )


security = HTTPBearer(auto_error=False)
# Explicit demo accounts. Set THERMOTWIN_USERS to JSON for production-like credentials.
USERS = json.loads(
    os.getenv(
        "THERMOTWIN_USERS",
        '{"admin":{"password":"demo-admin","role":"admin"},"dispatcher":{"password":"demo-dispatcher","role":"dispatcher"},"observer":{"password":"demo-observer","role":"observer"}}',
    )
)
tokens = {}


def auth(credential: HTTPAuthorizationCredentials | None = Depends(security)):
    if not credential or credential.credentials not in tokens:
        raise HTTPException(401, "AUTH_REQUIRED")
    item = tokens[credential.credentials]
    if item["expires"] < time.time():
        raise HTTPException(401, "TOKEN_EXPIRED")
    return item


def writer(user=Depends(auth)):
    if user["role"] == "observer":
        raise HTTPException(403, "READ_ONLY")
    return user


def admin(user=Depends(auth)):
    if user["role"] != "admin":
        raise HTTPException(403, "ADMIN_REQUIRED")
    return user


def current_network(version=None):
    payload = (
        store.get("network:" + version) if version else store.listing("network")[0]
    )
    if not payload:
        raise HTTPException(404, "UNKNOWN_NETWORK_VERSION")
    return Network.model_validate(payload)


def connectivity_warnings(network):
    from .engine import reachable

    states = {v.id: "open" for v in network.valves}
    result = []
    for contour in ["supply", "return"]:
        seen = reachable(network, states, contour)
        isolated = [
            n.id for n in network.nodes if n.contour == contour and n.id not in seen
        ]
        if isolated:
            result.append(
                {
                    "code": "DISCONNECTED_TOPOLOGY",
                    "contour": contour,
                    "node_ids": isolated,
                }
            )
    return result


async def broadcast(payload):
    for ws in list(clients):
        try:
            await ws.send_json(payload)
        except Exception:
            clients.discard(ws)


async def tick():
    global telemetry_counter
    while True:
        network = current_network()
        telemetry.update(
            generate(network, telemetry, telemetry_counter, telemetry_profile)
        )
        store.put(
            uid(),
            "telemetry_batch",
            {"timestamp": now(), "readings": list(telemetry.values())},
        )
        await broadcast({"type": "telemetry", "readings": list(telemetry.values())})
        telemetry_counter += 1
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app):
    global pool
    store.init()
    networks = store.listing("network")
    if not networks or (
        networks[0]["version"] in {"demo-1", "demo-2"}
        and not store.get("network:kostanay-yubileyny-1")
    ):
        n = make_kostanay()
        store.put("network:" + n.version, "network", n.model_dump(mode="json"))
    pool = ProcessPoolExecutor(max_workers=2)
    task = asyncio.create_task(tick())
    yield
    task.cancel()
    pool.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="ThermoTwin", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://localhost:3001"
    ).split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class Login(BaseModel):
    username: str
    password: str


@app.post("/api/v1/auth/login")
def login(data: Login):
    account = USERS.get(data.username)
    if not account or not secrets.compare_digest(account["password"], data.password):
        raise HTTPException(401, "INVALID_CREDENTIALS")
    token = secrets.token_urlsafe(32)
    tokens[token] = {
        "username": data.username,
        "role": account["role"],
        "expires": time.time() + 8 * 3600,
    }
    audit(tokens[token], "login", data.username)
    return {"token": token, "role": account["role"], "username": data.username}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/network")
def network(version: str | None = None, user=Depends(auth)):
    return current_network(version)


@app.get("/api/v1/network/versions")
def versions(user=Depends(auth)):
    return [
        {"version": n["version"], "demo": n["demo"]} for n in store.listing("network")
    ]


@app.get("/api/v1/network/elements/{id}")
def element(id: str, user=Depends(auth)):
    n = current_network()
    for group in ["nodes", "pipes", "valves", "consumers", "sources", "sensors"]:
        for obj in getattr(n, group):
            if obj.id == id:
                return {"type": group, "element": obj.model_dump()}
    raise HTTPException(404, "UNKNOWN_ELEMENT")


@app.post("/api/v1/network/import")
def import_network(data: dict, user=Depends(admin)):
    try:
        if data.get("type") == "FeatureCollection":
            canonical = {
                **data.get("properties", {}),
                "nodes": [],
                "pipes": [],
                "valves": [],
                "consumers": [],
                "sources": [],
                "sensors": [],
            }
            for feature in data.get("features", []):
                attrs = feature["properties"].copy()
                kind = attrs.pop("entity")
                if kind not in (
                    "nodes",
                    "pipes",
                    "valves",
                    "consumers",
                    "sources",
                    "sensors",
                ):
                    raise ValueError("Unknown entity")
                geometry = feature.get("geometry")
                if kind == "nodes":
                    attrs["coordinates"] = geometry["coordinates"]
                if kind == "pipes":
                    attrs["geometry"] = geometry["coordinates"]
                canonical[kind].append(attrs)
            data = canonical
        n = Network.model_validate(data)
    except (ValidationError, KeyError, TypeError, ValueError) as e:
        raise HTTPException(422, {"code": "INVALID_NETWORK", "errors": str(e)})
    if store.get("network:" + n.version):
        raise HTTPException(409, "IMMUTABLE_VERSION_EXISTS")
    warnings = connectivity_warnings(n)
    store.put("network:" + n.version, "network", n.model_dump(mode="json"))
    audit(user, "network_import", n.version)
    telemetry.clear()
    return {"version": n.version, "warnings": warnings}


@app.post("/api/v1/simulations")
async def run_simulation(data: SimulationInput, user=Depends(writer)):
    n = current_network(data.network_version)
    id = uid()
    created = now()
    # Every run persists an immutable input snapshot, including source and valve states.
    try:
        result = await asyncio.get_running_loop().run_in_executor(
            pool, simulate, n, data
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    result.update(
        simulation_id=id,
        network_version=n.version,
        request=data.model_dump(),
        created_at=created,
        demo=n.demo,
        model_snapshot=n.model_dump(mode="json"),
    )
    store.put(id, "simulation", result)
    audit(user, "simulation_create", id)
    await broadcast({"type": "simulation", "simulation_id": id})
    return {k: v for k, v in result.items() if k != "model_snapshot"}


@app.get("/api/v1/simulations")
def simulations(user=Depends(auth)):
    return [
        {k: v for k, v in x.items() if k != "model_snapshot"}
        for x in store.listing("simulation")
    ]


@app.get("/api/v1/simulations/{id}")
def simulation(id: str, user=Depends(auth)):
    r = store.get(id)
    if not r or "simulation_id" not in r:
        raise HTTPException(404, "UNKNOWN_SIMULATION")
    return {k: v for k, v in r.items() if k != "model_snapshot"}


@app.get("/api/v1/telemetry")
def readings(user=Depends(auth)):
    result = []
    for reading in telemetry.values():
        r = reading.copy()
        age = (
            datetime.now(timezone.utc) - datetime.fromisoformat(r["timestamp"])
        ).total_seconds()
        if age > 90:
            r["status"] = "no_connection"
        result.append(r)
    return result


class TelemetryProfile(BaseModel):
    profile: str


@app.post("/api/v1/telemetry/profile")
async def profile(data: TelemetryProfile, user=Depends(writer)):
    global telemetry_profile, telemetry_counter
    if data.profile not in PROFILES:
        raise HTTPException(422, "UNKNOWN_TELEMETRY_PROFILE")
    telemetry_profile = data.profile
    telemetry_counter = 0
    telemetry.update(generate(current_network(), telemetry, 0, telemetry_profile))
    audit(user, "telemetry_profile", data.profile)
    await broadcast({"type": "telemetry", "readings": list(telemetry.values())})
    return {"profile": telemetry_profile, "mode": "simulation"}


@app.get("/api/v1/telemetry/history")
def telemetry_history(user=Depends(auth)):
    return store.listing("telemetry_batch", limit=100)


@app.post("/api/v1/telemetry")
def receive(data: list[Reading], user=Depends(writer)):
    valid = {s.id for s in current_network().sensors}
    batch = []
    for r in data:
        if r.sensor_id not in valid:
            raise HTTPException(422, "UNKNOWN_SENSOR")
        try:
            t = datetime.fromisoformat(r.timestamp.replace("Z", "+00:00"))
            if (
                t.tzinfo is None
                or abs((datetime.now(timezone.utc) - t).total_seconds()) > 86400
            ):
                raise ValueError()
        except ValueError:
            raise HTTPException(422, "INVALID_UTC_TIMESTAMP")
        batch.append(
            r.model_dump()
            | {
                "timestamp": t.astimezone(timezone.utc).isoformat(),
                "mode": "test_source",
                "status": "normal",
            }
        )
    for r in batch:
        telemetry[r["sensor_id"]] = r
        store.put(uid(), "reading", r)
    audit(user, "telemetry_ingest", str(len(batch)))
    return {"accepted": len(batch)}


def selected_result(result, index):
    variants = result.get("variants", [])
    if (not variants and index != 0) or (variants and index >= len(variants)):
        raise HTTPException(422, "UNKNOWN_VARIANT")
    if not variants:
        return result
    chosen = variants[index]
    output = result | chosen | {"variant_index": index}
    if "affected_segments" not in chosen:
        from .engine import reachable

        network = Network.model_validate(result["model_snapshot"])
        states = result["initial_valve_states"].copy()
        for operation in chosen["valve_operations"]:
            states[operation["valve_id"]] = operation["state"]
        reach = {c: reachable(network, states, c) for c in ["supply", "return"]}
        segments = [
            p.id
            for p in network.pipes
            if p.start not in reach[p.contour] or p.end not in reach[p.contour]
        ]
        target = result["request"]["incident"]["segment_id"]
        if (
            result["request"]["incident"]["type"] != "pressure_drop"
            and target not in segments
        ):
            segments.append(target)
        output["affected_segments"] = segments
    return output


class IncidentCreate(BaseModel):
    simulation_id: str
    variant_index: int = Field(default=0, ge=0)


@app.post("/api/v1/incidents")
def create_incident(data: IncidentCreate, user=Depends(writer)):
    s = store.get(data.simulation_id)
    if not s or "simulation_id" not in s:
        raise HTTPException(404, "UNKNOWN_SIMULATION")
    chosen = selected_result(s, data.variant_index)
    id = uid()
    r = {
        "id": id,
        "simulation_id": data.simulation_id,
        "variant_index": data.variant_index,
        "affected_consumers": chosen["affected_consumers"],
        "valve_operations": chosen["valve_operations"],
        "type": s["request"]["incident"]["type"],
        "segment_id": s["request"]["incident"]["segment_id"],
        "status": "registered",
        "demo": s["demo"],
        "created_at": now(),
        "author": user["username"],
    }
    store.put(id, "incident", r)
    audit(user, "incident_create", id)
    return r


@app.get("/api/v1/incidents")
def incidents(user=Depends(auth)):
    return store.listing("incident")


@app.get("/api/v1/audit")
def audit_logs(user=Depends(admin)):
    return store.listing("audit")


@app.get("/api/v1/reports/{id}")
def report(id: str, variant_index: int = Query(default=0, ge=0), user=Depends(auth)):
    r = store.get(id)
    if not r or "simulation_id" not in r:
        raise HTTPException(404, "UNKNOWN_SIMULATION")
    r = selected_result(r, variant_index)
    font = "Helvetica"
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]:
        if os.path.exists(path):
            if "ReportFont" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("ReportFont", path))
            font = "ReportFont"
            break
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.setTitle("ThermoTwin — аварийный сценарий")
    y = 800

    def line(text):
        nonlocal y
        if y < 55:
            c.showPage()
            y = 800
        c.setFont(font, 10)
        c.drawString(40, y, str(text)[:110])
        y -= 17

    for text in [
        "ThermoTwin — отчёт по сценарию",
        "ДЕМОНСТРАЦИЯ / СИНТЕТИЧЕСКАЯ СЕТЬ" if r["demo"] else "Расчётный сценарий",
        f"Дата: {r['created_at']}",
        f"Версия сети: {r['network_version']}",
        f"Сценарий: {id}",
        f"Вариант: {r.get('name', 'без допустимого варианта')}",
        f"Авария: {r['request']['incident']}",
        f"Статус: {r['status']}",
        f"Отключено зданий: {len(r['affected_consumers'])}",
        f"Население: {r.get('estimated_population', 'нет данных')}",
        f"Время расчёта: {r['execution_ms']} мс",
        f"Гидравлика: {r['hydraulic_validation']['status']}",
    ]:
        line(text)
    geography = r["model_snapshot"].get("geography")
    if geography:
        line(
            f"Территория: {geography['country']}, {geography['region']}, {geography['city']}, мкр. {geography['district']}"
        )
        line(
            "Трассы смоделированы вдоль дорог OpenStreetMap; параметры теплосети условные."
        )
    for warning in (
        r["warnings"]
        + r["hydraulic_validation"].get("assumptions", [])
        + r["hydraulic_validation"].get("warnings", [])
    ):
        line(warning)
    line("Предлагаемые операции:")
    for op in r["valve_operations"]:
        line(f"{op['valve_id']} → {op['state']}")
    line("Затронутые потребители:")
    byid = {b["id"]: b for b in r["model_snapshot"]["consumers"]}
    for bid in r["affected_consumers"]:
        line(f"{bid}: {byid[bid]['address']}")
    c.showPage()
    c.setFont(font, 14)
    c.drawString(40, 800, "Схема сети / зона отключения")
    affected = set(r["affected_segments"])
    pipes = r["model_snapshot"]["pipes"]
    pts = [point for p in pipes for point in p["geometry"]]
    if pts:
        xmin = min(p[0] for p in pts)
        xmax = max(p[0] for p in pts)
        ymin = min(p[1] for p in pts)
        ymax = max(p[1] for p in pts)
        for p in pipes:
            c.setStrokeColorRGB(0.9, 0.2, 0.15) if p[
                "id"
            ] in affected else c.setStrokeColorRGB(0.35, 0.55, 0.6)
            path = c.beginPath()
            for i, point in enumerate(p["geometry"]):
                x = 40 + 510 * (point[0] - xmin) / max(xmax - xmin, 1e-8)
                yy = 120 + 600 * (point[1] - ymin) / max(ymax - ymin, 1e-8)
                (path.moveTo if i == 0 else path.lineTo)(x, yy)
            c.drawPath(path)
    c.save()
    audit(user, "report_download", id)
    return Response(
        buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="ThermoTwin-{id}.pdf"'},
    )


@app.websocket("/api/v1/ws")
async def ws(websocket: WebSocket):
    # Browser sends token as first message, avoiding credentials in URLs/server logs.
    await websocket.accept()
    try:
        token = await asyncio.wait_for(websocket.receive_text(), 5)
        if token not in tokens or tokens[token]["expires"] < time.time():
            await websocket.close(code=1008)
            return
        clients.add(websocket)
        await websocket.send_json(
            {"type": "telemetry", "readings": list(telemetry.values())}
        )
        while True:
            await websocket.receive_text()
            if tokens[token]["expires"] < time.time():
                await websocket.close(code=1008)
                break
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        clients.discard(websocket)
