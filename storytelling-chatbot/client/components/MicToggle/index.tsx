import { usePipecatClientMicControl } from "@pipecat-ai/client-react";
import { IconMicrophone, IconMicrophoneOff } from "@tabler/icons-react";

export const MicToggle: React.FC = () => {
  const { enableMic, isMicEnabled } = usePipecatClientMicControl();

  const text = isMicEnabled ? (
    <IconMicrophoneOff size={21} />
  ) : (
    <IconMicrophone size={21} />
  );

  return (
    <button
      className="MicToggle UIButton"
      onClick={() => enableMic(!isMicEnabled)}
    >
      {text}
    </button>
  );
};

export default MicToggle;
