import React, { useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Icons } from './Icons';

export type AlertType = 'success' | 'error' | 'warning' | 'info';

export interface AlertConfig {
  isOpen: boolean;
  type: AlertType;
  title: string;
  message: string;
}

interface AlertModalProps {
  config: AlertConfig;
  onClose: () => void;
}

const alertStyles: Record<AlertType, { icon: React.ReactNode; bg: string; border: string; text: string }> = {
  success: {
    icon: <Icons.CheckCircle className="w-6 h-6" />,
    bg: 'bg-emerald-50 dark:bg-emerald-900/20',
    border: 'border-emerald-200 dark:border-emerald-800',
    text: 'text-emerald-600 dark:text-emerald-400',
  },
  error: {
    icon: <Icons.AlertCircle className="w-6 h-6" />,
    bg: 'bg-rose-50 dark:bg-rose-900/20',
    border: 'border-rose-200 dark:border-rose-800',
    text: 'text-rose-600 dark:text-rose-400',
  },
  warning: {
    icon: <Icons.AlertTriangle className="w-6 h-6" />,
    bg: 'bg-amber-50 dark:bg-amber-900/20',
    border: 'border-amber-200 dark:border-amber-800',
    text: 'text-amber-600 dark:text-amber-400',
  },
  info: {
    icon: <Icons.Info className="w-6 h-6" />,
    bg: 'bg-blue-50 dark:bg-blue-900/20',
    border: 'border-blue-200 dark:border-blue-800',
    text: 'text-blue-600 dark:text-blue-400',
  },
};

const AlertModal: React.FC<AlertModalProps> = ({ config, onClose }) => {
  const { isOpen, type, title, message } = config;
  const style = alertStyles[type];

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape' || e.key === 'Enter') {
      onClose();
    }
  }, [onClose]);

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen, handleKeyDown]);

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          onClick={onClose}
        >
          {/* Backdrop */}
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />
          
          {/* Modal */}
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            transition={{ type: 'spring', duration: 0.3 }}
            onClick={(e) => e.stopPropagation()}
            className={`relative w-full max-w-md rounded-2xl border ${style.border} ${style.bg} p-6 shadow-xl`}
          >
            {/* Close button */}
            <button
              onClick={onClose}
              className="absolute right-4 top-4 p-1 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
            >
              <Icons.X className="w-5 h-5 text-slate-400" />
            </button>

            {/* Content */}
            <div className="flex items-start gap-4">
              <div className={`flex-shrink-0 ${style.text}`}>
                {style.icon}
              </div>
              <div className="flex-1 min-w-0">
                <h3 className={`text-lg font-semibold ${style.text}`}>
                  {title}
                </h3>
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                  {message}
                </p>
              </div>
            </div>

            {/* Action button */}
            <div className="mt-6 flex justify-end">
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={onClose}
                className={`px-4 py-2 rounded-xl font-medium text-sm ${style.text} hover:bg-black/5 dark:hover:bg-white/5 border ${style.border} transition-colors`}
              >
                OK
              </motion.button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

// Hook for easier state management
export const useAlert = () => {
  const [alertConfig, setAlertConfig] = React.useState<AlertConfig>({
    isOpen: false,
    type: 'info',
    title: '',
    message: '',
  });

  const showAlert = (type: AlertType, title: string, message: string = '') => {
    setAlertConfig({ isOpen: true, type, title, message });
  };

  const closeAlert = () => {
    setAlertConfig(prev => ({ ...prev, isOpen: false }));
  };

  return { alertConfig, showAlert, closeAlert };
};

export default AlertModal;
