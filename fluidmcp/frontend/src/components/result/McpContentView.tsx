import React from 'react';
import './McpContentView.css';

interface McpContent {
  type: string;
  text?: string;
  data?: string;
  mimeType?: string;
}

interface McpContentViewProps {
  content: McpContent[];
}

export const McpContentView: React.FC<McpContentViewProps> = ({ content }) => {
  if (!Array.isArray(content) || content.length === 0) {
    return <div className="mcp-content-empty">No content to display</div>;
  }

  return (
    <div className="mcp-content-container">
      {content.map((item, index) => {
        // Handle text content
        if (item.type === 'text' && item.text) {
          return (
            <div key={index} className="mcp-content-text">
              <pre>{item.text}</pre>
            </div>
          );
        }

        // Handle image content
        if (item.type === 'image' && item.data && item.mimeType) {
          const imageUrl = `data:${item.mimeType};base64,${item.data}`;
          return (
            <div key={index} className="mcp-content-image">
              <img src={imageUrl} alt={`Result ${index + 1}`} />
              <div className="mcp-content-image-info">
                <span className="mcp-content-mime">{item.mimeType}</span>
              </div>
            </div>
          );
        }

        // Handle resource content (URLs)
        if (item.type === 'resource' && 'uri' in item) {
          const uri = (item as any).uri;
          return (
            <div key={index} className="mcp-content-resource">
              <a href={uri} target="_blank" rel="noopener noreferrer">
                {uri}
              </a>
            </div>
          );
        }

        // Fallback for unknown types
        return (
          <div key={index} className="mcp-content-unknown">
            <pre>{JSON.stringify(item, null, 2)}</pre>
          </div>
        );
      })}
    </div>
  );
};
