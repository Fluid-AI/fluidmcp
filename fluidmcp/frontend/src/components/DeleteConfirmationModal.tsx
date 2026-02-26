import { useState } from 'react';
import { Server } from '../types/server';

interface DeleteConfirmationModalProps {
  server: Server;
  onDisable: () => Promise<void>;
  onDelete: () => Promise<void>;
  onCancel: () => void;
}

type Step = 'choose' | 'confirm-delete';

export const DeleteConfirmationModal: React.FC<DeleteConfirmationModalProps> = ({
  server,
  onDisable,
  onDelete,
  onCancel,
}) => {
  const [step, setStep] = useState<Step>('choose');
  const [processing, setProcessing] = useState(false);

  const handleDisable = async () => {
    setProcessing(true);
    try {
      await onDisable();
      onCancel();
    } finally {
      setProcessing(false);
    }
  };

  const handleConfirmDelete = async () => {
    setProcessing(true);
    try {
      await onDelete();
      onCancel();
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <div className="relative bg-gradient-to-br from-zinc-900 to-zinc-800 border border-zinc-700 rounded-xl shadow-2xl max-w-lg w-full p-6">
        {step === 'choose' ? (
          <>
            <h2 className="text-2xl font-bold text-white mb-4">
              What would you like to do?
            </h2>
            <p className="text-zinc-400 mb-6">
              Choose how to handle "{server.name}"
            </p>

            {/* Disable Option */}
            <div className="mb-4 p-4 bg-zinc-800/50 border border-zinc-700 rounded-lg hover:border-blue-500 transition-colors">
              <div className="flex items-start space-x-3">
                <div className="text-2xl">🔒</div>
                <div className="flex-1">
                  <h3 className="font-semibold text-white mb-1">Disable Server</h3>
                  <p className="text-sm text-zinc-400 mb-3">
                    Hides from Dashboard. You can re-enable later.
                  </p>
                  <button
                    onClick={handleDisable}
                    disabled={processing}
                    className="px-4 py-2 bg-yellow-600 text-white rounded-lg hover:bg-yellow-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {processing ? 'Disabling...' : 'Disable'}
                  </button>
                </div>
              </div>
            </div>

            {/* Delete Option */}
            <div className="mb-6 p-4 bg-zinc-800/50 border border-zinc-700 rounded-lg hover:border-red-500 transition-colors">
              <div className="flex items-start space-x-3">
                <div className="text-2xl">🗑️</div>
                <div className="flex-1">
                  <h3 className="font-semibold text-white mb-1">Delete Server</h3>
                  <p className="text-sm text-zinc-400 mb-3">
                    Permanent removal. Only admins can recover.
                  </p>
                  <button
                    onClick={() => setStep('confirm-delete')}
                    disabled={processing}
                    className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>

            {/* Cancel */}
            <div className="flex justify-end">
              <button
                onClick={onCancel}
                disabled={processing}
                className="px-4 py-2 text-zinc-300 bg-zinc-800 rounded-lg hover:bg-zinc-700 transition-colors"
              >
                Cancel
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="text-center mb-6">
              <div className="text-5xl mb-4">⚠️</div>
              <h2 className="text-2xl font-bold text-white mb-2">
                Warning: Irreversible Action
              </h2>
              <p className="text-zinc-400">
                This will permanently delete the server.
              </p>
              <p className="text-zinc-400">
                Only administrators can recover deleted servers.
              </p>
            </div>

            <div className="bg-zinc-800/50 border border-yellow-600/50 rounded-lg p-4 mb-6">
              <p className="text-sm text-white font-medium mb-1">Server: {server.name}</p>
              <p className="text-xs text-zinc-400 font-mono">ID: {server.id}</p>
            </div>

            <p className="text-center text-zinc-300 mb-6">
              Are you sure you want to continue?
            </p>

            <div className="flex justify-center space-x-3">
              <button
                onClick={() => setStep('choose')}
                disabled={processing}
                className="px-6 py-2 text-zinc-300 bg-zinc-800 rounded-lg hover:bg-zinc-700 transition-colors"
              >
                Go Back
              </button>
              <button
                onClick={handleConfirmDelete}
                disabled={processing}
                className="px-6 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {processing ? 'Deleting...' : 'Confirm Delete'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
