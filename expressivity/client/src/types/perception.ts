/**
 * The demo's own messages from the bot, sent as RTVI server messages: the
 * clips it can play, and when one starts and finishes (server/bot.py,
 * server/clips.py). The turns, their words, their readings and how long each
 * read took come from Pipecat's own RTVI events.
 */

/** The two models that read each turn: Pipecat Voice Reader hears the voice, Pipecat Tone Reader reads the words. */
export const MODELS = ["voice", "words"] as const;
export type Model = (typeof MODELS)[number];

export interface ClipInfo {
  id: string;
  mood: string;
  /** Whether it was meant: "sincere" or "sarcastic". */
  sincerity: string;
  voice: string;
  text: string;
  duration: number;
}

export type ServerMessage =
  | { type: "clips"; clips: ClipInfo[] }
  | { type: "clip-started"; clipId: string }
  | { type: "clip-finished"; clipId: string; completed: boolean };

const MESSAGE_TYPES: ReadonlySet<string> = new Set<ServerMessage["type"]>([
  "clips",
  "clip-started",
  "clip-finished",
]);

/** Whether a server message is one of the demo's. The bot is the only sender, so its shape is taken on trust. */
export function isServerMessage(data: unknown): data is ServerMessage {
  return (
    typeof data === "object" &&
    data !== null &&
    "type" in data &&
    typeof data.type === "string" &&
    MESSAGE_TYPES.has(data.type)
  );
}
