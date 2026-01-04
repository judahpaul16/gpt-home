import React, { useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Icons } from './Icons';

export interface ConfirmConfig {
  isOpen: boolean;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  variant?: 'default' | 'danger';
  onConfirm: () => void;
}

interface ConfirmModalProps {
  config: ConfirmConfig;
  onClose: () => void;
}

const ConfirmModal: React.FC<ConfirmModalProps> = ({ config, onClose }) => {
  const { isOpen, title, message, confirmText = 'Confirm', cancelText = 'Cancel', variant = 'default', onConfirm } = config;
  const confirmButtonRef = useRef<HTMLButtonElement>(null);

  const handleConfirm = useCallback(() => {
    onConfirm();
    onClose();
  }, [onConfirm, onClose]);

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
    } else if (e.key === 'Enter') {
      handleConfirm();
    }
  }, [onClose, handleConfirm]);

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      confirmButtonRef.current?.focus();
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen, handleKeyDown]);

  const variantStyles = {
    default: {
      icon: <Icons.AlertCircle className="w-6 h-6" />,
      bg: 'bg-slate-50 dark:bg-slate-800',
      border: 'border-slate-200 dark:border-slate-700',
      iconColor: 'text-primary-500',
      confirmBtn: 'bg-primary-500 hover:bg-primary-600 text-white',
    },
    danger: {
      icon: <Icons.AlertTriangle className="w-6 h-6" />,
      bg: 'bg-slate-50 dark:bg-slate-800',
      border: 'border-slate-200 dark:border-slate-700',
      iconColor: 'text-rose-500',
      confirmBtn: 'bg-rose-500 hover:bg-rose-600 text-white',
    },
  };

  const style = variantStyles[variant];

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
            {/* Content */}
            <div className="flex items-start gap-4">
              <div className={`flex-shrink-0 ${style.iconColor}`}>
                {style.icon}
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
                  {title}
                </h3>
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                  {message}
                </p>
              </div>
            </div>

            {/* Action buttons */}
            <div className="mt-6 flex justify-end gap-3">
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={onClose}
                className="px-4 py-2 rounded-xl font-medium text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-600 transition-colors"
              >
                {cancelText}
              </motion.button>
              <motion.button
                ref={confirmButtonRef}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={handleConfirm}
                className={`px-4 py-2 rounded-xl font-medium text-sm ${style.confirmBtn} transition-colors`}
              >
                {confirmText}
              </motion.button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

// Hook for easier state management
export const useConfirm = () => {
  const [confirmConfig, setConfirmConfig] = React.useState<ConfirmConfig>({
    isOpen: false,
    title: '',
    message: '',
    onConfirm: () => {},
  });

  const showConfirm = (
    title: string,
    message: string,
    onConfirm: () => void,
    options?: { confirmText?: string; cancelText?: string; variant?: 'default' | 'danger' }
  ) => {
    setConfirmConfig({
      isOpen: true,
      title,
      message,
      onConfirm,
      ...options,
    });
  };

  const closeConfirm = () => {
    setConfirmConfig(prev => ({ ...prev, isOpen: false }));
  };

  return { confirmConfig, showConfirm, closeConfirm };
};

export default ConfirmModal;
