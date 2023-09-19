import React, { useEffect, useState, useRef } from 'react';
import '../css/EventLogs.css';

interface LogEntry {
  content: string;
  isNew: boolean;
}

const EventLogs: React.FC = () => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [newLogs, setNewLogs] = useState<LogEntry[]>([]);
  const logContainerRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await fetch('/logs', { method: 'POST' });
        const data = await response.json();
        const fetchedLogs: LogEntry[] = data.log_data.split('\n').map((log: string) => ({ content: log, isNew: false }));

        // Identify new logs
        const newEntries: LogEntry[] = fetchedLogs.filter(
          (fetchedLog: LogEntry) => !logs.some((existingLog: LogEntry) => existingLog.content === fetchedLog.content)
        ).map((log: LogEntry) => ({ ...log, isNew: true }));

        setNewLogs(newEntries);

        // Combine old logs with new logs
        const combinedLogs: LogEntry[] = [...logs, ...newEntries];

        setLogs(combinedLogs);

        if (logContainerRef.current) {
          logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
        }
      } catch (error) {
        console.error('Error fetching logs:', error);
      }
    };

    fetchLogs();
    const intervalId = setInterval(fetchLogs, 2000);
    return () => clearInterval(intervalId);
  }, [logs]);

  const renderLogs = () => {
    return logs.map((log, index) => {
      const key = `${log.content}-${index}`;
      const isNewEntry = newLogs.some((newLog: LogEntry) => newLog.content === log.content);
      return (
        <div className={isNewEntry ? 'new-entry' : 'old-entry'} key={key}>
          {log.content}
        </div>
      );
    });
  };

  return (
    <div className="dashboard log-dashboard">
      <pre className="log-container" ref={logContainerRef}>
        {renderLogs()}
      </pre>
    </div>
  );
};

export default EventLogs;
