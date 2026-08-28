#
# Copyright (c) 2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Pseudo reservation tools for the phonellm example bot.

Tools are declared with explicit ``FunctionSchema`` objects bundled into a
``ToolsSchema``. Each schema carries its ``handler``, so listing the schema on
the ``LLMContext`` (``LLMContext(tools=TOOLS)``) both advertises the tool to
the LLM and registers the handler — no separate registration step.

The "backend" is an in-memory ``ReservationStore``, shared with the handlers
via ``PipelineWorker(app_resources=...)`` and read back as
``params.app_resources``.
"""

from typing import Any

from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
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


async def get_reservation(params: FunctionCallParams):
    store: ReservationStore = params.app_resources
    args = params.arguments
    reservation = store.find(args.get("confirmation_number"), args.get("name"))
    logger.info(f"get_reservation({args}) -> {reservation}")
    if reservation:
        await params.result_callback({"found": True, "reservation": reservation})
    else:
        await params.result_callback(
            {"found": False, "message": "No reservation matches that confirmation number or name."}
        )


async def create_reservation(params: FunctionCallParams):
    store: ReservationStore = params.app_resources
    args = params.arguments
    reservation = store.create(
        name=args["name"],
        party_size=args["party_size"],
        date=args["date"],
        time=args["time"],
    )
    logger.info(f"create_reservation({args}) -> {reservation}")
    await params.result_callback({"success": True, "reservation": reservation})


async def update_reservation(params: FunctionCallParams):
    store: ReservationStore = params.app_resources
    args = params.arguments
    reservation = store.find(args.get("confirmation_number"), args.get("name"))
    if not reservation:
        logger.info(f"update_reservation({args}) -> not found")
        await params.result_callback(
            {
                "success": False,
                "message": "No reservation matches that confirmation number or name.",
            }
        )
        return
    for field in ("name", "party_size", "date", "time"):
        if args.get(field) is not None:
            reservation[field] = args[field]
    logger.info(f"update_reservation({args}) -> {reservation}")
    await params.result_callback({"success": True, "reservation": reservation})


get_reservation_schema = FunctionSchema(
    name="get_reservation",
    description="Look up an existing reservation by confirmation number or by the name it's under.",
    properties={
        "confirmation_number": {
            "type": "string",
            "description": "The reservation's confirmation number, e.g. '101'.",
        },
        "name": {
            "type": "string",
            "description": "The full name the reservation is under, e.g. 'Alice Smith'.",
        },
    },
    required=[],
    handler=get_reservation,
)

create_reservation_schema = FunctionSchema(
    name="create_reservation",
    description="Create a new reservation once the name, party size, date, and time are all known.",
    properties={
        "name": {
            "type": "string",
            "description": "The full name to put the reservation under.",
        },
        "party_size": {
            "type": "integer",
            "description": "Number of people in the party.",
        },
        "date": {
            "type": "string",
            "description": "Reservation date in YYYY-MM-DD format.",
        },
        "time": {
            "type": "string",
            "description": "Reservation time in 24-hour HH:MM format.",
        },
    },
    required=["name", "party_size", "date", "time"],
    handler=create_reservation,
)

update_reservation_schema = FunctionSchema(
    name="update_reservation",
    description="Update an existing reservation. Look it up by confirmation number or name, then change only the fields the caller wants changed.",
    properties={
        "confirmation_number": {
            "type": "string",
            "description": "The reservation's confirmation number, e.g. '101'.",
        },
        "name": {
            "type": "string",
            "description": "The full name the reservation is under (also used to look it up when no confirmation number is given).",
        },
        "party_size": {
            "type": "integer",
            "description": "New number of people in the party.",
        },
        "date": {
            "type": "string",
            "description": "New reservation date in YYYY-MM-DD format.",
        },
        "time": {
            "type": "string",
            "description": "New reservation time in 24-hour HH:MM format.",
        },
    },
    required=[],
    handler=update_reservation,
)

TOOLS = ToolsSchema(
    standard_tools=[
        get_reservation_schema,
        create_reservation_schema,
        update_reservation_schema,
    ]
)
