import React, { useState } from 'react';

interface JsonNodeProps {
  data: any;
  depth: number;
  name?: string;
}

const JsonNode: React.FC<JsonNodeProps> = ({ data, depth, name }) => {
  const [isCollapsed, setIsCollapsed] = useState(depth > 2);

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
    return (
      <div className="json-line">
        {name && <span className="json-key">{name}: </span>}
        <span className="json-string">"{data}"</span>
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
          <div style={{ paddingLeft: '1rem' }}>
            {data.map((item, idx) => (
              <JsonNode key={idx} data={item} depth={depth + 1} />
            ))}
            <div>]</div>
          </div>
        )}
      </div>
    );
  }

  // Objects
  if (type === 'object') {
    const keys = Object.keys(data);
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
          <div style={{ paddingLeft: '1rem' }}>
            {keys.map((key) => (
              <JsonNode key={key} name={key} data={data[key]} depth={depth + 1} />
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
  data: any;
  initialDepth?: number;
}

export const JsonResultView: React.FC<JsonResultViewProps> = ({
  data,
  initialDepth = 2,
}) => {
  return (
    <div className="json-viewer">
      <JsonNode data={data} depth={0} />
    </div>
  );
};
