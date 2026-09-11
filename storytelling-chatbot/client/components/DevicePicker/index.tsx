"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { DeviceError, RTVIEvent } from "@pipecat-ai/client-js";
import {
  usePipecatClient,
  usePipecatClientMediaDevices,
  useRTVIClientEvent,
} from "@pipecat-ai/client-react";
import { IconMicrophone, IconDeviceSpeaker } from "@tabler/icons-react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { AudioIndicatorBar } from "../AudioIndicator";

export default function DevicePicker() {
  const client = usePipecatClient();
  const {
    availableMics,
    availableSpeakers,
    selectedMic,
    selectedSpeaker,
    updateMic,
    updateSpeaker,
  } = usePipecatClientMediaDevices();
  const [micError, setMicError] = useState<DeviceError | null>(null);
  const initialized = useRef(false);

  // Ask for microphone access so we can list the devices and show levels
  useEffect(() => {
    if (!client || initialized.current) return;
    initialized.current = true;
    client.initDevices().catch((e) => console.error("initDevices failed", e));
  }, [client]);

  useRTVIClientEvent(
    RTVIEvent.DeviceError,
    useCallback((error: DeviceError) => {
      if (error.devices.includes("mic")) setMicError(error);
    }, [])
  );

  return (
    <div className="flex flex-col gap-5">
      <section>
        <label className="uppercase text-sm tracking-wider text-gray-500">
          Microphone:
        </label>
        <div className="flex flex-row gap-4 items-center mt-2">
          <IconMicrophone size={24} />
          <div className="flex flex-col flex-1 gap-3">
            <Select
              value={selectedMic?.deviceId}
              onValueChange={(id) => updateMic(id)}
            >
              <SelectTrigger className="">
                <SelectValue
                  placeholder={micError ? "No microphone access" : "Microphone"}
                />
              </SelectTrigger>
              <SelectContent>
                {availableMics.map((m) => (
                  <SelectItem key={m.deviceId} value={m.deviceId}>
                    {m.label || "Microphone"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <AudioIndicatorBar />
          </div>
        </div>
      </section>

      <section>
        <label className="uppercase text-sm tracking-wider text-gray-500">
          Speakers:
        </label>
        <div className="flex flex-row gap-4 items-center mt-2">
          <IconDeviceSpeaker size={24} />
          <Select
            value={selectedSpeaker?.deviceId}
            onValueChange={(id) => updateSpeaker(id)}
          >
            <SelectTrigger className="">
              <SelectValue placeholder="Speakers" />
            </SelectTrigger>
            <SelectContent>
              {availableSpeakers.map((s) => (
                <SelectItem key={s.deviceId} value={s.deviceId}>
                  {s.label || "Speakers"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </section>
      {micError && (
        <div className="error">
          {micError.type === "permissions" ? (
            <p className="text-red-500">
              Please check your browser and system permissions. Make sure that
              this app is allowed to access your microphone.
            </p>
          ) : micError.type === "in-use" ? (
            <p className="text-red-500">
              Your microphone is being used by another app. Please close any
              other apps using your microphone and restart this app.
            </p>
          ) : micError.type === "not-found" ? (
            <p className="text-red-500">
              No microphone seems to be connected. Please connect a microphone.
            </p>
          ) : micError.type === "undefined-mediadevices" ? (
            <p className="text-red-500">
              This app is not supported on your device. Please update your
              software or use a different device.
            </p>
          ) : (
            <p className="text-red-500">
              There seems to be an issue accessing your microphone. Try
              restarting the app or consult a system administrator.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
