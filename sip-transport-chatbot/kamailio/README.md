# SIP bot behind a self-hosted Kamailio

The SIP examples' Daily-provisioned tiers need a Daily account; this one
runs entirely on your own machines. A Kamailio container is the
registrar, the bot registers to it, and any softphone registered to the
same Kamailio can call the bot. No external service or API key is
involved — the greeting uses local Kokoro TTS.

```
softphone ──INVITE──> Kamailio ──lookup(location)──> bot
                        │                              │
                        └────── signaling only ────────┘
media:  softphone <───────── direct RTP ─────────────> bot
```

This is the carrier-style topology: the registration edge is separate
from the media path. A PBX (FreeSWITCH, Asterisk) can sit behind or
beside Kamailio for transfer, transcoding, or conferencing without
touching the bot.

## Requirements

- Docker (for the Kamailio registrar)
- A softphone (Linphone, MicroSIP, Zoiper)

## Run Kamailio

```bash
cd sip/kamailio
docker run -d --name kamailio -p 5060:5060/udp -p 5060:5060/tcp \
  -v "$(pwd)/kamailio.cfg:/etc/kamailio/kamailio.cfg:ro" \
  kamailio/kamailio:latest
```

The bundled `kamailio.cfg` is a minimal registrar: REGISTERs are stored
in memory, INVITEs for registered users relay to the bot's NAT-received
address, unregistered targets get 480, anything else 405. No digest
auth — fine for the lab; the production notes below cover adding it.

## Run the bot

```bash
cd sip/kamailio
uv sync
cp env.example .env   # then set KAMAILIO_REGISTRAR to the Kamailio host
uv run python bot.py
```

Wait for `Registered to SIP server, AOR = sip:5001@kamailio.lab`.

## Call the bot

Add an account in your softphone pointing at the Kamailio container —
server `<kamailio-host>:5060`, transport UDP, any username and password
(the bundled config does not authenticate) — and dial `5001`. The bot
answers, speaks its greeting, and hangs up.

## NAT

The bot re-REGISTERs every 25 seconds (`reg_interval`) so NAT UDP flows
stay open, and sends `+sip.instance` (RFC 5626) so a restarted bot
replaces its stale binding instead of stacking contacts. On the server
side, `force_rport()` + `fix_nated_register()` record the NAT-received
address and `handle_ruri_alias()` relays the INVITE there.

## Scaling out

One bot process handles one call at a time. For concurrent calls run
several bot processes: multiple `SIPConnection`s sharing one AOR in a
single process auto-dispatch inbound calls to the first idle connection
(486 when all are busy); across hosts, put a dispatcher in front, or
replicate the location table with the `dmq_usrloc` module for
multi-active registrars.

## Production hardening

- digest auth (`auth` module + `pv_auth_check`), TLS
- `dispatcher` for load-balancing bot farms, `dmq_usrloc` for HA
- a database for `usrloc` (`db_mode=1`) so registrations survive restarts
- `rtpengine` when media must be anchored (recording, far-end NAT)
