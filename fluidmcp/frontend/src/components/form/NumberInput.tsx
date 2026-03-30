import React from 'react';
import type { JsonSchemaProperty } from '../../types/server';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

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
  const errorId = error ? `${name}-error` : undefined;
  const descId = schema.description ? `${name}-desc` : undefined;

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
    <div className="space-y-2">
      <Label htmlFor={name} className="text-sm font-medium text-zinc-200">
        {label}
        {required && <span className="text-red-400 ml-1">*</span>}
      </Label>

      {schema.description && (
        <p id={descId} className="text-xs text-zinc-400">
          {schema.description}
        </p>
      )}

      <Input
        type="number"
        id={name}
        name={name}
        value={value}
        onChange={handleChange}
        step={isInteger ? '1' : 'any'}
        min={schema.minimum}
        max={schema.maximum}
        className={error ? 'border-red-500 focus-visible:ring-red-500' : ''}
        aria-invalid={error ? 'true' : 'false'}
        aria-describedby={[descId, errorId].filter(Boolean).join(' ') || undefined}
        aria-required={required}
      />

      {error && (
        <p id={errorId} className="text-xs text-red-400 mt-1" role="alert">
          {error}
        </p>
      )}
    </div>
  );
};
