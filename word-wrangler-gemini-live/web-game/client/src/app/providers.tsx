'use client';

import { ConfigurationProvider } from '@/contexts/Configuration';
import { PipecatProvider } from '@/providers/PipecatProvider';
import { PipecatClientAudio } from '@pipecat-ai/client-react';
import { ReactNode } from 'react';

export function Providers({ children }: { children: ReactNode }) {
  return (
    <ConfigurationProvider>
      <PipecatProvider>
        <PipecatClientAudio />
        {children}
      </PipecatProvider>
    </ConfigurationProvider>
  );
}
