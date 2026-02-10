import React, { useState, useEffect } from 'react';

interface JsonNodeProps {
  data: unknown;
  name?: string;
  expandAll?: boolean;
}

const JsonNode: React.FC<JsonNodeProps> = ({ data, name, expandAll = false }) => {
  const [isCollapsed, setIsCollapsed] = useState(!expandAll);

  // Sync with parent expand/collapse control
  useEffect(() => {
    setIsCollapsed(!expandAll);
  }, [expandAll]);

  if (data === null) {
    return (
      <div style={{ marginBottom: '0.35rem' }}>
        {name && <span style={{ color: '#93c5fd', marginRight: '0.5rem', fontWeight: '500' }}>{name}: </span>}
        <span style={{ color: '#6b7280', fontStyle: 'italic' }}>null</span>
      </div>
    );
  }

  if (data === undefined) {
    return (
      <div style={{ marginBottom: '0.35rem' }}>
        {name && <span style={{ color: '#93c5fd', marginRight: '0.5rem', fontWeight: '500' }}>{name}: </span>}
        <span style={{ color: '#6b7280', fontStyle: 'italic' }}>undefined</span>
      </div>
    );
  }

  const type = typeof data;

  // Primitives
  if (type === 'string') {
    const strData = data as string;
    return (
      <div style={{ marginBottom: '0.35rem' }}>
        {name && <span style={{ color: '#93c5fd', marginRight: '0.5rem', fontWeight: '500' }}>{name}: </span>}
        <span style={{ color: '#86efac' }}>"{strData}"</span>
      </div>
    );
  }

  if (type === 'number') {
    return (
      <div style={{ marginBottom: '0.35rem' }}>
        {name && <span style={{ color: '#93c5fd', marginRight: '0.5rem', fontWeight: '500' }}>{name}: </span>}
        <span style={{ color: '#fbbf24' }}>{String(data)}</span>
      </div>
    );
  }

  if (type === 'boolean') {
    return (
      <div style={{ marginBottom: '0.35rem' }}>
        {name && <span style={{ color: '#93c5fd', marginRight: '0.5rem', fontWeight: '500' }}>{name}: </span>}
        <span style={{ color: '#c084fc' }}>{String(data)}</span>
      </div>
    );
  }

  // Arrays
  if (Array.isArray(data)) {
    if (data.length === 0) {
      return (
        <div style={{ marginBottom: '0.35rem' }}>
          {name && <span style={{ color: '#93c5fd', marginRight: '0.5rem', fontWeight: '500' }}>{name}: </span>}
          <span style={{ color: '#e5e7eb' }}>[]</span>
        </div>
      );
    }

    return (
      <div style={{ marginBottom: '0.35rem' }}>
        {name && <span style={{ color: '#93c5fd', marginRight: '0.5rem', fontWeight: '500' }}>{name}: </span>}
        <span
          onClick={() => setIsCollapsed(!isCollapsed)}
          style={{ 
            cursor: 'pointer', 
            userSelect: 'none',
            color: '#9ca3af',
            marginRight: '0.5rem',
            fontSize: '0.85rem'
          }}
        >
          {isCollapsed ? '▶' : '▼'}
        </span>
        <span style={{ color: '#e5e7eb' }}>{isCollapsed ? `[${data.length} items]` : '['}</span>
        {!isCollapsed && (
          <div style={{ marginLeft: '2rem', marginTop: '0.25rem' }}>
            {data.map((item, idx) => (
              <JsonNode key={idx} name={`[${idx}]`} data={item} expandAll={expandAll} />
            ))}
            <div style={{ color: '#e5e7eb', marginTop: '0.25rem' }}>]</div>
          </div>
        )}
      </div>
    );
  }

  // Objects
  if (type === 'object') {
    const objData = data as Record<string, unknown>;
    const keys = Object.keys(objData);
    if (keys.length === 0) {
      return (
        <div style={{ marginBottom: '0.35rem' }}>
          {name && <span style={{ color: '#93c5fd', marginRight: '0.5rem', fontWeight: '500' }}>{name}: </span>}
          <span style={{ color: '#e5e7eb' }}>{'{}'}</span>
        </div>
      );
    }

    return (
      <div style={{ marginBottom: '0.35rem' }}>
        {name && <span style={{ color: '#93c5fd', marginRight: '0.5rem', fontWeight: '500' }}>{name}: </span>}
        <span
          onClick={() => setIsCollapsed(!isCollapsed)}
          style={{ 
            cursor: 'pointer', 
            userSelect: 'none',
            color: '#9ca3af',
            marginRight: '0.5rem',
            fontSize: '0.85rem'
          }}
        >
          {isCollapsed ? '▶' : '▼'}
        </span>
        <span style={{ color: '#e5e7eb' }}>{isCollapsed ? `{${keys.length} keys}` : '{'}</span>
        {!isCollapsed && (
          <div style={{ marginLeft: '2rem', marginTop: '0.25rem' }}>
            {keys.map((key) => (
              <JsonNode key={key} name={key} data={objData[key]} expandAll={expandAll} />
            ))}
            <div style={{ color: '#e5e7eb', marginTop: '0.25rem' }}>{'}'}</div>
          </div>
        )}
      </div>
    );
  }

  return <div style={{ marginBottom: '0.35rem', color: '#e5e7eb' }}>{String(data)}</div>;
};

interface JsonResultViewProps {
  data: unknown;
  expandAll?: boolean;
}

export const JsonResultView: React.FC<JsonResultViewProps> = ({ data, expandAll = false }) => {
  return (
    <div style={{ 
      fontFamily: 'ui-monospace, monospace',
      fontSize: '0.95rem',
      lineHeight: '1.8',
      padding: '0.5rem 0'
    }}>
      <JsonNode data={data} expandAll={expandAll} />
    </div>
  );
};
