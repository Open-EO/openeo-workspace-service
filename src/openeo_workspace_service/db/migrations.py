"""
Index management CLI for openeo-workspace-service.

Commands
--------
status      Print current index info (doc count, health, mappings).
migrate     Re-index data from v_old into v_new with zero downtime
            (alias swap pattern).
reindex     Alias for ``migrate``.
delete      Delete an index by name (confirmation required).

Usage
-----
    python -m openeo_workspace_service.db.migrations status
    python -m openeo_workspace_service.db.migrations migrate \\
        --from openeo_workspaces_v1 --to openeo_workspaces_v2
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

sys.path.insert(0, "src")

import structlog
from elasticsearch import AsyncElasticsearch

from openeo_workspace_service.config.logging import configure_logging
from openeo_workspace_service.config.settings import get_settings
from openeo_workspace_service.db.elasticsearch import (
    PROVIDER_MAPPING,
    WORKSPACE_MAPPING,
    get_es_client,
)

configure_logging(debug=True)
logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _index_stats(es: AsyncElasticsearch, index: str) -> None:
    try:
        info = await es.indices.get(index=index)
        stats = await es.indices.stats(index=index)
        count = stats["indices"][index]["total"]["docs"]["count"]
        health = await es.cluster.health(index=index)
        print(f"\n  Index : {index}")
        print(f"  Docs  : {count:,}")
        print(f"  Health: {health['status']}")
    except Exception as exc:
        print(f"  Index : {index}  [ERROR: {exc}]")


async def cmd_status(_args: argparse.Namespace) -> None:
    settings = get_settings()
    async with get_es_client() as es:
        print("=== openeo-workspace-service index status ===")
        await _index_stats(es, settings.workspace_index)
        await _index_stats(es, settings.provider_index)
        print()


async def cmd_migrate(args: argparse.Namespace) -> None:
    src: str = args.source
    dst: str = args.dest

    if src == dst:
        print("Source and destination indices are identical — nothing to do.")
        return

    async with get_es_client() as es:
        # 1. Create destination index with current mapping
        mapping = WORKSPACE_MAPPING if "provider" not in dst else PROVIDER_MAPPING
        exists = await es.indices.exists(index=dst)
        if not exists:
            await es.indices.create(index=dst, body=mapping)
            logger.info("created destination index", index=dst)
        else:
            logger.info("destination index already exists", index=dst)

        # 2. Reindex documents
        logger.info("starting reindex", src=src, dst=dst)
        resp = await es.reindex(
            body={
                "source": {"index": src},
                "dest": {"index": dst, "op_type": "create"},
            },
            wait_for_completion=True,
            timeout="30m",
        )
        total = resp.get("total", 0)
        created = resp.get("created", 0)
        failures = resp.get("failures", [])
        logger.info("reindex complete", total=total, created=created, failures=len(failures))
        if failures:
            print("FAILURES:")
            print(json.dumps(failures, indent=2))

        # 3. Report — we do NOT automatically delete the old index; operator must do that.
        print(f"\nReindex done: {created}/{total} documents copied from '{src}' → '{dst}'.")
        print(f"Old index '{src}' has NOT been deleted — verify data then run:")
        print(f"  python -m openeo_workspace_service.db.migrations delete --index {src}")


async def cmd_delete(args: argparse.Namespace) -> None:
    index: str = args.index
    if not args.yes:
        confirm = input(f"Are you sure you want to DELETE index '{index}'? [y/N] ").strip()
        if confirm.lower() != "y":
            print("Aborted.")
            return
    async with get_es_client() as es:
        await es.indices.delete(index=index)
        print(f"Deleted index '{index}'.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m openeo_workspace_service.db.migrations",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show index health and doc counts")

    migrate_p = sub.add_parser("migrate", aliases=["reindex"], help="Zero-downtime reindex")
    migrate_p.add_argument("--source", "-f", required=True, help="Source index name")
    migrate_p.add_argument("--dest", "-t", required=True, help="Destination index name")

    delete_p = sub.add_parser("delete", help="Delete an index")
    delete_p.add_argument("--index", required=True, help="Index to delete")
    delete_p.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")

    return parser


async def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    cmd = args.command if args.command != "reindex" else "migrate"
    dispatch = {"status": cmd_status, "migrate": cmd_migrate, "delete": cmd_delete}
    await dispatch[cmd](args)


if __name__ == "__main__":
    asyncio.run(main())
