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

// Allowed image MIME types (SVG removed due to XSS risk)
const ALLOWED_IMAGE_MIMES = [
  'image/png',
  'image/jpeg',
  'image/jpg',
  'image/gif',
  'image/webp'
];

const MAX_IMAGE_SIZE_MB = 10;

// Validate base64 string
function isValidBase64(data: string): boolean {
  // Check for empty strings
  if (!data || data.length === 0) {
    return false;
  }

  // Base64 length must be multiple of 4
  if (data.length % 4 !== 0) {
    return false;
  }

  // Check if string contains only valid base64 characters
  // Valid base64: A-Za-z0-9+/ with up to 2 '=' padding at the end
  return /^[A-Za-z0-9+/]*={0,2}$/.test(data);
}

// Validate image data
function validateImage(data: string, mimeType: string): { valid: boolean; error?: string } {
  // Check base64 validity first
  if (!isValidBase64(data)) {
    return { valid: false, error: 'Invalid base64 data' };
  }

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
  // Block protocol-relative URLs and dangerous schemes
  if (uri.startsWith('//') ||
      uri.startsWith('javascript:') ||
      uri.startsWith('data:') ||
      uri.startsWith('file:') ||
      uri.startsWith('vbscript:')) {
    return false;
  }

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
          // Type guard: ensure text is a string
          if (typeof item.text !== 'string') {
            return (
              <div key={index} className="mcp-content-warning">
                <strong>⚠️ Text Validation Failed:</strong> Invalid text data type
              </div>
            );
          }

          return (
            <div key={index} className="mcp-content-text">
              <pre>{item.text}</pre>
            </div>
          );
        }

        // Handle image content
        if (item.type === 'image' && item.data && item.mimeType) {
          // Type guards: ensure data and mimeType are strings
          if (typeof item.data !== 'string' || typeof item.mimeType !== 'string') {
            return (
              <div key={index} className="mcp-content-warning">
                <strong>⚠️ Image Validation Failed:</strong> Invalid image data type
              </div>
            );
          }

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
          // Type guard: ensure URI is a string
          if (typeof item.uri !== 'string') {
            return (
              <div key={index} className="mcp-content-warning">
                <strong>⚠️ URL Validation Failed:</strong> Invalid URI data type
              </div>
            );
          }

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
