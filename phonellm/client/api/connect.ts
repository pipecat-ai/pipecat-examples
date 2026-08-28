import type { VercelRequest, VercelResponse } from "@vercel/node"

/**
 * Starts a Pipecat Cloud agent session and hands the browser what it needs to
 * join it. BOT_START_URL is the agent's full start endpoint, e.g.
 * https://api.pipecat.daily.co/v1/public/<agent-name>/start.
 *
 * The client can't call Pipecat Cloud itself: starting a session takes the
 * organization's public API key, and anything shipped to the browser is
 * readable by anyone. So the key lives here, in a serverless function, and the
 * browser only ever sees the room it may join.
 *
 * The response shape is dictated by the caller: the Pipecat client posts here
 * via startBotAndConnect() and passes the JSON straight to connect(), so this
 * must return Daily call options — `{ url, token }`.
 *
 * Note this endpoint is unauthenticated. Anyone who finds it can start a
 * session on your account, so gate it before putting it in front of real
 * traffic — a bot check, a signed session, or rate limiting.
 */

interface StartResponse {
  dailyRoom?: string
  dailyToken?: string
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST")
    res.status(405).json({ error: "Method not allowed" })
    return
  }

  const startUrl = process.env.BOT_START_URL
  const publicKey = process.env.BOT_START_PUBLIC_KEY
  if (!startUrl || !publicKey) {
    console.error(
      "Missing BOT_START_URL or BOT_START_PUBLIC_KEY — set both in the " +
        "project's environment variables."
    )
    res
      .status(500)
      .json({ error: "The server is not configured to start a bot" })
    return
  }

  let started: Response
  try {
    started = await fetch(startUrl, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${publicKey}`,
        "Content-Type": "application/json",
      },
      // Pipecat Cloud creates the Daily room and passes it to the agent, so
      // bot.py picks it up through its "daily" transport params.
      body: JSON.stringify({ createDailyRoom: true }),
    })
  } catch (err) {
    console.error("Could not reach Pipecat Cloud:", err)
    res.status(502).json({ error: "Could not reach Pipecat Cloud" })
    return
  }

  if (!started.ok) {
    // Logged, not returned: the body names the agent and can explain which
    // credential was rejected.
    console.error(
      `Pipecat Cloud rejected the start request (${started.status}): ${await started.text()}`
    )
    res.status(502).json({ error: "Failed to start the bot" })
    return
  }

  const { dailyRoom, dailyToken } = (await started.json()) as StartResponse
  if (!dailyRoom) {
    console.error("Pipecat Cloud started a session without a Daily room")
    res.status(502).json({ error: "Failed to start the bot" })
    return
  }

  res.status(200).json({ url: dailyRoom, token: dailyToken })
}
