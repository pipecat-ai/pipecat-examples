"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { BotTTSTextData, RTVIEvent } from "@pipecat-ai/client-js";
import { useRTVIClientEvent } from "@pipecat-ai/client-react";

import styles from "./StoryTranscript.module.css";

export default function StoryTranscript() {
  const [sentences, setSentences] = useState<string[]>([]);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);

    intervalRef.current = setInterval(() => {
      if (sentences.length > 2) {
        setSentences((s) => s.slice(1));
      }
    }, 2500);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [sentences]);

  // The text sent to TTS is the story as narrated, with the [break] markers
  // already stripped by the server
  useRTVIClientEvent(
    RTVIEvent.BotTtsText,
    useCallback((data: BotTTSTextData) => {
      const text = data.text.trim();
      if (text) setSentences((s) => [...s, text]);
    }, [])
  );

  return (
    <div className={styles.container}>
      {sentences.map((sentence, index) => (
        <p key={index} className={`${styles.transcript} ${styles.sentence}`}>
          <span>{sentence}</span>
        </p>
      ))}
    </div>
  );
}
