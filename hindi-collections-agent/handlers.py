#
# Copyright (c) 2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Tools for the payment reminder flow in flow.yaml.

Each tool does its work and returns ``(result, TRANSITION_IN_YAML)``. The tool
never picks the next step; flow.yaml does.
"""

from loguru import logger
from pipecat.flows import TRANSITION_IN_YAML, FlowManager

# Stand-in for the loan system. Keyed by the last four digits of the loan number.
LOANS = {
    "4321": {"customer_name": "Amit", "emi_amount": "8,500 rupees", "due_date": "November 20"},
}


MAX_VERIFY_TRIES = 3


async def verify_customer(flow_manager: FlowManager, last_four: str):
    """Check the last four digits of the caller's loan number.

    Args:
        last_four: The last four digits of the loan number, digits only (for example "4321").
    """
    # Keep only the digits, and read Hindi digits too ("४३२१" becomes "4321").
    digits = "".join(str(int(c)) for c in last_four if c.isdigit())
    loan = LOANS.get(digits)
    if loan:
        # The loan details only reach the LLM after this check passes: the
        # next step's prompt is filled in from this state.
        flow_manager.state.update(loan)
        status = "verified"
    else:
        # Stay on this step and ask again, but end the call after a few misses
        # so a caller cannot keep guessing.
        tries = flow_manager.state["verify_tries"] = flow_manager.state.get("verify_tries", 0) + 1
        status = "locked" if tries >= MAX_VERIFY_TRIES else "retry"
    logger.info(f"verify_customer({last_four!r}) -> {status}")
    return {"status": status}, TRANSITION_IN_YAML


async def record_promise_to_pay(flow_manager: FlowManager, date: str):
    """Record the date the caller promised to pay the overdue amount.

    Args:
        date: The date the caller promised to pay, as they said it (for example "Friday").
    """
    # A real bot would write this to the collections system.
    flow_manager.state["promise_date"] = date
    logger.info(f"record_promise_to_pay({date!r})")
    return {"recorded": True, "date": date}, TRANSITION_IN_YAML
