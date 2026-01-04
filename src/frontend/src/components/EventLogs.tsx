import React, { useEffect, useState, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';
import { Icons, Spinner } from './Icons';
import { cn } from '../lib/utils';
import ConfirmModal, { useConfirm } from './ConfirmModal';

interface Log {
  content: string;
  isNew: boolean;
  type: string;
}

const logTypeColors: { [key: string]: { bg: string; text: string; dot: string } } = {
  success: { bg: 'bg-emerald-100 dark:bg-emerald-900/20', text: 'text-emerald-700 dark:text-emerald-400', dot: 'bg-emerald-500' },
  info: { bg: 'bg-primary-100 dark:bg-primary-900/20', text: 'text-primary-700 dark:text-primary-400', dot: 'bg-primary-500' },
  warning: { bg: 'bg-amber-100 dark:bg-amber-900/20', text: 'text-amber-700 dark:text-amber-400', dot: 'bg-amber-500' },
  error: { bg: 'bg-rose-100 dark:bg-rose-900/20', text: 'text-rose-700 dark:text-rose-400', dot: 'bg-rose-500' },
  critical: { bg: 'bg-rose-200 dark:bg-rose-900/40', text: 'text-rose-800 dark:text-rose-300', dot: 'bg-rose-600' },
  debug: { bg: 'bg-slate-100 dark:bg-slate-800/50', text: 'text-slate-600 dark:text-slate-400', dot: 'bg-slate-400' },
};

const EventLogs: React.FC = () => {
  const [logs, setLogs] = useState<Log[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const [userHasScrolled, setUserHasScrolled] = useState(false);
  const userHasScrolledRef = useRef(false);
  const [initialLogCount, setInitialLogCount] = useState<number | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const { confirmConfig, showConfirm, closeConfirm } = useConfirm();
  const [activeFilters, setActiveFilters] = useState<{ [key: string]: boolean }>({
    warning: true,
    info: true,
    critical: true,
    success: true,
    error: true,
    debug: true,
  });

  const scrollToBottom = useCallback(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
      setUserHasScrolled(false);
      userHasScrolledRef.current = false;
    }
  }, []);

  // Fetch initial logs
  useEffect(() => {
    const fetchAllLogs = async () => {
      try {
        const response = await fetch('/logs', { method: 'POST' });
        const data = await response.json();
        const logLevels = ['SUCCESS', 'INFO', 'ERROR', 'WARNING', 'DEBUG', 'CRITICAL'];
        let logArray = data.log_data.split('\n');
        logArray = logArray.filter((log: string) => log !== '');
        for (let i = 0; i < logArray.length; i++) {
          const log = logArray[i];
          if (!logLevels.some(level => log.startsWith(level))) {
            if (i > 0) {
              logArray[i - 1] += `\n${log}`;
            }
            logArray.splice(i, 1);
            i--;
          }
        }
        const allLogs = logArray.map((log: string) => ({
          content: log,
          isNew: false,
          type: log.split(":")[0].toLowerCase(),
        }));
        setLogs(allLogs);
        setInitialLogCount(allLogs.length);
      } catch (error) {
        console.error('Error fetching initial logs:', error);
        setInitialLogCount(0);
      } finally {
        setIsLoading(false);
      }
    };
    fetchAllLogs();
  }, []);

  // SSE connection for live log updates
  useEffect(() => {
    if (initialLogCount === null) return;

    let reconnectTimeout: NodeJS.Timeout | null = null;
    let isConnecting = false;

    const connectSSE = (startFrom: number) => {
      if (isConnecting) return;
      isConnecting = true;

      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      const eventSource = new EventSource(`/logs/stream?last_line_number=${startFrom}`);
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        isConnecting = false;
      };

      // Handle ping events (heartbeat) - just ignore them, they keep connection alive
      eventSource.addEventListener('ping', () => {
        // Heartbeat received - connection is alive
      });

      eventSource.onmessage = (event) => {
        try {
          // Skip empty data (shouldn't happen but just in case)
          if (!event.data || event.data === '') return;
          
          const logData = JSON.parse(event.data);
          const newLog: Log = {
            content: logData.content,
            isNew: true,
            type: logData.type,
          };

          setLogs(prevLogs => [...prevLogs, newLog]);

          if (!userHasScrolledRef.current && logContainerRef.current) {
            setTimeout(() => {
              if (logContainerRef.current) {
                logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
              }
            }, 50);
          }

          setTimeout(() => {
            setLogs(prevLogs =>
              prevLogs.map(log =>
                log.content === logData.content ? { ...log, isNew: false } : log
              )
            );
          }, 2000);
        } catch (error) {
          // Ignore parse errors for ping/empty messages
        }
      };

      eventSource.onerror = (e) => {
        // Only reconnect if the connection was actually closed
        if (eventSource.readyState === EventSource.CLOSED) {
          eventSource.close();
          eventSourceRef.current = null;
          isConnecting = false;

          if (reconnectTimeout) clearTimeout(reconnectTimeout);
          reconnectTimeout = setTimeout(() => {
            setLogs(prevLogs => {
              connectSSE(prevLogs.length);
              return prevLogs;
            });
          }, 5000);
        }
      };
    };

    connectSSE(initialLogCount);

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, [initialLogCount]);

  // Handle scroll
  useEffect(() => {
    const handleScroll = () => {
      if (logContainerRef.current) {
        const { scrollTop, scrollHeight, clientHeight } = logContainerRef.current;
        const isAtBottom = Math.abs(scrollHeight - scrollTop - clientHeight) < 10;
        const hasScrolled = !isAtBottom;
        setUserHasScrolled(hasScrolled);
        userHasScrolledRef.current = hasScrolled;
      }
    };

    const logRef = logContainerRef.current;
    logRef?.addEventListener('scroll', handleScroll);
    return () => logRef?.removeEventListener('scroll', handleScroll);
  }, []);

  const toggleFilter = (type: string) => {
    setActiveFilters({ ...activeFilters, [type]: !activeFilters[type] });
  };

  const clearLogs = () => {
    showConfirm(
      'Clear Logs',
      'Are you sure you want to clear all logs?',
      () => {
        axios.post('/clear-logs').then(() => {
          setLogs([]);
          if (eventSourceRef.current) {
            eventSourceRef.current.close();
          }
          setInitialLogCount(0);
        });
      },
      { confirmText: 'Clear', variant: 'danger' }
    );
  };

  const filteredLogs = logs.filter(log => activeFilters[log.type]);

  return (
    <>
      <ConfirmModal config={confirmConfig} onClose={closeConfirm} />
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Event Logs</h1>
            <p className="text-slate-500 dark:text-slate-400 mt-1">Real-time system activity and diagnostics</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="badge-info">
              <Icons.Terminal className="w-3.5 h-3.5 mr-1.5" />
              {logs.length} entries
            </span>
          </div>
        </div>

        {/* Filters */}
      <div className="card p-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm font-medium text-slate-600 dark:text-slate-400">Filters:</span>
          {Object.keys(activeFilters).map((type) => {
            const colors = logTypeColors[type] || logTypeColors.debug;
            return (
              <button
                key={type}
                onClick={() => toggleFilter(type)}
                className={cn(
                  "flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-all",
                  activeFilters[type]
                    ? `${colors.bg} ${colors.text}`
                    : "bg-slate-100 dark:bg-dark-700 text-slate-400 dark:text-slate-500"
                )}
              >
                <span className={cn("w-2 h-2 rounded-full", activeFilters[type] ? colors.dot : "bg-slate-300 dark:bg-slate-600")} />
                {type.charAt(0).toUpperCase() + type.slice(1)}
              </button>
            );
          })}
          <button
            onClick={clearLogs}
            className="ml-auto btn-danger text-sm py-1.5 flex items-center gap-2"
          >
            <Icons.Trash className="w-4 h-4" />
            Clear
          </button>
        </div>
      </div>

      {/* Log container */}
      <div className="card overflow-hidden relative">
        {isLoading ? (
          <div className="flex items-center justify-center h-96">
            <Spinner size="lg" />
          </div>
        ) : (
          <div
            ref={logContainerRef}
            className="h-[500px] overflow-y-auto p-4 font-mono text-sm bg-slate-900 dark:bg-dark-950"
          >
            <AnimatePresence initial={false}>
              {filteredLogs.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-slate-500">
                  <Icons.Terminal className="w-12 h-12 mb-4 opacity-50" />
                  <p>No logs to display</p>
                </div>
              ) : (
                filteredLogs.map((log, index) => {
                  const colors = logTypeColors[log.type] || logTypeColors.debug;
                  return (
                    <motion.div
                      key={`${log.content}-${index}`}
                      initial={log.isNew ? { opacity: 0, x: -20 } : false}
                      animate={{ opacity: 1, x: 0 }}
                      className={cn(
                        "py-2 px-3 mb-1 rounded-lg text-slate-200 whitespace-pre-wrap break-all",
                        log.isNew && "ring-2 ring-primary-500/50 bg-primary-500/10"
                      )}
                    >
                      <span className={cn(
                        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-semibold mr-2",
                        colors.bg, colors.text
                      )}>
                        <span className={cn("w-1.5 h-1.5 rounded-full", colors.dot)} />
                        {log.type.toUpperCase()}
                      </span>
                      <span className="text-slate-400">{log.content.substring(log.content.indexOf(':') + 1)}</span>
                    </motion.div>
                  );
                })
              )}
            </AnimatePresence>
          </div>
        )}

        {/* Scroll to latest button */}
        <AnimatePresence>
          {userHasScrolled && filteredLogs.length > 0 && (
            <motion.button
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              onClick={scrollToBottom}
              className="absolute bottom-6 right-6 bg-primary-500 hover:bg-primary-600 text-white px-4 py-2 rounded-full flex items-center gap-2 shadow-lg transition-colors"
            >
              <Icons.ArrowDown className="w-4 h-4" />
              Latest
            </motion.button>
          )}
        </AnimatePresence>
      </div>
    </div>
    </>
  );
};

export default EventLogs;