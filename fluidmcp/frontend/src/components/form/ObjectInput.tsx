import React from 'react';
import type { JsonSchemaProperty } from '../../types/server';

interface ObjectInputProps {
  name: string;
  schema: JsonSchemaProperty;
  value: Record<string, any>;
  onChange: (value: Record<string, any>) => void;
  error?: string;
  required?: boolean;
}

export const ObjectInput: React.FC<ObjectInputProps> = ({
  name,
  schema,
  value,
  onChange,
  error,
  required,
}) => {
  const label = schema.title || name;

  // For simple objects with defined properties, render fields
  if (schema.properties) {
    const handleFieldChange = (fieldName: string, fieldValue: any) => {
      // Guard against prototype pollution
      if (['__proto__', 'constructor', 'prototype'].includes(fieldName)) {
        console.warn(`Blocked prototype pollution attempt: ${fieldName}`);
        return;
      }
      onChange({
        ...value,
        [fieldName]: fieldValue,
      });
    };

    return (
      <div className="form-field object-input">
        <label>
          {label}
          {required && <span className="required">*</span>}
        </label>

        {schema.description && (
          <p className="field-description">{schema.description}</p>
        )}

        <div className="object-fields">
          {Object.entries(schema.properties).map(([fieldName, fieldSchema]) => {
            const fieldValue = value[fieldName] ?? '';
            const isFieldRequired = schema.required?.includes(fieldName);

            return (
              <div key={fieldName} className="object-field">
                <label htmlFor={`${name}.${fieldName}`}>
                  {fieldSchema.title || fieldName}
                  {isFieldRequired && <span className="required">*</span>}
                </label>

                {fieldSchema.description && (
                  <p className="field-description">{fieldSchema.description}</p>
                )}

                {fieldSchema.type === 'string' ? (
                  <input
                    type="text"
                    id={`${name}.${fieldName}`}
                    value={fieldValue}
                    onChange={(e) => handleFieldChange(fieldName, e.target.value)}
                  />
                ) : fieldSchema.type === 'number' || fieldSchema.type === 'integer' ? (
                  <input
                    type="number"
                    id={`${name}.${fieldName}`}
                    value={fieldValue}
                    onChange={(e) => {
                      const parsed = fieldSchema.type === 'integer'
                        ? parseInt(e.target.value, 10)
                        : parseFloat(e.target.value);
                      if (!isNaN(parsed)) {
                        handleFieldChange(fieldName, parsed);
                      }
                    }}
                    step={fieldSchema.type === 'integer' ? '1' : 'any'}
                  />
                ) : fieldSchema.type === 'boolean' ? (
                  <input
                    type="checkbox"
                    id={`${name}.${fieldName}`}
                    checked={fieldValue}
                    onChange={(e) => handleFieldChange(fieldName, e.target.checked)}
                  />
                ) : (
                  <input
                    type="text"
                    id={`${name}.${fieldName}`}
                    value={fieldValue}
                    onChange={(e) => handleFieldChange(fieldName, e.target.value)}
                  />
                )}
              </div>
            );
          })}
        </div>

        {error && <span className="error-message">{error}</span>}
      </div>
    );
  }

  // For free-form objects without defined properties, use JSON textarea
  const handleJsonChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    try {
      const parsed = JSON.parse(e.target.value);
      if (typeof parsed === 'object' && !Array.isArray(parsed)) {
        onChange(parsed);
      }
    } catch {
      // Keep editing invalid JSON - don't update value
    }
  };

  return (
    <div className="form-field object-input">
      <label htmlFor={name}>
        {label}
        {required && <span className="required">*</span>}
      </label>

      {schema.description && (
        <p className="field-description">{schema.description}</p>
      )}

      <textarea
        id={name}
        value={JSON.stringify(value, null, 2)}
        onChange={handleJsonChange}
        rows={6}
        placeholder="Enter JSON object"
      />

      {error && <span className="error-message">{error}</span>}
    </div>
  );
};
