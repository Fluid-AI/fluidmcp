import React from 'react';
import type { JsonSchemaProperty } from '../../types/server';

interface BooleanInputProps {
  name: string;
  schema: JsonSchemaProperty;
  value: boolean;
  onChange: (value: boolean) => void;
  error?: string;
  required?: boolean;
}

export const BooleanInput: React.FC<BooleanInputProps> = ({
  name,
  schema,
  value,
  onChange,
  error,
  required,
}) => {
  const label = schema.title || name;
  const errorId = error ? `${name}-error` : undefined;
  const descId = schema.description ? `${name}-desc` : undefined;

  return (
    <div className="form-field">
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <label style={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: '0.75rem',
          cursor: 'pointer',
          userSelect: 'none',
          paddingTop: '0.5rem'
        }}>
          <input
            type="checkbox"
            id={name}
            name={name}
            checked={value}
            onChange={(e) => onChange(e.target.checked)}
            style={{
              width: '1.25rem',
              height: '1.25rem',
              cursor: 'pointer',
              accentColor: '#6366f1',
              flexShrink: 0
            }}
            aria-invalid={error ? 'true' : 'false'}
            aria-describedby={[descId, errorId].filter(Boolean).join(' ') || undefined}
            aria-required={required}
          />
          <span style={{ 
            color: error ? '#ef4444' : '#e5e7eb',
            fontSize: '0.95rem',
            lineHeight: '1.5'
          }}>
            {label}
            {required && <span style={{ color: '#ef4444', marginLeft: '0.25rem' }}>*</span>}
          </span>
        </label>

        {schema.description && (
          <p 
            id={descId} 
            style={{ 
              color: 'rgba(255, 255, 255, 0.6)', 
              fontSize: '0.875rem',
              margin: 0,
              paddingLeft: '2rem'
            }}
          >
            {schema.description}
          </p>
        )}
      </div>

      {error && (
        <span 
          id={errorId} 
          style={{ 
            color: '#ef4444', 
            fontSize: '0.875rem',
            display: 'block',
            marginTop: '0.5rem'
          }} 
          role="alert"
        >
          {error}
        </span>
      )}
    </div>
  );
};
