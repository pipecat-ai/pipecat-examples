"use client"

import { usePipecatConversation } from "@pipecat-ai/client-react"
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  type ReactNode,
} from "react"

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
  const contentRef = useRef<HTMLDivElement>(null)
  // Follow the tail until the reader scrolls away from it, then leave them
  // where they are — the rule a terminal pager uses.
  const pinned = useRef(true)
  // Our own scrollTop writes fire a scroll event like any other; ignore that
  // one, or the growth we just chased would read as the reader scrolling up.
  const selfScrolling = useRef(false)

  const stickToBottom = useCallback(() => {
    const element = scrollRef.current
    if (!element || !pinned.current) return
    if (element.scrollTop === element.scrollHeight - element.clientHeight) return
    selfScrolling.current = true
    element.scrollTop = element.scrollHeight
  }, [])

  useLayoutEffect(stickToBottom, [lines, stickToBottom])

  // A new line is not the only thing that lengthens the log: a streaming
  // message grows in place, and a wrap reflows on resize. Watch the content
  // box so the tail is chased whenever it moves, not only when lines change.
  useEffect(() => {
    const content = contentRef.current
    if (!content || typeof ResizeObserver === "undefined") return
    const observer = new ResizeObserver(() => stickToBottom())
    observer.observe(content)
    return () => observer.disconnect()
  }, [stickToBottom])

  return (
    <div
      ref={scrollRef}
      onScroll={() => {
        const element = scrollRef.current
        if (!element) return
        if (selfScrolling.current) {
          selfScrolling.current = false
          return
        }
        // Generous slack: sub-pixel line heights and a mid-growth scroll
        // event both leave the tail a few pixels off exact.
        pinned.current =
          element.scrollHeight - element.scrollTop - element.clientHeight < 24
      }}
      // gap-2 sets the rows apart without touching the line height, so a
      // wrapped line still sits tight under the one it continues.
      className={cn(
        "flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto",
        className
      )}
    >
      {/* shrink-0: a flex child in a scrolling column is squeezed to fit
          instead of overflowing into the scroll. */}
      <div ref={contentRef} className="flex shrink-0 flex-col gap-2">
        {lines.length === 0 ? (
          <LogRow>no session · connect to start one</LogRow>
        ) : (
          lines.map((line) => (
            <div key={line.key} className="shrink-0">
              {line.node}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
