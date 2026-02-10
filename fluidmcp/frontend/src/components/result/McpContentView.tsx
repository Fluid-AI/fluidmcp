import React from 'react';

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
    return (
      <div style={{ 
        padding: '1rem',
        color: 'rgba(255, 255, 255, 0.6)',
        textAlign: 'center'
      }}>
        No content to display
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      {content.map((item, index) => {
        // Handle text content
        if (item.type === 'text' && item.text) {
          // Type guard: ensure text is a string
          if (typeof item.text !== 'string') {
            return (
              <div 
                key={index} 
                style={{
                  padding: '1rem',
                  background: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  borderRadius: '0.5rem',
                  color: '#fca5a5'
                }}
              >
                <strong>⚠️ Text Validation Failed:</strong> Invalid text data type
              </div>
            );
          }

          return (
            <div 
              key={index} 
              style={{
                padding: '1.5rem',
                background: 'linear-gradient(to bottom right, rgba(59, 130, 246, 0.05), rgba(139, 92, 246, 0.05))',
                border: '1px solid rgba(99, 102, 241, 0.2)',
                borderRadius: '0.75rem'
              }}
            >
              <div style={{ 
                color: '#e5e7eb',
                fontSize: '1rem',
                lineHeight: '1.8',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                fontFamily: 'system-ui, -apple-system, sans-serif'
              }}>
                {item.text}
              </div>
            </div>
          );
        }

        // Handle image content
        if (item.type === 'image' && item.data && item.mimeType) {
          // Type guards: ensure data and mimeType are strings
          if (typeof item.data !== 'string' || typeof item.mimeType !== 'string') {
            return (
              <div 
                key={index} 
                style={{
                  padding: '1rem',
                  background: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  borderRadius: '0.5rem',
                  color: '#fca5a5'
                }}
              >
                <strong>⚠️ Image Validation Failed:</strong> Invalid image data type
              </div>
            );
          }

          const validation = validateImage(item.data, item.mimeType);

          if (!validation.valid) {
            return (
              <div 
                key={index} 
                style={{
                  padding: '1rem',
                  background: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  borderRadius: '0.5rem',
                  color: '#fca5a5'
                }}
              >
                <strong>⚠️ Image Validation Failed:</strong> {validation.error}
              </div>
            );
          }

          const imageUrl = `data:${item.mimeType};base64,${item.data}`;
          return (
            <div 
              key={index} 
              style={{
                padding: '1rem',
                background: 'rgba(0, 0, 0, 0.2)',
                borderRadius: '0.5rem'
              }}
            >
              <img 
                src={imageUrl} 
                alt={`Result ${index + 1}`}
                style={{
                  maxWidth: '100%',
                  height: 'auto',
                  borderRadius: '0.375rem'
                }}
              />
              <div style={{ 
                marginTop: '0.5rem',
                fontSize: '0.875rem',
                color: 'rgba(255, 255, 255, 0.6)'
              }}>
                <span>{item.mimeType}</span>
              </div>
            </div>
          );
        }

        // Handle resource content (URLs)
        if (item.type === 'resource' && item.uri) {
          // Type guard: ensure URI is a string
          if (typeof item.uri !== 'string') {
            return (
              <div 
                key={index} 
                style={{
                  padding: '1rem',
                  background: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  borderRadius: '0.5rem',
                  color: '#fca5a5'
                }}
              >
                <strong>⚠️ URL Validation Failed:</strong> Invalid URI data type
              </div>
            );
          }

          if (!isSafeUrl(item.uri)) {
            return (
              <div 
                key={index} 
                style={{
                  padding: '1rem',
                  background: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  borderRadius: '0.5rem',
                  color: '#fca5a5'
                }}
              >
                <strong>⚠️ Unsafe URL:</strong> <code>{item.uri}</code>
                <p style={{ marginTop: '0.5rem', fontSize: '0.875rem' }}>
                  Only HTTP and HTTPS URLs are allowed for security reasons.
                </p>
              </div>
            );
          }

          return (
            <div 
              key={index} 
              style={{
                padding: '1rem',
                background: 'rgba(0, 0, 0, 0.2)',
                borderRadius: '0.5rem'
              }}
            >
              <a 
                href={item.uri} 
                target="_blank" 
                rel="noopener noreferrer"
                style={{
                  color: '#60a5fa',
                  textDecoration: 'none',
                  transition: 'color 0.2s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.color = '#93c5fd'}
                onMouseLeave={(e) => e.currentTarget.style.color = '#60a5fa'}
              >
                {item.uri}
              </a>
            </div>
          );
        }

        // Fallback for unknown types
        return (
          <div 
            key={index} 
            style={{
              padding: '1rem',
              background: 'rgba(0, 0, 0, 0.2)',
              borderRadius: '0.5rem'
            }}
          >
            <pre style={{ 
              margin: 0,
              color: '#e5e7eb',
              fontSize: '0.875rem',
              lineHeight: '1.6',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word'
            }}>
              {JSON.stringify(item, null, 2)}
            </pre>
          </div>
        );
      })}
    </div>
  );
};
