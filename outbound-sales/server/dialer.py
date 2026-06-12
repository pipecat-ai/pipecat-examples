#
# Copyright (c) 2024–2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Batch dialer: calls every lead in leads.csv, five at a time.

For each batch it POSTs /dialout to server.py once per lead, then polls
results.csv until every call in the batch has an outcome row (the bot writes
one when a call ends) or the timeout passes. Leads that already have a row in
results.csv are skipped, so re-running the dialer resumes where it left off.

Usage::

    uv run dialer.py [--leads leads.csv] [--server http://localhost:8080]

Note: this completion signal (a shared results.csv) works for local runs,
where all bot sessions run in one process on one filesystem. On Pipecat Cloud
each bot runs in its own container; there you'd report outcomes to a webhook
or shared storage instead.
"""

import argparse
import asyncio
import csv
import time
import uuid
from pathlib import Path

import aiohttp
from loguru import logger

from results import append_result, read_results

BATCH_SIZE = 5
POLL_INTERVAL_SECS = 5
CALL_TIMEOUT_SECS = 360


def read_leads(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return [row for row in csv.DictReader(f) if row.get("phone")]


async def dial_lead(session: aiohttp.ClientSession, server_url: str, lead: dict, call_id: str):
    """POST one /dialout request. Raises on failure."""
    payload = {
        "dialout_settings": {"phone_number": lead["phone"]},
        "lead": {
            "phone": lead["phone"],
            "name": lead.get("name") or None,
            "company": lead.get("company") or None,
        },
        "call_id": call_id,
    }
    async with session.post(f"{server_url}/dialout", json=payload) as response:
        if response.status != 200:
            raise RuntimeError(f"/dialout returned {response.status}: {await response.text()}")


async def run_batch(session: aiohttp.ClientSession, server_url: str, batch: list[dict]):
    """Dial one batch and wait until every call has an outcome row."""
    pending: dict[str, dict] = {}

    for lead in batch:
        call_id = uuid.uuid4().hex
        try:
            await dial_lead(session, server_url, lead, call_id)
            logger.info(f"Dialing {lead['phone']} ({lead.get('name') or 'unknown'}) [{call_id}]")
            pending[call_id] = lead
        except Exception as e:
            logger.error(f"Failed to start call to {lead['phone']}: {e}")
            append_result(
                {
                    "call_id": call_id,
                    "lead_phone": lead["phone"],
                    "lead_name": lead.get("name", ""),
                    "lead_company": lead.get("company", ""),
                    "outcome": "error",
                    "notes": str(e),
                }
            )

    deadline = time.monotonic() + CALL_TIMEOUT_SECS
    while pending and time.monotonic() < deadline:
        await asyncio.sleep(POLL_INTERVAL_SECS)
        rows = read_results()
        for call_id in list(pending):
            if call_id in rows:
                lead = pending.pop(call_id)
                logger.info(f"Call to {lead['phone']} finished: {rows[call_id]['outcome']}")

    # Anything still pending gets a timeout row. The bot may still write its
    # own row later; read_results keeps the first row per call_id.
    for call_id, lead in pending.items():
        logger.warning(f"Call to {lead['phone']} timed out after {CALL_TIMEOUT_SECS}s")
        append_result(
            {
                "call_id": call_id,
                "lead_phone": lead["phone"],
                "lead_name": lead.get("name", ""),
                "lead_company": lead.get("company", ""),
                "outcome": "timeout",
            }
        )


async def main():
    parser = argparse.ArgumentParser(description="Batch dialer for the outbound sales bot")
    parser.add_argument("--leads", default="leads.csv", help="Path to the leads CSV")
    parser.add_argument("--server", default="http://localhost:8080", help="server.py base URL")
    args = parser.parse_args()

    leads = read_leads(Path(args.leads))
    already_called = {row["lead_phone"] for row in read_results().values()}
    todo = [lead for lead in leads if lead["phone"] not in already_called]
    skipped = len(leads) - len(todo)
    if skipped:
        logger.info(f"Skipping {skipped} lead(s) already in results.csv")
    if not todo:
        logger.info("Nothing to do.")
        return

    async with aiohttp.ClientSession() as session:
        for i in range(0, len(todo), BATCH_SIZE):
            batch = todo[i : i + BATCH_SIZE]
            logger.info(f"--- Batch {i // BATCH_SIZE + 1}: {len(batch)} call(s) ---")
            await run_batch(session, args.server, batch)

    rows = read_results()
    captured = sum(1 for row in rows.values() if row["outcome"] == "contact_captured")
    logger.info(f"Done. {len(rows)} call(s) recorded, {captured} contact(s) captured.")
    logger.info("See results.csv for details.")


if __name__ == "__main__":
    asyncio.run(main())
