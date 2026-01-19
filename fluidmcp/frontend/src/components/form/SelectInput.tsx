import React from 'react';
import type { JsonSchemaProperty } from '../../types/server';

interface SelectInputProps {
  name: string;
  schema: JsonSchemaProperty;
  value: any;
  onChange: (value: any) => void;
  error?: string;
  required?: boolean;
}

export const SelectInput: React.FC<SelectInputProps> = ({
  name,
  schema,
  value,
  onChange,
  error,
  required,
}) => {
  const label = schema.title || name;
  const options = schema.enum || [];

  return (
    <div className="form-field">
      <label htmlFor={name}>
        {label}
        {required && <span className="required">*</span>}
      </label>

      {schema.description && (
        <p className="field-description">{schema.description}</p>
      )}

      <select
        id={name}
        name={name}
        value={value}
        onChange={(e) => {
          const selectedValue = e.target.value;
          // Try to parse as number or boolean if needed
          if (schema.type === 'number' || schema.type === 'integer') {
            onChange(parseFloat(selectedValue));
          } else if (schema.type === 'boolean') {
            onChange(selectedValue === 'true');
          } else {
            onChange(selectedValue);
          }
        }}
        className={error ? 'error' : ''}
      >
        <option value="">Select an option...</option>
        {options.map((option) => (
          <option key={String(option)} value={String(option)}>
            {String(option)}
          </option>
        ))}
      </select>

      {error && <span className="error-message">{error}</span>}
    </div>
  );
};
