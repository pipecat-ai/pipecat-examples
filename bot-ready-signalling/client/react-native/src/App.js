import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Button, SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';
import { PipecatClient } from '@pipecat-ai/client-js';
import { RNDailyTransport } from '@pipecat-ai/react-native-daily-transport';
import { API_BASE_URL } from '@env';

/**
 * CallScreen wraps Pipecat's React Native client.
 *
 * The bot-ready handshake is handled by RTVI: the SDK signals client-ready
 * automatically once the transport reaches the `ready` state, the bot replies
 * with `bot-ready`, and only then does the bot push its first TTS frame. No
 * manual sendAppMessage / "playable" plumbing is needed.
 */
const CallScreen = () => {
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [isConnected, setIsConnected] = useState(false);
  const [logs, setLogs] = useState([]);
  const clientRef = useRef(null);

  const log = useCallback((message) => {
    const entry = `${new Date().toISOString()} - ${message}`;
    setLogs((prevLogs) => [...prevLogs, entry]);
    console.log(message);
  }, []);

  const connect = useCallback(async () => {
    if (clientRef.current) return;

    const inCallStates = new Set([
      'authenticating',
      'authenticated',
      'connecting',
      'connected',
      'ready',
    ]);

    const client = new PipecatClient({
      transport: new RNDailyTransport(),
      enableMic: true,
      enableCam: false,
      callbacks: {
        onTransportStateChanged: (state) => {
          setConnectionStatus(state);
          setIsConnected(inCallStates.has(state));
          log(`State: ${state}`);
        },
        onBotReady: () => {
          log('Bot ready: greeting will play next.');
        },
        onDisconnected: () => {
          log('Disconnected from bot.');
          setIsConnected(false);
        },
        onError: (error) => {
          log(`Error: ${error?.data?.message || error?.message || error}`);
        },
      },
    });

    clientRef.current = client;

    try {
      log('Connecting to bot...');
      await client.startBotAndConnect({
        endpoint: `${API_BASE_URL}/connect`,
      });
      log('Connection complete.');
    } catch (error) {
      log(`Error connecting: ${error?.message || error}`);
      try {
        await client.disconnect();
      } catch (_) {
        // ignore cleanup errors after a failed connect
      }
      clientRef.current = null;
    }
  }, [log]);

  const disconnect = useCallback(async () => {
    const client = clientRef.current;
    if (!client) return;
    try {
      await client.disconnect();
    } catch (error) {
      log(`Error disconnecting: ${error?.message || error}`);
    } finally {
      clientRef.current = null;
    }
  }, [log]);

  useEffect(() => {
    return () => {
      if (clientRef.current) {
        clientRef.current.removeAllListeners();
        clientRef.current.disconnect().catch(() => {});
        clientRef.current = null;
      }
    };
  }, []);

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        <View style={styles.statusBar}>
          <Text>
            Status: <Text style={styles.status}>{connectionStatus}</Text>
          </Text>
          <View style={styles.controls}>
            <Button
              title={isConnected ? 'Disconnect' : 'Connect'}
              onPress={isConnected ? disconnect : connect}
            />
          </View>
        </View>

        <View style={styles.debugPanel}>
          <Text style={styles.debugTitle}>Debug Info</Text>
          <ScrollView style={styles.debugLog}>
            {logs.map((logEntry, index) => (
              <Text key={index} style={styles.logText}>
                {logEntry}
              </Text>
            ))}
          </ScrollView>
        </View>
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: '#f0f0f0', padding: 20 },
  container: { flex: 1, margin: 20 },
  statusBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 10,
    backgroundColor: '#fff',
    borderRadius: 8,
    marginBottom: 20,
  },
  status: { fontWeight: 'bold' },
  controls: { flexDirection: 'row', gap: 10 },
  debugPanel: { height: '80%', backgroundColor: '#fff', borderRadius: 8, padding: 20 },
  debugTitle: { fontSize: 16, fontWeight: 'bold' },
  debugLog: {
    height: '100%',
    overflow: 'scroll',
    backgroundColor: '#f8f8f8',
    padding: 10,
    borderRadius: 4,
  },
  logText: { fontFamily: 'monospace', fontSize: 12, lineHeight: 16 },
});

export default CallScreen;
