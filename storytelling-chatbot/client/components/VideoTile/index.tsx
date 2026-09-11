import React from "react";
import { PipecatClientVideo } from "@pipecat-ai/client-react";

import StoryTranscript from "@/components/StoryTranscript";

import styles from "./VideoTile.module.css";

interface Props {
  inactive: boolean;
}

// The bot's video track carries the current story illustration
const VideoTile = ({ inactive }: Props) => {
  return (
    <div className={`${styles.container} ${inactive ? styles.inactive : ""} `}>
      <StoryTranscript />

      <div className={styles.videoTile}>
        <PipecatClientVideo
          participant="bot"
          fit="cover"
          className="aspect-square w-full h-full"
        />
      </div>
    </div>
  );
};

export default VideoTile;
