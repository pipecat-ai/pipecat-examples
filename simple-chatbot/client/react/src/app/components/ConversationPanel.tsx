"use client";

import { MessagesSquareIcon } from "lucide-react";
import { useState } from "react";

import { Conversation } from "@/components/pipecat/conversation";
import type { TextRenderMode } from "@/components/pipecat/conversation-message";
import { TextInput } from "@/components/pipecat/text-input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { Panel, PanelHeader, PanelTitle } from "./Panel";

const RENDER_MODES: { value: TextRenderMode; label: string }[] = [
  { value: "karaoke", label: "Karaoke" },
  { value: "captions", label: "Captions" },
  { value: "instant", label: "Instant" },
];

export function ConversationPanel({ className }: { className?: string }) {
  const [renderMode, setRenderMode] = useState<TextRenderMode>("karaoke");

  return (
    <Panel aria-label="Conversation" className={className}>
      <PanelHeader className="justify-between">
        <PanelTitle className="flex items-center gap-2">
          <MessagesSquareIcon className="size-4" />
          Conversation
        </PanelTitle>
        <Select
          items={RENDER_MODES}
          value={renderMode}
          onValueChange={(value) => {
            if (value) setRenderMode(value);
          }}
        >
          <SelectTrigger size="sm" aria-label="Text render mode">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {RENDER_MODES.map((mode) => (
              <SelectItem key={mode.value} value={mode.value}>
                {mode.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </PanelHeader>
      <Conversation textRenderMode={renderMode} className="min-h-0 flex-1" />
      <div className="shrink-0 p-3">
        <TextInput placeholder="Type message..." />
      </div>
    </Panel>
  );
}
