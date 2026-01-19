import React from 'react';
import { JsonSchemaProperty } from '../../types/server';

interface NumberInputProps {
  name: string;
  schema: JsonSchemaProperty;
  value: number;
  onChange: (value: number) => void;
  error?: string;
  required?: boolean;
}

export const NumberInput: React.FC<NumberInputProps> = ({
  name,
  schema,
  value,
  onChange,
  error,
  required,
}) => {
  const label = schema.title || name;
  const isInteger = schema.type === 'integer';

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const rawValue = e.target.value;
    if (rawValue === '') {
      onChange(0);
      return;
    }

    const parsed = isInteger ? parseInt(rawValue, 10) : parseFloat(rawValue);
    if (!isNaN(parsed)) {
      onChange(parsed);
    }
  };

  return (
    <div className="form-field">
      <label htmlFor={name}>
        {label}
        {required && <span className="required">*</span>}
      </label>

      {schema.description && (
        <p className="field-description">{schema.description}</p>
      )}

      <input
        type="number"
        id={name}
        name={name}
        value={value}
        onChange={handleChange}
        step={isInteger ? '1' : 'any'}
        min={schema.minimum}
        max={schema.maximum}
        className={error ? 'error' : ''}
      />

      {error && <span className="error-message">{error}</span>}
    </div>
  );
};
