import React from 'react';
import './McpContentView.css';

interface McpContent {
  type: 'text' | 'image' | 'resource' | string;
  text?: string;
  data?: string;
  mimeType?: string;
  uri?: string;
}

interface McpContentViewProps {
  content: McpContent[];
}

// Allowed image MIME types
const ALLOWED_IMAGE_MIMES = [
  'image/png',
  'image/jpeg',
  'image/jpg',
  'image/gif',
  'image/webp',
  'image/svg+xml'
];

const MAX_IMAGE_SIZE_MB = 10;

// Validate image data
function validateImage(data: string, mimeType: string): { valid: boolean; error?: string } {
  // Check MIME type
  if (!ALLOWED_IMAGE_MIMES.includes(mimeType)) {
    return { valid: false, error: `Unsupported image type: ${mimeType}` };
  }

  // Check size (base64 length * 0.75 ≈ bytes)
  const estimatedBytes = data.length * 0.75;
  const estimatedMB = estimatedBytes / (1024 * 1024);

  if (estimatedMB > MAX_IMAGE_SIZE_MB) {
    return {
      valid: false,
      error: `Image too large: ${estimatedMB.toFixed(1)}MB (max ${MAX_IMAGE_SIZE_MB}MB)`
    };
  }

  return { valid: true };
}

// Validate URL scheme (only allow http/https)
function isSafeUrl(uri: string): boolean {
  try {
    const url = new URL(uri);
    return url.protocol === 'http:' || url.protocol === 'https:';
  } catch {
    return false;
  }
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
          const validation = validateImage(item.data, item.mimeType);

          if (!validation.valid) {
            return (
              <div key={index} className="mcp-content-warning">
                <strong>⚠️ Image Validation Failed:</strong> {validation.error}
              </div>
            );
          }

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
        if (item.type === 'resource' && item.uri) {
          if (!isSafeUrl(item.uri)) {
            return (
              <div key={index} className="mcp-content-warning">
                <strong>⚠️ Unsafe URL:</strong> <code>{item.uri}</code>
                <p className="mcp-content-warning-detail">
                  Only HTTP and HTTPS URLs are allowed for security reasons.
                </p>
              </div>
            );
          }

          return (
            <div key={index} className="mcp-content-resource">
              <a href={item.uri} target="_blank" rel="noopener noreferrer">
                {item.uri}
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
