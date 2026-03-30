import React from 'react';
import type { JsonSchemaProperty } from '../../types/server';
import { Label } from '@/components/ui/label';

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
    <div className="space-y-2">
      <div className="flex items-start space-x-3">
        <input
          type="checkbox"
          id={name}
          name={name}
          checked={value}
          onChange={(e) => onChange(e.target.checked)}
          className="h-5 w-5 mt-0.5 rounded border-zinc-700 bg-zinc-900/50 text-indigo-600 focus:ring-2 focus:ring-zinc-600 focus:ring-offset-0 cursor-pointer"
          aria-invalid={error ? 'true' : 'false'}
          aria-describedby={[descId, errorId].filter(Boolean).join(' ') || undefined}
          aria-required={required}
        />
        <div className="flex-1">
          <Label htmlFor={name} className="text-sm font-medium text-zinc-200 cursor-pointer">
            {label}
            {required && <span className="text-red-400 ml-1">*</span>}
          </Label>
          {schema.description && (
            <p id={descId} className="text-xs text-zinc-400 mt-1">
              {schema.description}
            </p>
          )}
        </div>
      </div>

      {error && (
        <p id={errorId} className="text-xs text-red-400" role="alert">
          {error}
        </p>
      )}
    </div>
  );
};
