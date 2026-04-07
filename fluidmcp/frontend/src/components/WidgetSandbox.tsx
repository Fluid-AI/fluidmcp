import { useEffect, useRef, useState } from 'react';
import apiClient from '@/services/api';

interface WidgetSandboxProps {
  sessionId: string;
  resourceUri: string;
  toolInput: Record<string, any>;
  toolResult: any;
}

export function WidgetSandbox({ sessionId, resourceUri, toolInput, toolResult }: WidgetSandboxProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(300);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [errorMsg, setErrorMsg] = useState('');
  // Tracks pending requests WE sent to the widget (id → resolve/reject)
  const pendingRef = useRef<Map<number, { resolve: (v: any) => void; reject: (e: any) => void }>>(new Map());
  // Fallback timeout: if widget doesn't complete MCP handshake, auto-clear loading state
  const readyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;

    // Send a message to the proxy iframe (which forwards to the inner widget iframe)
    const sendToProxy = (data: any) => {
      iframe.contentWindow?.postMessage(data, '*');
    };

    const handleMessage = async (event: MessageEvent) => {
      // Only handle messages from our proxy iframe
      if (event.source !== iframe.contentWindow) return;
      const msg = event.data;
      if (!msg || typeof msg !== 'object') return;

      // If this is a response to a request WE sent (has id + result/error, no method)
      if (msg.id !== undefined && !msg.method && (msg.result !== undefined || msg.error !== undefined)) {
        const pending = pendingRef.current.get(msg.id);
        if (pending) {
          pendingRef.current.delete(msg.id);
          if (msg.error) pending.reject(new Error(msg.error.message || 'Widget error'));
          else pending.resolve(msg.result);
        }
        return;
      }

      // Requests / notifications FROM the widget
      const method: string = msg.method;
      if (!method) return;

      // ── Proxy is ready: fetch widget HTML and load it ──────────────────────
      if (method === 'ui/notifications/sandbox-proxy-ready') {
        try {
          const res = await apiClient.readInspectorResource(sessionId, resourceUri);
          const html: string = res?.text || res?.content || '';
          if (!html) {
            setStatus('error');
            setErrorMsg('Widget resource returned empty HTML');
            return;
          }
          sendToProxy({
            jsonrpc: '2.0',
            method: 'ui/notifications/sandbox-resource-ready',
            params: { html },
          });
          // Fallback: if the widget doesn't implement the MCP UI handshake,
          // auto-clear the loading overlay after 2 s so the widget is visible.
          readyTimeoutRef.current = setTimeout(() => {
            setStatus(prev => prev === 'loading' ? 'ready' : prev);
          }, 2000);
        } catch (e: any) {
          setStatus('error');
          setErrorMsg(`Failed to load widget: ${e.message}`);
        }
        return;
      }

      // ── Widget handshake ───────────────────────────────────────────────────
      if (method === 'ui/initialize') {
        sendToProxy({
          jsonrpc: '2.0',
          id: msg.id,
          result: {
            protocolVersion: '2025-06-18',
            hostInfo: { name: 'FluidMCP Inspector', version: '1.0.0' },
            hostCapabilities: {},
          },
        });
        return;
      }

      if (method === 'ui/notifications/initialized') {
        if (readyTimeoutRef.current) clearTimeout(readyTimeoutRef.current);
        setStatus('ready');
        // Send tool arguments to widget
        sendToProxy({
          jsonrpc: '2.0',
          method: 'ui/notifications/tool-input',
          params: { arguments: toolInput },
        });
        // Send structured result data (structuredContent for widget, not LLM)
        const raw = toolResult?.result ?? toolResult ?? {};
        const structuredContent = raw.structuredContent ?? null;
        const content = raw.content ?? [];
        if (structuredContent !== null || content.length > 0) {
          sendToProxy({
            jsonrpc: '2.0',
            method: 'ui/notifications/tool-result',
            params: { content, structuredContent },
          });
        }
        return;
      }

      // ── Widget requests a tool call ────────────────────────────────────────
      if (method === 'tools/call') {
        const { name, arguments: args } = msg.params || {};
        try {
          const result = await apiClient.runInspectorTool(sessionId, name, args || {});
          sendToProxy({ jsonrpc: '2.0', id: msg.id, result });
        } catch (e: any) {
          sendToProxy({ jsonrpc: '2.0', id: msg.id, error: { code: -32000, message: e.message } });
        }
        return;
      }

      // ── Widget reads a resource ────────────────────────────────────────────
      if (method === 'resources/read') {
        const { uri } = msg.params || {};
        try {
          const result = await apiClient.readInspectorResource(sessionId, uri);
          sendToProxy({ jsonrpc: '2.0', id: msg.id, result });
        } catch (e: any) {
          sendToProxy({ jsonrpc: '2.0', id: msg.id, error: { code: -32000, message: e.message } });
        }
        return;
      }

      // ── Widget resizes itself ──────────────────────────────────────────────
      if (method === 'ui/notifications/size-change') {
        const { height: h } = msg.params || {};
        if (typeof h === 'number' && h > 0) {
          setHeight(Math.min(h + 20, 800));
        }
        return;
      }

      // ── Widget wants to open a link ────────────────────────────────────────
      if (method === 'ui/open-link') {
        const { url } = msg.params || {};
        if (url) window.open(url, '_blank', 'noopener,noreferrer');
        if (msg.id !== undefined) sendToProxy({ jsonrpc: '2.0', id: msg.id, result: {} });
        return;
      }

      // ── Widget injects a message into chat ─────────────────────────────────
      if (method === 'ui/message') {
        // Future: bubble up to chat. For now, just ack.
        if (msg.id !== undefined) sendToProxy({ jsonrpc: '2.0', id: msg.id, result: {} });
        return;
      }
    };

    window.addEventListener('message', handleMessage);
    return () => {
      window.removeEventListener('message', handleMessage);
      pendingRef.current.clear();
      if (readyTimeoutRef.current) clearTimeout(readyTimeoutRef.current);
    };
  }, [sessionId, resourceUri, toolInput, toolResult]);

  if (status === 'error') {
    return (
      <div style={{
        marginTop: '0.5rem', padding: '0.5rem 0.75rem',
        fontSize: '0.75rem', color: '#fca5a5',
        background: 'rgba(239,68,68,0.1)',
        border: '1px solid rgba(239,68,68,0.3)',
        borderRadius: '6px',
      }}>
        Widget error: {errorMsg}
      </div>
    );
  }

  return (
    <div style={{
      marginTop: '0.6rem',
      borderRadius: '8px',
      overflow: 'hidden',
      border: '1px solid rgba(99,102,241,0.35)',
      background: '#fff',
      position: 'relative',
    }}>
      {status === 'loading' && (
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'rgba(9,9,11,0.7)', fontSize: '0.75rem',
          color: 'rgba(255,255,255,0.5)', zIndex: 1,
        }}>
          Loading widget...
        </div>
      )}
      <iframe
        ref={iframeRef}
        src={`${import.meta.env.BASE_URL}sandbox-proxy.html`}
        sandbox="allow-scripts allow-same-origin allow-forms"
        title="MCP Widget"
        style={{
          width: '100%',
          height: `${height}px`,
          border: 'none',
          display: 'block',
          transition: 'height 0.15s ease',
        }}
      />
    </div>
  );
}
