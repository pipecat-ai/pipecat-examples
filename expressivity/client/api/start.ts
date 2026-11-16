/**
 * Starts a session of the demo's bot on Pipecat Cloud, for the hosted page.
 *
 * The page POSTs here instead of calling Pipecat Cloud itself, so the public
 * API key stays on the server. Written as a web-standard handler in the `api/`
 * folder, which is how Vercel serves it; on another host, mount `POST` at
 * `/api/start`.
 */

const PIPECAT_CLOUD_API = "https://api.pipecat.daily.co/v1/public";

interface StartResponse {
  dailyRoom?: unknown;
  dailyToken?: unknown;
}

function failure(status: number, error: string): Response {
  return Response.json({ error }, { status });
}

export async function POST(): Promise<Response> {
  const agent = process.env.PIPECAT_CLOUD_AGENT_NAME;
  const apiKey = process.env.PIPECAT_CLOUD_PUBLIC_KEY;
  if (!agent || !apiKey) {
    return failure(500, "The demo isn't configured to start sessions.");
  }

  const started = await fetch(`${PIPECAT_CLOUD_API}/${agent}/start`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ createDailyRoom: true }),
  });
  if (!started.ok) {
    console.error(`Pipecat Cloud refused the session: HTTP ${started.status}`);
    return failure(502, "Couldn't start a session.");
  }

  // Only what the page's transport needs to join the room is passed on.
  const { dailyRoom, dailyToken } = (await started.json()) as StartResponse;
  if (typeof dailyRoom !== "string" || typeof dailyToken !== "string") {
    return failure(502, "Couldn't start a session.");
  }
  return Response.json({ dailyRoom, dailyToken });
}
