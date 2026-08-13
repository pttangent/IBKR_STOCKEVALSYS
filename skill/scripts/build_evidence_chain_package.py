#!/usr/bin/env python3
"""Finalize, validate, render and package a portable evidence-chain report."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_cmd(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--structured-report", default="structured_report.json")
    ap.add_argument("--zip")
    ap.add_argument("--export-dir", help="Directory for exported ZIP packages; defaults to outputs/export/<as-of>")
    ap.add_argument("--modules")
    args = ap.parse_args()

    run = Path(args.run_dir).resolve()
    structured = (run / args.structured_report if not Path(args.structured_report).is_absolute() else Path(args.structured_report)).resolve()
    script_dir = Path(__file__).resolve().parent

    # Mechanical/PIT finalization first, then research-semantic finalization.
    # Neither pass invents facts; both repair or block contradictions using the
    # frozen deterministic/source artifacts in the run directory.
    run_cmd([
        sys.executable, str(script_dir / "finalize_structured_report.py"),
        "--report", str(structured), "--run-dir", str(run),
    ])
    run_cmd([
        sys.executable, str(script_dir / "finalize_research_semantics.py"),
        "--report", str(structured), "--run-dir", str(run),
    ])
    data = json.loads(structured.read_text(encoding="utf-8"))
    run_id = data["run_id"]
    markdown = run / f"{run_id}_complete_report.md"
    html = run / f"{run_id}_complete_report.html"

    run_cmd([sys.executable, str(script_dir / "validate_structured_report.py"), "--report", str(structured)])

    command = [sys.executable, str(script_dir / "render_markdown_report.py"), "--structured-report", str(structured), "--output", str(markdown)]
    if args.modules:
        command += ["--modules", args.modules]
    run_cmd(command)

    command = [sys.executable, str(script_dir / "render_html_report.py"), "--structured-report", str(structured), "--run-dir", str(run), "--output", str(html)]
    if args.modules:
        command += ["--modules", args.modules]
    run_cmd(command)

    export_dir = (Path(args.export_dir).resolve() if args.export_dir else run.parent / "export" / str(data.get("as_of") or run_id.rsplit("_", 1)[-1]))
    export_dir.mkdir(parents=True, exist_ok=True)
    zip_path = Path(args.zip).resolve() if args.zip else export_dir / f"{run_id}_evidence_chain_report_package.zip"
    excluded = {zip_path.resolve()}
    files: list[Path] = []
    canonical_reader_names = {markdown.name, html.name}
    for path in sorted(run.rglob("*")):
        if not path.is_file() or path.resolve() in excluded:
            continue
        if path.name in {"evidence_chain_manifest.json", "SHA256SUMS.txt"}:
            continue
        if path.suffix.lower() in {".tmp", ".lock", ".zip"}:
            continue
        # Do not carry stale duplicate reader outputs from older naming schemes.
        if path.suffix.lower() in {".md", ".html"} and "complete_report" in path.name and path.name not in canonical_reader_names:
            continue
        files.append(path)

    manifest = {
        "schema_version": "2.1",
        "package_type": "evidence_chain_report_package",
        "run_id": run_id,
        "symbol": data.get("symbol"),
        "as_of": data.get("as_of"),
        "evidence_cutoff": data.get("evidence_cutoff"),
        "price_timestamp": data.get("price_timestamp"),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "canonical_report": structured.relative_to(run).as_posix() if structured.is_relative_to(run) else structured.name,
        "reader_outputs": [markdown.name, html.name],
        "finalization_status": data.get("package_hints", {}).get("finalization_status"),
        "semantic_finalization_status": data.get("package_hints", {}).get("semantic_finalization_status"),
        "artifact_count": len(files),
        "artifacts": [],
    }
    for path in files:
        rel = path.relative_to(run).as_posix()
        manifest["artifacts"].append({"path": rel, "size_bytes": path.stat().st_size, "sha256": sha256(path)})

    manifest_path = run / "evidence_chain_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sums_path = run / "SHA256SUMS.txt"
    checksum_files = files + [manifest_path]
    sums_path.write_text("".join(f"{sha256(path)}  {path.relative_to(run).as_posix()}\n" for path in checksum_files), encoding="utf-8")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files + [manifest_path, sums_path]:
            archive.write(path, path.relative_to(run).as_posix())

    print(json.dumps({
        "zip": str(zip_path),
        "artifact_count": len(files) + 2,
        "structured_report": str(structured),
        "markdown": str(markdown),
        "html": str(html),
        "finalization_status": data.get("package_hints", {}).get("finalization_status"),
        "semantic_finalization_status": data.get("package_hints", {}).get("semantic_finalization_status"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
