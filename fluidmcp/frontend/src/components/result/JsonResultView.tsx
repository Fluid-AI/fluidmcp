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
      <div className="json-line">
        {name && <span className="json-key">{name}: </span>}
        <span className="json-null">null</span>
      </div>
    );
  }

  if (data === undefined) {
    return (
      <div className="json-line">
        {name && <span className="json-key">{name}: </span>}
        <span className="json-null">undefined</span>
      </div>
    );
  }

  const type = typeof data;

  // Primitives
  if (type === 'string') {
    const strData = data as string;
    return (
      <div className="json-line">
        {name && <span className="json-key">{name}: </span>}
        <span className="json-string">"{strData}"</span>
      </div>
    );
  }

  if (type === 'number' || type === 'boolean') {
    return (
      <div className="json-line">
        {name && <span className="json-key">{name}: </span>}
        <span className={`json-${type}`}>{String(data)}</span>
      </div>
    );
  }

  // Arrays
  if (Array.isArray(data)) {
    if (data.length === 0) {
      return (
        <div className="json-line">
          {name && <span className="json-key">{name}: </span>}
          <span>[]</span>
        </div>
      );
    }

    return (
      <div className="json-line">
        {name && <span className="json-key">{name}: </span>}
        <span
          className="json-toggle"
          onClick={() => setIsCollapsed(!isCollapsed)}
        >
          {isCollapsed ? '▶' : '▼'}
        </span>
        <span>{isCollapsed ? `[${data.length} items]` : '['}</span>
        {!isCollapsed && (
          <div className="json-children">
            {data.map((item, idx) => (
              <JsonNode key={idx} name={`[${idx}]`} data={item} expandAll={expandAll} />
            ))}
            <div>]</div>
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
        <div className="json-line">
          {name && <span className="json-key">{name}: </span>}
          <span>{'{}'}</span>
        </div>
      );
    }

    return (
      <div className="json-line">
        {name && <span className="json-key">{name}: </span>}
        <span
          className="json-toggle"
          onClick={() => setIsCollapsed(!isCollapsed)}
        >
          {isCollapsed ? '▶' : '▼'}
        </span>
        <span>{isCollapsed ? `{${keys.length} keys}` : '{'}</span>
        {!isCollapsed && (
          <div className="json-children">
            {keys.map((key) => (
              <JsonNode key={key} name={key} data={objData[key]} expandAll={expandAll} />
            ))}
            <div>{'}'}</div>
          </div>
        )}
      </div>
    );
  }

  return <div className="json-line">{String(data)}</div>;
};

interface JsonResultViewProps {
  data: unknown;
  expandAll?: boolean;
}

export const JsonResultView: React.FC<JsonResultViewProps> = ({ data, expandAll = false }) => {
  return (
    <div className="json-viewer">
      <JsonNode data={data} expandAll={expandAll} />
    </div>
  );
};
