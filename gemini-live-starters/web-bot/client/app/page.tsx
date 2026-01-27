'use client';

import { useState, useEffect } from 'react';
import { PipecatAppBase } from '@pipecat-ai/voice-ui-kit';

import { ClientApp } from './ClientApp';

import '@pipecat-ai/voice-ui-kit/styles.scoped';

export default function Home() {
  const [isMobile, setIsMobile] = useState(false);

  // Detect mobile devices
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(
        /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(
          navigator.userAgent
        )
      );
    };
    checkMobile();
  }, []);

  return (
    <div className="vkui-root">
      <div className="voice-ui-kit">
        <PipecatAppBase
          transportType="daily"
          connectParams={{
            endpoint: '/api/start',
          }}>
          {({ handleConnect, handleDisconnect }) => (
            <ClientApp
              connect={handleConnect}
              disconnect={handleDisconnect}
              isMobile={isMobile}
            />
          )}
        </PipecatAppBase>
      </div>
    </div>
  );
}
