"""Tracked, idempotent SQL migration runner for finance-mcp.

Migrations are the numbered ``*.sql`` files in ``auth/migrations/``. This runner
records every applied file in a ``schema_migrations`` table, so each migration
runs exactly once and re-running is a no-op. A session-level advisory lock
serializes concurrent runs (parallel service starts / overlapping deploys).

Usage (run from the finance-mcp working dir, e.g. inside the container):

    python -m auth.migrate            # apply every pending migration (default)
    python -m auth.migrate status     # show applied vs pending, flag drift
    python -m auth.migrate backfill                # mark all files applied WITHOUT running them
    python -m auth.migrate backfill --through 038   # ...only up through version 038

``backfill`` is the one-time step for a pre-existing database that predates this
runner: it seeds ``schema_migrations`` from the current files so the first real
deploy doesn't try to re-run already-applied DDL. A brand-new/empty database
needs no backfill — ``apply`` runs everything from 001.

DB connection comes from ``DATABASE_URL``; if unset it is assembled from
``DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME``.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

import psycopg2

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

# Stable, arbitrary key for pg_advisory_lock so only one runner mutates the
# schema at a time. Any constant works as long as it never changes.
_ADVISORY_LOCK_KEY = 7_280_415_551

# Table created by 001; its presence on an empty tracking table means we're
# pointed at an existing DB that must be backfilled before applying.
_BASELINE_SENTINEL_TABLE = "users"

_VERSION_RE = re.compile(r"^(\d+)")


def _log(msg: str) -> None:
    print(f"[migrate] {msg}", flush=True)


def _connect():
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        return psycopg2.connect(dsn)
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
        user=os.environ["DB_USER"],
        password=os.environ.get("DB_PASSWORD", ""),
        dbname=os.environ.get("DB_NAME", "tally"),
    )


def _version_of(filename: str) -> int:
    m = _VERSION_RE.match(filename)
    if not m:
        raise ValueError(f"迁移文件名缺少前导版本号: {filename}")
    return int(m.group(1))


def _discover() -> list[tuple[int, str, Path]]:
    if not MIGRATIONS_DIR.is_dir():
        raise SystemExit(f"找不到迁移目录: {MIGRATIONS_DIR}")
    files = [p for p in MIGRATIONS_DIR.glob("*.sql") if p.is_file()]
    out = [(_version_of(p.name), p.name, p) for p in files]
    out.sort(key=lambda t: (t[0], t[1]))
    return out


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ensure_table(conn) -> None:
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS public.schema_migrations (
                    filename   text PRIMARY KEY,
                    version    integer NOT NULL,
                    checksum   text NOT NULL DEFAULT '',
                    applied_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )


def _applied(conn) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT filename, checksum FROM public.schema_migrations")
        return {row[0]: row[1] for row in cur.fetchall()}


def _baseline_present(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{_BASELINE_SENTINEL_TABLE}",))
        return bool(cur.fetchone()[0])


def _acquire_lock(conn) -> None:
    # Session-level lock; survives the per-migration commits below and is released
    # explicitly (or on connection close). Blocks until any other runner finishes.
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_lock(%s)", (_ADVISORY_LOCK_KEY,))
    conn.commit()


def _release_lock(conn) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(%s)", (_ADVISORY_LOCK_KEY,))
        conn.commit()
    except Exception:  # best-effort; connection close releases it anyway
        pass


def cmd_status(conn) -> int:
    _ensure_table(conn)
    applied = _applied(conn)
    drift = []
    pending = []
    for version, name, path in _discover():
        if name in applied:
            if applied[name] and applied[name] != _checksum(path):
                drift.append(name)
        else:
            pending.append(name)
    _log(f"已应用 {len(applied)} 条, 待应用 {len(pending)} 条")
    for name in pending:
        _log(f"  PENDING  {name}")
    for name in drift:
        _log(f"  DRIFT    {name}  (已应用但文件内容已变更, checksum 不匹配)")
    if not pending and not drift:
        _log("数据库已是最新, 无待应用迁移。")
    return 0


def cmd_backfill(conn, through: int | None) -> int:
    _ensure_table(conn)
    _acquire_lock(conn)
    try:
        applied = _applied(conn)
        marked = 0
        with conn:
            with conn.cursor() as cur:
                for version, name, path in _discover():
                    if through is not None and version > through:
                        continue
                    if name in applied:
                        continue
                    cur.execute(
                        """
                        INSERT INTO public.schema_migrations (filename, version, checksum)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (filename) DO NOTHING
                        """,
                        (name, version, _checksum(path)),
                    )
                    marked += 1
                    _log(f"  backfilled  {name}")
        _log(f"回填完成, 标记 {marked} 条为已应用 (未执行任何 SQL)。")
    finally:
        _release_lock(conn)
    return 0


def cmd_apply(conn) -> int:
    _ensure_table(conn)
    applied = _applied(conn)
    pending = [(v, n, p) for v, n, p in _discover() if n not in applied]

    if not pending:
        _log("数据库已是最新, 无待应用迁移。")
        return 0

    # Guard: empty tracking table on a populated DB means this is a pre-existing
    # database. Applying from 001 would re-run already-applied (non-idempotent)
    # DDL. Refuse and point at backfill, unless explicitly overridden.
    if not applied and _baseline_present(conn) and os.environ.get("MIGRATE_ALLOW_DIRTY_BASELINE") != "1":
        _log("检测到已存在的数据库 (有基线表) 但 schema_migrations 为空。")
        _log("请先运行 `python -m auth.migrate backfill` 标记历史迁移, 再 apply。")
        _log("(确实要从 001 重跑, 设 MIGRATE_ALLOW_DIRTY_BASELINE=1)")
        return 3

    _acquire_lock(conn)
    try:
        # Re-read after lock: another runner may have applied some while we waited.
        applied = _applied(conn)
        pending = [(v, n, p) for v, n, p in _discover() if n not in applied]
        _log(f"待应用 {len(pending)} 条迁移。")
        for version, name, path in pending:
            sql = path.read_text(encoding="utf-8")
            if not sql.strip():
                _log(f"  跳过空文件 {name} (仅记录)")
            try:
                with conn:
                    with conn.cursor() as cur:
                        if sql.strip():
                            cur.execute(sql)
                        cur.execute(
                            """
                            INSERT INTO public.schema_migrations (filename, version, checksum)
                            VALUES (%s, %s, %s)
                            """,
                            (name, version, _checksum(path)),
                        )
                _log(f"  applied  {name}")
            except Exception as exc:  # noqa: BLE001 - surface and abort the deploy
                _log(f"  FAILED   {name}: {exc}")
                _log("迁移失败, 已回滚该条, 中止。后续迁移与服务启动不会进行。")
                return 1
        _log(f"全部完成, 应用了 {len(pending)} 条迁移。")
    finally:
        _release_lock(conn)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="auth.migrate", description="finance-mcp DB 迁移运行器")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("apply", help="应用全部待执行迁移 (默认)")
    sub.add_parser("status", help="查看已应用/待应用, 检测漂移")
    bf = sub.add_parser("backfill", help="把现有文件标记为已应用而不执行 (existing DB 一次性)")
    bf.add_argument("--through", type=int, default=None, help="只回填到该版本号 (含)")

    args = parser.parse_args(argv)
    command = args.command or "apply"

    conn = _connect()
    try:
        if command == "status":
            return cmd_status(conn)
        if command == "backfill":
            return cmd_backfill(conn, args.through)
        return cmd_apply(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
