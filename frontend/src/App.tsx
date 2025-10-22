import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  activateSession,
  createSession,
  deleteSession,
  fetchAnalysisConfig,
  fetchSessionProgress,
  fetchSessionMessages,
  listSessions,
  login,
  logout,
  renameSession,
  resetAnalysisConfig,
  updateAnalysisConfig
} from "./api";
import { useChatWebSocket, type WebSocketHandlers } from "./hooks/useChatWebSocket";
import type {
  AnalysisConfig,
  AuthInfo,
  ChatMessage,
  ProgressEntry,
  SessionMeta
} from "./types";

const DEFAULT_CONFIG: AnalysisConfig = {
  news: true,
  fundamentals: true,
  market: true,
  sentiment: true
};

type ThinkingLogEntry = {
  actor: string;
  label: string;
  content: string;
  timestamp: string;
};

const TOOL_DISPLAY_LABELS: Record<string, string> = {
  call_analyst: "Analyst 子代理",
  call_researcher: "Researcher 子代理",
  call_trader: "Trader 子代理",
  call_risk_manager: "风险管理模块",
  read_file: "文件读取工具",
  write_file: "文件写入工具"
};

const formatTimestamp = (iso: string) => {
  try {
    const date = new Date(iso);
    return date.toLocaleTimeString("zh-CN", { hour12: false });
  } catch {
    return iso;
  }
};

function LoginView({
  onLogin,
  loading,
  error
}: {
  onLogin: (payload: { email?: string; password?: string; guest?: boolean }) => Promise<void>;
  loading: boolean;
  error: string | null;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    await onLogin({ email, password });
  };

  const handleGuest = async () => {
    await onLogin({ guest: true });
  };

  return (
    <div className="login-shell">
      <div className="login-card">
        <h1>Market Lens AI</h1>
        <p className="login-subtitle">FastAPI + WebSocket 全新实时体验</p>
        {error ? <div className="error-box">{error}</div> : null}
        <form className="login-form" onSubmit={handleSubmit}>
          <label>
            邮箱
            <input
              type="email"
              placeholder="name@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label>
            密码
            <input
              type="password"
              placeholder="请输入密码"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          <button type="submit" disabled={loading}>
            {loading ? "登录中…" : "登录"}
          </button>
        </form>
        <button className="ghost-button" onClick={handleGuest} disabled={loading}>
          游客体验
        </button>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const className = useMemo(() => {
    switch (message.role) {
      case "user":
        return "bubble bubble-user";
      case "assistant":
        return "bubble bubble-assistant";
      case "tool":
        return "bubble bubble-tool";
      default:
        return "bubble bubble-system";
    }
  }, [message.role]);

  if (message.role === "tool" || message.role === "system") {
    return (
      <div className={className}>
        <pre>{message.content}</pre>
      </div>
    );
  }

  const lines = message.content.split(/\n/);
  return (
    <div className={className}>
      {lines.map((line, index) => (
        <span key={index}>
          {line}
          {index < lines.length - 1 ? <br /> : null}
        </span>
      ))}
    </div>
  );
}

interface SidebarProps {
  auth: AuthInfo;
  sessions: SessionMeta[];
  analysisConfig: AnalysisConfig;
  onSelectSession: (sessionId: string) => Promise<void>;
  onCreateSession: () => Promise<void>;
  onRenameSession: (sessionId: string, name: string) => Promise<void>;
  onDeleteSession: (sessionId: string) => Promise<void>;
  onToggleConfig: (key: keyof AnalysisConfig, value: boolean) => Promise<void>;
  onResetConfig: () => Promise<void>;
  onLogout: () => Promise<void>;
}

function Sidebar({
  auth,
  sessions,
  analysisConfig,
  onSelectSession,
  onCreateSession,
  onRenameSession,
  onDeleteSession,
  onToggleConfig,
  onResetConfig,
  onLogout
}: SidebarProps) {
  const [renameTarget, setRenameTarget] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const startRename = (session: SessionMeta) => {
    setRenameTarget(session.id);
    setRenameValue(session.name);
  };

  const submitRename = async (event: React.FormEvent, sessionId: string) => {
    event.preventDefault();
    if (!renameValue.trim()) return;
    await onRenameSession(sessionId, renameValue.trim());
    setRenameTarget(null);
    setRenameValue("");
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-top">
        <h2>👤 {auth.displayName}</h2>
        <p className="role-tag">{auth.role === "guest" ? "游客模式" : "正式用户"}</p>
        <button className="ghost-button" onClick={onLogout}>
          退出登录
        </button>
      </div>

      <div className="sidebar-section">
        <div className="section-header">
          <h3>对话会话</h3>
          <button onClick={onCreateSession}>新建</button>
        </div>
        <div className="session-list">
          {sessions.map((session) => (
            <div
              key={session.id}
              className={`session-item ${session.isActive ? "active" : ""}`}
            >
              {renameTarget === session.id ? (
                <form onSubmit={(event) => submitRename(event, session.id)} className="rename-form">
                  <input
                    value={renameValue}
                    onChange={(event) => setRenameValue(event.target.value)}
                    autoFocus
                    onBlur={() => setRenameTarget(null)}
                  />
                </form>
              ) : (
                <button className="session-button" onClick={() => onSelectSession(session.id)}>
                  <span className="session-name">{session.name}</span>
                  <span className="session-time">{formatTimestamp(session.createdAt)}</span>
                </button>
              )}
              <div className="session-actions">
                <button onClick={() => startRename(session)}>重命名</button>
                <button onClick={() => onDeleteSession(session.id)}>删除</button>
              </div>
            </div>
          ))}
          {sessions.length === 0 ? <p className="empty-hint">暂无会话</p> : null}
        </div>
      </div>

      <div className="sidebar-section">
        <div className="section-header">
          <h3>分析配置</h3>
          <button onClick={onResetConfig}>重置</button>
        </div>
        <div className="toggle-list">
          {(Object.keys(analysisConfig) as (keyof AnalysisConfig)[]).map((key) => (
            <label key={key} className="toggle-item">
              <input
                type="checkbox"
                checked={analysisConfig[key]}
                onChange={(event) => onToggleConfig(key, event.target.checked)}
              />
              <span>{key}</span>
            </label>
          ))}
        </div>
      </div>
    </aside>
  );
}

interface ChatComposerProps {
  disabled: boolean;
  onSend: (text: string) => Promise<void>;
}

function ChatComposer({ disabled, onSend }: ChatComposerProps) {
  const [value, setValue] = useState("");

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) return;
    await onSend(trimmed);
    setValue("");
  };

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <textarea
        placeholder="请输入问题或任务…"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        disabled={disabled}
        rows={3}
      />
      <button type="submit" disabled={disabled || !value.trim()}>
        发送
      </button>
    </form>
  );
}

interface DashboardProps {
  auth: AuthInfo;
  sessions: SessionMeta[];
  analysisConfig: AnalysisConfig;
  messages: ChatMessage[];
  streamingReply: string;
  progress: ProgressEntry[];
  thinkingLog: ThinkingLogEntry[];
  statusMessage: string | null;
  errorMessage: string | null;
  showProgressPanel: boolean;
  showThinkingPanel: boolean;
  onToggleProgressPanel: () => void;
  onToggleThinkingPanel: () => void;
  onSelectSession: (sessionId: string) => Promise<void>;
  onCreateSession: () => Promise<void>;
  onRenameSession: (sessionId: string, name: string) => Promise<void>;
  onDeleteSession: (sessionId: string) => Promise<void>;
  onToggleConfig: (key: keyof AnalysisConfig, value: boolean) => Promise<void>;
  onResetConfig: () => Promise<void>;
  onLogout: () => Promise<void>;
  onSendMessage: (text: string) => Promise<void>;
  streaming: boolean;
  connected: boolean;
}

function Dashboard({
  auth,
  sessions,
  analysisConfig,
  messages,
  streamingReply,
  progress,
  thinkingLog,
  statusMessage,
  errorMessage,
  showProgressPanel,
  showThinkingPanel,
  onToggleProgressPanel,
  onToggleThinkingPanel,
  onSelectSession,
  onCreateSession,
  onRenameSession,
  onDeleteSession,
  onToggleConfig,
  onResetConfig,
  onLogout,
  onSendMessage,
  streaming,
  connected
}: DashboardProps) {
  const progressArrow = showProgressPanel ? "▾" : "▸";
  const thinkingArrow = showThinkingPanel ? "▾" : "▸";
  const progressEndRef = useRef<HTMLDivElement | null>(null);
  const thinkingEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (showProgressPanel) {
      progressEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [progress, showProgressPanel]);

  useEffect(() => {
    if (showThinkingPanel) {
      thinkingEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [thinkingLog, showThinkingPanel]);

  return (
    <div className="dashboard">
      <Sidebar
        auth={auth}
        sessions={sessions}
        analysisConfig={analysisConfig}
        onSelectSession={onSelectSession}
        onCreateSession={onCreateSession}
        onRenameSession={onRenameSession}
        onDeleteSession={onDeleteSession}
        onToggleConfig={onToggleConfig}
        onResetConfig={onResetConfig}
        onLogout={onLogout}
      />
      <main className="main">
        <header className="main-header">
          <div>
            <h1>Market Lens Realtime Console</h1>
            <p>FastAPI + WebSocket + React · 全新的实时流式体验</p>
          </div>
          <div className="status-indicators">
            <span className={`pill ${connected ? "ok" : "warn"}`}>
              {connected ? "WebSocket 已连接" : "等待连接"}
            </span>
            <span className={`pill ${streaming ? "info" : ""}`}>
              {streaming ? "生成中…" : "待命"}
            </span>
          </div>
        </header>
        <div className="workspace">
          <section className="chat-window">
            <div className="messages">
              {messages.map((message, index) => (
                <MessageBubble key={`${index}-${message.role}`} message={message} />
              ))}
              {streamingReply ? (
                <div className="bubble bubble-assistant streaming">{streamingReply}▌</div>
              ) : null}
            </div>
            <div className="status-bar">
              {statusMessage ? <span>{statusMessage}</span> : null}
              {errorMessage ? <span className="error-text">{errorMessage}</span> : null}
            </div>
            <ChatComposer disabled={streaming} onSend={onSendMessage} />
          </section>

          <div className="side-panels">
            <aside className={`progress-panel model-thinking-panel ${showThinkingPanel ? "open" : "closed"}`}>
              <button className="progress-toggle" type="button" onClick={onToggleThinkingPanel}>
                <span className="progress-icon">{thinkingArrow}</span>
                <span>Model Thinking</span>
              </button>
              {showThinkingPanel ? (
                <div className="progress-list thinking-list">
                  {thinkingLog.length ? (
                    thinkingLog.map((entry, index) => (
                      <div
                        key={`${entry.timestamp}-${index}`}
                        className="progress-item thinking-item"
                        title={entry.label}
                      >
                        <span className="progress-time">{formatTimestamp(entry.timestamp)}</span>
                        <span className="progress-message">
                          {entry.label ? `[${entry.label}] ` : ""}
                          {entry.content}
                        </span>
                      </div>
                    ))
                  ) : (
                    <p className="empty-hint">等待模型动作…</p>
                  )}
                  <div ref={thinkingEndRef} />
                </div>
              ) : null}
            </aside>

            <aside className={`progress-panel ${showProgressPanel ? "open" : "closed"}`}>
              <button className="progress-toggle" type="button" onClick={onToggleProgressPanel}>
                <span className="progress-icon">{progressArrow}</span>
                <span>实时进度</span>
              </button>
              {showProgressPanel ? (
                <div className="progress-list">
                  {progress.length ? (
                    progress.map((item, index) => {
                      const stage = item.stage || item.level?.toLowerCase() || "log";
                      const severity = stage === "error" || item.level === "ERROR" ? "error" : stage === "end" ? "done" : stage === "start" ? "start" : "log";
                      return (
                        <div
                          key={`${item.timestamp}-${index}`}
                          className={`progress-item progress-${severity}`}
                          title={item.level ? `${item.level}` : undefined}
                        >
                          <span className="progress-time">{formatTimestamp(item.timestamp)}</span>
                          <span className="progress-message">{item.message}</span>
                        </div>
                      );
                    })
                  ) : (
                    <p className="empty-hint">等待任务执行…</p>
                  )}
                  <div ref={progressEndRef} />
                </div>
              ) : null}
            </aside>
          </div>
        </div>
      </main>
    </div>
  );
}

function App() {
  const [auth, setAuth] = useState<AuthInfo | null>(null);
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [analysisConfig, setAnalysisConfig] = useState<AnalysisConfig>(DEFAULT_CONFIG);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [progress, setProgress] = useState<ProgressEntry[]>([]);
  const [thinkingLog, setThinkingLog] = useState<ThinkingLogEntry[]>([]);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [streamingReply, setStreamingReply] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [loginLoading, setLoginLoading] = useState(false);
  const [progressVisible, setProgressVisible] = useState(true);
  const [thinkingVisible, setThinkingVisible] = useState(true);

  const deriveThinkingLabel = useCallback((tool?: string | null) => {
    if (!tool || tool === "log" || tool === "manager") {
      return "Manager 主代理";
    }
    return TOOL_DISPLAY_LABELS[tool] ?? tool;
  }, []);

  const refreshSessions = useCallback(
    async (token: string, fallbackSessionId?: string | null) => {
      const list = await listSessions(token);
      setSessions(list);
      const active =
        list.find((session) => session.isActive)?.id ??
        fallbackSessionId ??
        list[list.length - 1]?.id ??
        null;
      setActiveSessionId(active ?? null);
      return active ?? null;
    },
    []
  );

  useEffect(() => {
    if (!auth?.token) return;
    (async () => {
      try {
        const config = await fetchAnalysisConfig(auth.token);
        setAnalysisConfig(config);
        const active = await refreshSessions(auth.token, auth.activeSessionId);
        if (active) {
          const [history, progressHistory] = await Promise.all([
            fetchSessionMessages(auth.token, active),
            fetchSessionProgress(auth.token, active)
          ]);
          setMessages(history);
          const ordered = [...progressHistory]
            .sort(
              (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
            )
            .slice(-200);
          setProgress(ordered);
          const thinkingHistory = ordered
            .filter((item) => (item.stage ?? "").toLowerCase() === "thinking" && item.message)
            .map<ThinkingLogEntry>((item) => ({
              actor: item.tool ?? "manager",
              label: deriveThinkingLabel(item.tool),
              content: item.message,
              timestamp: item.timestamp ?? new Date().toISOString()
            }));
          setThinkingLog(thinkingHistory);
        } else {
          setMessages([]);
          setProgress([]);
          setThinkingLog([]);
        }
      } catch (error) {
        setErrorMessage((error as Error).message);
      }
    })();
  }, [auth, refreshSessions, deriveThinkingLabel]);

  useEffect(() => {
    if (!auth?.token || !activeSessionId) {
      setMessages([]);
      setProgress([]);
      setThinkingLog([]);
      return;
    }
    (async () => {
      try {
        const [history, progressHistory] = await Promise.all([
          fetchSessionMessages(auth.token, activeSessionId),
          fetchSessionProgress(auth.token, activeSessionId)
        ]);
        setMessages(history);
        const ordered = [...progressHistory]
          .sort(
            (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
          )
          .slice(-200);
        setProgress(ordered);
        const thinkingHistory = ordered
          .filter((item) => (item.stage ?? "").toLowerCase() === "thinking" && item.message)
          .map<ThinkingLogEntry>((item) => ({
            actor: item.tool ?? "manager",
            label: deriveThinkingLabel(item.tool),
            content: item.message,
            timestamp: item.timestamp ?? new Date().toISOString()
          }));
        setThinkingLog(thinkingHistory);
      } catch (error) {
        setErrorMessage((error as Error).message);
      }
    })();
  }, [auth?.token, activeSessionId, deriveThinkingLabel]);

  const wsHandlers = useMemo<WebSocketHandlers>(
    () => ({
      onToken: (token: string) => {
        setStreamingReply((prev) => prev + token);
        setIsStreaming(true);
      },
      onStatus: (message: string) => setStatusMessage(message || null),
      onProgress: (entry: ProgressEntry) => {
        if (!entry.message) return;
        setProgress((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.message === entry.message && last.timestamp === entry.timestamp) {
            return prev;
          }
          return [...prev.slice(-199), entry];
        });
        if ((entry.stage ?? "").toLowerCase() === "thinking") {
          const thinkingEntry: ThinkingLogEntry = {
            actor: entry.tool ?? "manager",
            label: deriveThinkingLabel(entry.tool),
            content: entry.message,
            timestamp: entry.timestamp ?? new Date().toISOString()
          };
          setThinkingLog((prev) => {
            const last = prev[prev.length - 1];
            if (
              last &&
              last.content === thinkingEntry.content &&
              last.actor === thinkingEntry.actor
            ) {
              return prev;
            }
            return [...prev.slice(-199), thinkingEntry];
          });
        }
      },
      onThinkingStatus: ({ actor, label, status, message }) => {
        if (status === "error" && message) {
          const timestamp = new Date().toISOString();
          setThinkingLog((prev) => [
            ...prev.slice(-199),
            {
              actor,
              label: label ?? deriveThinkingLabel(actor),
              content: message,
              timestamp
            }
          ]);
        }
      },
      onThinkingContent: ({ actor, label, content }) => {
        const text = content.trim();
        if (!text) return;
        const timestamp = new Date().toISOString();
        setThinkingLog((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.content === text && last.actor === actor) {
            return prev;
          }
          return [
            ...prev.slice(-199),
            {
              actor,
              label: label ?? deriveThinkingLabel(actor),
              content: text,
              timestamp
            }
          ];
        });
      },
      onFinal: ({ content, messages: history }: { content: string; messages: ChatMessage[] }) => {
        setIsStreaming(false);
        setStreamingReply("");
        if (history && history.length) {
          setMessages(history);
        } else {
          setMessages((prev) => [...prev, { role: "assistant", content }]);
        }
      },
      onError: (message: string) => {
        setErrorMessage(message);
        setIsStreaming(false);
      }
    }),
    [deriveThinkingLabel]
  );

  const { isConnected, sendMessage } = useChatWebSocket(
    auth?.token ?? null,
    activeSessionId,
    wsHandlers
  );

  const handleSend = useCallback(
    async (text: string) => {
      if (!auth?.token || !activeSessionId) {
        setErrorMessage("请先选择会话");
        return;
      }
      try {
        setMessages((prev) => [...prev, { role: "user", content: text }]);
        setStreamingReply("");
        setErrorMessage(null);
        setIsStreaming(true);
        setProgressVisible(true);
        sendMessage(text);
      } catch (error) {
        setErrorMessage((error as Error).message);
      }
    },
    [auth?.token, activeSessionId, sendMessage]
  );

  const handleLogin = useCallback(
    async (payload: { email?: string; password?: string; guest?: boolean }) => {
      setLoginError(null);
      setLoginLoading(true);
      try {
        const info = await login(payload);
        setAuth(info);
        setActiveSessionId(info.activeSessionId);
      } catch (error) {
        setLoginError((error as Error).message);
      } finally {
        setLoginLoading(false);
      }
    },
    []
  );

  const handleLogout = useCallback(async () => {
    if (!auth?.token) return;
    try {
      await logout(auth.token);
    } finally {
      setAuth(null);
      setSessions([]);
      setMessages([]);
      setProgress([]);
      setProgressVisible(true);
      setThinkingLog([]);
      setThinkingVisible(true);
      setActiveSessionId(null);
    }
  }, [auth]);

  const handleSelectSession = useCallback(
    async (sessionId: string) => {
      if (!auth?.token) return;
      try {
        await activateSession(auth.token, sessionId);
        setSessions((prev) =>
          prev.map((session) => ({
            ...session,
            isActive: session.id === sessionId
          }))
        );
        setActiveSessionId(sessionId);
      } catch (error) {
        setErrorMessage((error as Error).message);
      }
    },
    [auth]
  );

  const handleCreateSession = useCallback(async () => {
    if (!auth?.token) return;
    try {
      const created = await createSession(auth.token);
      await refreshSessions(auth.token, created.id);
      setProgress([]);
      setProgressVisible(true);
      setThinkingLog([]);
    } catch (error) {
      setErrorMessage((error as Error).message);
    }
  }, [auth, refreshSessions]);

  const handleRenameSession = useCallback(
    async (sessionId: string, name: string) => {
      if (!auth?.token) return;
      try {
        await renameSession(auth.token, sessionId, name);
        setSessions((prev) =>
          prev.map((session) =>
            session.id === sessionId ? { ...session, name } : session
          )
        );
      } catch (error) {
        setErrorMessage((error as Error).message);
      }
    },
    [auth]
  );

  const handleDeleteSession = useCallback(
    async (sessionId: string) => {
      if (!auth?.token) return;
      try {
        await deleteSession(auth.token, sessionId);
        const remaining = sessions.filter((session) => session.id !== sessionId);
        setSessions(remaining);
        if (activeSessionId === sessionId) {
          const next = remaining[remaining.length - 1]?.id ?? null;
          setActiveSessionId(next);
          setProgress([]);
          setProgressVisible(true);
          setThinkingLog([]);
          if (next && auth.token) {
            await activateSession(auth.token, next);
            const history = await fetchSessionMessages(auth.token, next);
            setMessages(history);
          } else {
            setMessages([]);
          }
        }
      } catch (error) {
        setErrorMessage((error as Error).message);
      }
    },
    [auth, sessions, activeSessionId]
  );

  const handleToggleConfig = useCallback(
    async (key: keyof AnalysisConfig, value: boolean) => {
      if (!auth?.token) return;
      try {
        const updated = await updateAnalysisConfig(auth.token, { [key]: value });
        setAnalysisConfig(updated);
      } catch (error) {
        setErrorMessage((error as Error).message);
      }
    },
    [auth]
  );

  const handleResetConfig = useCallback(async () => {
    if (!auth?.token) return;
    try {
      const cfg = await resetAnalysisConfig(auth.token);
      setAnalysisConfig(cfg);
    } catch (error) {
      setErrorMessage((error as Error).message);
    }
  }, [auth]);

  if (!auth) {
    return <LoginView onLogin={handleLogin} loading={loginLoading} error={loginError} />;
  }

  return (
    <Dashboard
      auth={auth}
      sessions={sessions}
      analysisConfig={analysisConfig}
      messages={messages}
      streamingReply={streamingReply}
      progress={progress}
      thinkingLog={thinkingLog}
      statusMessage={statusMessage}
      errorMessage={errorMessage}
      showProgressPanel={progressVisible}
      showThinkingPanel={thinkingVisible}
      onToggleProgressPanel={() => setProgressVisible((prev) => !prev)}
      onToggleThinkingPanel={() => setThinkingVisible((prev) => !prev)}
      onSelectSession={handleSelectSession}
      onCreateSession={handleCreateSession}
      onRenameSession={handleRenameSession}
      onDeleteSession={handleDeleteSession}
      onToggleConfig={handleToggleConfig}
      onResetConfig={handleResetConfig}
      onLogout={handleLogout}
      onSendMessage={handleSend}
      streaming={isStreaming}
      connected={isConnected}
    />
  );
}

export default App;
