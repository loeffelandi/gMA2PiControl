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

  it('reads network status and sends network candidates', async () => {
    const status = {
      backend: 'networkmanager',
      available: true,
      can_manage: true,
      interface: { name: 'eth0', type: 'ethernet', state: 'connected', connection: 'Wired' },
      mode: 'static',
      current: {
        address: '192.168.10.50',
        subnet_mask: '255.255.255.0',
        gateway: '192.168.10.1',
        dns: ['192.168.10.1'],
      },
      pending: null,
      last_result: null,
      self_connection: false,
      error: null,
      warnings: [],
    };
    const fetchImpl = vi.fn().mockResolvedValue(response(status));
    const client = new ApiClient({ fetchImpl });

    expect((await client.network()).current.address).toBe('192.168.10.50');
    expect(fetchImpl).toHaveBeenCalledWith(
      '/api/network',
      expect.objectContaining({ method: 'GET' }),
    );

    fetchImpl.mockResolvedValue(response({ valid: true, target_url: null, warnings: [] }));
    const candidate = {
      mode: 'static' as const,
      address: '192.168.10.60',
      subnet_mask: '255.255.255.0',
    };
    await client.validateNetwork(candidate);
    const [path, init] = fetchImpl.mock.calls[1] as [string, RequestInit];
    expect(path).toBe('/api/network/validate');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual(candidate);
    expect((init.headers as Record<string, string>)[REQUEST_HEADER]).toBe('1');

    fetchImpl.mockResolvedValue(response({ ...status, mode: 'fallback' }));
    await client.emergencyNetwork();
    const [emergencyPath, emergencyInit] = fetchImpl.mock.calls[2] as [
      string,
      RequestInit,
    ];
    expect(emergencyPath).toBe('/api/network/emergency');
    expect(emergencyInit.method).toBe('POST');
    expect(JSON.parse(String(emergencyInit.body))).toEqual({});
  });

  it('exposes the field of a network validation error', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      response(
        { error: 'validation_error', field: 'subnet_mask', detail: 'keine gültige Maske' },
        422,
      ),
    );
    const client = new ApiClient({ fetchImpl });
    await expect(
      client.validateNetwork({ mode: 'static', address: '192.168.10.60', subnet_mask: 'x' }),
    ).rejects.toMatchObject({
      status: 422,
      code: 'validation_error',
      field: 'subnet_mask',
      detail: 'keine gültige Maske',
    });
  });

  it('wraps network failures', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new Error('offline'));
    const client = new ApiClient({ fetchImpl });

    await expect(client.status()).rejects.toBeInstanceOf(ApiError);
  });
});
