"""Reproducible KPI + independent correctness audit on the district model.

PYTHONPATH=backend backend/.venv/bin/python scripts/benchmark_kostanay.py
Starts its own API on an ephemeral loopback port and temporary SQLite database.
Legacy demo-2 reports and the working database are never overwritten.
"""

import os

for variable in (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "MKL_NUM_THREADS",
):
    os.environ[variable] = "1"

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import socket
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

import httpx
import numpy as np
from app.engine import simulate
from app.hydraulics import solve_hydraulics
from app.kostanay import make_kostanay
from app.kpi_validation import check_result, check_hydraulics
from app.models import SimulationInput

ROOT = Path(__file__).resolve().parents[1]
CORE_KEYS = {
    "status",
    "admissible",
    "affected_consumers",
    "affected_segments",
    "newly_affected_consumers",
    "disconnected_buildings",
    "estimated_population",
    "valve_operations",
    "variants",
    "hydraulic_validation",
    "warnings",
    "initial_valve_states",
}


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def canonical(result):
    return {k: result[k] for k in CORE_KEYS if k in result}


def distribution(samples):
    return {
        "count": len(samples),
        "p50_ms": round(float(np.percentile(samples, 50)), 2),
        "p95_ms": round(float(np.percentile(samples, 95)), 2),
        "max_ms": round(max(samples), 2),
        "samples_ms": [round(v, 6) for v in samples],
    }


def cases(network):
    trunk = network.pipes[0].id
    conn = next(
        p.id
        for p in network.pipes
        if p.contour == "supply" and p.route_kind == "building_connection"
    )
    reserve = next(p.id for p in network.pipes if p.contour == "supply" and p.backup)
    source = network.sources[0].supply_node
    source_pipe = next(
        p.id
        for p in network.pipes
        if p.contour == "supply" and not p.backup and source in {p.start, p.end}
    )
    inputs = [
        ("supply_break_no_reserve", "pipe_break", trunk, False, 0.6),
        ("supply_break_with_reserve", "pipe_break", trunk, True, 0.6),
        ("return_break_no_reserve", "pipe_break", "R" + trunk[1:], False, 0.6),
        ("return_break_with_reserve", "pipe_break", "R" + trunk[1:], True, 0.6),
        ("building_supply_break", "pipe_break", conn, True, 0.6),
        ("building_return_break", "pipe_break", "R" + conn[1:], True, 0.6),
        ("valve_failure_local", "valve_failure", conn, True, 0.6),
        ("valve_failure_source", "valve_failure", source_pipe, True, 0.6),
        ("pressure_drop_0_9", "pressure_drop", trunk, True, 0.9),
        ("pressure_drop_0_6", "pressure_drop", trunk, True, 0.6),
        ("closed_reserve_break", "pipe_break", reserve, True, 0.6),
    ]
    return [
        (
            name,
            SimulationInput(
                network_version=network.version,
                incident={
                    "type": event,
                    "segment_id": segment,
                    "pressure_factor": factor,
                },
                constraints={"allow_backup_routes": backup},
            ),
        )
        for name, event, segment, backup, factor in inputs
    ]


def correctness(network, selected):
    before = network.model_dump(mode="json")
    baseline = check_hydraulics(
        network,
        {v.id: v.state for v in network.valves},
        solve_hydraulics(network, {v.id: v.state for v in network.valves}),
    )
    requests = [
        SimulationInput(
            network_version=network.version,
            incident={"type": event, "segment_id": p.id},
            constraints={"allow_backup_routes": backup},
        )
        for p in network.pipes
        for event, backup in [
            ("pipe_break", False),
            ("pipe_break", True),
            ("valve_failure", True),
        ]
    ]
    requests.extend(req for name, req in selected if name.startswith("pressure_drop"))
    summary = {
        "passed": True,
        "scenarios_checked": 0,
        "variants_checked": 0,
        "infeasible_proved": 0,
        "max_pressure_error_bar": 0.0,
        "max_flow_magnitude_error_m3h": 0.0,
        "max_nodal_residual_m3h": 0.0,
        "event_counts": dict(Counter(r.incident.type for r in requests)),
        "all_672_segments_covered": True,
        "baseline": baseline,
        "numerical_tolerance": 0.000051,
        "nodal_residual_tolerance": 1e-7,
    }
    coverage = []
    for i, req in enumerate(requests, 1):
        result = simulate(network, req)
        checked = check_result(network, req, result)
        summary["scenarios_checked"] += 1
        summary["variants_checked"] += checked["variants_checked"]
        summary["infeasible_proved"] += int(checked.get("infeasible_proved", False))
        for k in (
            "max_pressure_error_bar",
            "max_flow_magnitude_error_m3h",
            "max_nodal_residual_m3h",
        ):
            summary[k] = max(summary[k], checked.get(k, 0))
        coverage.append(
            {
                "request": req.model_dump(),
                "result_sha256": digest(canonical(result)),
                "status": result["status"],
                "variant_disconnections": [
                    v["disconnected_buildings"] for v in result["variants"]
                ],
            }
        )
        if i % 100 == 0:
            print(f"Correctness: {i}/{len(requests)} scenarios", flush=True)
    assert network.model_dump(mode="json") == before, "Canonical model was mutated"
    summary["model_unchanged"] = True
    summary["coverage"] = coverage
    return summary


def kernel_benchmark(network, selected, runs):
    measured, expected = {}, {}
    for name, request in selected:
        first = simulate(network, request)
        check_result(network, request, first)
        expected[name] = canonical(first)
        for _ in range(3):
            assert canonical(simulate(network, request)) == expected[name]
        samples = []
        for _ in range(runs):
            started = time.perf_counter()
            result = simulate(network, request)
            samples.append((time.perf_counter() - started) * 1000)
            assert canonical(result) == expected[name], "Repeated result changed"
        measured[name] = {
            "request": request.model_dump(),
            "timing": distribution(samples),
            "result_sha256": digest(expected[name]),
            "result": {
                "status": first["status"],
                "variants": [
                    {
                        k: v[k]
                        for k in (
                            "name",
                            "admissible",
                            "disconnected_buildings",
                            "affected_consumers",
                            "valve_operations",
                        )
                    }
                    | {
                        "hydraulic_status": v["hydraulic_validation"]["status"],
                        "minimum_differential_bar": v["hydraulic_validation"].get(
                            "minimum_differential_bar"
                        ),
                    }
                    for v in first["variants"]
                ],
            },
        }
        print(
            f"Kernel: {name}, p95={measured[name]['timing']['p95_ms']} ms", flush=True
        )
    return measured, expected


async def http_benchmark(
    network, selected, expected, runs, batches, clients, directory
):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(
        os.environ,
        PYTHONPATH=str(ROOT / "backend"),
        DATABASE_URL="sqlite:///" + str(Path(directory) / "benchmark.db"),
    )
    log = open(Path(directory) / "api.log", "w+")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=log,
    )
    try:
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}",
            timeout=30,
            limits=httpx.Limits(
                max_connections=clients, max_keepalive_connections=clients
            ),
        ) as client:
            for _ in range(100):
                if process.poll() is not None:
                    log.seek(0)
                    raise RuntimeError("Isolated API failed to start: " + log.read())
                try:
                    r = await client.get("/health")
                    if r.status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                await asyncio.sleep(0.1)
            else:
                raise RuntimeError("Isolated API health timeout")
            r = await client.post(
                "/api/v1/auth/login",
                json={"username": "dispatcher", "password": "demo-dispatcher"},
            )
            r.raise_for_status()
            client.headers["Authorization"] = "Bearer " + r.json()["token"]
            r = await client.get("/api/v1/network")
            r.raise_for_status()
            assert digest(r.json()) == digest(network.model_dump(mode="json")), (
                "API loaded a different model"
            )
            measured = {}
            for name, request in selected:

                async def run():
                    started = time.perf_counter()
                    response = await client.post(
                        "/api/v1/simulations", json=request.model_dump()
                    )
                    response.raise_for_status()
                    payload = response.json()
                    elapsed = (time.perf_counter() - started) * 1000
                    return elapsed, payload

                def validate(payload):
                    assert payload["network_version"] == network.version
                    assert canonical(payload) == expected[name], (
                        f"API/kernel mismatch: {name}"
                    )

                async def checked_run():
                    elapsed, payload = await run()
                    validate(payload)
                    return elapsed

                warmup = [await checked_run() for _ in range(3)]
                sequential = [await checked_run() for _ in range(runs)]
                concurrent, batch_times = [], []
                for _ in range(batches):
                    started = time.perf_counter()
                    replies = await asyncio.gather(*(run() for _ in range(clients)))
                    batch_times.append((time.perf_counter() - started) * 1000)
                    concurrent.extend(elapsed for elapsed, _ in replies)
                    # No reference comparison may delay another timed client.
                    for _, payload in replies:
                        validate(payload)
                measured[name] = {
                    "warmup_ms": warmup,
                    "sequential": distribution(sequential),
                    "concurrent": distribution(concurrent),
                    "concurrent_batch_ms": batch_times,
                    "all_http_results_match_kernel": True,
                }
                print(
                    f"HTTP: {name}, p95={measured[name]['sequential']['p95_ms']} ms, {clients} clients p95={measured[name]['concurrent']['p95_ms']} ms",
                    flush=True,
                )
            return measured
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        log.close()


def validation_suite():
    with tempfile.TemporaryDirectory(prefix="thermotwin-tests-") as directory:
        xml_path = Path(directory) / "pytest.xml"
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-q", f"--junitxml={xml_path}"],
            cwd=ROOT / "backend",
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(
                "Backend tests failed:\n" + result.stdout + result.stderr
            )
        suites = ET.parse(xml_path).getroot().iter("testsuite")
        counts = Counter()
        for suite in suites:
            for k in ("tests", "failures", "errors", "skipped"):
                counts[k] += int(suite.attrib.get(k, 0))
        print(
            f"Backend suite: {counts['tests']} tests, {counts['failures']} failures",
            flush=True,
        )
        return {
            "command": "cd backend && .venv/bin/python -m pytest tests -q",
            "exit_code": result.returncode,
            **counts,
            "run_before_measurements": True,
        }


def write_markdown(report, path):
    kpi, model, audit = report["kpi"], report["model"], report["correctness"]
    lines = [
        "# KPI и корректность · Костанай, «Юбилейный»",
        "",
        f"Модель **`{model['version']}`**: {model['nodes']} узлов, {model['pipes']} трубы, {model['consumers']} здания, {model['valves']} задвижки и {model['sensors']} датчиков.",
        "",
        f"Измерения: {report['started_at']} — {report['finished_at']} (UTC). Проверочный код: `{report['git_commit']}`. SHA-256 файла модели: `{model['file_sha256']}`.",
        "",
        f"**KPI p95 ≤ {kpi['limit_ms']} мс выполнен** для всех 11 сценариев и обоих HTTP-режимов. Худший p95 ядра: **{kpi['worst_case_kernel_p95_ms']} мс**; HTTP последовательно: **{kpi['worst_case_http_p95_ms']} мс**; при 10 одновременно отправленных запросах: **{kpi['worst_case_concurrent_http_p95_ms']} мс**.",
        "",
        "Это отдельный локальный отчёт новой карты. Значения 62,62 мс, 330,21 мс и 942,55 мс относятся к старой demo-2 и не переносятся на эту модель. Методики и размер сетей различаются; прямое сравнение скорости по этим числам не является серверным испытанием.",
        "",
        "## Стенд и методика",
        "",
        f"- {report['environment']['platform']}; {report['environment']['cpu']}; {report['environment']['ram_bytes'] / 1024**3:.0f} ГиБ RAM; Python {report['environment']['python']}.",
        "- Отдельный FastAPI/uvicorn-процесс на временном loopback-порту; два worker-процесса расчётов, временная SQLite. Рабочая база и история сценариев не изменялись.",
        "- Генератор телеметрии включён, период 30 с. Численные библиотеки ограничены одним потоком. На том же компьютере работают другие приложения, включая локальные ThermoTwin API/frontend; аппаратная изоляция отсутствует. Во время итоговых замеров сборка и pytest параллельно не запускались.",
        f"- Для каждого из 11 сценариев: {report['method']['warmup_runs_per_case']} прогрева, {report['method']['sequential_runs_per_case']} последовательных измерений ядра и HTTP, {report['method']['concurrent_batches_per_case']} пачек по {report['method']['clients_per_batch']} одновременно отправленных HTTP-запросов. Внутри пачки — один сценарий; смешанная нагрузка не измерялась.",
        "- p95 вычисляется отдельно для каждого сценария и режима по numpy.percentile с линейной интерполяцией. Прогрев исключён. Сводное число — максимум p95 по сценариям, а не процентиль смешанного набора.",
        "- Время ядра включает simulate на разобранной модели. HTTP включает валидацию, очередь/расчёт в worker, сохранение снимка в SQLite, передачу и декодирование JSON. Открытие карты, загрузка тайлов, WebSocket и PDF в эти задержки не входят.",
        "- Сравнение результатов выполнено вне измеряемых интервалов; в конкурентной пачке — после завершения всех ответов. Ошибки HTTP не исключались бы из статистики: они прерывают успешный отчёт.",
        "",
        "## Задержки",
        "",
        "Все значения ниже в миллисекундах; max — максимум среди конкурентных HTTP-ответов.",
        "",
        "| Сценарий | Ядро p95 | HTTP p95 | HTTP, 10 клиентов p95 | HTTP, 10 клиентов max |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, item in report["kernel"].items():
        http = report["http"][name]
        lines.append(
            f"| `{name}` | {item['timing']['p95_ms']:.2f} | {http['sequential']['p95_ms']:.2f} | {http['concurrent']['p95_ms']:.2f} | {http['concurrent']['max_ms']:.2f} |"
        )
    lines += [
        "",
        "## Корректность",
        "",
        f"Проверено **{audit['scenarios_checked']} сценариев** и **{audit['variants_checked']} вариантов**: 1 344 разрыва (каждый из 672 участков с резервом и без), 672 отказа участковых задвижек и два снижения давления. Для {audit['infeasible_proved']} сценариев невозможность изоляции независимо подтверждена. Исходная модель не изменилась.",
        "",
        "Эталон в backend/app/kpi_validation.py не использует engine, hydraulics и графовые функции NetworkX: достижимость проверяется обычным BFS, гидравлика решается плотной системой NumPy по узловым балансам. Проверены множества отключённых зданий и участков, числа отключений, новые отключения, разрешённость операций, изоляция повреждения, отсутствие переключений отказавшей задвижки, статус гидравлики и согласованность выбранного варианта.",
        "",
        f"Давления и **модули расходов** совпадают с независимым решением с допуском {audit['numerical_tolerance']} (округление production-ответа до четырёх знаков). Максимальная ошибка давления: {audit['max_pressure_error_bar']:.9g} бар; расхода: {audit['max_flow_magnitude_error_m3h']:.9g} м³/ч. Максимальная невязка эталонных узловых уравнений: {audit['max_nodal_residual_m3h']:.9g} м³/ч при пороге 1e-7. Знак production-расхода зависит от ориентации ребра недиректированного графа; его соответствие pipe.start → pipe.end этот отчёт не подтверждает.",
        "",
        f"Дополнительно прошли {report['tests']['tests']} backend-теста. Негативные тесты проверяют, что эталон отклоняет подменённое число отключений и неверное давление. Для каждого из 11 измеряемых сценариев все повторные результаты воспроизводимы; все {len(report['http']) * (report['method']['warmup_runs_per_case'] + report['method']['sequential_runs_per_case'] + report['method']['concurrent_batches_per_case'] * report['method']['clients_per_batch'])} HTTP-ответов совпали с результатом ядра после исключения времени исполнения и служебных метаданных.",
        "",
        "| Контрольный сценарий | Вариант | Отключено зданий | Статус гидравлики | Операций |",
        "|---|---|---:|---|---:|",
    ]
    for name, item in report["kernel"].items():
        variants = item["result"]["variants"]
        if not variants:
            lines.append(
                f"| `{name}` | Изоляция невозможна (`infeasible`) | — | — | 0 |"
            )
        for variant in variants:
            lines.append(
                f"| `{name}` | {variant['name']} | {variant['disconnected_buildings']} | `{variant['hydraulic_status']}` | {len(variant['valve_operations'])} |"
            )
    lines += [
        "",
        "## Границы подтверждения",
        "",
        "Подтверждены алгоритмическая корректность и скорость заявленной стационарной модели Δp=R·Q при ΔT=40°C на зафиксированном снимке. Географическое совпадение с дорогами OSM проверяется backend-тестами. Фактические нагрузки, расположение источника/арматуры, инженерная точность реальной сети, глобальная оптимальность выбора резервов и промышленная нагрузка этим отчётом не подтверждаются.",
        "",
        "Для pressure_drop_0_6 топологически отключённых зданий нет, но гидравлика outside_applicability. Для полной изоляции района без резерва статус insufficient_data означает отсутствие обслуживаемых потребителей для проверки перепада; такие варианты не отмечены допустимыми.",
        "",
        "## Воспроизведение и исходные данные",
        "",
        "```sh",
        "PYTHONPATH=backend backend/.venv/bin/python scripts/benchmark_kostanay.py",
        "```",
        "",
        f"[Машиночитаемый отчёт]({path.with_suffix('.json').name}) содержит каждый замер, входы сценариев, контрольные списки зданий/операций, покрытие всех 2 018 сценариев с хешами результатов, версии библиотек и SHA-256 исходников. Предыдущие docs/kpi-report.json и docs/kpi-http-report.json не изменены.",
    ]
    path.write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=50)
    parser.add_argument("--batches", type=int, default=5)
    parser.add_argument("--clients", type=int, default=10)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/kpi-kostanay.json")
    args = parser.parse_args()
    if sys.flags.optimize or min(args.runs, args.batches, args.clients) < 1:
        raise ValueError(
            "Positive sample counts and enabled Python assertions are required"
        )
    started = datetime.now(timezone.utc).isoformat()
    tests = validation_suite()
    network = make_kostanay()
    assert network.version == "kostanay-yubileyny-1" and len(network.pipes) == 672
    selected = cases(network)
    print("Starting exhaustive independent correctness audit", flush=True)
    audit = correctness(network, selected)
    kernel, expected = kernel_benchmark(network, selected, args.runs)
    with tempfile.TemporaryDirectory(prefix="thermotwin-kpi-") as directory:
        http = asyncio.run(
            http_benchmark(
                network,
                selected,
                expected,
                args.runs,
                args.batches,
                args.clients,
                directory,
            )
        )
    worst_kernel = max(v["timing"]["p95_ms"] for v in kernel.values())
    worst_http = max(v["sequential"]["p95_ms"] for v in http.values())
    worst_concurrent = max(v["concurrent"]["p95_ms"] for v in http.values())
    source_paths = [
        ROOT / "backend/app" / name
        for name in (
            "engine.py",
            "hydraulics.py",
            "models.py",
            "main.py",
            "store.py",
            "kpi_validation.py",
        )
    ]
    report = {
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in source_paths
        },
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "model": {
            "version": network.version,
            "nodes": len(network.nodes),
            "pipes": len(network.pipes),
            "consumers": len(network.consumers),
            "valves": len(network.valves),
            "sensors": len(network.sensors),
            "canonical_sha256": digest(network.model_dump(mode="json")),
            "file_sha256": hashlib.sha256(
                (ROOT / "backend/app/data/kostanay-yubileyny-network.json").read_bytes()
            ).hexdigest(),
        },
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu": subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
            ).strip()
            if sys.platform == "darwin"
            else platform.processor(),
            "ram_bytes": int(
                subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
            )
            if sys.platform == "darwin"
            else None,
            "packages": {
                name: importlib.metadata.version(name)
                for name in (
                    "numpy",
                    "scipy",
                    "networkx",
                    "fastapi",
                    "uvicorn",
                    "sqlalchemy",
                    "httpx",
                )
            },
            "numeric_threads": 1,
            "api_workers": 1,
            "calculation_process_workers": 2,
            "database": "temporary SQLite, own database",
            "transport": "loopback TCP HTTP, dedicated API, no frontend traffic",
            "telemetry": "normal generator every 30 seconds, enabled",
            "hardware_isolated": False,
        },
        "method": {
            "warmup_runs_per_case": 3,
            "sequential_runs_per_case": args.runs,
            "concurrent_batches_per_case": args.batches,
            "clients_per_batch": args.clients,
            "percentile": "numpy.percentile, linear interpolation",
            "http_includes": "request validation, process queue/calculation, snapshot persistence, response transfer and JSON decode",
            "kernel_includes": "simulate on already parsed immutable model and request",
            "correctness_checks_outside_timed_interval": True,
            "legacy_reports_unchanged": True,
        },
        "tests": tests,
        "correctness": audit,
        "kernel": kernel,
        "http": http,
        "kpi": {
            "limit_ms": 10000,
            "worst_case_kernel_p95_ms": worst_kernel,
            "worst_case_http_p95_ms": worst_http,
            "worst_case_concurrent_http_p95_ms": worst_concurrent,
            "passed": max(worst_kernel, worst_http, worst_concurrent) <= 10000
            and audit["passed"],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    write_markdown(report, args.output.with_suffix(".md"))
    print(
        json.dumps(
            {
                "report": str(args.output),
                "correctness_scenarios": audit["scenarios_checked"],
                "kpi": report["kpi"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    if not report["kpi"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
