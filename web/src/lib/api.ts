/** Typed client for the ma2pi JSON API. */

export const EXPECTED_API_VERSION = '1';
export const REQUEST_HEADER = 'X-Ma2pi-Request';

export interface ApiErrorPayload {
  error: string;
  detail?: string;
  field?: string;
  retry_after?: number;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: string;
  readonly field?: string;
  readonly retryAfter?: number;

  constructor(
    status: number,
    code: string,
    detail = '',
    field?: string,
    retryAfter?: number,
  ) {
    super(detail ? `${code}: ${detail}` : code);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.field = field;
    this.retryAfter = retryAfter;
  }
}

export class VersionMismatchError extends Error {
  readonly expected: string;
  readonly actual: string;

  constructor(expected: string, actual: string) {
    super(`API-Version ${actual} passt nicht zur Oberfläche (${expected})`);
    this.name = 'VersionMismatchError';
    this.expected = expected;
    this.actual = actual;
  }
}

export interface VersionInfo {
  api: string;
  package: string;
  ui: string;
}

export interface ActivityDevice {
  rx: number;
  tx: number;
  last_rx: number | null;
  last_tx: number | null;
}

export interface ActivityEntry {
  seq: number;
  ts: number;
  direction: 'rx' | 'tx';
  device: string;
  kind: string;
  summary: string;
}

export interface ActivityInfo {
  devices: Record<string, ActivityDevice>;
  log: ActivityEntry[];
}

export interface DevicePresence {
  connected: boolean;
  path: string | null;
  seen: boolean;
}

export interface StatusInfo {
  connected: boolean;
  authenticated: boolean;
  session: number | null;
  queue_depth: number;
  rate: number;
  screen_mode: boolean;
  frames_sent: number;
  last_frame_types: string[];
  reconnects: number;
  last_error: string | null;
  generation: number;
  busy: boolean;
  activity?: ActivityInfo;
  presence?: Record<string, DevicePresence>;
}

export type NetworkMode = 'dhcp' | 'static';

export interface NetworkCandidate {
  mode: NetworkMode;
  address?: string;
  subnet_mask?: string;
  gateway?: string;
  dns?: string[];
}

export interface NetworkCurrent {
  address: string | null;
  subnet_mask: string | null;
  gateway: string | null;
  dns: string[];
}

export interface NetworkInterfaceInfo {
  name: string;
  type: string;
  state: string;
  connection: string | null;
}

export interface NetworkPending extends NetworkCandidate {
  phase: string;
  started_at: string | null;
  deadline: string | null;
  target_url: string | null;
  error: string | null;
}

export interface NetworkLastResult {
  status: 'confirmed' | 'rolled_back' | 'failed' | 'fallback';
  at: string | null;
  detail: string | null;
}

export interface NetworkStatus {
  backend: string;
  available: boolean;
  can_manage: boolean;
  interface: NetworkInterfaceInfo | null;
  mode: string;
  current: NetworkCurrent;
  pending: NetworkPending | null;
  last_result: NetworkLastResult | null;
  self_connection: boolean;
  error: string | null;
  warnings: string[];
}

export interface NetworkValidation {
  valid: boolean;
  target_url: string | null;
  warnings: string[];
}

export interface NetworkApplyResult {
  pending: NetworkPending;
  target_url: string | null;
}

export interface RecoveryStatus {
  available: boolean;
  enabled: boolean;
  active: boolean;
  ssid: string;
  password: string;
  auto: boolean;
  auto_triggered: boolean;
  address: string | null;
  url: string;
  error: string | null;
}

export interface RecoverySettings {
  enabled: boolean;
  ssid: string;
  password: string;
  auto: boolean;
}

export interface Ma2Config {
  host: string;
  port: number;
  path: string;
  username: string;
  password_set?: boolean;
}

export interface DeviceValueControl {
  control: string;
  note: number;
  kind: 'fader' | 'encoder';
}

export interface DeviceControlInventory {
  id: string;
  kind: 'button' | 'fader' | 'poti' | 'encoder' | 'relative-encoder';
  label: string | null;
}

export interface DeviceBank {
  number: number;
  channel: number;
  notes: Record<string, string>;
}

export interface LayoutCell {
  label: string;
  control: string | null;
  col_span: number;
  row_span: number;
  color: string | null;
  row: number | null;
  col: number | null;
}

export interface DeviceLayout {
  profile: string;
  columns: number;
  rows: { cells: LayoutCell[] }[];
}

export interface DeviceControls {
  keys: { code: string; control: string }[];
  notes: { note: number; control: string }[];
  encoders: Record<string, unknown>[];
  midi_encoders: Record<string, unknown>[];
  values: DeviceValueControl[];
  inventory: DeviceControlInventory[];
  banks: DeviceBank[];
  logical: string[];
}

export interface DeviceEntry {
  name: string;
  backend: string;
  profile: string;
  vendor_id: number;
  product_id: number;
  vendor_product: string;
  name_contains: string | null;
  detected: Record<string, unknown> | null;
  controls: DeviceControls;
  layout: DeviceLayout | null;
  bank_size: number;
}

export interface DeviceLearnStatus {
  active: boolean;
  device?: string;
  bank?: number;
  channel?: number;
  current?: string | null;
  total?: number;
  index?: number;
  captured?: { note: number; control: string }[];
  paused?: boolean;
  error?: string | null;
  elapsed?: number;
  cancelled?: boolean;
  saved?: boolean;
  abandoned?: boolean;
}

export interface BackupEntry {
  id: string;
  size: number;
  modified: string;
  last_good: boolean;
}

export interface AuthStatus {
  pin_enabled: boolean;
  pin_set: boolean;
  authenticated: boolean;
}

export interface LearnResult {
  kind: 'key' | 'encoder';
  status: 'active' | 'captured' | 'timeout' | 'cancelled';
  control: string | null;
  device: string | null;
  raw: string | null;
  direction: number;
  detents: number;
  elapsed: number;
  timed_out: boolean;
}

export interface ApiClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  onUnauthorized?: (() => void) | null;
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  onUnauthorized: (() => void) | null;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? '').replace(/\/$/, '');
    this.onUnauthorized = options.onUnauthorized ?? null;
    const impl = options.fetchImpl ?? fetch;
    // Bind explicitly: calling a stored fetch as a method sets `this` to the
    // client and Chrome rejects it with "Illegal invocation".
    this.fetchImpl = (input, init) => impl(input, init);
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
  ): Promise<T> {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (method !== 'GET' && method !== 'HEAD') {
      headers['Content-Type'] = 'application/json';
      headers[REQUEST_HEADER] = '1';
    }

    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (error) {
      throw new ApiError(
        0,
        'network_error',
        error instanceof Error ? error.message : 'Netzwerkfehler',
      );
    }

    const text = await response.text();
    let payload: unknown = null;
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = null;
      }
    }

    if (!response.ok) {
      const failure = (payload ?? {}) as Partial<ApiErrorPayload>;
      const headerRetry = response.headers?.get?.('Retry-After');
      const parsedHeader =
        headerRetry !== null && headerRetry !== undefined && headerRetry !== ''
          ? Number(headerRetry)
          : undefined;
      const retryAfter =
        typeof failure.retry_after === 'number' && Number.isFinite(failure.retry_after)
          ? failure.retry_after
          : parsedHeader !== undefined && Number.isFinite(parsedHeader)
            ? parsedHeader
            : undefined;
      const detail =
        failure.detail ??
        (response.status === 429 && failure.error === 'pin_locked' && retryAfter !== undefined
          ? `Zu viele Fehlversuche – bitte ${retryAfter} s warten`
          : response.statusText);
      if (response.status === 401 && path !== '/api/auth/login') {
        this.onUnauthorized?.();
      }
      throw new ApiError(
        response.status,
        failure.error ?? 'http_error',
        detail,
        failure.field,
        retryAfter,
      );
    }
    return payload as T;
  }

  version(): Promise<VersionInfo> {
    return this.request<VersionInfo>('GET', '/api/version');
  }

  async checkVersion(): Promise<VersionInfo> {
    const info = await this.version();
    if (info.api !== EXPECTED_API_VERSION) {
      throw new VersionMismatchError(EXPECTED_API_VERSION, info.api);
    }
    return info;
  }

  status(): Promise<StatusInfo> {
    return this.request<StatusInfo>('GET', '/api/status');
  }

  network(): Promise<NetworkStatus> {
    return this.request<NetworkStatus>('GET', '/api/network');
  }

  validateNetwork(candidate: NetworkCandidate): Promise<NetworkValidation> {
    return this.request<NetworkValidation>('POST', '/api/network/validate', candidate);
  }

  applyNetwork(candidate: NetworkCandidate): Promise<NetworkApplyResult> {
    return this.request<NetworkApplyResult>('PUT', '/api/network', candidate);
  }

  confirmNetwork(): Promise<NetworkStatus> {
    return this.request<NetworkStatus>('POST', '/api/network/confirm', {});
  }

  rollbackNetwork(): Promise<NetworkStatus> {
    return this.request<NetworkStatus>('POST', '/api/network/rollback', {});
  }

  recovery(): Promise<RecoveryStatus> {
    return this.request<RecoveryStatus>('GET', '/api/recovery');
  }

  saveRecovery(settings: RecoverySettings): Promise<RecoveryStatus> {
    return this.request<RecoveryStatus>('PUT', '/api/recovery', settings);
  }

  authStatus(): Promise<AuthStatus> {
    return this.request<AuthStatus>('GET', '/api/auth/status');
  }

  login(pin: string): Promise<{ ok: boolean }> {
    return this.request<{ ok: boolean }>('POST', '/api/auth/login', { pin });
  }

  logout(): Promise<{ ok: boolean }> {
    return this.request<{ ok: boolean }>('POST', '/api/auth/logout', {});
  }

  config(): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>('GET', '/api/config');
  }

  updateConfig(patch: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>('PUT', '/api/config', patch);
  }

  validateConfig(patch: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>('POST', '/api/config/validate', patch);
  }

  testConnection(body: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>('POST', '/api/test-connection', body);
  }

  async devices(): Promise<DeviceEntry[]> {
    const body = await this.request<{ devices: DeviceEntry[] }>('GET', '/api/devices');
    return body.devices;
  }

  deviceLearnStatus(): Promise<DeviceLearnStatus> {
    return this.request<DeviceLearnStatus>('GET', '/api/device-learn');
  }

  startDeviceLearn(device: string, bank: number, control?: string): Promise<DeviceLearnStatus> {
    return this.request<DeviceLearnStatus>('POST', '/api/device-learn/start', {
      device,
      bank,
      ...(control ? { control } : {}),
    });
  }

  skipDeviceLearn(): Promise<DeviceLearnStatus> {
    return this.request<DeviceLearnStatus>('POST', '/api/device-learn/skip', {});
  }

  cancelDeviceLearn(): Promise<{ cancelled: boolean }> {
    return this.request<{ cancelled: boolean }>('POST', '/api/device-learn/cancel', {});
  }

  finishDeviceLearn(): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>('POST', '/api/device-learn/finish', {});
  }

  async backups(): Promise<BackupEntry[]> {
    const body = await this.request<{ backups: BackupEntry[] }>('GET', '/api/backups');
    return body.backups;
  }

  createBackup(): Promise<BackupEntry> {
    return this.request<BackupEntry>('POST', '/api/backups', {});
  }

  restoreBackup(id: string): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>(
      'POST',
      `/api/backups/${encodeURIComponent(id)}/restore`,
      {},
    );
  }

  startLearn(kind: 'key' | 'encoder', device?: string): Promise<LearnResult> {
    return this.request<LearnResult>('POST', '/api/learn/start', { kind, device });
  }

  cancelLearn(): Promise<{ cancelled: boolean; learn: LearnResult | null }> {
    return this.request<{ cancelled: boolean; learn: LearnResult | null }>(
      'POST',
      '/api/learn/cancel',
      {},
    );
  }
}
