import { NextResponse } from "next/server";

/**
 * Starts a bot session.
 *
 * Forwards the client's request to BOT_START_URL, which is either the local
 * development runner (`uv run bot.py`) or a Pipecat Cloud agent. The Pipecat
 * Cloud public API key is added here so it never reaches the browser.
 */
export async function POST(request: Request) {
  const botStartUrl =
    process.env.BOT_START_URL || "http://localhost:7860/start";

  try {
    // The client picks the transport, so pass its request body straight through.
    const requestData = await request.json();

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };

    if (process.env.BOT_START_PUBLIC_API_KEY) {
      headers.Authorization = `Bearer ${process.env.BOT_START_PUBLIC_API_KEY}`;
    }

    const response = await fetch(botStartUrl, {
      method: "POST",
      headers,
      body: JSON.stringify(requestData),
    });

    if (!response.ok) {
      throw new Error(`Failed to connect to Pipecat: ${response.statusText}`);
    }

    const data = await response.json();

    if (data.error) {
      throw new Error(data.error);
    }

    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { error: `Failed to process connection request: ${error}` },
      { status: 500 }
    );
  }
}
