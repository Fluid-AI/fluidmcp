import { describe, expect, it } from 'vitest';
import { buildEnvPayload } from './envPayload';

describe('buildEnvPayload', () => {
  it('keeps plain strings for untouched legacy configs', () => {
    expect(buildEnvPayload({ A: '1', B: '2' }, '', {})).toEqual({ A: '1', B: '2' });
  });

  it('marks listed keys required and creates unlisted new keys as optional', () => {
    expect(buildEnvPayload({ API_KEY: 'k', DEBUG: 'false' }, 'API_KEY', {})).toEqual({
      API_KEY: { value: 'k', required: true },
      DEBUG: { value: 'false', required: false },
    });
  });

  it('unsets a previously required key by storing required: false', () => {
    const existing = { A: { required: true }, B: { required: true } };
    expect(buildEnvPayload({ A: '1', B: '2' }, 'A', existing)).toEqual({
      A: { value: '1', required: true },
      B: { value: '2', required: false },
    });
  });

  it('clearing the field unsets every previously required key', () => {
    const existing = { A: { required: true } };
    expect(buildEnvPayload({ A: '1', B: '2' }, '', existing)).toEqual({
      A: { value: '1', required: false },
      B: { value: '2', required: false },
    });
  });

  it('preserves descriptions and explicit required: false', () => {
    const existing = { A: { required: true, description: 'Key' }, B: { required: false, description: 'Opt' } };
    expect(buildEnvPayload({ A: '1', B: '2' }, 'A', existing)).toEqual({
      A: { value: '1', required: true, description: 'Key' },
      B: { value: '2', required: false, description: 'Opt' },
    });
  });

  it('does not start declaring when only descriptions exist', () => {
    expect(buildEnvPayload({ A: '1' }, '', { A: { description: 'd' } })).toEqual({
      A: { value: '1', description: 'd' },
    });
  });
});
