import React from 'react';
import { JsonSchemaProperty } from '../../types/server';
import { StringInput } from './StringInput';
import { NumberInput } from './NumberInput';
import { BooleanInput } from './BooleanInput';
import { SelectInput } from './SelectInput';
import { ArrayInput } from './ArrayInput';
import { ObjectInput } from './ObjectInput';

interface SchemaFieldRendererProps {
  name: string;
  schema: JsonSchemaProperty;
  value: any;
  onChange: (value: any) => void;
  error?: string;
  required?: boolean;
}

export const SchemaFieldRenderer: React.FC<SchemaFieldRendererProps> = ({
  name,
  schema,
  value,
  onChange,
  error,
  required,
}) => {
  // If the field has enum values, render as select
  if (schema.enum && schema.enum.length > 0) {
    return (
      <SelectInput
        name={name}
        schema={schema}
        value={value}
        onChange={onChange}
        error={error}
        required={required}
      />
    );
  }

  // Route to appropriate input component based on type
  switch (schema.type) {
    case 'string':
      return (
        <StringInput
          name={name}
          schema={schema}
          value={value || ''}
          onChange={onChange}
          error={error}
          required={required}
        />
      );

    case 'number':
    case 'integer':
      return (
        <NumberInput
          name={name}
          schema={schema}
          value={value ?? 0}
          onChange={onChange}
          error={error}
          required={required}
        />
      );

    case 'boolean':
      return (
        <BooleanInput
          name={name}
          schema={schema}
          value={value ?? false}
          onChange={onChange}
          error={error}
          required={required}
        />
      );

    case 'array':
      return (
        <ArrayInput
          name={name}
          schema={schema}
          value={value ?? []}
          onChange={onChange}
          error={error}
          required={required}
        />
      );

    case 'object':
      return (
        <ObjectInput
          name={name}
          schema={schema}
          value={value ?? {}}
          onChange={onChange}
          error={error}
          required={required}
        />
      );

    default:
      // Fallback to string input for unknown types
      return (
        <StringInput
          name={name}
          schema={schema}
          value={String(value ?? '')}
          onChange={onChange}
          error={error}
          required={required}
        />
      );
  }
};
