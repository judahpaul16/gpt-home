import React, { useEffect, useState, useRef } from 'react';
import '../css/EventLogs.css';

interface Log {
  content: string;
  isNew: boolean;
  type: string;
}

const EventLogs: React.FC = () => {
  const [logs, setLogs] = useState<Log[]>([]);
  const logContainerRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await fetch('/logs', { method: 'POST' });
        const data = await response.json();
        const fetchedLogs = data.log_data.split('\n').filter((log: string) => log.trim() !== '');

        setLogs(prevLogs => {
          const existingLogContents = new Set(prevLogs.map(log => log.content));
          const newLogs = fetchedLogs
            .filter((log: any) => !existingLogContents.has(log))
            .map((log: any) => ({
              content: log,
              isNew: true,
              type: log.split(":")[0].toLowerCase(),
            }));

          if (newLogs.length > 0) {
            // Remove the 'new' flag from old logs
            const updatedOldLogs = prevLogs.map(log => ({ ...log, isNew: false }));

            // Scroll to the bottom
            if (logContainerRef.current) {
              logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
            }

            return [...updatedOldLogs, ...newLogs];
          }

          return prevLogs;
        });
      } catch (error) {
        console.error('Error fetching logs:', error);
      }
    };

    fetchLogs();
    const intervalId = setInterval(fetchLogs, 2000);
    return () => clearInterval(intervalId);
  }, []); // Empty dependency array

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
