/** Typed client for the ma2pi JSON API. */

export const EXPECTED_API_VERSION = '1';
export const REQUEST_HEADER = 'X-Ma2pi-Request';

export interface ApiErrorPayload {
  error: string;
  detail?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: string;

  constructor(status: number, code: string, detail = '') {
    super(detail ? `${code}: ${detail}` : code);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.detail = detail;
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
}

export interface Ma2Config {
  host: string;
  port: number;
  path: string;
  username: string;
  password_set?: boolean;
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
  controls: Record<string, unknown>;
}

export interface BackupEntry {
  id: string;
  size: number;
  modified: string;
  last_good: boolean;
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
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? '').replace(/\/$/, '');
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
      throw new ApiError(
        response.status,
        failure.error ?? 'http_error',
        failure.detail ?? response.statusText,
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
