# SIP Trunk Webhook

A `sip_client` SIP trunk on Daily provisions a SIP account **per inbound
call** and POSTs a signed `sip_trunk.incoming` notification to the trunk's
`webhook_url`. No long-lived credential exists anywhere, and concurrent
calls each get their own account — the shape Pipecat Cloud runs.

Two files implement it:

- [`server.py`](server.py) — the webhook endpoint. Answers Daily's
  `sip_trunk.test` probe, validates the notification fields, verifies the
  `X-Siptrunk-Signature` over the raw request bytes (the steps Pipecat
  Cloud's handler takes), and starts one bot per call.
- [`bot.py`](bot.py) — the dial-in voice agent the server starts, on the
  per-call account the notification carries. Also runs standalone against
  any account (`uv run python trunk/bot.py -t sip -d`).

> [!IMPORTANT]
> The full walkthrough — why the probe matters, where the secret comes
> from, signature details, duplicate handling — is in
> [`README.md`](../README.md#tier-4--the-webhook-trunk-path-optional).

## Run it

Start the server where Daily can reach it, through a tunnel in development:

```bash
SIP_TRUNK_HMAC=placeholder uv run python trunk/server.py --port 7860
ngrok http 7860
```

Create the trunk against it (the create fails unless the server answers the
probe):

```bash
curl -s -X POST "$DAILY_API_URL/sip-trunk" \
  -H "Authorization: Bearer $DAILY_API_KEY" -H "Content-Type: application/json" \
  -d '{"trunk_name": "mytrunk", "trunk_type": "sip_client",
       "trunk_config": {"is_open": true, "exp_offset": 3600},
       "sip_client_template": {"transport": "tls"},
       "notification": {"webhook_url": "https://<host>/daily-sip-trunk-webhook"}}'
```

The response carries `config.notification.hmac` — the real value of
`SIP_TRUNK_HMAC` — so restart the server with it. Then point a phone number
at the trunk and call it.

Environment: `SIP_TRUNK_HMAC`, plus the agent's `DEEPGRAM_API_KEY`,
`OPENAI_API_KEY` and `CARTESIA_API_KEY`.
