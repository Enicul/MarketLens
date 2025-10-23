import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  ChatMessage,
  ProgressEntry,
  ThinkingContentPayload,
  ThinkingStatusPayload
} from "../types";

export interface WebSocketHandlers {
  onToken?: (token: string) => void;
  onStatus?: (message: string) => void;
  onFinal?: (payload: { content: string; messages: ChatMessage[] }) => void;
  onProgress?: (entry: ProgressEntry) => void;
  onThinkingStatus?: (payload: ThinkingStatusPayload) => void;
  onThinkingContent?: (payload: ThinkingContentPayload) => void;
  onError?: (message: string) => void;
}

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
const WS_BASE = import.meta.env.VITE_WS_BASE ?? API_BASE.replace(/^http/, "ws");

export function useChatWebSocket(
  token: string | null,
  sessionId: string | null,
  handlers: WebSocketHandlers
) {
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!token || !sessionId) {
      setIsConnected(false);
      wsRef.current?.close();
      wsRef.current = null;
      return;
    }

    const url = `${WS_BASE}/ws/chat/${sessionId}?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      handlers.onStatus?.("WebSocket connection established");
    };

    ws.onclose = () => {
      setIsConnected(false);
      handlers.onStatus?.("WebSocket connection closed");
    };

    ws.onerror = () => {
      handlers.onError?.("WebSocket connection error");
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data ?? "{}") as Record<string, unknown>;
        switch (data.type) {
          case "token":
            handlers.onToken?.(String(data.token ?? ""));
            break;
          case "status":
            handlers.onStatus?.(String(data.message ?? ""));
            break;
          case "progress":
            handlers.onProgress?.({
              type: typeof data.type === "string" ? data.type : "progress",
              message: String(data.message ?? ""),
              timestamp: typeof data.timestamp === "string" ? data.timestamp : new Date().toISOString(),
              tool: typeof data.tool === "string" ? data.tool : null,
              stage: typeof data.stage === "string" ? data.stage : null,
              level: typeof data.level === "string" ? data.level : null
            });
            break;
          case "log":
            // Debug logs are streamed to CLI; UI ignores them intentionally.
            break;
          case "thinking_status":
            {
              const statusValue: ThinkingStatusPayload["status"] =
                data.status === "stop" || data.status === "error"
                  ? (data.status as ThinkingStatusPayload["status"])
                  : "start";
              handlers.onThinkingStatus?.({
                actor: String(data.actor ?? "manager"),
                label: typeof data.label === "string" ? data.label : undefined,
                status: statusValue,
                message: typeof data.message === "string" ? data.message : undefined
              });
            }
            break;
          case "thinking_content":
            handlers.onThinkingContent?.({
              actor: String(data.actor ?? "manager"),
              label: typeof data.label === "string" ? data.label : undefined,
              content: String(data.content ?? "")
            });
            break;
          case "final":
            handlers.onFinal?.({
              content: String(data.content ?? ""),
              messages: (data.messages as ChatMessage[]) ?? []
            });
            break;
          case "error":
            handlers.onError?.(String(data.message ?? "Unknown error"));
            break;
          default:
            break;
        }
      } catch (error) {
        handlers.onError?.(`Failed to parse message: ${(error as Error).message}`);
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
      setIsConnected(false);
    };
  }, [token, sessionId, handlers]);

  const sendMessage = useCallback(
    (content: string) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        throw new Error("WebSocket connection is not open");
      }
      wsRef.current.send(JSON.stringify({ type: "user_message", content }));
    },
    []
  );

  return useMemo(
    () => ({
      isConnected,
      sendMessage
    }),
    [isConnected, sendMessage]
  );
}
