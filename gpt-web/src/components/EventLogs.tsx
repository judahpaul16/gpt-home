import React, { useEffect, useState, useRef } from 'react';
import '../css/EventLogs.css';

interface LogEntry {
  content: string;
  isNew: boolean;
  type: string;
}

const EventLogs: React.FC = () => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const logContainerRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await fetch('/logs', { method: 'POST' });
        const data = await response.json();
        const fetchedLogs = data.log_data.split('\n');

        // Identify new logs
        const newLogs: LogEntry[] = fetchedLogs.filter(
          (fetchedLog: string) => !logs.some((existingLog: LogEntry) => existingLog.content === fetchedLog)
        ).map((log: string) => {
          const type = log.split(":")[0]; // Extract log type
          return { content: log, isNew: true, type: type.toLowerCase() };
        });

        setLogs(prevLogs => [...prevLogs, ...newLogs]);

        // Remove the 'new' flag after 2 seconds
        setTimeout(() => {
          setLogs(prevLogs => prevLogs.map(log => ({ ...log, isNew: false })));
        }, 2000);

        if (logContainerRef.current) {
          logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
        }
      } catch (error) {
        console.error('Error fetching logs:', error);
      }
    };

    // Initial fetch
    fetchLogs();

    // Set up interval
    const intervalId = setInterval(fetchLogs, 2000);

    // Cleanup
    return () => {
      clearInterval(intervalId);
    };
  }, [logs]);

  const renderLogs = () => {
    return logs.map((log, index) => {
      const key = `${log.content}-${index}`;
      const classes = [log.isNew ? 'new-entry' : 'old-entry', log.type].join(' ');
      return (
        <div className={classes} key={key}>
          {log.content}
        </div>
      );
    });
  };

  return (
    <div className="dashboard log-dashboard">
      <h2>Event Logs</h2>
      <pre className="log-container" ref={logContainerRef}>
        {renderLogs()}
      </pre>
    </div>
  );
};

export default EventLogs;
