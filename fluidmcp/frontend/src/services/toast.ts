import toast from 'react-hot-toast';

/**
 * Toast utility service for FluidMCP
 * Wrapper around react-hot-toast with pre-configured styling
 */

const baseStyle = {
  background: '#1e293b',
  color: '#f1f5f9',
  borderRadius: '8px',
  padding: '12px 16px',
  fontSize: '14px',
  boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
};

export const showSuccess = (message: string, id?: string) => {
  return toast.success(message, {
    id,
    duration: 4000,
    style: baseStyle,
    iconTheme: {
      primary: '#22c55e',
      secondary: '#1e293b',
    },
  });
};

export const showError = (message: string, id?: string) => {
  return toast.error(message, {
    id,
    duration: 5000, // Slightly longer for errors
    style: baseStyle,
    iconTheme: {
      primary: '#ef4444',
      secondary: '#1e293b',
    },
  });
};

export const showInfo = (message: string, id?: string) => {
  return toast(message, {
    id,
    duration: 4000,
    style: baseStyle,
    icon: 'ℹ️',
  });
};

export const showWarning = (message: string, id?: string) => {
  return toast(message, {
    id,
    duration: 4000,
    style: {
      ...baseStyle,
      borderLeft: '4px solid #eab308',
    },
    icon: '⚠️',
  });
};

export const showLoading = (message: string, id?: string) => {
  return toast.loading(message, {
    id,
    style: baseStyle,
  });
};

export const dismissToast = (id?: string) => {
  if (id) {
    toast.dismiss(id);
  } else {
    toast.dismiss();
  }
};

export const dismissAll = () => {
  toast.dismiss();
};

// Default export for convenience
export default {
  success: showSuccess,
  error: showError,
  info: showInfo,
  warning: showWarning,
  loading: showLoading,
  dismiss: dismissToast,
  dismissAll,
};
