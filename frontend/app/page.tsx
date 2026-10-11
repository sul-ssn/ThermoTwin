"use client";
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import {
  Activity,
  ArrowRight,
  Check,
  ChevronRight,
  Download,
  Flame,
  Layers,
  Map,
  Play,
  Plus,
  Radio,
  Search,
  Settings,
  Shield,
  TriangleAlert,
  Upload,
  X,
  LogOut,
  Clock,
  GitCompareArrows,
  LayoutDashboard,
  FileText,
  Users,
  Bell,
  Grid2X2,
  ChevronDown,
  CircleHelp,
  Building2,
  Gauge,
  Thermometer,
  RefreshCw,
  Eye,
  CheckCircle2,
  CircleDot,
  Droplets,
  ArrowLeft,
  MoreHorizontal,
  Filter,
  SlidersHorizontal,
  LocateFixed,
  Menu,
  Zap,
  Network as NetworkIcon,
  MapPin,
  CircleX,
  ExternalLink,
  Save,
  PanelRightClose,
  PanelRightOpen,
} from "lucide-react";
import type { Network, Simulation, Reading } from "./types";
import TelemetryChart from "../components/TelemetryChart";
import ReportPreview from "../components/ReportPreview";
const NetworkMap = dynamic(() => import("../components/NetworkMap"), {
  ssr: false,
});
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const labels: Record<string, string> = {
  pipe_break: "Разрыв трубы",
  valve_failure: "Отказ задвижки",
  pressure_drop: "Снижение давления",
  success: "Успешно",
  outside_applicability: "За границами применимости",
  not_converged: "Не сошёлся",
  insufficient_data: "Недостаточно данных",
};
export default function Dashboard() {
  const [variantChoices, setVariantChoices] = useState<Record<string, number>>(
    {},
  );
  const [step, setStep] = useState(1),
    [variantIndex, setVariantIndex] = useState(0),
    [telemetryView, setTelemetryView] = useState("map"),
    [telemetryFilter, setTelemetryFilter] = useState("all"),
    [sensorKind, setSensorKind] = useState("all"),
    [sensorId, setSensorId] = useState(""),
    [reportId, setReportId] = useState(""),
    [reportFilter, setReportFilter] = useState("all"),
    [telemetryHistory, setTelemetryHistory] = useState<
      { timestamp: string; readings: Reading[] }[]
    >([]),
    [objectTab, setObjectTab] = useState("telemetry"),
    [layersOpen, setLayersOpen] = useState(true),
    [mobileNav, setMobileNav] = useState(false),
    [panelOpen, setPanelOpen] = useState(true),
    [showSupply, setShowSupply] = useState(true),
    [showValves, setShowValves] = useState(true),
    [showBasemap, setShowBasemap] = useState(true),
    [showZones, setShowZones] = useState(true),
    [selectedVariant, setSelectedVariant] = useState(false);
  const [telemetryProfile, setTelemetryProfile] = useState("normal");
  const [profileBusy, setProfileBusy] = useState(false);
  const [token, setToken] = useState(""),
    [role, setRole] = useState("dispatcher"),
    [network, setNetwork] = useState<Network | null>(null),
    [tab, setTab] = useState("map"),
    [selected, setSelected] = useState(""),
    [search, setSearch] = useState(""),
    [incident, setIncident] = useState("pipe_break"),
    [result, setResult] = useState<Simulation | null>(null),
    [history, setHistory] = useState<Simulation[]>([]),
    [readings, setReadings] = useState<Reading[]>([]),
    [incidents, setIncidents] = useState<any[]>([]),
    [audit, setAudit] = useState<any[]>([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [showReturn, setShowReturn] = useState(true),
    [showConsumers, setShowConsumers] = useState(true),
    [showSensors, setShowSensors] = useState(true),
    [backup, setBackup] = useState(true),
    [username, setUsername] = useState("dispatcher"),
    [password, setPassword] = useState("demo-dispatcher");
  async function request(
    path: string,
    options: RequestInit = {},
    access = token,
  ) {
    const r = await fetch(API + "/api/v1" + path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + access,
        ...options.headers,
      },
    });
    if (!r.ok) {
      if (r.status === 401 && access) {
        sessionStorage.removeItem("thermotwin");
        setToken("");
        setNetwork(null);
      }
      const e = await r.json();
      throw Error(
        typeof e.detail === "string" ? e.detail : JSON.stringify(e.detail),
      );
    }
    return r.json();
  }
  function applyNetwork(n: Network) {
    setNetwork(n);
    setSensorId((current) =>
      n.sensors.some((s) => s.id === current)
        ? current
        : (n.sensors[0]?.id ?? ""),
    );
    setSelected((current) =>
      [
        ...n.pipes,
        ...n.valves,
        ...n.consumers,
        ...n.sensors,
        ...n.sources,
      ].some((o) => o.id === current)
        ? current
        : (n.pipes.find((p) => !p.backup)?.id ?? ""),
    );
  }
  async function refresh(access = token) {
    const [n, s, t, i]: [Network, Simulation[], Reading[], any[]] = await Promise.all([
      request("/network", {}, access),
      request("/simulations", {}, access),
      request("/telemetry", {}, access),
      request("/incidents", {}, access),
    ]);
    applyNetwork(n);
    setHistory(s);
    setReadings(t);
    setIncidents(i);
  }
  useEffect(() => {
    const saved = sessionStorage.getItem("thermotwin");
    if (saved) {
      const s = JSON.parse(saved);
      setToken(s.token);
      setRole(s.role);
      setUsername(s.username ?? "dispatcher");
    }
  }, []);
  useEffect(() => {
    if (!token) return;
    refresh().catch((e) => setError(e.message));
    const poll = setInterval(
      () =>
        request("/telemetry")
          .then(setReadings)
          .catch((e) => setError(e.message)),
      30000,
    );
    const ws = new WebSocket(API.replace(/^http/, "ws") + "/api/v1/ws");
    ws.onopen = () => ws.send(token);
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.type === "telemetry") setReadings(data.readings);
    };
    return () => {
      clearInterval(poll);
      ws.close();
    };
  }, [token]);
  useEffect(() => {
    if (token && tab === "telemetry")
      request("/telemetry/history")
        .then(setTelemetryHistory)
        .catch((e) => setError(String(e)));
  }, [token, tab]);
  async function login(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = await request(
        "/auth/login",
        { method: "POST", body: JSON.stringify({ username, password }) },
        "",
      );
      sessionStorage.setItem("thermotwin", JSON.stringify(data));
      setToken(data.token);
      setRole(data.role);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function run() {
    if (!network) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const data = await request("/simulations", {
        method: "POST",
        body: JSON.stringify({
          network_version: network.version,
          incident: { type: incident, segment_id: target },
          constraints: {
            consider_supply: true,
            consider_return: true,
            allow_backup_routes: backup,
          },
        }),
      });
      setResult(data);
      setStep(4);
      setVariantIndex(0);
      setSelectedVariant(false);
      setHistory((h) => [data, ...h]);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function download(id: string) {
    try {
      const response = await fetch(
        API +
          "/api/v1/reports/" +
          id +
          "?variant_index=" +
          (result?.simulation_id === id && tab === "scenarios"
            ? variantIndex
            : (variantChoices[id] ?? 0)),
        {
          headers: { Authorization: "Bearer " + token },
        },
      );
      if (!response.ok) throw Error("Не удалось сформировать отчёт");
      const url = URL.createObjectURL(await response.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = "ThermoTwin-" + id + ".pdf";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(String(e));
    }
  }
  async function register() {
    if (!result) return;
    try {
      const data = await request("/incidents", {
        method: "POST",
        body: JSON.stringify({
          simulation_id: result.simulation_id,
          variant_index: variantIndex,
        }),
      });
      setIncidents((items) => [data, ...items]);
      setNotice("Демонстрационный инцидент зарегистрирован");
    } catch (e) {
      setError(String(e));
    }
  }
  async function importFile(file?: File) {
    if (!file) return;
    setBusy(true);
    try {
      const data = await request("/network/import", {
        method: "POST",
        body: await file.text(),
      });
      await refresh();
      setResult(null);
      setNotice(
        `Импортирована версия ${data.version}. Предупреждений: ${data.warnings.length}`,
      );
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  const valve = network?.valves.find((v) => v.id === selected);
  const target =
    valve?.segment_id ??
    (network?.pipes.some((p) => p.id === selected) ? selected : "");
  const pipe = network?.pipes.find((p) => p.id === target);
  const consumer = network?.consumers.find((b) => b.id === selected);
  const sensor = network?.sensors.find((s) => s.id === selected);
  const source = network?.sources.find((s) => s.id === selected);
  const matches = network
    ? [
        ...network.pipes.map((p) => ({
          id: p.id,
          name:
            p.contour === "supply"
              ? "Подающий трубопровод"
              : "Обратный трубопровод",
        })),
        ...network.consumers.map((b) => ({ id: b.id, name: b.address })),
        ...network.valves.map((v) => ({ id: v.id, name: "Задвижка" })),
        ...network.sensors.map((s) => ({ id: s.id, name: "Датчик" })),
        ...network.sources.map((s) => ({ id: s.id, name: "Источник тепла" })),
      ]
        .filter((o) =>
          (o.id + " " + o.name).toLowerCase().includes(search.toLowerCase()),
        )
        .slice(0, 8)
    : [];
  const navItems = [
    { key: "overview", icon: LayoutDashboard, label: "Дашборд" },
    { key: "map", icon: Map, label: "Карта сети" },
    { key: "scenarios", icon: GitCompareArrows, label: "Симуляции" },
    { key: "telemetry", icon: Activity, label: "Телеметрия" },
    { key: "incidents", icon: TriangleAlert, label: "Инциденты" },
    { key: "reports", icon: FileText, label: "Отчёты" },
    { key: "imports", icon: Upload, label: "Импорт сети" },
    { key: "users", icon: Users, label: "Пользователи" },
    { key: "settings", icon: Settings, label: "Настройки" },
  ];
  const titles: Record<string, string> = {
    overview: "Дашборд",
    map: "Карта тепловой сети",
    scenarios: "Симуляция аварии",
    telemetry: "Телеметрия",
    incidents: "Инциденты",
    reports: "Отчёты",
    imports: "Импорт сети",
    users: "Пользователи",
    settings: "Настройки",
  };
  const time = (value: string, full = false) =>
    new Date(value).toLocaleString("ru-RU", {
      timeZone: "Asia/Almaty",
      ...(full ? {} : { hour: "2-digit", minute: "2-digit" }),
    });
  function navigate(key: string) {
    setTab(key);
    setMobileNav(false);
    setNotice("");
    if (key === "map" || key === "telemetry" || key === "overview") {
      setResult(null);
      request("/network").then(applyNetwork).catch((e) => setError(String(e)));
    }
    if ((key === "settings" || key === "imports") && role === "admin")
      request("/audit")
        .then(setAudit)
        .catch((e) => setError(String(e)));
  }
  async function openSimulation(s: Simulation, index = 0) {
    try {
      const snapshotNetwork = await request(
        "/network?version=" + encodeURIComponent(s.network_version),
      );
      setNetwork(snapshotNetwork);
      setResult(s);
      setSelected(s.request.incident.segment_id);
      setStep(4);
      setVariantIndex(index);
      setVariantChoices((choices) => ({
        ...choices,
        [s.simulation_id]: index,
      }));
      navigate("scenarios");
    } catch (e) {
      setError(String(e));
    }
  }
  function selectObject(id: string) {
    setSelected(id);
    setPanelOpen(true);
    if (network?.sensors.some((s) => s.id === id)) setSensorId(id);
  }
  const nodeLookup = Object.fromEntries(
    network?.nodes.map((n) => [n.id, n]) ?? [],
  );
  const online = readings.filter((r) => r.status !== "no_connection").length;
  const normal = readings.filter((r) => r.status === "normal").length;
  const alarms = readings.filter((r) => r.status === "alarm").length;
  const meanPressure = (contour: string) => {
    const rs = readings.filter(
      (r) =>
        network?.sensors.find((s) => s.id === r.sensor_id)?.kind ===
          "pressure" &&
        nodeLookup[
          network?.sensors.find((s) => s.id === r.sensor_id)?.node_id ?? ""
        ]?.contour === contour &&
        r.status !== "no_connection",
    );
    return rs.length
      ? (rs.reduce((sum, r) => sum + r.value, 0) / rs.length).toFixed(2)
      : "—";
  };
  const lastReading = readings.length
    ? readings.reduce((a, b) => (a.timestamp > b.timestamp ? a : b)).timestamp
    : "";
  const selectedReading = readings.find(
    (r) => r.sensor_id === (sensor?.id ?? sensorId),
  );
  const selectedSensor =
    network?.sensors.find((s) => s.id === (sensor?.id ?? sensorId)) ??
    network?.sensors[0];
  const sensorReadings = readings.filter(
    (r) =>
      (telemetryFilter === "all" || r.status === telemetryFilter) &&
      (sensorKind === "all" ||
        network?.sensors.find((s) => s.id === r.sensor_id)?.kind ===
          sensorKind),
  );
  const chartSamples = telemetryHistory
    .slice()
    .reverse()
    .map((batch) =>
      batch.readings.find((r) => r.sensor_id === selectedSensor?.id),
    )
    .filter((r): r is Reading => !!r)
    .map((r) => ({ timestamp: r.timestamp, value: r.value }));
  if (
    selectedReading &&
    !chartSamples.some((p) => p.timestamp === selectedReading.timestamp)
  )
    chartSamples.push({
      timestamp: selectedReading.timestamp,
      value: selectedReading.value,
    });
  const currentVariant = result?.variants[variantIndex];
  const displayedResult =
    result && currentVariant && tab === "scenarios"
      ? {
          ...result,
          ...currentVariant,
          affected_segments:
            currentVariant.affected_segments ??
            (variantIndex === 0
              ? result.affected_segments
              : (network?.pipes
                  .filter((p) =>
                    currentVariant.valve_operations.some(
                      (op) =>
                        op.state === "closed" &&
                        network.valves.find((v) => v.id === op.valve_id)
                          ?.segment_id === p.id,
                    ),
                  )
                  .map((p) => p.id) ?? [])),
        }
      : result;
  function chooseVariant(index: number, commit = false) {
    setVariantIndex(index);
    setSelectedVariant(commit);
    if (result)
      setVariantChoices((choices) => ({
        ...choices,
        [result.simulation_id]: index,
      }));
  }
  const baseReport = history.find(
    (s) => s.simulation_id === (reportId || history[0]?.simulation_id),
  );
  const report = baseReport
    ? {
        ...baseReport,
        ...baseReport.variants[variantChoices[baseReport.simulation_id] ?? 0],
      }
    : undefined;
  const filteredReports = history.filter(
    (s) => reportFilter === "all" || s.request.incident.type === reportFilter,
  );
  function stat(
    label: string,
    value: string | number,
    detail: string,
    Icon: typeof Activity,
    color = "blue",
  ) {
    return (
      <div className="metric">
        <span className={"metric-icon " + color}>
          <Icon size={19} />
        </span>
        <div>
          <strong>{value}</strong>
          <span>{label}</span>
          <small>{detail}</small>
        </div>
      </div>
    );
  }
  function mapContent(mode = "network") {
    if (!network) return null;
    return (
      <div
        className={
          "map-stage " + (mode === "simulation" ? "simulation-map" : "")
        }
      >
        <NetworkMap
          network={
            mode === "telemetry"
              ? {
                  ...network,
                  sensors: network.sensors.filter((s) =>
                    sensorReadings.some((r) => r.sensor_id === s.id),
                  ),
                }
              : network
          }
          result={displayedResult}
          selected={selected}
          onSelect={selectObject}
          showReturn={showReturn}
          showConsumers={showConsumers}
          showSensors={showSensors}
          readings={readings}
          showSupply={showSupply}
          showValves={showValves}
          showBasemap={showBasemap}
          showZones={showZones}
        />
        <div className="map-context">
          <span className="demo-chip">МОДЕЛЬ</span>{" "}
          {network.geography ? "Костанай · Юбилейный" : "Архивная сеть"} ·{" "}
          {network.version}
        </div>
        <button
          className="layer-button icon-button"
          aria-label="Слои карты"
          onClick={() => setLayersOpen(!layersOpen)}
        >
          <Layers size={18} />
        </button>
        {layersOpen && (
          <div className="layers">
            <div className="floating-title">
              Слои карты
              <button
                aria-label="Скрыть слои"
                onClick={() => setLayersOpen(false)}
              >
                <X size={13} />
              </button>
            </div>
            {[
              [showSupply, setShowSupply, "Трубопровод (подача)", "orange"],
              [showReturn, setShowReturn, "Трубопровод (обратка)", "blue"],
              [showValves, setShowValves, "Задвижки", "blue"],
              [showConsumers, setShowConsumers, "Потребители", "green"],
              [showSensors, setShowSensors, "Датчики", "green"],
              [showZones, setShowZones, "Зоны отключения", "red"],
              [showBasemap, setShowBasemap, "Городская подложка", "gray"],
            ].map(([value, set, label, color]) => (
              <label className="layer-toggle" key={label as string}>
                <input
                  type="checkbox"
                  checked={value as boolean}
                  onChange={(e) =>
                    (set as (v: boolean) => void)(e.target.checked)
                  }
                />
                <span className={"toggle " + color} />
                {label as string}
              </label>
            ))}
          </div>
        )}
        <div className="map-legend">
          <span>
            <i className="orange" />
            Подача
          </span>
          <span>
            <i className="blue" />
            Обратка
          </span>
          <span>
            <i className="green" />
            Датчик
          </span>
          {result && (
            <span>
              <i className="red" />
              Отключение
            </span>
          )}
        </div>
        <div className="map-demo-note">
          {network.geography
            ? "Теплосеть смоделирована вдоль дорог OSM"
            : "Архивная демонстрационная топология"}
          {displayedResult?.affected_consumers.length
            ? network.geography
              ? " · затронутые здания выделены"
              : " · граница зоны условная"
            : ""}
        </div>
      </div>
    );
  }
  function objectPanel() {
    if (!network) return null;
    return (
      <aside className="object-panel">
        <div className="section-heading">
          <h2>
            {pipe
              ? "Трубопровод"
              : consumer
                ? "Потребитель"
                : sensor
                  ? "Датчик"
                  : source
                    ? "Источник тепла"
                    : "Объект сети"}
          </h2>
          <button
            aria-label="Скрыть карточку объекта"
            onClick={() => setPanelOpen(false)}
          >
            <X size={16} />
          </button>
        </div>
        <div className="object-id">
          <span className="object-symbol">
            <NetworkIcon size={19} />
          </span>
          <div>
            <strong>{selected}</strong>
            <span>
              {pipe
                ? pipe.contour === "supply"
                  ? "Подающий контур"
                  : "Обратный контур"
                : (consumer?.address ??
                  sensor?.node_id ??
                  "Сетевая инфраструктура")}
            </span>
          </div>
        </div>
        <dl className="details">
          <dt>ID</dt>
          <dd className="mono">{selected}</dd>
          {pipe && (
            <>
              {pipe.name && (
                <>
                  <dt>Трасса</dt>
                  <dd>{pipe.name}</dd>
                </>
              )}
              <dt>Тип</dt>
              <dd>
                {pipe.backup ? "Резервная ветка" : "Участок трубопровода"}
              </dd>
              <dt>Контур</dt>
              <dd>{pipe.contour === "supply" ? "Подача" : "Обратка"}</dd>
              <dt>Диаметр</dt>
              <dd>DN {pipe.diameter_mm}</dd>
              <dt>Длина</dt>
              <dd>
                {pipe.length_m.toLocaleString("ru-RU", {
                  maximumFractionDigits: 1,
                })}{" "}
                м
              </dd>
              <dt>Статус</dt>
              <dd>
                <span
                  className={
                    "status " +
                    (result?.affected_segments.includes(pipe.id)
                      ? "danger"
                      : "success")
                  }
                >
                  {result?.affected_segments.includes(pipe.id)
                    ? "Изолирован"
                    : "Норма"}
                </span>
              </dd>
            </>
          )}
          {consumer && (
            <>
              <dt>Нагрузка</dt>
              <dd>{consumer.load_kw} кВт</dd>
              <dt>Численность</dt>
              <dd>{consumer.population ?? "Нет данных"}</dd>
            </>
          )}
          {sensor && (
            <>
              <dt>Измерение</dt>
              <dd>
                {sensor.kind === "pressure"
                  ? "Давление"
                  : sensor.kind === "temperature"
                    ? "Температура"
                    : "Расход"}
              </dd>
              <dt>Режим</dt>
              <dd>Виртуальный источник</dd>
            </>
          )}
        </dl>
        <div className="tabs compact">
          {[
            ["telemetry", "Телеметрия"],
            ["links", "Связанные"],
            ["actions", "Действия"],
          ].map(([key, label]) => (
            <button
              key={key}
              className={objectTab === key ? "active" : ""}
              onClick={() => setObjectTab(key)}
            >
              {label}
            </button>
          ))}
        </div>
        {objectTab === "telemetry" ? (
          <>
            <div className="mini-metrics">
              <div>
                <small>{sensor ? "Показание" : "Давление подачи"}</small>
                <strong>
                  {sensor
                    ? (selectedReading?.value ?? "—")
                    : meanPressure("supply")}{" "}
                  <em>{selectedReading?.unit ?? "бар"}</em>
                </strong>
                <span>
                  {sensor
                    ? selectedReading?.status === "no_connection"
                      ? "Нет связи"
                      : "Виртуальный датчик"
                    : "Среднее по датчикам"}
                </span>
              </div>
              <div>
                <small>Обратка</small>
                <strong>
                  {meanPressure("return")} <em>бар</em>
                </strong>
                <span>Среднее по сети</span>
              </div>
            </div>
            {selectedReading && (
              <small className="muted">
                Обновлено {time(selectedReading.timestamp)}
              </small>
            )}
          </>
        ) : objectTab === "links" ? (
          <div className="related">
            {pipe && (
              <>
                <span>
                  Начальный узел <b>{pipe.start}</b>
                </span>
                <span>
                  Конечный узел <b>{pipe.end}</b>
                </span>
                {network.valves
                  .filter((v) => v.segment_id === pipe.id)
                  .map((v) => (
                    <button
                      className="secondary full"
                      key={v.id}
                      onClick={() => selectObject(v.id)}
                    >
                      {v.id}
                      <ChevronRight size={13} />
                    </button>
                  ))}
              </>
            )}
            {consumer && (
              <>
                <span>
                  Подача <b>{consumer.supply_node}</b>
                </span>
                <span>
                  Обратка <b>{consumer.return_node}</b>
                </span>
              </>
            )}
            {sensor && (
              <span>
                Узел <b>{sensor.node_id}</b>
              </span>
            )}
          </div>
        ) : (
          <div className="related">
            <p>Расчётные действия выполняются в отдельном сценарии.</p>
            <button
              className="secondary full"
              disabled={!target || role === "observer"}
              onClick={() => {
                setStep(1);
                navigate("scenarios");
              }}
            >
              Создать сценарий <ArrowRight size={14} />
            </button>
          </div>
        )}
        <div className="object-actions">
          <button
            className="primary full"
            disabled={!target || role === "observer"}
            onClick={() => {
              setStep(1);
              navigate("scenarios");
            }}
          >
            <Flame size={16} />
            Смоделировать аварию
          </button>
          <button
            className="secondary full"
            disabled={!result}
            onClick={() => {
              setStep(4);
              navigate("scenarios");
            }}
          >
            <LocateFixed size={15} />
            Показать зону отключения
          </button>
          <button
            className="secondary full"
            disabled={!target || role === "observer" || busy}
            onClick={() => {
              setBackup(true);
              setStep(3);
              navigate("scenarios");
            }}
          >
            <Shield size={15} />
            Найти резервные маршруты
          </button>
        </div>
        <div className="panel-events">
          <div className="section-heading">
            <h3>Последние события</h3>
            <button className="link" onClick={() => navigate("incidents")}>
              Все события <ArrowRight size={12} />
            </button>
          </div>
          {incidents.slice(0, 3).map((i) => (
            <div className="event-row" key={i.id}>
              <i className="red" />
              <small>{time(i.created_at)}</small>
              <span>
                {labels[i.type]} · {i.segment_id}
              </span>
            </div>
          ))}
          {!incidents.length && (
            <p className="muted">Инциденты ещё не зарегистрированы</p>
          )}
        </div>
        <div className="panel-disclaimer">
          <Shield size={13} /> Поддержка решений. Без управления оборудованием.
        </div>
      </aside>
    );
  }
  if (!token)
    return (
      <main className="login">
        <div className="login-card">
          <div className="brand">
            <span className="brand-icon">
              <NetworkIcon size={26} />
            </span>
            ThermoTwin
          </div>
          <span className="eyebrow">ДИСПЕТЧЕРСКАЯ ПЛАТФОРМА</span>
          <h1>
            Тепловая сеть.
            <br />
            Под вашим контролем.
          </h1>
          <p>
            Цифровой двойник для моделирования аварий, мониторинга датчиков и
            оценки последствий.
          </p>
          <form onSubmit={login}>
            <label>
              Пользователь
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
              />
            </label>
            <label>
              Пароль
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </label>
            <button className="primary" disabled={busy}>
              {busy ? "Подключение…" : "Войти в систему"}
              <ArrowRight size={17} />
            </button>
          </form>
          {error && <div className="error">{error}</div>}
          <div className="demo-accounts">
            <span className="demo-chip">DEMO</span> dispatcher / demo-dispatcher
            <br />
            admin / demo-admin · observer / demo-observer
          </div>
        </div>
        <div className="login-art">
          <div className="login-grid">
            <span />
            <span />
            <span />
            <span />
            <span />
            <span />
            <span />
            <span />
            <span />
          </div>
          <span className="art-label">
            <span className="live-dot" />
            Цифровой двойник сети
          </span>
          <h2>
            Видеть состояние.
            <br />
            <span>Предвидеть последствия.</span>
          </h2>
          <p>Карта · Симуляции · Телеметрия · Отчёты</p>
          <small>THERMOTWIN / G-TON 2026</small>
        </div>
      </main>
    );
  return (
    <div className="shell">
      <aside className={"sidebar " + (mobileNav ? "mobile-open" : "")}>
        <div className="brand">
          <span className="brand-icon">
            <NetworkIcon size={23} />
          </span>
          ThermoTwin
        </div>
        <nav>
          {navItems.map(({ key, icon: Icon, label }, i) => (
            <button
              key={key}
              className={
                (tab === key ? "active " : "") + (i === 7 ? "nav-divider" : "")
              }
              onClick={() => navigate(key)}
              title={label}
            >
              <Icon size={17} />
              <span>{label}</span>
              {key === "incidents" && incidents.length > 0 && (
                <b className="nav-count">{incidents.length}</b>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="demo-note">
            <Shield size={16} />
            <div>
              <strong>Демонстрационная сеть</strong>
              <span>Юбилейный · {network?.version ?? "…"}</span>
            </div>
          </div>
          <button
            className="help-link"
            onClick={() => {
              setNotice(
                "Модель синтетическая. Расчёты служат для демонстрации и не управляют оборудованием.",
              );
              setMobileNav(false);
            }}
          >
            <CircleHelp size={16} />О платформе
          </button>
          <button
            className="logout"
            onClick={() => {
              sessionStorage.removeItem("thermotwin");
              setToken("");
              setNetwork(null);
              setResult(null);
            }}
          >
            <LogOut size={15} />
            Выйти из системы
          </button>
        </div>
      </aside>
      {mobileNav && (
        <button
          className="nav-scrim"
          aria-label="Закрыть меню"
          onClick={() => setMobileNav(false)}
        />
      )}
      <main className="main">
        <header className="topbar">
          <div className="topbar-left">
            <button
              className="mobile-menu icon-button"
              aria-label="Открыть меню"
              onClick={() => setMobileNav(true)}
            >
              <Menu size={20} />
            </button>
            <div className="search">
              <Search size={15} />
              <input
                aria-label="Поиск объектов"
                placeholder="Поиск по объектам, адресам, датчикам…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              {search && (
                <div className="search-results">
                  {matches.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => {
                        selectObject(m.id);
                        setSearch("");
                        navigate("map");
                      }}
                    >
                      <strong>{m.id}</strong>
                      <small>{m.name}</small>
                    </button>
                  ))}
                  {!matches.length && (
                    <span className="muted">Объекты не найдены</span>
                  )}
                </div>
              )}
            </div>
            <span className="district">
              {network?.geography
                ? `${network.geography.city} · ${network.geography.district}`
                : "Архивная модель"}{" "}
              <ChevronDown size={12} />
            </span>
            <span className="live-badge">
              <span className="live-dot" />
              Виртуальный Live
            </span>
          </div>
          <div className="topbar-right">
            <button
              className="icon-button apps-button"
              aria-label="Дашборд"
              onClick={() => navigate("overview")}
            >
              <Grid2X2 size={17} />
            </button>
            <button
              className="notification icon-button"
              aria-label="Инциденты"
              onClick={() => navigate("incidents")}
            >
              <Bell size={18} />
              {incidents.length > 0 && <b>{incidents.length}</b>}
            </button>
            <span className="header-divider" />
            <button className="profile" onClick={() => navigate("users")}>
              <span className="avatar">{role[0].toUpperCase()}</span>
              <span>
                <strong>{username}</strong>
                <small>
                  {role === "admin"
                    ? "Администратор"
                    : role === "observer"
                      ? "Наблюдатель"
                      : "Диспетчер"}
                </small>
              </span>
              <ChevronDown size={12} />
            </button>
          </div>
        </header>
        <div className="content">
          <div className="page-heading">
            <div>
              <span className="breadcrumb">
                Рабочее пространство <ChevronRight size={12} /> {titles[tab]}
              </span>
              <h1>{titles[tab]}</h1>
              <p>
                {tab === "map"
                  ? network?.geography
                    ? `${network.geography.country} → ${network.geography.region} → ${network.geography.city} → мкр. «${network.geography.district}»`
                    : "Архивная демонстрационная модель"
                  : tab === "scenarios"
                    ? "Моделирование инцидента, расчёт зоны отключения и сравнение вариантов"
                    : tab === "telemetry"
                      ? "Мониторинг датчиков, история показаний и отклонения"
                      : tab === "reports"
                        ? "PDF-отчёты по сохранённым расчётам и история сценариев"
                        : network?.geography
                          ? `${network.geography.country} → ${network.geography.region} → ${network.geography.city} → мкр. «${network.geography.district}»`
                          : "Архивная демонстрационная модель"}
              </p>
            </div>
            <div className="heading-actions">
              <span className="demo-chip">Синтетическая модель</span>
              {tab === "map" && (
                <button
                  className="secondary"
                  onClick={() => setPanelOpen(!panelOpen)}
                  aria-label="Карточка объекта"
                >
                  {panelOpen ? (
                    <PanelRightClose size={16} />
                  ) : (
                    <PanelRightOpen size={16} />
                  )}
                </button>
              )}
              {tab === "scenarios" && (
                <button
                  className="primary"
                  disabled={!result || role === "observer"}
                  onClick={register}
                >
                  <Plus size={15} />
                  Создать инцидент
                </button>
              )}
              {tab === "reports" && (
                <button
                  className="secondary"
                  disabled={!report}
                  onClick={() => report && download(report.simulation_id)}
                >
                  <Download size={15} />
                  Экспорт PDF
                </button>
              )}
            </div>
          </div>
          {error && (
            <div className="error">
              <TriangleAlert size={16} />
              <span>{error}</span>
              <button aria-label="Закрыть ошибку" onClick={() => setError("")}>
                <X size={15} />
              </button>
            </div>
          )}
          {notice && (
            <div className="notice">
              <Check size={16} />
              <span>{notice}</span>
              <button
                aria-label="Закрыть уведомление"
                onClick={() => setNotice("")}
              >
                <X size={15} />
              </button>
            </div>
          )}
          {!network ? (
            <div className="empty">Загрузка модели сети…</div>
          ) : (
            <>
              {(tab === "map" || tab === "overview") && (
                <>
                  <div className="stats">
                    {stat(
                      "Зарегистрировано инцидентов",
                      incidents.length,
                      "Демонстрационные события",
                      TriangleAlert,
                      "red",
                    )}
                    {stat(
                      "Потребителей подключено",
                      network.consumers.length,
                      `${network.pipes.length.toLocaleString("ru")} участков труб`,
                      Building2,
                      "cyan",
                    )}
                    {stat(
                      "Датчиков онлайн",
                      `${readings.length ? Math.round((online / readings.length) * 100) : 0}%`,
                      `${online} / ${readings.length} датчиков`,
                      Radio,
                      "green",
                    )}
                    {stat(
                      "Давление подачи",
                      `${meanPressure("supply")} бар`,
                      `Обратка: ${meanPressure("return")} бар`,
                      Gauge,
                      "blue",
                    )}
                    {stat(
                      "Показаний в норме",
                      normal,
                      `${alarms} отклонений`,
                      Activity,
                      "orange",
                    )}
                    {stat(
                      "Последнее обновление",
                      lastReading ? time(lastReading) : "—",
                      "Часовой пояс: Алматы",
                      Clock,
                      "blue",
                    )}
                  </div>
                  {tab === "map" ? (
                    <div
                      className={
                        "network-workspace " +
                        (!panelOpen ? "panel-hidden" : "")
                      }
                    >
                      {mapContent()}
                      {panelOpen && objectPanel()}
                    </div>
                  ) : (
                    <div className="overview-grid">
                      <section className="card">
                        <div className="section-heading">
                          <h2>Состояние тепловой сети</h2>
                          <button
                            className="link"
                            onClick={() => navigate("map")}
                          >
                            Открыть карту <ArrowRight size={14} />
                          </button>
                        </div>
                        {mapContent()}
                      </section>
                      <section className="card">
                        <div className="section-heading">
                          <h2>Последние расчёты</h2>
                          <span className="status neutral">
                            {history.length}
                          </span>
                        </div>
                        {history.slice(0, 5).map((s) => (
                          <button
                            className="scenario-row"
                            key={s.simulation_id}
                            onClick={() => openSimulation(s)}
                          >
                            <span className="row-icon">
                              <GitCompareArrows size={17} />
                            </span>
                            <div>
                              <strong>{labels[s.request.incident.type]}</strong>
                              <small>
                                {s.request.incident.segment_id} ·{" "}
                                {time(s.created_at)}
                              </small>
                            </div>
                            <b>
                              {s.affected_consumers.length}
                              <small>без тепла</small>
                            </b>
                            <ChevronRight size={14} />
                          </button>
                        ))}
                        {!history.length && (
                          <div className="empty small">
                            Создайте первый сценарий на карте
                          </div>
                        )}
                        <div className="info">
                          <Shield size={17} />
                          <p>
                            {network.nodes.length} узлов в текущей модели.
                            Сценарии сохраняются с версией модели и не меняют
                            фактическое состояние сети.
                          </p>
                        </div>
                      </section>
                    </div>
                  )}
                </>
              )}
              {tab === "scenarios" && (
                <>
                  <div className="stepper">
                    {["Тип аварии", "Участок", "Ограничения", "Результаты"].map(
                      (label, i) => (
                        <button
                          key={label}
                          className={
                            (step === i + 1 ? "current " : "") +
                            (step > i + 1 ? "completed" : "")
                          }
                          disabled={i === 3 && !result}
                          onClick={() => setStep(i + 1)}
                        >
                          <span>
                            {step > i + 1 ? <Check size={14} /> : i + 1}
                          </span>
                          <div>
                            <strong>{label}</strong>
                            <small>
                              {
                                [
                                  "Выбор события",
                                  "Выбор на карте",
                                  "Параметры расчёта",
                                  "Сравнение вариантов",
                                ][i]
                              }
                            </small>
                          </div>
                          {i < 3 && <i />}
                        </button>
                      ),
                    )}
                  </div>
                  <div className="simulation-workspace">
                    <section className="simulation-map-panel">
                      {mapContent("simulation")}
                    </section>
                    <section className="simulation-results">
                      <div className="section-heading">
                        <h2>
                          {step === 4
                            ? "Результат расчёта"
                            : `Шаг ${step}. ${["", "Тип аварии", "Повреждённый участок", "Ограничения расчёта"][step]}`}
                        </h2>
                        <span className="demo-chip">DEMO</span>
                      </div>
                      {step === 1 ? (
                        <>
                          <p className="muted">
                            Выберите событие для моделирования.
                          </p>
                          <div className="incident-options">
                            {[
                              [
                                "pipe_break",
                                "Разрыв трубы",
                                "Изоляция повреждённого участка",
                                Flame,
                              ],
                              [
                                "valve_failure",
                                "Отказ задвижки",
                                "Проверка альтернативной арматуры",
                                Shield,
                              ],
                              [
                                "pressure_drop",
                                "Снижение давления",
                                "Проверка граничных давлений",
                                Gauge,
                              ],
                            ].map(([key, title, description, Icon]) => {
                              const I = Icon as typeof Flame;
                              return (
                                <button
                                  key={key as string}
                                  className={incident === key ? "selected" : ""}
                                  onClick={() => setIncident(key as string)}
                                >
                                  <span className="row-icon">
                                    <I size={20} />
                                  </span>
                                  <div>
                                    <strong>{title as string}</strong>
                                    <small>{description as string}</small>
                                  </div>
                                  <span className="radio-ring">
                                    {incident === key && <i />}
                                  </span>
                                </button>
                              );
                            })}
                          </div>
                        </>
                      ) : step === 2 ? (
                        <>
                          <p className="muted">
                            Выберите трубопровод на карте или в списке.
                          </p>
                          <label className="field">
                            Участок сети
                            <select
                              aria-label="Участок сети"
                              value={target}
                              onChange={(e) => selectObject(e.target.value)}
                            >
                              <option value="" disabled>
                                Выберите участок
                              </option>
                              {network.pipes.map((p) => (
                                <option value={p.id} key={p.id}>
                                  {p.id} ·{" "}
                                  {p.contour === "supply"
                                    ? "Подача"
                                    : "Обратка"}{" "}
                                  · DN {p.diameter_mm}
                                </option>
                              ))}
                            </select>
                          </label>
                          {pipe && (
                            <div className="selection-summary">
                              <NetworkIcon size={20} />
                              <div>
                                <strong>{pipe.id}</strong>
                                <span>
                                  {pipe.length_m} м · DN {pipe.diameter_mm} ·{" "}
                                  {pipe.contour === "supply"
                                    ? "Подающий контур"
                                    : "Обратный контур"}
                                </span>
                              </div>
                            </div>
                          )}
                        </>
                      ) : step === 3 ? (
                        <>
                          <p className="muted">
                            Сценарий выполняется отдельно от состояния сети.
                          </p>
                          <div className="constraint-row">
                            <span>
                              <CheckCircle2 size={18} />
                              <strong>Подающий и обратный контуры</strong>
                            </span>
                            <small>Достижимость проверяется совместно</small>
                          </div>
                          <label className="constraint-row clickable">
                            <span>
                              <Shield size={18} />
                              <strong>Резервные маршруты</strong>
                              <input
                                type="checkbox"
                                checked={backup}
                                onChange={(e) => setBackup(e.target.checked)}
                              />
                            </span>
                            <small>
                              Искать переключения с меньшим числом отключений
                            </small>
                          </label>
                          <div className="selection-summary">
                            <TriangleAlert size={20} />
                            <div>
                              <strong>{labels[incident]}</strong>
                              <span>
                                {target || "Участок не выбран"} · версия{" "}
                                {network.version}
                              </span>
                            </div>
                          </div>
                          <div className="info">
                            <Shield size={16} />
                            <p>
                              Операции являются расчётными предложениями.
                              Система не управляет насосами и арматурой.
                            </p>
                          </div>
                        </>
                      ) : result ? (
                        <>
                          <div className="calculation-meta">
                            <span>
                              Время расчёта{" "}
                              <b>
                                {(result.execution_ms / 1000).toFixed(3)}{" "}
                                секунды
                              </b>
                            </span>
                            <span>
                              Статус{" "}
                              <b
                                className={
                                  "status " +
                                  (result.status === "infeasible"
                                    ? "danger"
                                    : "success")
                                }
                              >
                                {result.status === "infeasible"
                                  ? "Невыполнимо"
                                  : "Готово"}
                              </b>
                            </span>
                          </div>
                          <div className="tabs">
                            {result.variants.map((v, i) => (
                              <button
                                className={variantIndex === i ? "active" : ""}
                                key={v.name}
                                onClick={() => {
                                  chooseVariant(i);
                                }}
                              >
                                Вариант {i + 1}
                              </button>
                            ))}
                          </div>
                          <div className="variant-grid">
                            {result.variants.map((v, i) => (
                              <article
                                className={
                                  "variant " +
                                  (variantIndex === i ? "selected" : "")
                                }
                                key={v.name}
                              >
                                <div className="variant-heading">
                                  <h3>Вариант {String.fromCharCode(65 + i)}</h3>
                                  {i === 0 && v.admissible && (
                                    <span className="recommended">
                                      <CheckCircle2 size={12} />
                                      Рекомендуемый
                                    </span>
                                  )}
                                </div>
                                <p>{v.name}</p>
                                <div className="variant-stats">
                                  <div>
                                    <strong>
                                      {v.disconnected_buildings.toLocaleString(
                                        "ru",
                                      )}
                                    </strong>
                                    <small>Зданий без тепла</small>
                                  </div>
                                  <div>
                                    <strong>{v.valve_operations.length}</strong>
                                    <small>Переключений</small>
                                  </div>
                                  <div>
                                    <strong>
                                      {v.estimated_population?.toLocaleString(
                                        "ru",
                                      ) ?? "—"}
                                    </strong>
                                    <small>Условных жителей</small>
                                  </div>
                                  <div>
                                    <strong
                                      className={
                                        v.admissible ? "green-text" : "red-text"
                                      }
                                    >
                                      {v.admissible
                                        ? "Пройдена"
                                        : "Не пройдена"}
                                    </strong>
                                    <small>Проверка модели</small>
                                  </div>
                                </div>
                                <button
                                  className={
                                    variantIndex === i
                                      ? "primary full"
                                      : "secondary full"
                                  }
                                  onClick={() => {
                                    chooseVariant(i, true);
                                  }}
                                >
                                  {selectedVariant && variantIndex === i ? (
                                    <>
                                      <Check size={14} />
                                      Вариант выбран
                                    </>
                                  ) : (
                                    "Выбрать вариант"
                                  )}
                                </button>
                              </article>
                            ))}
                          </div>
                          {result.status === "infeasible" && (
                            <div className="info warning">
                              <TriangleAlert size={17} />
                              <p>
                                Повреждение нельзя изолировать доступной
                                арматурой. Зона последствий не определена.
                              </p>
                            </div>
                          )}
                          <div className="result-tables">
                            <section>
                              <h3>
                                Задвижки к переключению (
                                {currentVariant?.valve_operations.length ?? 0})
                              </h3>
                              <div className="table-scroll">
                                <table>
                                  <thead>
                                    <tr>
                                      <th>ID</th>
                                      <th>Статус</th>
                                      <th>Действие</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {currentVariant?.valve_operations.map(
                                      (op) => (
                                        <tr key={op.valve_id}>
                                          <td className="mono">
                                            {op.valve_id}
                                          </td>
                                          <td>
                                            <span className="status success">
                                              {network.valves.find(
                                                (v) => v.id === op.valve_id,
                                              )?.state === "closed"
                                                ? "Закрыта"
                                                : "Открыта"}
                                            </span>
                                          </td>
                                          <td>
                                            <span className="action-label">
                                              {op.state === "closed"
                                                ? "Закрыть"
                                                : "Открыть"}
                                            </span>
                                          </td>
                                        </tr>
                                      ),
                                    )}
                                  </tbody>
                                </table>
                              </div>
                            </section>
                            <section>
                              <h3>Затронутые потребители</h3>
                              <table>
                                <thead>
                                  <tr>
                                    <th>Показатель</th>
                                    <th>Количество</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  <tr>
                                    <td>Здания</td>
                                    <td>
                                      {currentVariant?.disconnected_buildings ??
                                        result.affected_consumers.length}
                                    </td>
                                  </tr>
                                  <tr>
                                    <td>Оценка численности</td>
                                    <td>
                                      {currentVariant?.estimated_population ??
                                        "Нет данных"}
                                    </td>
                                  </tr>
                                  <tr>
                                    <td>Перепад давления</td>
                                    <td>
                                      {currentVariant?.hydraulic_validation
                                        .minimum_differential_bar ?? "—"}{" "}
                                      бар
                                    </td>
                                  </tr>
                                </tbody>
                              </table>
                            </section>
                          </div>
                          <div className="calculation-notes">
                            <span
                              className={
                                "status " +
                                (currentVariant?.admissible
                                  ? "success"
                                  : "warning")
                              }
                            >
                              Гидравлика:{" "}
                              {
                                labels[
                                  currentVariant?.hydraulic_validation.status ??
                                    result.hydraulic_validation.status
                                ]
                              }
                            </span>
                            {result.warnings.map((w) => (
                              <p key={w}>
                                <CircleHelp size={12} />
                                {w}
                              </p>
                            ))}
                          </div>
                          <div className="result-actions">
                            <button
                              className="secondary"
                              onClick={() => download(result.simulation_id)}
                            >
                              <Download size={15} />
                              PDF-отчёт
                            </button>
                            <button
                              className="secondary"
                              disabled={role === "observer"}
                              onClick={register}
                            >
                              <Plus size={15} />
                              Зарегистрировать инцидент
                            </button>
                            <span className="muted">
                              <CheckCircle2 size={13} />
                              Расчёт сохранён
                            </span>
                          </div>
                        </>
                      ) : (
                        <div className="empty">Сначала выполните расчёт</div>
                      )}
                      {step < 4 && (
                        <div className="wizard-actions">
                          <button
                            className="secondary"
                            disabled={step === 1}
                            onClick={() => setStep(step - 1)}
                          >
                            <ArrowLeft size={15} />
                            Назад
                          </button>
                          {step < 3 ? (
                            <button
                              className="primary"
                              disabled={step === 2 && !target}
                              onClick={() => setStep(step + 1)}
                            >
                              Продолжить
                              <ArrowRight size={15} />
                            </button>
                          ) : (
                            <button
                              className="primary"
                              onClick={run}
                              disabled={busy || !target || role === "observer"}
                            >
                              <Play size={15} />
                              {busy
                                ? "Выполняется расчёт…"
                                : "Рассчитать последствия"}
                            </button>
                          )}
                        </div>
                      )}
                    </section>
                  </div>
                  <section className="card history-card">
                    <div className="section-heading">
                      <h2>Сохранённые сценарии</h2>
                      <span className="status neutral">{history.length}</span>
                    </div>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Сценарий</th>
                            <th>Участок</th>
                            <th>Версия</th>
                            <th>Отключено</th>
                            <th>Время</th>
                            <th>Действия</th>
                          </tr>
                        </thead>
                        <tbody>
                          {history.slice(0, 12).map((s) => (
                            <tr key={s.simulation_id}>
                              <td>{labels[s.request.incident.type]}</td>
                              <td className="mono">
                                {s.request.incident.segment_id}
                              </td>
                              <td>{s.network_version}</td>
                              <td>{s.affected_consumers.length} зданий</td>
                              <td>{time(s.created_at, true)}</td>
                              <td>
                                <button
                                  className="link"
                                  onClick={() => openSimulation(s)}
                                >
                                  Открыть
                                </button>
                                <button
                                  className="icon-button"
                                  aria-label="Скачать отчёт"
                                  onClick={() => download(s.simulation_id)}
                                >
                                  <Download size={14} />
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                </>
              )}
              {tab === "telemetry" && (
                <>
                  <div className="filter-bar">
                    <label>
                      Тип датчика
                      <select
                        aria-label="Тип датчика"
                        value={sensorKind}
                        onChange={(e) => setSensorKind(e.target.value)}
                      >
                        <option value="all">Все типы</option>
                        <option value="pressure">Давление</option>
                        <option value="temperature">Температура</option>
                        <option value="flow">Расход</option>
                      </select>
                    </label>
                    <label>
                      Статус
                      <select
                        aria-label="Статус датчика"
                        value={telemetryFilter}
                        onChange={(e) => setTelemetryFilter(e.target.value)}
                      >
                        <option value="all">Все</option>
                        <option value="normal">Норма</option>
                        <option value="alarm">Отклонение</option>
                        <option value="no_connection">Нет связи</option>
                      </select>
                    </label>
                    <label>
                      Виртуальный источник
                      <select
                        aria-label="Профиль телеметрии"
                        value={telemetryProfile}
                        disabled={role === "observer" || profileBusy}
                        onChange={async (e) => {
                          const profile = e.target.value;
                          setProfileBusy(true);
                          setTelemetryProfile(profile);
                          try {
                            await request("/telemetry/profile", {
                              method: "POST",
                              body: JSON.stringify({ profile }),
                            });
                            setReadings(await request("/telemetry"));
                          } catch (err) {
                            setError(String(err));
                          } finally {
                            setProfileBusy(false);
                          }
                        }}
                      >
                        <option value="normal">Штатный режим</option>
                        <option value="pipe_break">
                          Разрыв / падение давления
                        </option>
                        <option value="gradual_leak">Постепенная утечка</option>
                        <option value="no_connection">Отсутствие связи</option>
                      </select>
                    </label>
                    <button
                      className="primary"
                      onClick={() => {
                        request("/telemetry")
                          .then(setReadings)
                          .catch((e) => setError(String(e)));
                        request("/telemetry/history")
                          .then(setTelemetryHistory)
                          .catch((e) => setError(String(e)));
                      }}
                    >
                      <RefreshCw size={15} />
                      Обновить
                    </button>
                  </div>
                  <div className="stats telemetry-stats">
                    {stat(
                      "Датчиков онлайн",
                      online,
                      `${readings.length ? Math.round((online / readings.length) * 100) : 0}% сети`,
                      Radio,
                      "green",
                    )}
                    {stat(
                      "Отклонений",
                      alarms,
                      "Виртуальные показания",
                      CircleX,
                      "red",
                    )}
                    {stat(
                      "Нет связи",
                      readings.length - online,
                      "Последний замер сохранён",
                      TriangleAlert,
                      "orange",
                    )}
                    {stat(
                      "Показаний в норме",
                      normal,
                      "Текущий статус датчиков",
                      CheckCircle2,
                      "green",
                    )}
                    {stat(
                      "Последнее обновление",
                      lastReading ? time(lastReading) : "—",
                      "Интервал источника: 30 с",
                      Clock,
                      "blue",
                    )}
                  </div>
                  <div className="telemetry-workspace">
                    <section className="telemetry-main">
                      <div className="tabs telemetry-tabs">
                        {[
                          ["map", `Карта датчиков (${sensorReadings.length})`],
                          ["chart", "График"],
                          ["table", "Таблица"],
                        ].map(([key, label]) => (
                          <button
                            key={key}
                            className={telemetryView === key ? "active" : ""}
                            onClick={() => setTelemetryView(key)}
                          >
                            {label}
                          </button>
                        ))}
                      </div>
                      {telemetryView === "map" ? (
                        mapContent("telemetry")
                      ) : telemetryView === "chart" ? (
                        <div className="chart-large">
                          <h2>Датчик {selectedSensor?.id ?? "—"}</h2>
                          <TelemetryChart
                            samples={chartSamples}
                            unit={selectedReading?.unit ?? "бар"}
                          />
                        </div>
                      ) : (
                        <div className="table-scroll">
                          <table>
                            <thead>
                              <tr>
                                <th>Датчик</th>
                                <th>Тип</th>
                                <th>Показание</th>
                                <th>Статус</th>
                                <th>Обновление</th>
                              </tr>
                            </thead>
                            <tbody>
                              {sensorReadings.map((r) => (
                                <tr
                                  className={
                                    selectedSensor?.id === r.sensor_id
                                      ? "selected-row"
                                      : ""
                                  }
                                  key={r.sensor_id}
                                  onClick={() => {
                                    setSensorId(r.sensor_id);
                                    setSelected(r.sensor_id);
                                  }}
                                >
                                  <td className="mono">{r.sensor_id}</td>
                                  <td>
                                    {network.sensors.find(
                                      (s) => s.id === r.sensor_id,
                                    )?.kind === "pressure"
                                      ? "Давление"
                                      : network.sensors.find(
                                            (s) => s.id === r.sensor_id,
                                          )?.kind === "temperature"
                                        ? "Температура"
                                        : "Расход"}
                                  </td>
                                  <td>
                                    {r.value} {r.unit}
                                  </td>
                                  <td>
                                    <span
                                      className={
                                        "status " +
                                        (r.status === "normal"
                                          ? "success"
                                          : r.status === "alarm"
                                            ? "danger"
                                            : "neutral")
                                      }
                                    >
                                      {r.status === "normal"
                                        ? "Норма"
                                        : r.status === "alarm"
                                          ? "Отклонение"
                                          : "Нет связи"}
                                    </span>
                                  </td>
                                  <td>{time(r.timestamp)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {!sensorReadings.length && (
                            <div className="empty small">
                              Нет датчиков по выбранным фильтрам
                            </div>
                          )}
                        </div>
                      )}
                    </section>
                    <aside className="sensor-panel">
                      <div className="section-heading">
                        <h2>{selectedSensor?.id ?? "Датчик"}</h2>
                        <span
                          className={
                            "status " +
                            (selectedReading?.status === "normal"
                              ? "success"
                              : "danger")
                          }
                        >
                          {selectedReading?.status === "normal"
                            ? "Норма"
                            : selectedReading?.status === "no_connection"
                              ? "Нет связи"
                              : "Отклонение"}
                        </span>
                      </div>
                      <dl className="details">
                        <dt>Тип</dt>
                        <dd>
                          {selectedSensor?.kind === "pressure"
                            ? "Давление"
                            : selectedSensor?.kind === "temperature"
                              ? "Температура"
                              : "Расход"}
                        </dd>
                        <dt>Расположение</dt>
                        <dd>{selectedSensor?.node_id ?? "—"}</dd>
                        <dt>Источник</dt>
                        <dd>Виртуальный</dd>
                        <dt>Текущее значение</dt>
                        <dd className="sensor-value">
                          {selectedReading?.value ?? "—"}{" "}
                          {selectedReading?.unit ?? "бар"}
                        </dd>
                        <dt>Обновление</dt>
                        <dd>
                          {selectedReading
                            ? time(selectedReading.timestamp)
                            : "—"}
                        </dd>
                      </dl>
                      <label className="field">
                        Выбрать датчик
                        <select
                          aria-label="Выбрать датчик"
                          value={selectedSensor?.id ?? ""}
                          onChange={(e) => {
                            setSensorId(e.target.value);
                            setSelected(e.target.value);
                          }}
                        >
                          {network.sensors.map((s) => (
                            <option key={s.id} value={s.id}>
                              {s.id}
                            </option>
                          ))}
                        </select>
                      </label>
                      <TelemetryChart
                        samples={chartSamples}
                        unit={selectedReading?.unit ?? "бар"}
                      />
                      <div className="section-heading">
                        <h3>Последние показания</h3>
                        <span className="status neutral">UTC+05</span>
                      </div>
                      {chartSamples
                        .slice(-5)
                        .reverse()
                        .map((p, i) => (
                          <div className="event-row" key={p.timestamp + i}>
                            <i className="green" />
                            <small>{time(p.timestamp)}</small>
                            <span>
                              {p.value} {selectedReading?.unit ?? "бар"}
                            </span>
                          </div>
                        ))}
                      <div className="panel-disclaimer">
                        <CircleHelp size={14} />
                        История получена из журнала показаний backend.
                      </div>
                    </aside>
                  </div>
                </>
              )}
              {tab === "reports" && (
                <div className="reports-workspace">
                  <section className="reports-main">
                    <div className="tabs">
                      <button className="active">Создать отчёт</button>
                      <span className="tabs-note">
                        Отчёты формируются из сохранённых расчётов
                      </span>
                    </div>
                    <div className="report-types">
                      <div className="report-type selected">
                        <span className="metric-icon blue">
                          <FileText size={21} />
                        </span>
                        <div>
                          <strong>Отчёт об инциденте</strong>
                          <small>Описание, действия, схема</small>
                        </div>
                        <CheckCircle2 size={16} />
                      </div>
                      <div className="report-type">
                        <span className="metric-icon green">
                          <GitCompareArrows size={21} />
                        </span>
                        <div>
                          <strong>Отчёт по симуляции</strong>
                          <small>Результаты расчёта и ограничения</small>
                        </div>
                      </div>
                    </div>
                    <div className="filter-bar report-filters">
                      <label>
                        Расчётный сценарий
                        <select
                          aria-label="Расчёт для отчёта"
                          value={report?.simulation_id ?? ""}
                          onChange={(e) => setReportId(e.target.value)}
                        >
                          {history.map((s) => (
                            <option
                              key={s.simulation_id}
                              value={s.simulation_id}
                            >
                              {labels[s.request.incident.type]} ·{" "}
                              {s.request.incident.segment_id} ·{" "}
                              {time(s.created_at)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Тип события
                        <select
                          aria-label="Тип отчёта"
                          value={reportFilter}
                          onChange={(e) => setReportFilter(e.target.value)}
                        >
                          <option value="all">Все события</option>
                          <option value="pipe_break">Разрыв трубы</option>
                          <option value="valve_failure">Отказ задвижки</option>
                          <option value="pressure_drop">
                            Снижение давления
                          </option>
                        </select>
                      </label>
                      <button
                        className="primary"
                        disabled={!report}
                        onClick={() => report && download(report.simulation_id)}
                      >
                        <FileText size={15} />
                        Сгенерировать отчёт
                      </button>
                    </div>
                    <div className="section-heading">
                      <h2>Последние отчёты</h2>
                      <span className="status neutral">PDF</span>
                    </div>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Название</th>
                            <th>Тип</th>
                            <th>Создан</th>
                            <th>Статус</th>
                            <th>Действия</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filteredReports.slice(0, 20).map((s) => (
                            <tr key={s.simulation_id}>
                              <td>
                                <span className="report-name">
                                  <FileText size={15} />
                                  {s.request.incident.segment_id}
                                </span>
                              </td>
                              <td>
                                <span className="status info-status">
                                  {labels[s.request.incident.type]}
                                </span>
                              </td>
                              <td>{time(s.created_at, true)}</td>
                              <td>
                                <span className="status success">Готово</span>
                              </td>
                              <td>
                                <button
                                  className="icon-button"
                                  aria-label="Предпросмотр отчёта"
                                  onClick={() => setReportId(s.simulation_id)}
                                >
                                  <Eye size={15} />
                                </button>
                                <button
                                  className="icon-button"
                                  aria-label="Скачать PDF"
                                  onClick={() => download(s.simulation_id)}
                                >
                                  <Download size={15} />
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {!history.length && (
                        <div className="empty">
                          Выполните расчёт, чтобы создать первый отчёт
                        </div>
                      )}
                    </div>
                  </section>
                  <aside className="report-preview">
                    <h3>Предпросмотр отчёта</h3>
                    <ReportPreview
                      variantIndex={
                        report ? (variantChoices[report.simulation_id] ?? 0) : 0
                      }
                      id={report?.simulation_id ?? ""}
                      api={API}
                      token={token}
                    />
                    {report && (
                      <div className="report-summary">
                        <span className="demo-chip">DEMO</span>
                        <h3>{labels[report.request.incident.type]}</h3>
                        <p>{report.request.incident.segment_id}</p>
                        <dl className="details">
                          <dt>Без теплоснабжения</dt>
                          <dd>{report.affected_consumers.length} зданий</dd>
                          <dt>Операций</dt>
                          <dd>{report.valve_operations.length}</dd>
                          <dt>Версия сети</dt>
                          <dd>{report.network_version}</dd>
                        </dl>
                      </div>
                    )}
                  </aside>
                </div>
              )}
              {tab === "incidents" && (
                <section className="card">
                  <div className="section-heading">
                    <div>
                      <h2>Журнал инцидентов</h2>
                      <p className="muted">
                        Зарегистрированные события и связанные расчёты
                      </p>
                    </div>
                    <span className="status neutral">
                      {incidents.length} событий
                    </span>
                  </div>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Событие</th>
                          <th>Участок</th>
                          <th>Автор</th>
                          <th>Дата</th>
                          <th>Режим</th>
                          <th>Действия</th>
                        </tr>
                      </thead>
                      <tbody>
                        {incidents.map((i) => (
                          <tr key={i.id}>
                            <td>
                              <span className="incident-title">
                                <i className="red" />
                                {labels[i.type]}
                              </span>
                            </td>
                            <td className="mono">{i.segment_id}</td>
                            <td>{i.author}</td>
                            <td>{time(i.created_at, true)}</td>
                            <td>
                              <span className="demo-chip">
                                {i.demo ? "DEMO" : "Фактическое"}
                              </span>
                            </td>
                            <td>
                              <button
                                className="link"
                                onClick={() => {
                                  const s = history.find(
                                    (s) => s.simulation_id === i.simulation_id,
                                  );
                                  if (s) {
                                    openSimulation(s, i.variant_index ?? 0);
                                  }
                                }}
                              >
                                Открыть расчёт
                                <ArrowRight size={12} />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {!incidents.length && (
                      <div className="empty">
                        <TriangleAlert size={24} />
                        Инциденты ещё не зарегистрированы
                      </div>
                    )}
                  </div>
                </section>
              )}
              {(tab === "imports" || tab === "settings") && (
                <section className="card settings-card">
                  <div className="section-heading">
                    <h2>
                      {tab === "imports"
                        ? "Импорт и версии модели"
                        : "Параметры отображения"}
                    </h2>
                    <span className="status info-status">
                      {network.version}
                    </span>
                  </div>
                  {tab === "settings" && (
                    <div className="preferences">
                      <label>
                        <input
                          type="checkbox"
                          checked={showBasemap}
                          onChange={(e) => setShowBasemap(e.target.checked)}
                        />
                        Городская подложка
                      </label>
                      <label>
                        <input
                          type="checkbox"
                          checked={showReturn}
                          onChange={(e) => setShowReturn(e.target.checked)}
                        />
                        Показывать обратный контур
                      </label>
                      <label>
                        <input
                          type="checkbox"
                          checked={showSensors}
                          onChange={(e) => setShowSensors(e.target.checked)}
                        />
                        Показывать датчики
                      </label>
                    </div>
                  )}
                  <p className="muted">
                    Модель сети версионируется. Импорт новой версии сохраняет
                    предыдущие расчёты и их исходные данные.
                  </p>
                  {role === "admin" ? (
                    <>
                      <label className="upload">
                        <Upload size={29} />
                        <strong>Загрузите JSON или GeoJSON</strong>
                        <span>Каноническая модель с новой версией сети</span>
                        <input
                          type="file"
                          aria-label="Импорт сети"
                          accept=".json,.geojson"
                          disabled={busy}
                          onChange={(e) => importFile(e.target.files?.[0])}
                        />
                      </label>
                      <h2>Журнал аудита</h2>
                      <div className="table-scroll">
                        <table>
                          <thead>
                            <tr>
                              <th>Пользователь</th>
                              <th>Операция</th>
                              <th>Объект</th>
                              <th>Время</th>
                            </tr>
                          </thead>
                          <tbody>
                            {audit.slice(0, 30).map((a) => (
                              <tr key={a.id}>
                                <td>{a.user}</td>
                                <td>{a.action}</td>
                                <td className="mono">{a.target}</td>
                                <td>{time(a.timestamp, true)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </>
                  ) : (
                    <div className="info">
                      <Shield size={17} />
                      <p>
                        Импорт модели и журнал аудита доступны администратору.
                      </p>
                    </div>
                  )}
                  <div className="info">
                    <CircleHelp size={17} />
                    <p>
                      Гидравлика использует линейное эффективное сопротивление
                      Δp = R·Q и постоянную нагрузку при ΔT = 40 °C. Насосные
                      кривые и тепловые потери не моделируются.
                    </p>
                  </div>
                </section>
              )}
              {tab === "users" && (
                <section className="card">
                  <div className="section-heading">
                    <h2>Роли и доступ</h2>
                    <span className="status info-status">
                      Ваш доступ: {role}
                    </span>
                  </div>
                  <p className="muted">
                    Права проверяются backend для каждой операции.
                  </p>
                  <div className="role-grid">
                    {[
                      [
                        "admin",
                        "Администратор",
                        "Импорт сети, настройки, аудит и все операции диспетчера",
                        Shield,
                      ],
                      [
                        "dispatcher",
                        "Диспетчер",
                        "Расчёты, регистрация инцидентов, телеметрия и отчёты",
                        Users,
                      ],
                      [
                        "observer",
                        "Наблюдатель",
                        "Просмотр карты, показаний и сохранённых результатов",
                        Eye,
                      ],
                    ].map(([key, label, description, Icon]) => {
                      const I = Icon as typeof Shield;
                      return (
                        <div
                          className={
                            "role-card " + (role === key ? "selected" : "")
                          }
                          key={key as string}
                        >
                          <I size={25} />
                          <h3>{label as string}</h3>
                          <p>{description as string}</p>
                          {role === key && (
                            <span className="status success">Текущая роль</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}
            </>
          )}
          <footer>
            <span>
              ThermoTwin <b>·</b> Цифровой двойник тепловой сети
            </span>
            <span>Демонстрационная модель · G-TON 2026</span>
          </footer>
        </div>
        <nav className="mobile-bottom">
          {navItems
            .filter((n) =>
              [
                "map",
                "scenarios",
                "incidents",
                "telemetry",
                "reports",
              ].includes(n.key),
            )
            .map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                className={tab === key ? "active" : ""}
                onClick={() => navigate(key)}
              >
                <Icon size={18} />
                <span>{label}</span>
              </button>
            ))}
        </nav>
      </main>
    </div>
  );
}
