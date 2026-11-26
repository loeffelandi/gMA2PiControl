import { describe, expect, it, vi } from 'vitest';

import {
  ApiClient,
  ApiError,
  EXPECTED_API_VERSION,
  REQUEST_HEADER,
  VersionMismatchError,
} from './api';

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('ApiClient', () => {
  it('reads status successfully', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      response({ connected: true, session: 7, generation: 2 }),
    );
    const client = new ApiClient({ fetchImpl });

    const status = await client.status();

    expect(status.connected).toBe(true);
    expect(status.session).toBe(7);
    expect(fetchImpl).toHaveBeenCalledWith(
      '/api/status',
      expect.objectContaining({ method: 'GET' }),
    );
  });

  it('surfaces validation errors with field detail', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      response(
        { error: 'validation_error', detail: 'ma2.port: muss zwischen 1 und 65535 liegen' },
        422,
      ),
    );
    const client = new ApiClient({ fetchImpl });

    await expect(client.updateConfig({ ma2: { port: 70000 } })).rejects.toMatchObject({
      status: 422,
      code: 'validation_error',
      detail: 'ma2.port: muss zwischen 1 und 65535 liegen',
    });
  });

  it('sends JSON and the request header for writes', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(response({ ok: true }));
    const client = new ApiClient({ fetchImpl });

    await client.createBackup();

    const [, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe('POST');
    expect((init.headers as Record<string, string>)['Content-Type']).toBe(
      'application/json',
    );
    expect((init.headers as Record<string, string>)[REQUEST_HEADER]).toBe('1');
  });

  it('reports a version mismatch', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      response({ api: '2', package: '0.2.0', ui: 'x' }),
    );
    const client = new ApiClient({ fetchImpl });

    await expect(client.checkVersion()).rejects.toBeInstanceOf(VersionMismatchError);
  });

  it('accepts the expected API version', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      response({ api: EXPECTED_API_VERSION, package: '0.1.0', ui: 'x' }),
    );
    const client = new ApiClient({ fetchImpl });

    const info = await client.checkVersion();
    expect(info.api).toBe(EXPECTED_API_VERSION);
  });

  it('wraps network failures', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new Error('offline'));
    const client = new ApiClient({ fetchImpl });

    await expect(client.status()).rejects.toBeInstanceOf(ApiError);
  });
});
