"""`kavra` command line: serve, doctor, ingest, demo-seed."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def _utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run("kavra.api:app", host=args.host, port=args.port, log_level="info")


def cmd_doctor(_: argparse.Namespace) -> int:
    """Ping every configured provider with a tiny structured request. Never prints keys."""
    from pydantic import BaseModel

    from kavra.config import get_settings
    from kavra.llm.base import strict_schema
    from kavra.llm.router import build_provider

    class Pong(BaseModel):
        ok: bool
        word: str

    s = get_settings()
    print(
        f"local_mode={s.local_mode}  gemini_key={'set' if s.gemini_api_key else 'MISSING'}  groq_key={'set' if s.groq_api_key else 'MISSING'}"
    )
    specs = {
        "generator": [s.generator, *s.generator_fallbacks.split(",")],
        "auditor": [s.auditor, *s.auditor_fallbacks.split(",")],
    }
    failures = 0
    for role, lst in specs.items():
        for spec in [x.strip() for x in lst if x.strip()]:
            p = build_provider(spec, s)
            if p is None:
                print(f"  ✗ {role:9} {spec:40} not configured")
                failures += 1
                continue
            t0 = time.perf_counter()
            try:
                r = p.complete_json(
                    "Reply with JSON.",
                    'Return {"ok": true, "word": "merhaba"}',
                    strict_schema(Pong),
                    0.0,
                )
                Pong.model_validate(r.data)
                print(f"  ✓ {role:9} {spec:40} {int((time.perf_counter() - t0) * 1000)} ms")
            except Exception as e:
                failures += 1
                print(f"  ✗ {role:9} {spec:40} {str(e)[:140]}")
    return 1 if failures else 0


def cmd_ingest(args: argparse.Namespace) -> None:
    from kavra.db import get_db
    from kavra.ingest import kind_for
    from kavra.service import Service

    svc = Service(get_db())
    if args.path.startswith("http"):
        res = svc.add_youtube(args.path)
    else:
        p = Path(args.path)
        kind = kind_for(p)
        if not kind:
            raise SystemExit("unsupported file type")
        res = svc.add_file(p.name, p, kind)
    print(json.dumps(res))
    while svc.jobs.run_next():
        job = svc.db.one("SELECT status, stage, message FROM jobs ORDER BY id DESC LIMIT 1")
        print(json.dumps(job, ensure_ascii=False))


def cmd_demo(_: argparse.Namespace) -> None:
    """Fill an empty database with demo material (no API key needed)."""
    from kavra.db import get_db
    from kavra.demo import seed

    db = get_db()
    if db.scalar("SELECT COUNT(*) FROM documents"):
        raise SystemExit("database is not empty; set DATA_DIR to a new folder for the demo")
    print(json.dumps(seed(db), ensure_ascii=False, indent=1))


def main() -> None:
    _utf8()
    ap = argparse.ArgumentParser(prog="kavra")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("serve")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8000)
    sp.set_defaults(fn=cmd_serve)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    sub.add_parser("demo").set_defaults(fn=cmd_demo)
    ip = sub.add_parser("ingest")
    ip.add_argument("path")
    ip.set_defaults(fn=cmd_ingest)
    args = ap.parse_args()
    rc = args.fn(args)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
