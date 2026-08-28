#
# Copyright (c) 2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Pseudo reservation tools for the phonellm example bot.

Tools are declared as **direct functions**: a single async function is both the
handler and the schema. Pipecat derives the tool's name, description, parameters
and which of them are required from the signature and the Google-style
docstring, so listing the function in ``LLMContext(tools=TOOLS)`` is all it
takes — no ``FunctionSchema`` and no separate registration step.

Alongside the reservation tools, ``end_call`` hangs the call up.

The "backend" is an in-memory ``ReservationStore``, shared with the handlers
via ``PipelineWorker(app_resources=...)`` and read back as
``params.app_resources``.
"""

from typing import Any

from loguru import logger
from pipecat.adapters.schemas.direct_function import tool_options
from pipecat.frames.frames import EndWorkerFrame
from pipecat.services.llm_service import FunctionCallParams


class ReservationStore:
    """In-memory stand-in for a real reservation system.

    One instance per session; seeded with a reservation so lookups can
    succeed straight away.
    """

    def __init__(self) -> None:
        self._next_id = 102
        self.reservations: dict[str, dict[str, Any]] = {
            "101": {
                "confirmation_number": "101",
                "name": "Alice Smith",
                "party_size": 2,
                "date": "2026-08-28",
                "time": "19:00",
            },
        }

    def create(self, name: str, party_size: int, date: str, time: str) -> dict[str, Any]:
        confirmation_number = str(self._next_id)
        self._next_id += 1
        reservation = {
            "confirmation_number": confirmation_number,
            "name": name,
            "party_size": party_size,
            "date": date,
            "time": time,
        }
        self.reservations[confirmation_number] = reservation
        return reservation

    def find(self, confirmation_number: str | None, name: str | None) -> dict[str, Any] | None:
        if confirmation_number:
            return self.reservations.get(confirmation_number)
        if name:
            needle = name.strip().lower()
            for reservation in self.reservations.values():
                if reservation["name"].lower() == needle:
                    return reservation
        return None


async def get_reservation(
    params: FunctionCallParams,
    confirmation_number: str | None = None,
    name: str | None = None,
):
    """Look up an existing reservation by confirmation number or by the name it's under.

    Args:
        confirmation_number: The reservation's confirmation number, e.g. '101'.
        name: The full name the reservation is under, e.g. 'Alice Smith'.
    """
    store: ReservationStore = params.app_resources
    reservation = store.find(confirmation_number, name)
    logger.info(f"get_reservation({confirmation_number=}, {name=}) -> {reservation}")
    if reservation:
        await params.result_callback({"found": True, "reservation": reservation})
    else:
        await params.result_callback(
            {"found": False, "message": "No reservation matches that confirmation number or name."}
        )


async def create_reservation(
    params: FunctionCallParams,
    name: str,
    party_size: int,
    date: str,
    time: str,
):
    """Create a new reservation once the name, party size, date, and time are all known.

    Args:
        name: The full name to put the reservation under.
        party_size: Number of people in the party.
        date: Reservation date in YYYY-MM-DD format.
        time: Reservation time in 24-hour HH:MM format.
    """
    store: ReservationStore = params.app_resources
    reservation = store.create(name=name, party_size=party_size, date=date, time=time)
    logger.info(f"create_reservation({name=}, {party_size=}, {date=}, {time=}) -> {reservation}")
    await params.result_callback({"success": True, "reservation": reservation})


async def update_reservation(
    params: FunctionCallParams,
    confirmation_number: str | None = None,
    name: str | None = None,
    party_size: int | None = None,
    date: str | None = None,
    time: str | None = None,
):
    """Update an existing reservation.

    Look it up by confirmation number or name, then change only the fields the
    caller wants changed.

    Args:
        confirmation_number: The reservation's confirmation number, e.g. '101'.
        name: The full name the reservation is under (also used to look it up when no confirmation number is given).
        party_size: New number of people in the party.
        date: New reservation date in YYYY-MM-DD format.
        time: New reservation time in 24-hour HH:MM format.
    """
    store: ReservationStore = params.app_resources
    reservation = store.find(confirmation_number, name)
    updates = {"name": name, "party_size": party_size, "date": date, "time": time}
    if not reservation:
        logger.info(f"update_reservation({confirmation_number=}, {updates}) -> not found")
        await params.result_callback(
            {
                "success": False,
                "message": "No reservation matches that confirmation number or name.",
            }
        )
        return
    for field, value in updates.items():
        if value is not None:
            reservation[field] = value
    logger.info(f"update_reservation({confirmation_number=}, {updates}) -> {reservation}")
    await params.result_callback({"success": True, "reservation": reservation})


# cancel_on_interruption=False so the tool call survives interruptions — without
# it, the bot's own farewell audio bleeding back through the mic can register as
# a new turn, cancel the in-flight end_call, and leave the caller saying goodbye
# twice.
@tool_options(cancel_on_interruption=False)
async def end_call(params: FunctionCallParams):
    """End the call and hang up.

    Use this once the caller is finished — they say goodbye, or their reservation
    is settled and they need nothing else. Say a short farewell in the same turn:
    the call stays up until that has finished playing.
    """
    logger.info("end_call -> hanging up once the farewell has played")
    # Resolve the call first so the LLM can produce its farewell turn; the
    # EndWorkerFrame then drains the queued frames — the closing TTS among them —
    # before the worker shuts down.
    await params.result_callback({"success": True})
    await params.llm.push_frame(EndWorkerFrame())


TOOLS = [get_reservation, create_reservation, update_reservation, end_call]
