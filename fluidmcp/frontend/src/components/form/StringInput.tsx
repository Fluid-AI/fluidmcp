import React from 'react';
import type { JsonSchemaProperty } from '../../types/server';

interface StringInputProps {
  name: string;
  schema: JsonSchemaProperty;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  required?: boolean;
}

export const StringInput: React.FC<StringInputProps> = ({
  name,
  schema,
  value,
  onChange,
  error,
  required,
}) => {
  const label = schema.title || name;
  const isTextarea = schema.maxLength && schema.maxLength > 100;
  const errorId = error ? `${name}-error` : undefined;
  const descId = schema.description ? `${name}-desc` : undefined;

  return (
    <div className="form-field">
      <label htmlFor={name}>
        {label}
        {required && <span className="required">*</span>}
      </label>

      {schema.description && (
        <p id={descId} className="field-description">{schema.description}</p>
      )}

      {isTextarea ? (
        <textarea
          id={name}
          name={name}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={schema.default || ''}
          rows={5}
          className={error ? 'error' : ''}
          aria-invalid={error ? 'true' : 'false'}
          aria-describedby={[descId, errorId].filter(Boolean).join(' ') || undefined}
          aria-required={required}
        />
      ) : (
        <input
          type={schema.format === 'email' ? 'email' : schema.format === 'url' ? 'url' : 'text'}
          id={name}
          name={name}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={schema.default || ''}
          minLength={schema.minLength}
          maxLength={schema.maxLength}
          className={error ? 'error' : ''}
          aria-invalid={error ? 'true' : 'false'}
          aria-describedby={[descId, errorId].filter(Boolean).join(' ') || undefined}
          aria-required={required}
        />
      )}

      {error && <span id={errorId} className="error-message" role="alert">{error}</span>}
    </div>
  );
};
