import React, { useState, useEffect } from 'react';
import type { ServerEnvMetadataResponse } from '../types/server';
import './ServerEnvForm.css';

interface ServerEnvFormProps {
  serverId: string;
  configEnv: Record<string, string>; // Template env from server config
  envMetadata: ServerEnvMetadataResponse; // Metadata from backend
  onSubmit: (env: Record<string, string>) => Promise<void>;
  onCancel?: () => void;
  serverState: string;
}

export const ServerEnvForm: React.FC<ServerEnvFormProps> = ({
  configEnv,
  envMetadata,
  onSubmit,
  onCancel,
  serverState,
}) => {
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Initialize form with empty values (never pre-populate for security)
  useEffect(() => {
    const initialValues: Record<string, string> = {};
    Object.keys(configEnv).forEach((key) => {
      initialValues[key] = '';
    });
    setFormValues(initialValues);
  }, [configEnv]);

  const handleInputChange = (key: string, value: string) => {
    setFormValues((prev) => ({
      ...prev,
      [key]: value,
    }));

    // Clear validation error for this field
    if (validationErrors[key]) {
      setValidationErrors((prev) => {
        const updated = { ...prev };
        delete updated[key];
        return updated;
      });
    }
  };

  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};

    Object.entries(formValues).forEach(([key, value]) => {
      const metadata = envMetadata[key];

      // Check required fields (only enforce if not already configured)
      // This allows "leave empty to keep current value" UX for existing values
      if (metadata?.required && !value && !metadata?.present) {
        errors[key] = 'This field is required';
      }

      // Check for null bytes
      if (value && value.includes('\x00')) {
        errors[key] = 'Value cannot contain null bytes';
      }

      // Check max length (10k chars)
      if (value && value.length > 10000) {
        errors[key] = 'Value is too long (max 10,000 characters)';
      }
    });

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    setIsSubmitting(true);

    try {
      // Only send non-empty values to preserve existing secrets
      // Empty values are ignored intentionally - users cannot clear values once set
      // This is a security-first design to prevent accidental credential deletion
      // (Support for explicit clearing can be added in a future enhancement)
      const envToSubmit: Record<string, string> = {};
      Object.entries(formValues).forEach(([key, value]) => {
        if (value !== '') {
          envToSubmit[key] = value;
        }
      });

      await onSubmit(envToSubmit);
    } catch (error) {
      console.error('Failed to submit env variables:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const isSensitiveField = (key: string): boolean => {
    const lowerKey = key.toLowerCase();
    const sensitivePatterns = [
      'key', 'token', 'secret', 'password', 'credential',
      'apikey', 'api_key', 'auth', 'jwt', 'bearer',
      'private', 'passphrase', 'salt', 'hash'
    ];

    // Check if field name ends with or contains sensitive keywords
    // This catches variations like: api_key_prod, database_token, oauth_secret_backup
    return sensitivePatterns.some(pattern =>
      lowerKey.endsWith(pattern) ||
      lowerKey.includes(`_${pattern}`) ||
      lowerKey.includes(`${pattern}_`)
    );
  };

  const envKeys = Object.keys(configEnv);

  if (envKeys.length === 0) {
    return null;
  }

  const isRunning = serverState === 'running';

  return (
    <div className="server-env-form">
      <form onSubmit={handleSubmit}>
        <div className="env-fields">
          {envKeys.map((key) => {
            const metadata = envMetadata[key];
            const isConfigured = metadata?.present || false;
            const isSensitive = isSensitiveField(key);
            const error = validationErrors[key];

            return (
              <div key={key} className={`env-field ${error ? 'has-error' : ''}`}>
                <label htmlFor={`env-${key}`}>
                  {key}
                  {metadata?.required && <span className="required"> *</span>}
                  {isConfigured && (
                    <span className="configured-badge" title="Value is configured">
                      ✓ Configured
                    </span>
                  )}
                </label>

                {metadata?.description && (
                  <p className="field-description">{metadata.description}</p>
                )}

                <input
                  id={`env-${key}`}
                  type={isSensitive ? 'password' : 'text'}
                  value={formValues[key] || ''}
                  onChange={(e) => handleInputChange(key, e.target.value)}
                  placeholder={
                    isConfigured
                      ? 'Leave empty to keep current value'
                      : 'Enter value...'
                  }
                  className={error ? 'error' : ''}
                />

                {error && <p className="field-error">{error}</p>}
              </div>
            );
          })}
        </div>

        {isRunning && (
          <div className="restart-warning">
            <span className="warning-icon">⚠️</span>
            <span>Saving environment variables will restart this server.</span>
          </div>
        )}

        <div className="form-actions">
          <button
            type="submit"
            disabled={isSubmitting}
            className="submit-button"
          >
            {isSubmitting ? 'Saving...' : 'Save Environment Variables'}
          </button>

          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              disabled={isSubmitting}
              className="cancel-button"
            >
              Cancel
            </button>
          )}
        </div>
      </form>
    </div>
  );
};
