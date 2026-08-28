import { NextResponse } from 'next/server';

/**
 * Proxy for the per-session bot endpoints.
 *
 * SmallWebRTC connects in two steps: `/api/start` returns a session id, then
 * the transport posts its WebRTC offer to `/sessions/{sessionId}/api/offer`
 * (deriving that URL from the start endpoint) and PATCHes it to renegotiate.
 */
async function handleRequest(
  request: Request,
  { params }: { params: Promise<{ sessionId: string; path: string[] }> }
) {
  const botBaseUrl =
    process.env.BOT_START_URL?.replace('/start', '') || 'http://localhost:7860';
  const { sessionId, path } = await params;
  const targetUrl = `${botBaseUrl}/sessions/${sessionId}/${path.join('/')}`;

  try {
    const body = await request.text();

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    if (process.env.BOT_START_PUBLIC_API_KEY) {
      headers.Authorization = `Bearer ${process.env.BOT_START_PUBLIC_API_KEY}`;
    }

    const response = await fetch(targetUrl, {
      method: request.method,
      headers,
      body,
    });

    if (!response.ok) {
      throw new Error(`Failed to proxy request: ${response.statusText}`);
    }

    const data = await response.json();

    if (data.error) {
      throw new Error(data.error);
    }

    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { error: `Failed to proxy session request: ${error}` },
      { status: 500 }
    );
  }
}

export async function POST(
  request: Request,
  context: { params: Promise<{ sessionId: string; path: string[] }> }
) {
  return handleRequest(request, context);
}

export async function PATCH(
  request: Request,
  context: { params: Promise<{ sessionId: string; path: string[] }> }
) {
  return handleRequest(request, context);
}
