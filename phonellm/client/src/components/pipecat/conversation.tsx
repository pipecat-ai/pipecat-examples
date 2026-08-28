"use client"

import { usePipecatConversation } from "@pipecat-ai/client-react"
import { useEffect, useMemo, useRef, type ReactNode } from "react"

import {
  ConversationMessageItem,
  MessageRow,
} from "@/components/pipecat/conversation-message"
import { useSessionLog } from "@/hooks/use-session"
import { cn } from "@/lib/utils"

/** A session-log line: the transcript's own narration, not a message. */
function LogRow({ children }: { children: ReactNode }) {
  return (
    <MessageRow
      glyph="◆"
      glyphClassName="text-muted-foreground/70"
      className="text-muted-foreground/70"
    >
      {children}
    </MessageRow>
  )
}

interface Line {
  key: string
  /** Epoch ms, used only to interleave the two sources. */
  at: number
  node: ReactNode
}

export interface ConversationProps {
  className?: string
}

/**
 * The session printed as a terminal log: the conversation and the
 * session's own narration (see useSessionLog) interleaved in the order
 * they happened, one line per event. Follows the tail unless the reader
 * has scrolled up. Must be rendered inside a PipecatClientProvider.
 */
export function Conversation({ className }: ConversationProps) {
  const { messages } = usePipecatConversation()
  const log = useSessionLog()

  const lines = useMemo<Line[]>(() => {
    const fromMessages = messages.map((message, index) => ({
      key: `msg-${message.createdAt}-${index}`,
      at: new Date(message.createdAt).getTime(),
      node: <ConversationMessageItem message={message} />,
    }))
    const fromLog = log.map((entry) => ({
      key: entry.id,
      at: entry.at,
      node: <LogRow>{entry.text}</LogRow>,
    }))
    return [...fromMessages, ...fromLog].sort((a, b) => a.at - b.at)
  }, [messages, log])

  const scrollRef = useRef<HTMLDivElement>(null)
  // Follow the tail until the reader scrolls away from it, then leave them
  // where they are — the rule a terminal pager uses.
  const pinned = useRef(true)

  useEffect(() => {
    const element = scrollRef.current
    if (!element || !pinned.current) return
    element.scrollTop = element.scrollHeight
  }, [lines])

  return (
    <div
      ref={scrollRef}
      onScroll={() => {
        const element = scrollRef.current
        if (!element) return
        pinned.current =
          element.scrollHeight - element.scrollTop - element.clientHeight < 8
      }}
      // gap-2 sets the rows apart without touching the line height, so a
      // wrapped line still sits tight under the one it continues.
      className={cn(
        "flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto",
        className
      )}
    >
      {lines.length === 0 ? (
        <LogRow>no session · connect to start one</LogRow>
      ) : (
        lines.map((line) => (
          // shrink-0: flex children in a scrolling column would otherwise
          // be squeezed instead of overflowing into the scroll.
          <div key={line.key} className="shrink-0">
            {line.node}
          </div>
        ))
      )}
    </div>
  )
}
