import React from 'react';
import type { JsonSchemaProperty } from '../../types/server';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

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

      {isTextarea ? (
        <Textarea
          id={name}
          name={name}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={schema.default || ''}
          rows={5}
          className={error ? 'border-red-500 focus-visible:ring-red-500' : ''}
          aria-invalid={error ? 'true' : 'false'}
          aria-describedby={[descId, errorId].filter(Boolean).join(' ') || undefined}
          aria-required={required}
        />
      ) : (
        <Input
          type={schema.format === 'email' ? 'email' : schema.format === 'url' ? 'url' : 'text'}
          id={name}
          name={name}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={schema.default || ''}
          minLength={schema.minLength}
          maxLength={schema.maxLength}
          className={error ? 'border-red-500 focus-visible:ring-red-500' : ''}
          aria-invalid={error ? 'true' : 'false'}
          aria-describedby={[descId, errorId].filter(Boolean).join(' ') || undefined}
          aria-required={required}
        />
      )}

      {error && (
        <p id={errorId} className="text-xs text-red-400 mt-1" role="alert">
          {error}
        </p>
      )}
    </div>
  );
};
