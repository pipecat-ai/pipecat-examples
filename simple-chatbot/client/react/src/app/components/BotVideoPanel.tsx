"use client";

import {
  PipecatClientVideo,
  usePipecatClientMediaTrack,
  usePipecatClientTransportState,
} from "@pipecat-ai/client-react";
import { VideoOffIcon } from "lucide-react";

import { cn } from "@/lib/utils";

import { Panel, PanelContent, PanelHeader, PanelTitle } from "./Panel";

export function BotVideoPanel({ className }: { className?: string }) {
  const transportState = usePipecatClientTransportState();
  const track = usePipecatClientMediaTrack("video", "bot");
  // Some transports expose a placeholder bot track before the session is
  // live, and the track hook keeps the previous session's ended track after
  // a disconnect, so require a live track and a connected transport.
  const hasVideo =
    !!track &&
    track.readyState === "live" &&
    (transportState === "connected" || transportState === "ready");

  return (
    <Panel aria-label="Bot video" className={className}>
      <PanelHeader>
        <PanelTitle>Bot video</PanelTitle>
      </PanelHeader>
      <PanelContent>
        <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-lg bg-muted/40">
          <PipecatClientVideo
            participant="bot"
            fit="contain"
            className={cn("h-full w-full", !hasVideo && "hidden")}
          />
          {!hasVideo && (
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <VideoOffIcon className="size-4" />
              No video
            </p>
          )}
        </div>
      </PanelContent>
    </Panel>
  );
}
