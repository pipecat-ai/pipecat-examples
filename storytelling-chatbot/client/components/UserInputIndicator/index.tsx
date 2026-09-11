import React, { useCallback, useEffect, useRef, useState } from "react";
import { RTVIEvent, TranscriptData } from "@pipecat-ai/client-js";
import { useRTVIClientEvent } from "@pipecat-ai/client-react";
import { IconMicrophone } from "@tabler/icons-react";

import { TypewriterEffect } from "../ui/typewriter";
import AudioIndicator from "../AudioIndicator";

import styles from "./UserInputIndicator.module.css";

interface Props {
  active: boolean;
}

export default function UserInputIndicator({ active }: Props) {
  const [transcription, setTranscription] = useState<string[]>([]);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const resetTimeout = () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    timeoutRef.current = setTimeout(() => {
      setTranscription([]);
    }, 5000);
  };

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  useRTVIClientEvent(
    RTVIEvent.UserTranscript,
    useCallback((data: TranscriptData) => {
      if (data.final) {
        setTranscription((t) => [...t, ...data.text.split(" ")]);
        resetTimeout();
      }
    }, [])
  );

  useEffect(() => {
    if (active) return;
    const t = setTimeout(() => setTranscription([]), 4000);
    return () => clearTimeout(t);
  }, [active]);

  return (
    <div className={`${styles.panel} ${active ? styles.active : ""}`}>
      <div className="relative z-20 flex flex-col">
        <div
          className={`${styles.micIcon} ${active ? styles.micIconActive : ""}`}
        >
          <IconMicrophone size={42} />
          {active && <AudioIndicator />}
        </div>
        <footer className={styles.transcript}>
          <TypewriterEffect words={transcription} />
        </footer>
      </div>
    </div>
  );
}
