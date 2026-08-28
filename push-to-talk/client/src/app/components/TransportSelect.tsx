import {
  Select,
  SelectContent,
  SelectGuide,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@pipecat-ai/voice-ui-kit';

import { TRANSPORT_LABELS, type TransportType } from '../../config';

interface TransportSelectProps {
  transportType: TransportType;
  onTransportChange: (type: TransportType) => void;
  availableTransports: TransportType[];
}

// This page keeps a white background in either color scheme, so the control
// uses fixed colors instead of theme tokens, which would flip in dark mode and
// leave light text on a light page.
export const TransportSelect = ({
  transportType,
  onTransportChange,
  availableTransports,
}: TransportSelectProps) => {
  return (
    <Select value={transportType} onValueChange={onTransportChange}>
      <SelectTrigger
        className="bg-white text-zinc-900 border-zinc-200 hover:bg-zinc-50 shadow-long/[0.08] [&_svg]:text-zinc-400">
        <SelectGuide className="text-zinc-500">Transport</SelectGuide>
        <SelectValue placeholder="Select transport" />
      </SelectTrigger>
      {/* Anchored to the bottom of the screen, so open upwards. */}
      <SelectContent
        side="top"
        sideOffset={8}
        className="bg-white text-zinc-900 border-zinc-200">
        {availableTransports.map((transport) => (
          <SelectItem
            key={transport}
            value={transport}
            className="focus:bg-zinc-100 focus:text-zinc-900 [&_svg]:text-zinc-500">
            {TRANSPORT_LABELS[transport]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
};
