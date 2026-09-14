"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { TRANSPORT_LABELS, type TransportType } from "../../config";

interface TransportSelectProps {
  transportType: TransportType;
  onTransportChange: (type: TransportType) => void;
  availableTransports: TransportType[];
}

export const TransportSelect = ({
  transportType,
  onTransportChange,
  availableTransports,
}: TransportSelectProps) => {
  const items = availableTransports.map((transport) => ({
    value: transport,
    label: TRANSPORT_LABELS[transport],
  }));

  return (
    <Select
      items={items}
      value={transportType}
      onValueChange={(value) => {
        if (value) onTransportChange(value);
      }}
    >
      <SelectTrigger
        aria-label="Transport"
        className="h-10 gap-3 px-3 font-mono text-xs"
      >
        <span className="font-sans text-muted-foreground">Transport</span>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {items.map((item) => (
          <SelectItem key={item.value} value={item.value} className="font-mono text-xs">
            {item.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
};
