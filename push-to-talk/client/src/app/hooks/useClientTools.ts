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

    // Data only the browser has. Always return a value, and never let the
    // handler throw. Throwing, or returning null/undefined, sends nothing
    // back, and the bot then waits on this call for the rest of the session.
    // Telling the LLM it failed is always better than going silent.
    client.registerFunctionCallHandler('get_browser_info', async () => {
      try {
        return {
          userAgent: navigator.userAgent,
          language: navigator.language,
          screen: `${window.screen.width}x${window.screen.height}`,
          timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        };
      } catch (error) {
        return { error: `Could not read browser info: ${error}` };
      }
    });

    return () => {
      client.unregisterFunctionCallHandler('get_browser_info');
    };
  }, [client]);
}
