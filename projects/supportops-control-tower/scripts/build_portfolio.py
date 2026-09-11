"""Build portable portfolio pages from recorded evidence; no backend runs are simulated."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IN_PORTFOLIO = ROOT.parent.name == "projects" and (ROOT.parents[1] / "index.html").is_file()
EXPORT_ROOT = ROOT.parents[1] if IN_PORTFOLIO else ROOT / "portfolio-export"


def code_hash(root: Path) -> str:
    paths = sorted(list((root / "supportops").glob("*.py")) + [root / "scripts" / "supportops.py"])
    payload = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def chart(dates: list[dict]) -> str:
    values = [r["metrics"]["ccr_pct"] for r in dates]
    requirement = dates[-1]["metrics"]["ccr_requirement_pct"]
    low, high = min(*values, requirement) - 8, max(*values, requirement) + 8
    x = lambda i: 90 + i * 255
    y = lambda value: 60 + (high-value)/(high-low)*230
    parts = ['<svg class="zoomable-chart" tabindex="0" data-title="Three-date synthetic capacity coverage" viewBox="0 0 700 360" role="img" aria-label="Three recorded capacity-coverage ratios compared with the configured requirement"><text x="45" y="30" fill="#c2c9d6" font-size="15">Capacity coverage / percent</text>']
    for index in range(4):
        value = low+(high-low)*index/3
        parts.append(f'<path d="M55 {y(value):.2f}H660" stroke="#566789"/><text x="4" y="{y(value)+5:.2f}" fill="#c2c9d6" font-size="14">{value:.0f}</text>')
    parts.append(f'<path d="M55 {y(requirement):.2f}H660" stroke="#ff8993" stroke-width="2" stroke-dasharray="6 5"/><text x="455" y="{y(requirement)-10:.2f}" fill="#ff8993" font-size="14">{requirement:.0f}% requirement</text>')
    points = " L ".join(f"{x(i)} {y(v):.2f}" for i, v in enumerate(values))
    parts.append(f'<path d="M {points}" fill="none" stroke="#f2c46d" stroke-width="4"/>')
    for i, value in enumerate(values):
        color = "#ff8993" if value < requirement else "#f2c46d"
        parts.append(f'<circle cx="{x(i)}" cy="{y(value):.2f}" r="7" fill="{color}"/><text text-anchor="middle" x="{x(i)}" y="{y(value)-19:.2f}" fill="#faf8f2" font-size="24">{value:.1f}%</text><text text-anchor="middle" x="{x(i)}" y="335" fill="#c2c9d6" font-size="16">{html.escape(dates[i]["run_date"])}</text>')
    return "".join(parts)+"</svg>"


def package_source() -> Path:
    target = ROOT / "source.zip"
    allowed = {"supportops", "config", "data", "scripts", "tests", "docs", "results", "web", "presentation"}
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(ROOT.rglob("*")):
            relative = path.relative_to(ROOT)
            if not path.is_file() or "__pycache__" in relative.parts or path.suffix in {".pyc", ".zip", ".tmp"}:
                continue
            if len(relative.parts) > 1 and relative.parts[0] not in allowed:
                continue
            if len(relative.parts) == 1 and path.name not in {"README.md", "requirements.txt", "project.json", "index.html"}:
                continue
            info = zipfile.ZipInfo(relative.as_posix(), (2026, 9, 11, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            content = path.read_bytes()
            if relative.as_posix() == "index.html":
                content = content.decode("utf-8").replace('href="../../index.html" data-home', 'href="https://bjabour.github.io/professional-projects/" data-home').encode("utf-8")
            bundle.writestr(info, content)
    return target


def build(data_path: Path | None = None) -> list[Path]:
    source = data_path or ROOT / "results" / "dashboard-data.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    checks = ROOT / "results" / "control-checks.json"
    if not checks.exists():
        checks = source.parent / "control-checks.json"
    if not checks.exists():
        raise ValueError("Run scripts/check_controls.py before building the portfolio.")
    evidence = json.loads(checks.read_text(encoding="utf-8"))
    if evidence.get("status") != "PASS" or not evidence.get("checks") or any(c.get("status") != "PASS" for c in evidence["checks"]):
        raise ValueError("Control checks must all pass before portfolio evidence is presented.")
    engine_root = source.parent.parent
    actual_code_hash = code_hash(engine_root)
    if evidence.get("code_sha256") != actual_code_hash:
        raise ValueError("Control checks are stale relative to the engine source. Run them again.")
    test_hash = hashlib.sha256((engine_root / "tests" / "test_controls.py").read_bytes()).hexdigest()
    if evidence.get("test_source_sha256") != test_hash:
        raise ValueError("Control-check evidence is stale relative to its test source.")
    data["control_checks"] = evidence
    if len(data.get("dates", [])) != 3:
        raise ValueError("The portfolio requires all three verified demonstration dates.")
    for run in data["dates"]:
        if run["provenance"]["integrity"] != "VERIFIED" or run["execution_status"] != "COMPLETED":
            raise ValueError(f"Unverified or incomplete run: {run['run_date']}")
        if run["provenance"]["code_sha256"] != actual_code_hash:
            raise ValueError("The dashboard export and current engine source do not match. Run all dates again.")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
    page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    page = page.replace("/* EMBED_CSS */", (ROOT / "web" / "styles.css").read_text(encoding="utf-8"))
    page = page.replace("/* EMBED_DATA */", "window.SUPPORTOPS_DATA=" + payload + ";")
    page = page.replace("/* EMBED_JS */", (ROOT / "web" / "dashboard.js").read_text(encoding="utf-8"))
    if "/* EMBED_" in page:
        raise ValueError("An unresolved build token remains.")
    local_page = page.replace('href="../../../index.html" data-home', 'href="../../index.html" data-home').replace('href="../presentation/index.html" data-study', 'href="presentation/index.html" data-study').replace('href="../README.md" data-source', 'href="README.md" data-source')
    portable_page = page.replace('href="../../../index.html" data-home', 'href="index.html" data-home').replace('href="../presentation/index.html" data-study', 'href="supportops-control-tower-case-study.html" data-study').replace('href="../README.md" data-source', 'href="projects/supportops-control-tower/README.md" data-source')
    if not IN_PORTFOLIO:
        local_page = local_page.replace('href="../../index.html" data-home', 'href="https://bjabour.github.io/professional-projects/" data-home')
        portable_page = portable_page.replace('href="index.html" data-home', 'href="https://bjabour.github.io/professional-projects/" data-home').replace('href="projects/supportops-control-tower/README.md" data-source', 'href="../README.md" data-source')
    local_page = local_page.replace('href="../README.md#interpretation" data-scope', 'href="README.md#interpretation" data-scope')
    scope_path = "projects/supportops-control-tower/README.md#interpretation" if IN_PORTFOLIO else "../README.md#interpretation"
    portable_page = portable_page.replace('href="../README.md#interpretation" data-scope', 'href="' + scope_path + '" data-scope')
    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    targets = [ROOT / "index.html", EXPORT_ROOT / "supportops-control-tower.html"]
    targets[0].write_text(local_page, encoding="utf-8")
    targets[1].write_text(portable_page, encoding="utf-8")
    story = (ROOT / "web" / "story.html").read_text(encoding="utf-8")
    last = data["dates"][-1]
    count = len(data.get("control_checks", {}).get("checks", []))
    passed = sum(c.get("passed", c.get("status") in ("PASS", "PASSED")) for c in data.get("control_checks", {}).get("checks", []))
    replacements = {
        "__CCR__": f"{last['metrics']['ccr_pct']:.1f}",
        "__GAP__": f"{max(0, last['metrics']['required_handling_minutes'] * last['metrics']['ccr_requirement_pct'] / 100 - last['metrics']['available_agent_minutes']):.2f}",
        "__WARNINGS__": str(len(last["warnings"])),
        "__REQUIREMENT__": f"{last['metrics']['ccr_requirement_pct']:.0f}",
        "__CAPACITY_CHART__": chart(data["dates"]),
        "__CHECK_COUNT__": str(count),
        "__PASS_COUNT__": str(passed),
        "__CHECK_LIST__": "".join('<div class="check-row"><span>' + ("✓" if c.get("status") == "PASS" else "×") + '</span><p>' + html.escape(c.get("title", c.get("name", c.get("id", "")))) + "</p></div>" for c in data["control_checks"]["checks"][:8]),
    }
    for token, value in replacements.items():
        story = story.replace(token, value)
    if re.search(r"__[A-Z_]+__", story):
        raise ValueError("Unresolved case-study tokens.")
    target = ROOT / "presentation" / "index.html"
    target.write_text(story, encoding="utf-8")
    targets.append(target)
    standalone = EXPORT_ROOT / "supportops-control-tower-case-study.html"
    subprocess.run(["node", str(ROOT / "scripts" / "presentation" / "export_standalone.mjs"), "--input", str(target), "--output", str(standalone)], check=True)
    standalone.write_text(
        standalone.read_text(encoding="utf-8")
        .replace('href="../index.html" data-demo', 'href="supportops-control-tower.html" data-demo')
        .replace('href="../README.md" data-readme', 'href="' + ("projects/supportops-control-tower/README.md" if IN_PORTFOLIO else "../README.md") + '" data-readme'),
        encoding="utf-8",
    )
    targets.extend([standalone, package_source()])
    for path in targets:
        print(path.relative_to(ROOT.parents[1] if IN_PORTFOLIO else ROOT))
    return targets


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, help="Alternative recorded dashboard-data.json.")
    build(parser.parse_args().data)
