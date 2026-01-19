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

  return (
    <div className="form-field">
      <div className="checkbox-wrapper">
        <label className="checkbox-label">
          <input
            type="checkbox"
            id={name}
            name={name}
            checked={value}
            onChange={(e) => onChange(e.target.checked)}
            className={error ? 'error' : ''}
          />
          <span>
            {label}
            {required && <span className="required">*</span>}
          </span>
        </label>

        {schema.description && (
          <p className="field-description">{schema.description}</p>
        )}
      </div>

      {error && <span className="error-message">{error}</span>}
    </div>
  );
};
