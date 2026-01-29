import React, { useState } from 'react';
import type { JsonSchemaProperty } from '../../types/server';

interface ArrayInputProps {
  name: string;
  schema: JsonSchemaProperty;
  value: any[];
  onChange: (value: any[]) => void;
  error?: string;
  required?: boolean;
}

export const ArrayInput: React.FC<ArrayInputProps> = ({
  name,
  schema,
  value,
  onChange,
  error,
  required,
}) => {
  const label = schema.title || name;
  const itemSchema = schema.items;

  // Track JSON parse errors for each item
  const [jsonErrors, setJsonErrors] = useState<Record<number, string>>({});

  // Track raw text input for JSON items (allows typing invalid JSON)
  const [jsonText, setJsonText] = useState<Record<number, string>>({});

  // Determine if items are primitives or objects
  const isPrimitiveArray = itemSchema && ['string', 'number', 'integer', 'boolean'].includes(itemSchema.type);

  const handleAddItem = () => {
    if (!itemSchema) return;

    let newItem: any;
    switch (itemSchema.type) {
      case 'string':
        newItem = '';
        break;
      case 'number':
      case 'integer':
        newItem = 0;
        break;
      case 'boolean':
        newItem = false;
        break;
      case 'object':
        newItem = {};
        break;
      default:
        newItem = null;
    }

    onChange([...value, newItem]);
  };

  const handleRemoveItem = (index: number) => {
    const newArray = [...value];
    newArray.splice(index, 1);
    onChange(newArray);
  };

  const handleUpdateItem = (index: number, newValue: any) => {
    const newArray = [...value];
    newArray[index] = newValue;
    onChange(newArray);
  };

  return (
    <div className="form-field array-input">
      <label>
        {label}
        {required && <span className="required">*</span>}
      </label>

      {schema.description && (
        <p className="field-description">{schema.description}</p>
      )}

      <div className="array-items">
        {value.map((item, index) => (
          <div key={index} className="array-item">
            <div className="array-item-content">
              {isPrimitiveArray ? (
                itemSchema.type === 'string' ? (
                  <input
                    type="text"
                    value={item}
                    onChange={(e) => handleUpdateItem(index, e.target.value)}
                    placeholder={`Item ${index + 1}`}
                  />
                ) : itemSchema.type === 'number' || itemSchema.type === 'integer' ? (
                  <input
                    type="number"
                    value={item}
                    onChange={(e) => {
                      const parsed = itemSchema.type === 'integer'
                        ? parseInt(e.target.value, 10)
                        : parseFloat(e.target.value);
                      if (!isNaN(parsed)) {
                        handleUpdateItem(index, parsed);
                      }
                    }}
                    step={itemSchema.type === 'integer' ? '1' : 'any'}
                  />
                ) : itemSchema.type === 'boolean' ? (
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={item}
                      onChange={(e) => handleUpdateItem(index, e.target.checked)}
                    />
                    <span>Item {index + 1}</span>
                  </label>
                ) : null
              ) : (
                <div className="json-input-wrapper">
                  <textarea
                    value={jsonText[index] ?? (typeof item === 'object' ? JSON.stringify(item, null, 2) : String(item))}
                    onChange={(e) => {
                      const newText = e.target.value;
                      // Always update the text (allow typing)
                      setJsonText((prev) => ({ ...prev, [index]: newText }));

                      // Try to parse, but don't block on error
                      try {
                        const parsed = JSON.parse(newText);
                        handleUpdateItem(index, parsed);
                        // Clear error on successful parse
                        setJsonErrors((prev) => {
                          const updated = { ...prev };
                          delete updated[index];
                          return updated;
                        });
                      } catch (err) {
                        // Show error but allow continued typing
                        setJsonErrors((prev) => ({
                          ...prev,
                          [index]: 'Invalid JSON format',
                        }));
                      }
                    }}
                    rows={3}
                    placeholder={`Item ${index + 1} (JSON)`}
                    className={jsonErrors[index] ? 'error' : ''}
                  />
                  {jsonErrors[index] && (
                    <span className="error-message">{jsonErrors[index]}</span>
                  )}
                </div>
              )}
            </div>
            <button
              type="button"
              className="btn-remove"
              onClick={() => handleRemoveItem(index)}
              title="Remove item"
            >
              Remove
            </button>
          </div>
        ))}
      </div>

      <button
        type="button"
        className="btn-add"
        onClick={handleAddItem}
      >
        Add Item
      </button>

      {error && <span className="error-message">{error}</span>}
    </div>
  );
};
