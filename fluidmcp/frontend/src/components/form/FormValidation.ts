import { JsonSchemaProperty } from '../../types/server';

export interface ValidationError {
  field: string;
  message: string;
}

/**
 * Validate a single field value against its JSON Schema property definition
 */
export function validateField(
  fieldName: string,
  value: any,
  schema: JsonSchemaProperty,
  isRequired: boolean = false
): ValidationError | null {
  // Check required
  if (isRequired && (value === null || value === undefined || value === '')) {
    return {
      field: fieldName,
      message: `${schema.title || fieldName} is required`,
    };
  }

  // If not required and empty, skip validation
  if (!isRequired && (value === null || value === undefined || value === '')) {
    return null;
  }

  // Type validation
  const actualType = Array.isArray(value) ? 'array' : typeof value;
  const expectedType = schema.type;

  if (expectedType === 'string') {
    if (actualType !== 'string') {
      return {
        field: fieldName,
        message: `${schema.title || fieldName} must be a string`,
      };
    }

    // String length validation
    if (schema.minLength !== undefined && value.length < schema.minLength) {
      return {
        field: fieldName,
        message: `${schema.title || fieldName} must be at least ${
          schema.minLength
        } characters`,
      };
    }

    if (schema.maxLength !== undefined && value.length > schema.maxLength) {
      return {
        field: fieldName,
        message: `${schema.title || fieldName} must be at most ${
          schema.maxLength
        } characters`,
      };
    }

    // Format validation
    if (schema.format === 'email' && !isValidEmail(value)) {
      return {
        field: fieldName,
        message: `${schema.title || fieldName} must be a valid email address`,
      };
    }

    if (schema.format === 'url' && !isValidUrl(value)) {
      return {
        field: fieldName,
        message: `${schema.title || fieldName} must be a valid URL`,
      };
    }

    // Enum validation
    if (schema.enum && !schema.enum.includes(value)) {
      return {
        field: fieldName,
        message: `${schema.title || fieldName} must be one of: ${schema.enum.join(
          ', '
        )}`,
      };
    }
  } else if (expectedType === 'number' || expectedType === 'integer') {
    const numValue = typeof value === 'string' ? parseFloat(value) : value;

    if (isNaN(numValue)) {
      return {
        field: fieldName,
        message: `${schema.title || fieldName} must be a number`,
      };
    }

    if (expectedType === 'integer' && !Number.isInteger(numValue)) {
      return {
        field: fieldName,
        message: `${schema.title || fieldName} must be an integer`,
      };
    }

    // Number range validation
    if (schema.minimum !== undefined && numValue < schema.minimum) {
      return {
        field: fieldName,
        message: `${schema.title || fieldName} must be at least ${
          schema.minimum
        }`,
      };
    }

    if (schema.maximum !== undefined && numValue > schema.maximum) {
      return {
        field: fieldName,
        message: `${schema.title || fieldName} must be at most ${
          schema.maximum
        }`,
      };
    }
  } else if (expectedType === 'boolean') {
    if (typeof value !== 'boolean') {
      return {
        field: fieldName,
        message: `${schema.title || fieldName} must be a boolean`,
      };
    }
  } else if (expectedType === 'array') {
    if (!Array.isArray(value)) {
      return {
        field: fieldName,
        message: `${schema.title || fieldName} must be an array`,
      };
    }

    // Array length validation
    if (schema.minItems !== undefined && value.length < schema.minItems) {
      return {
        field: fieldName,
        message: `${schema.title || fieldName} must have at least ${
          schema.minItems
        } items`,
      };
    }

    if (schema.maxItems !== undefined && value.length > schema.maxItems) {
      return {
        field: fieldName,
        message: `${schema.title || fieldName} must have at most ${
          schema.maxItems
        } items`,
      };
    }
  } else if (expectedType === 'object') {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) {
      return {
        field: fieldName,
        message: `${schema.title || fieldName} must be an object`,
      };
    }
  }

  return null;
}

/**
 * Validate all form values against the complete schema
 */
export function validateForm(
  values: Record<string, any>,
  schema: {
    type: string;
    properties?: Record<string, JsonSchemaProperty>;
    required?: string[];
  }
): ValidationError[] {
  const errors: ValidationError[] = [];

  if (!schema.properties) {
    return errors;
  }

  // Validate each field
  Object.entries(schema.properties).forEach(([fieldName, fieldSchema]) => {
    const value = values[fieldName];
    const isRequired = schema.required?.includes(fieldName) || false;

    const error = validateField(fieldName, value, fieldSchema, isRequired);
    if (error) {
      errors.push(error);
    }
  });

  return errors;
}

/**
 * Email validation helper
 */
function isValidEmail(email: string): boolean {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
}

/**
 * URL validation helper
 */
function isValidUrl(url: string): boolean {
  try {
    new URL(url);
    return true;
  } catch {
    return false;
  }
}

/**
 * Get default value for a schema property
 */
export function getDefaultValue(schema: JsonSchemaProperty): any {
  if (schema.default !== undefined) {
    return schema.default;
  }

  switch (schema.type) {
    case 'string':
      return '';
    case 'number':
    case 'integer':
      return 0;
    case 'boolean':
      return false;
    case 'array':
      return [];
    case 'object':
      return {};
    default:
      return null;
  }
}

/**
 * Initialize form values from schema
 */
export function initializeFormValues(
  schema: {
    type: string;
    properties?: Record<string, JsonSchemaProperty>;
    required?: string[];
  },
  initialValues?: Record<string, any>
): Record<string, any> {
  const values: Record<string, any> = {};

  if (!schema.properties) {
    return values;
  }

  Object.entries(schema.properties).forEach(([fieldName, fieldSchema]) => {
    if (initialValues && initialValues[fieldName] !== undefined) {
      values[fieldName] = initialValues[fieldName];
    } else {
      values[fieldName] = getDefaultValue(fieldSchema);
    }
  });

  return values;
}
