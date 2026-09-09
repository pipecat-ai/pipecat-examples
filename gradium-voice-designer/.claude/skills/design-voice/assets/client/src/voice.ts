/**
 * Who the bot is, as written by the design-voice skill into public/voice.json.
 *
 * The skill's `client` step writes this file after a voice is kept, and copies the
 * reference image (if the voice was designed from one) into public/ next to it:
 *
 *     {
 *       "name": "Gruff Irishman",
 *       "image": "/gruff-irishman.png",
 *       "brief": "A gruff Irish male voice, 45 to 60, ...",
 *       "persona": "You are Declan, a gruff but good-hearted Irish innkeeper ..."
 *     }
 *
 * Every field is optional. A missing or malformed file behaves like all nulls.
 */
export interface VoiceInfo {
  /** Working name of the voice, shown in the header. */
  name: string | null
  /** URL of the reference image, served from public/. Replaces the visualizer. */
  image: string | null
  /** The description the voice was designed from. */
  brief: string | null
  /** The persona line the bot's system prompt starts with. */
  persona: string | null
}

export const EMPTY_VOICE: VoiceInfo = {
  name: null,
  image: null,
  brief: null,
  persona: null,
}

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null
}

/** Fetch /voice.json. Never throws; anything unexpected yields EMPTY_VOICE. */
export async function loadVoice(): Promise<VoiceInfo> {
  try {
    const response = await fetch("/voice.json", { cache: "no-store" })
    if (!response.ok) return EMPTY_VOICE
    const data: unknown = await response.json()
    if (!data || typeof data !== "object") return EMPTY_VOICE
    const record = data as Record<string, unknown>
    return {
      name: optionalString(record.name),
      image: optionalString(record.image),
      brief: optionalString(record.brief),
      persona: optionalString(record.persona),
    }
  } catch {
    return EMPTY_VOICE
  }
}
