import { usePipecatClientMediaDevices } from "@pipecat-ai/client-react";

export function MicrophoneSelector() {
  const { availableMics, selectedMic, updateMic } =
    usePipecatClientMediaDevices();

  if (!availableMics || availableMics.length === 0) {
    return null;
  }

  return (
    <div className="microphone-selector">
      <label htmlFor="mic-select">Microphone: </label>
      <select
        id="mic-select"
        onChange={(ev) => updateMic(ev.target.value)}
        value={selectedMic?.deviceId || ""}
      >
        {availableMics.map((mic) => (
          <option key={mic.deviceId} value={mic.deviceId}>
            {mic.label || `Microphone ${mic.deviceId.substring(0, 8)}`}
          </option>
        ))}
      </select>
    </div>
  );
}
