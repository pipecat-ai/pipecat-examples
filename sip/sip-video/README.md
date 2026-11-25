# SIP Video

The bot answers incoming calls with video and echoes the caller's audio and
video back — call it from a video-capable SIP client to see and hear
yourself. No AI services, no API keys: the pipeline is
`input → mirror → output`.

> [!IMPORTANT]
> Setup instructions — dependencies, API keys, provisioning, softphone
> options, terminology — are in [`README.md`](../README.md).

## Run it

From the example root:

```bash
uv run python sip-video/bot.py -t sip -d
```

No SIP account needed on the command line: with `DAILY_API_KEY` set, the
runner provisions a temporary SIP client on your Daily domain, prints the
URI to dial, and deletes it again when the bot exits. To use your own
account instead:

```bash
SIP_USER=1001 SIP_PASS=secret SIP_DOMAIN=sip.example.com \
    uv run python sip-video/bot.py -t sip -d
```

## Dial it

Call the printed URI from a video-capable client — Linphone works; enable
its camera for the call. You should see your own video mirrored back and
hear your own voice. OpenCV ships with the `sip` extra, so the example's
`uv sync` already installed everything.

**Wear headphones** — the bot echoes audio verbatim, so speakers into mic
feed back.
