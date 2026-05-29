import {
  ConsoleTemplate,
  FullScreenContainer,
  Select,
  SelectContent,
  SelectGuide,
  SelectItem,
  SelectTrigger,
  SelectValue,
  ThemeProvider,
} from "@pipecat-ai/voice-ui-kit";
import React, { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";

// When VITE_BOT_START_URL is set the client connects directly to Pipecat Cloud
// using Daily transport. Without it, SmallWebRTC is used for local development
// and the request is proxied to the local bot server on port 7860.
const botStartUrl = import.meta.env.VITE_BOT_START_URL || "/start";
const botStartApiKey = import.meta.env.VITE_BOT_START_PUBLIC_API_KEY || "";

const isPipecatCloud = Boolean(import.meta.env.VITE_BOT_START_URL);

const VOICES: { value: string; label: string }[] = [
  { value: "_6Aslh2DxfmnRLmP", label: "Default" },
  { value: "m86j6D7UZpGzHsNu", label: "Jackie" },
  { value: "YTpq7expH9539ERJ", label: "Emma" },
  { value: "ubuXFxVQwVYnZQhy", label: "Eva" },
  // Add more Gradium voice IDs here
];

type VoiceSelectProps = {
  value: string;
  onValueChange: (value: string) => void;
};

function VoiceSelect({ value, onValueChange }: VoiceSelectProps) {
  return (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger
        aria-label="Voice"
        className="voice-select-trigger"
        rounded="lg"
        size="md"
      >
        <SelectGuide>Voice</SelectGuide>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {VOICES.map(({ value, label }) => (
          <SelectItem key={value} value={value}>
            {label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function Home() {
  const [voice, setVoice] = useState(VOICES[0].value);

  const headers = new Headers();
  if (botStartApiKey) {
    headers.set("Authorization", `Bearer ${botStartApiKey}`);
  }

  const startBotParams = isPipecatCloud
    ? {
        endpoint: botStartUrl,
        requestData: { createDailyRoom: true, voice },
        headers,
      }
    : {
        endpoint: "/start",
        requestData: {
          createDailyRoom: false,
          enableDefaultIceServers: true,
          transport: "webrtc",
          body: { voice },
        },
      };

  return (
    <ThemeProvider>
      <FullScreenContainer>
        <ConsoleTemplate
          key={voice}
          transportType={isPipecatCloud ? "daily" : "smallwebrtc"}
          startBotParams={startBotParams}
          transportOptions={isPipecatCloud ? {} : { waitForICEGathering: true }}
          noUserVideo={true}
          logoComponent={
            <VoiceSelect value={voice} onValueChange={setVoice} />
          }
        />
      </FullScreenContainer>
    </ThemeProvider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Home />
  </StrictMode>,
);
