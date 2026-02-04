import React, { useState, useEffect } from 'react';
import type { JsonSchemaProperty } from '../../types/server';
import { SchemaFieldRenderer } from './SchemaFieldRenderer';
import { validateForm, initializeFormValues } from './FormValidation';

interface JsonSchemaFormProps {
  schema: {
    type: string;
    properties?: Record<string, JsonSchemaProperty>;
    required?: string[];
  };
  initialValues?: Record<string, any>;
  onSubmit: (values: Record<string, any>) => void | Promise<void>;
  submitLabel?: string;
  loading?: boolean;
}

export const JsonSchemaForm: React.FC<JsonSchemaFormProps> = ({
  schema,
  initialValues,
  onSubmit,
  submitLabel = 'Submit',
  loading = false,
}) => {
  const [values, setValues] = useState<Record<string, any>>(() =>
    initializeFormValues(schema, initialValues)
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  // Update form values when initialValues change
  useEffect(() => {
    if (initialValues) {
      setValues(initializeFormValues(schema, initialValues));
      setTouched({});
      setErrors({});
    }
  }, [initialValues, schema]);

  const handleFieldChange = (fieldName: string, value: any) => {
    setValues((prev) => ({
      ...prev,
      [fieldName]: value,
    }));

    // Mark field as touched
    setTouched((prev) => ({
      ...prev,
      [fieldName]: true,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validate all fields
    const validationErrors = validateForm(values, schema);

    if (validationErrors.length > 0) {
      // Convert validation errors to error map
      const errorMap: Record<string, string> = {};
      validationErrors.forEach((error) => {
        errorMap[error.field] = error.message;
      });
      setErrors(errorMap);

      // Mark all fields as touched
      const allTouched: Record<string, boolean> = {};
      if (schema.properties) {
        Object.keys(schema.properties).forEach((field) => {
          allTouched[field] = true;
        });
      }
      setTouched(allTouched);

      return;
    }

    // Clear errors and submit
    setErrors({});
    await onSubmit(values);
  };

  if (!schema.properties) {
    return <div className="form-error">Invalid schema: no properties defined</div>;
  }

  return (
    <form onSubmit={handleSubmit} className="json-schema-form">
      {Object.entries(schema.properties).map(([fieldName, fieldSchema]) => {
        const isRequired = schema.required?.includes(fieldName) || false;
        const fieldError = touched[fieldName] ? errors[fieldName] : undefined;

        return (
          <SchemaFieldRenderer
            key={fieldName}
            name={fieldName}
            schema={fieldSchema}
            value={values[fieldName]}
            onChange={(value) => handleFieldChange(fieldName, value)}
            error={fieldError}
            required={isRequired}
          />
        );
      })}

      <div className="form-actions">
        <button 
          type="submit" 
          className="px-6 py-2 bg-white hover:bg-zinc-100 text-black rounded-lg font-medium transition-all duration-200" 
          disabled={loading}
          style={{ opacity: loading ? 0.5 : 1, cursor: loading ? 'not-allowed' : 'pointer' }}
        >
          {loading ? 'Loading...' : submitLabel}
        </button>
      </div>

      {Object.keys(errors).length > 0 && (
        <div className="form-summary-error">
          Please fix the errors above before submitting.
        </div>
      )}
    </form>
  );
};
