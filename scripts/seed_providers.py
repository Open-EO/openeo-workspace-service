#!/usr/bin/env python3
"""
Seed workspace provider definitions into Elasticsearch.

Usage:
    python scripts/seed_providers.py [--reset]

Options:
    --reset   Delete existing providers before re-seeding.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

# Ensure the src layout is on the path when running as a script
sys.path.insert(0, "src")

from openeo_workspace_service.db.elasticsearch import (
    ProviderRepository,
    get_es_client,
    init_indices,
    seed_default_providers,
)


async def main(reset: bool) -> None:
    async with get_es_client() as es:
        await init_indices(es)
        repo = ProviderRepository(es)

        if reset:
            existing = await repo.list_all()
            for name in existing:
                await es.delete(
                    index=es._transport.hosts[0].get("host", ""),
                    id=name,
                    ignore=[404],
                )
            print(f"Deleted {len(existing)} existing providers.")

        await seed_default_providers(es)
        providers = await repo.list_all()
        print(f"Seeded providers: {', '.join(providers.keys())}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="Delete existing providers first")
    args = parser.parse_args()
    asyncio.run(main(reset=args.reset))
