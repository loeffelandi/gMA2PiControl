/** Live status via the `/api/events` WebSocket with automatic reconnect. */

import type {
  ActivityDevice,
  ActivityEntry,
  ActivityInfo,
  LearnResult,
  NetworkLastResult,
  NetworkPending,
  StatusInfo,
} from './api';

export type ConnectionState = 'connecting' | 'open' | 'closed';

export interface NetworkEventData {
  pending: NetworkPending | null;
  last_result: NetworkLastResult | null;
}

export interface ActivityState {
  devices: Record<string, ActivityDevice>;
  entries: ActivityEntry[];
}

export interface StatusState {
  connection: ConnectionState;
  reconnecting: boolean;
  status: StatusInfo | null;
  learn: LearnResult | null;
  network: NetworkEventData | null;
  activity: ActivityState;
  lastError: string | null;
}

export const LOG_LIMIT = 100;

const emptyActivity = (): ActivityState => ({ devices: {}, entries: [] });

function mergeSnapshot(incoming: ActivityInfo | undefined): ActivityState {
  return {
    devices: { ...(incoming?.devices ?? {}) },
    entries: [...(incoming?.log ?? [])].slice(-LOG_LIMIT),
  };
}

function mergeDelta(
  current: ActivityState,
  incoming: Partial<ActivityInfo> & { entries?: ActivityEntry[] },
): ActivityState {
  const devices = { ...current.devices, ...(incoming.devices ?? {}) };
  const seen = new Set(current.entries.map((entry) => entry.seq));
  const added = (incoming.entries ?? [])
    .filter((entry) => !seen.has(entry.seq))
    .sort((a, b) => a.seq - b.seq);
  const entries = [...current.entries, ...added]
    .sort((a, b) => a.seq - b.seq)
    .slice(-LOG_LIMIT);
  return { devices, entries };
}

export interface WebSocketLike {
  onopen: (() => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
  onclose: (() => void) | null;
  onerror: (() => void) | null;
  close(): void;
}

export type WebSocketFactory = (url: string) => WebSocketLike;

export interface StatusStoreOptions {
  url?: string;
  factory?: WebSocketFactory;
  reconnectBaseMs?: number;
  reconnectMaxMs?: number;
}

function defaultUrl(): string {
  if (typeof location === 'undefined') return '/api/events';
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${scheme}//${location.host}/api/events`;
}

const defaultFactory: WebSocketFactory = (url) =>
  new WebSocket(url) as unknown as WebSocketLike;

export class StatusStore {
  private readonly url: string;
  private readonly factory: WebSocketFactory;
  private readonly baseDelay: number;
  private readonly maxDelay: number;
  private readonly listeners = new Set<() => void>();
  private socket: WebSocketLike | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private wanted = false;
  private attempts = 0;

  state: StatusState = {
    connection: 'closed',
    reconnecting: false,
    status: null,
    learn: null,
    network: null,
    activity: emptyActivity(),
    lastError: null,
  };

  constructor(options: StatusStoreOptions = {}) {
    this.url = options.url ?? defaultUrl();
    this.factory = options.factory ?? defaultFactory;
    this.baseDelay = options.reconnectBaseMs ?? 1000;
    this.maxDelay = options.reconnectMaxMs ?? 10000;
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  connect(): void {
    this.wanted = true;
    if (this.socket !== null) return;
    this.open();
  }

  disconnect(): void {
    this.wanted = false;
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    const socket = this.socket;
    this.socket = null;
    if (socket !== null) {
      socket.close();
    }
    this.patch({ connection: 'closed', reconnecting: false });
  }

  private patch(values: Partial<StatusState>): void {
    this.state = { ...this.state, ...values };
    for (const listener of [...this.listeners]) listener();
  }

  private open(): void {
    this.patch({ connection: 'connecting', reconnecting: this.attempts > 0 });
    let socket: WebSocketLike;
    try {
      socket = this.factory(this.url);
    } catch (error) {
      this.patch({
        connection: 'closed',
        lastError: error instanceof Error ? error.message : 'WebSocket-Fehler',
      });
      this.scheduleReconnect();
      return;
    }

    this.socket = socket;
    socket.onopen = () => {
      this.attempts = 0;
      this.patch({ connection: 'open', reconnecting: false, lastError: null });
    };
    socket.onmessage = (event) => {
      this.receive(event.data);
    };
    socket.onerror = () => {
      this.patch({ lastError: 'WebSocket-Fehler' });
    };
    socket.onclose = () => {
      if (this.socket === socket) {
        this.socket = null;
        this.scheduleReconnect();
      }
    };
  }

  private receive(raw: string): void {
    let message: { type?: string; data?: unknown };
    try {
      message = JSON.parse(raw);
    } catch {
      return;
    }
    if (message.type === 'status' && message.data) {
      const info = message.data as StatusInfo;
      this.patch({
        status: info,
        activity: mergeSnapshot(info.activity),
        lastError: null,
      });
    } else if (message.type === 'activity' && message.data) {
      this.patch({
        activity: mergeDelta(
          this.state.activity,
          message.data as Partial<ActivityInfo> & { entries?: ActivityEntry[] },
        ),
      });
    } else if (message.type === 'learn' && message.data) {
      this.patch({ learn: message.data as LearnResult });
    } else if (message.type === 'network' && message.data) {
      this.patch({ network: message.data as NetworkEventData });
    }
  }

  private scheduleReconnect(): void {
    if (!this.wanted) return;
    this.patch({ connection: 'closed', reconnecting: true });
    if (this.timer !== null) return;
    this.attempts += 1;
    const delay = Math.min(
      this.maxDelay,
      this.baseDelay * 2 ** Math.min(this.attempts - 1, 4),
    );
    this.timer = setTimeout(() => {
      this.timer = null;
      if (this.wanted) this.open();
    }, delay);
  }
}
