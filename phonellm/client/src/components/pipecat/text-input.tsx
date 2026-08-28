"use client"

import {
  useConversationContext,
  usePipecatClient,
  usePipecatClientTransportState,
} from "@pipecat-ai/client-react"
import { useCallback, useLayoutEffect, useRef, useState } from "react"

import { cn } from "@/lib/utils"

const CONNECTED_STATES = ["connected", "ready"]

export interface TextInputProps {
  /** Placeholder shown while the field is empty. */
  placeholder?: string
  className?: string
}

/**
 * The prompt line: type a turn instead of speaking it. The field renders
 * its own text and a blinking block caret trailing it — the native caret
 * is hidden and the input's text is transparent, so what you read is the
 * line underneath, scrolled left once the text outruns the field. Sends on
 * Enter, injects the message into the conversation so it lands in the
 * transcript immediately, and clears only on a successful send. Must be
 * rendered inside a PipecatClientProvider.
 */
export function TextInput({
  placeholder = "type or talk",
  className,
}: TextInputProps) {
  const client = usePipecatClient()
  const transportState = usePipecatClientTransportState()
  const isConnected = CONNECTED_STATES.includes(transportState)
  const { injectMessage } = useConversationContext()

  const [value, setValue] = useState("")
  const [isSending, setIsSending] = useState(false)
  const lineRef = useRef<HTMLDivElement>(null)
  const [shift, setShift] = useState(0)

  // Keep the caret in view: once the line is wider than the field, slide it
  // left by the overflow, the way a terminal scrolls its input.
  useLayoutEffect(() => {
    const line = lineRef.current
    const field = line?.parentElement
    if (!line || !field) return
    const overflow = line.scrollWidth - field.clientWidth
    setShift(overflow > 0 ? -overflow : 0)
  }, [value])

  const send = useCallback(async () => {
    const text = value.trim()
    if (!text || !isConnected || !client || isSending) return
    setIsSending(true)
    try {
      // Inject first, so the line appears in the transcript straight away
      // and the bot's reply lands under it.
      injectMessage({
        role: "user",
        parts: [{ text, final: true, createdAt: new Date().toISOString() }],
      })
      await client.sendText(text)
      // Clear only on success, so a failed send keeps the draft.
      setValue("")
    } catch (error) {
      console.error("TextInput: send failed", error)
    } finally {
      setIsSending(false)
    }
  }, [value, isConnected, client, isSending, injectMessage])

  return (
    <div
      data-slot="text-input"
      className={cn("flex min-w-0 items-center gap-2", className)}
    >
      <span className="shrink-0 select-none text-muted-foreground">❯</span>
      <label className="relative min-w-0 flex-1 overflow-hidden">
        <div
          ref={lineRef}
          aria-hidden
          style={{ transform: `translateX(${shift}px)` }}
          className="pointer-events-none flex w-max items-center whitespace-pre"
        >
          <span>{value}</span>
          <span className="inline-block h-[1.15em] w-[0.6em] animate-terminal-caret bg-foreground" />
          {!value && <span className="ml-1 text-muted-foreground">{placeholder}</span>}
        </div>
        <input
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              !event.shiftKey &&
              !event.nativeEvent.isComposing
            ) {
              event.preventDefault()
              void send()
            }
          }}
          disabled={!isConnected || isSending}
          aria-label="Message"
          spellCheck={false}
          autoComplete="off"
          className="absolute inset-0 w-full bg-transparent text-transparent caret-transparent outline-none"
        />
      </label>
    </div>
  )
}
