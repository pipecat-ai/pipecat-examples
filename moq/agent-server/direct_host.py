#
# Copyright (c) 2024-2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""MoQ direct-mode host: a bot per client, discovered on the relay.

Direct mode is MoQ without a ``/start`` control plane. A single
:class:`MOQDirectHost` dials a relay once and watches it for clients. Each
client publishes its microphone under a session id it mints itself, and the
host answers by running one bot per id:

    {request_prefix}/{id}     <- the client publishes its mic here
    {response_prefix}/{id}    <- the bot publishes its reply here

The relay is the control plane. Nothing has to reach this process over HTTP
for a call to start, so the host runs behind NAT and a client needs only the
relay URL.

Request and response live under SEPARATE prefixes on purpose: the host only
``announced()``s ``request/*``, so its own ``response/*`` publishes never
appear in its own discovery stream, and a per-client token can be scoped
tightly -- publish ``request/<id>``, subscribe ``response/<id>`` -- so one
client can't read another's request or spoof a response. The prefixes are
just strings; the deployment chooses auth and namespacing.

Each session is an ordinary :class:`~pipecat.transports.moq.transport.MOQTransport`
in client mode, pointed at the pair of paths for its id via ``response_path``
and ``request_path``. That costs one relay connection per call and keeps the
host on supported API -- no transport internals are touched.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable

from loguru import logger
from pipecat.transports.moq.transport import MOQParams, MOQTransport

try:
    import moq
except ModuleNotFoundError as e:
    logger.error(f"Exception: {e}")
    logger.error("In order to use the MOQ direct host, you need to `pip install pipecat-ai[moq]`.")
    raise Exception(f"Missing module: {e}")


DEFAULT_RELAY_URL = "http://localhost:4443"
DEFAULT_REQUEST_PREFIX = "request"
DEFAULT_RESPONSE_PREFIX = "response"

# How long a session waits for the announcing client's media to arrive.
# The client is already there -- it announced -- so this only has to cover
# the round trip, not a human opening a page.
DEFAULT_PEER_WAIT_SECS = 60.0

# How often the host loop re-checks whether any call is still live.
_IDLE_POLL_SECS = 15.0


# Builds and runs one session's pipeline to completion. Called with the
# session's transport and its id; returns when the call ends.
SessionBot = Callable[[MOQTransport, str], Awaitable[None]]

# Admission policy: decides whether to answer an announced client. Receives
# the raw announcement (``.path``, ``.broadcast``, ``.hops``) and returns
# True to serve it. ``None`` answers every client.
ServeFilter = Callable[["moq.Announcement"], bool]


def _env_secs(name: str, default: float) -> float | None:
    """Read a duration from the environment, treating 0 as "disabled"."""
    return float(os.getenv(name, str(default))) or None


class MOQDirectHost:
    """Runs one voice bot per client announced under a request prefix.

    Sessions can't collide -- each call lives on its own pair of broadcast
    paths -- so one host handles any number of calls, concurrently or back
    to back.

    Lifecycle guards, which matter wherever instances are billed or capped
    (a deployed host with no exit holds an agent slot forever):

    - ``peer_wait_secs`` bounds how long a session waits for the announcing
      client's media before giving up.
    - ``host_idle_secs`` exits the host after that long with no live calls.
      ``None`` runs until cancelled -- right for a long-lived service, wrong
      for a capped per-instance deployment.
    - ``max_sessions`` caps concurrent pipelines; further clients wait.

    How long a *call* may sit idle is the bot's own business, since its
    ``PipelineWorker`` is what enforces it (see ``idle_timeout_secs``).

    Client departures are not announced by the relay (moq-ffi exposes no
    deactivation event), so a call ends when its transport sees the client's
    streams close, bounded by the guards above.

    Example::

        async def run_bot(transport, session_id):
            pipeline = Pipeline([transport.input(), stt, llm, tts, transport.output()])
            ...

        host = MOQDirectHost(
            MOQParams(audio_in_enabled=True, audio_out_enabled=True),
            run_bot,
            relay_url="http://localhost:4443",
        )
        await host.run()

    Args:
        params: Per-session MOQ media parameters, shared by every session.
            The broadcast paths, relay URL and TLS setting are filled in
            per call and don't need to be set here.
        run_bot: Builds and runs one session's pipeline to completion.
        relay_url: The MoQ relay to dial.
        request_prefix: Prefix clients announce their microphones under.
        response_prefix: Prefix the bot publishes its replies under. Keep it
            disjoint from ``request_prefix`` so the host never discovers its
            own replies.
        verify_ssl: Verify the relay's TLS certificate. Off for self-signed
            dev relays.
        max_sessions: Concurrency cap; further clients wait for a slot.
        peer_wait_secs: Per-session wait for the announcing client's media.
        host_idle_secs: Exit after this long with no live calls; ``None``
            runs until cancelled.
        should_serve: Optional admission policy ``(announcement) -> bool``.
            Return False to decline a client, e.g. self-electing one relay
            edge per client across a fleet. Default answers every client.
    """

    def __init__(
        self,
        params: MOQParams,
        run_bot: SessionBot,
        *,
        relay_url: str = DEFAULT_RELAY_URL,
        request_prefix: str = DEFAULT_REQUEST_PREFIX,
        response_prefix: str = DEFAULT_RESPONSE_PREFIX,
        verify_ssl: bool = True,
        max_sessions: int = 8,
        peer_wait_secs: float = DEFAULT_PEER_WAIT_SECS,
        host_idle_secs: float | None = None,
        should_serve: ServeFilter | None = None,
    ):
        """Initialize the MoQ direct host."""
        self._params = params
        self._run_bot = run_bot
        self._relay_url = relay_url
        self._request_prefix = request_prefix.rstrip("/")
        self._response_prefix = response_prefix.rstrip("/")
        self._verify_ssl = verify_ssl
        self._peer_wait_secs = peer_wait_secs
        self._host_idle_secs = host_idle_secs
        self._should_serve = should_serve
        self._sem = asyncio.Semaphore(max_sessions)

    @classmethod
    def from_env(cls, params: MOQParams, run_bot: SessionBot) -> "MOQDirectHost":
        """Build a host from ``MOQ_*`` environment variables.

        For platforms that start processes without CLI arguments. Reads:

        - ``MOQ_RELAY_URL`` (default ``http://localhost:4443``)
        - ``MOQ_REQUEST_PREFIX`` / ``MOQ_RESPONSE_PREFIX`` (default
          ``request`` / ``response``)
        - ``MOQ_TLS_INSECURE`` -- set to 1 to skip relay cert verification
        - ``MOQ_MAX_SESSIONS`` (default 8)
        - ``MOQ_PEER_WAIT_SECS`` (default 60)
        - ``MOQ_HOST_IDLE_SECS`` -- 0 disables (default 0, i.e. run forever)

        Args:
            params: Per-session MOQ media parameters.
            run_bot: Builds and runs one session's pipeline to completion.

        Returns:
            A host configured from the environment.
        """
        insecure = os.getenv("MOQ_TLS_INSECURE", "").strip().lower() in ("1", "true", "yes", "on")
        return cls(
            params,
            run_bot,
            relay_url=os.getenv("MOQ_RELAY_URL", DEFAULT_RELAY_URL),
            request_prefix=os.getenv("MOQ_REQUEST_PREFIX", DEFAULT_REQUEST_PREFIX),
            response_prefix=os.getenv("MOQ_RESPONSE_PREFIX", DEFAULT_RESPONSE_PREFIX),
            verify_ssl=not insecure,
            max_sessions=int(os.getenv("MOQ_MAX_SESSIONS", "8")),
            peer_wait_secs=float(os.getenv("MOQ_PEER_WAIT_SECS", str(DEFAULT_PEER_WAIT_SECS))),
            host_idle_secs=_env_secs("MOQ_HOST_IDLE_SECS", 0),
        )

    def session_id(self, announced_path: str) -> str:
        """Return the session id an announced path names.

        ``announced(prefix)`` re-roots at the prefix, so the path is already
        the id. Strip defensively in case a build hands back the full path.
        """
        prefix = f"{self._request_prefix}/"
        return announced_path.removeprefix(prefix)

    def session_params(self, session_id: str) -> MOQParams:
        """Return the MOQ params for one call.

        Both paths hang off the id the client chose, so a bot serves exactly
        the caller that announced it and nobody else.
        """
        return self._params.model_copy(
            update={
                "relay_url": self._relay_url,
                "serve": False,
                "verify_ssl": self._verify_ssl,
                "connection_timeout": self._peer_wait_secs,
                "response_path": f"{self._response_prefix}/{session_id}",
                "request_path": f"{self._request_prefix}/{session_id}",
            }
        )

    async def run(self):
        """Watch the relay and serve a bot per announced session id.

        Returns when ``host_idle_secs`` elapses with no live calls, or
        raises if the relay watch itself fails.
        """
        sessions: dict[str, asyncio.Task] = {}

        idle_note = (
            f", exits after {self._host_idle_secs:.0f}s with no calls"
            if self._host_idle_secs
            else ""
        )
        logger.info(
            f"MOQ direct host: connecting to {self._relay_url} "
            f"(discover {self._request_prefix!r}/* -> reply {self._response_prefix!r}/*"
            f"{idle_note})"
        )

        # Subscribe-only: this client never publishes, and giving it a
        # publish origin would re-announce every discovered request path
        # back to the relay as our own.
        origin = moq.OriginProducer()
        async with moq.Client(
            self._relay_url, tls_verify=self._verify_ssl, subscribe=origin
        ) as client:
            watch_task = asyncio.create_task(self._watch(client, sessions))
            last_active = time.monotonic()
            try:
                while True:
                    await asyncio.wait({watch_task}, timeout=_IDLE_POLL_SECS)
                    if watch_task.done():
                        await watch_task  # surface a relay/watch failure
                        break
                    if any(not task.done() for task in sessions.values()):
                        last_active = time.monotonic()
                    elif (
                        self._host_idle_secs is not None
                        and time.monotonic() - last_active > self._host_idle_secs
                    ):
                        logger.info(
                            f"MOQ direct host: no calls for {self._host_idle_secs:.0f}s — exiting"
                        )
                        break
            finally:
                watch_task.cancel()
                await self._drain(sessions)

    async def _watch(self, client: "moq.Client", sessions: dict[str, asyncio.Task]):
        """Dispatch a session per announced client id."""
        async for announcement in client.announced(f"{self._request_prefix}/"):
            session_id = self.session_id(announcement.path)
            if not session_id:
                continue

            for finished in [sid for sid, task in sessions.items() if task.done()]:
                del sessions[finished]
            # A client that drops and re-announces the same id would
            # otherwise get a second bot publishing to the same reply path.
            if session_id in sessions:
                continue

            if self._should_serve is not None and not self._should_serve(announcement):
                logger.debug(f"MOQ direct host: declined client {session_id!r}")
                continue

            logger.info(f"MOQ direct host: client {session_id!r} announced")
            sessions[session_id] = asyncio.create_task(self._session(session_id))

    async def _session(self, session_id: str):
        """Run one call, holding a concurrency slot for its duration."""
        if self._sem.locked():
            logger.warning(f"MOQ direct host: at capacity, client {session_id!r} waiting")
        async with self._sem:
            transport = MOQTransport(self.session_params(session_id))
            logger.info(f"MOQ direct host: session {session_id!r} starting")
            try:
                await self._run_bot(transport, session_id)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.opt(exception=e).error(f"MOQ direct host: session {session_id!r} failed")
            finally:
                await transport.disconnect()
                logger.info(f"MOQ direct host: session {session_id!r} ended")

    async def _drain(self, sessions: dict[str, asyncio.Task]):
        """Stop live calls before the shared relay connection closes."""
        live = [task for task in sessions.values() if not task.done()]
        for task in live:
            task.cancel()
        if live:
            await asyncio.gather(*live, return_exceptions=True)
