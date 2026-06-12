#
# Copyright (c) 2024–2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Shared results.csv helpers, used by both bot.py and dialer.py.

Each finished call appends exactly one row. The row is both the record of what
Hailey learned and the signal dialer.py polls for to know a call is done.
"""

import csv
import datetime
import fcntl
from pathlib import Path

RESULTS_CSV = Path(__file__).parent / "results.csv"

RESULTS_FIELDS = [
    "timestamp",
    "call_id",
    "lead_phone",
    "lead_name",
    "lead_company",
    "outcome",
    "contact_name",
    "contact_role",
    "contact_phone",
    "contact_email",
    "notes",
]


def append_result(row: dict) -> None:
    """Append one outcome row, creating the file with a header if needed.

    Locally all bot sessions run inside one process, but the file lock also
    covers multi-process writers (e.g. the dialer writing timeout rows while a
    late bot session finishes).
    """
    row = {"timestamp": datetime.datetime.now().isoformat(timespec="seconds"), **row}
    with open(RESULTS_CSV, "a", newline="") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            writer = csv.DictWriter(f, fieldnames=RESULTS_FIELDS)
            if f.tell() == 0:
                writer.writeheader()
            writer.writerow({field: row.get(field, "") for field in RESULTS_FIELDS})
            f.flush()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def read_results() -> dict[str, dict]:
    """Read results.csv keyed by call_id. The first row for a call_id wins.

    "First row wins" matters when the dialer writes a timeout row and a slow
    bot session writes its own row later: the timeout verdict stands.
    """
    if not RESULTS_CSV.exists():
        return {}
    results: dict[str, dict] = {}
    with open(RESULTS_CSV, newline="") as f:
        for row in csv.DictReader(f):
            results.setdefault(row["call_id"], row)
    return results
