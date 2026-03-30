import React from 'react';
import type { JsonSchemaProperty } from '../../types/server';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

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
  const errorId = error ? `${name}-error` : undefined;
  const descId = schema.description ? `${name}-desc` : undefined;

  const handleValueChange = (selectedValue: string) => {
    // Try to parse as number or boolean if needed
    if (schema.type === 'number' || schema.type === 'integer') {
      onChange(parseFloat(selectedValue));
    } else if (schema.type === 'boolean') {
      onChange(selectedValue === 'true');
    } else {
      onChange(selectedValue);
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

      <Select
        value={String(value)}
        onValueChange={handleValueChange}
      >
        <SelectTrigger
          id={name}
          className={error ? 'border-red-500 focus:ring-red-500' : ''}
          aria-invalid={error ? 'true' : 'false'}
          aria-describedby={[descId, errorId].filter(Boolean).join(' ') || undefined}
          aria-required={required}
        >
          <SelectValue placeholder="Select an option..." />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={String(option)} value={String(option)}>
              {String(option)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {error && (
        <p id={errorId} className="text-xs text-red-400 mt-1" role="alert">
          {error}
        </p>
      )}
    </div>
  );
};
