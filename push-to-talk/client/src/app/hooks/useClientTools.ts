import { usePipecatClient } from '@pipecat-ai/client-react';
import { useEffect } from 'react';

/**
 * Registers tools that the bot's LLM calls, but that run here in the browser.
 *
 * The server advertises `get_browser_info` to the LLM and then hands the call
 * straight back to us (see `run_on_client` in `server/bot.py`). The LLM waits
 * until the value we return below reaches its context.
 */
export function useClientTools() {
  const client = usePipecatClient();

  useEffect(() => {
    if (!client) return;

    // Data only the browser has. Always return something truthy: an empty
    // result stops the bot from speaking a follow-up.
    client.registerFunctionCallHandler('get_browser_info', async () => ({
      userAgent: navigator.userAgent,
      language: navigator.language,
      screen: `${window.screen.width}x${window.screen.height}`,
      timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    }));

    return () => {
      client.unregisterFunctionCallHandler('get_browser_info');
    };
  }, [client]);
}
