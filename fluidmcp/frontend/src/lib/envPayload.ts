import type { EnvDeclarations } from '../types/server';

export type EnvPayloadValue = string | { value: string; required?: boolean; description?: string };

/**
 * Build the `env` request payload from flat KEY=value pairs, the comma-separated
 * Required Variables field, and the server's previously stored metadata.
 *
 * The backend treats a key with no `required` flag as required, so once the user
 * is declaring required keys every other key is stored with an explicit
 * `required: false`. "Declaring" means the field is non-empty or the server
 * already carries a `required` declaration (so clearing the field unsets them).
 * Untouched legacy configs stay plain strings. Existing descriptions are preserved.
 */
export function buildEnvPayload(
  env: Record<string, string>,
  requiredField: string,
  existingMeta: EnvDeclarations = {},
): Record<string, EnvPayloadValue> {
  const requiredKeys = new Set(
    requiredField.split(',').map(k => k.trim()).filter(Boolean)
  );
  const declaring =
    requiredKeys.size > 0 ||
    Object.values(existingMeta).some(m => m?.required !== undefined);

  const result: Record<string, EnvPayloadValue> = {};
  Object.entries(env).forEach(([key, value]) => {
    const meta = { ...(existingMeta[key] || {}) };
    if (declaring) {
      meta.required = requiredKeys.has(key);
    }
    result[key] = Object.keys(meta).length > 0 ? { value, ...meta } : value;
  });
  return result;
}
