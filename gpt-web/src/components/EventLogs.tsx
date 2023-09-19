import React, { useEffect, useState, useRef } from 'react';
import '../css/EventLogs.css';

interface Log {
  content: string;
  isNew: boolean;
  type: string;
}

const EventLogs: React.FC = () => {
  const [logs, setLogs] = useState<Map<string, Log>>(new Map());
  const logContainerRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await fetch('/logs', { method: 'POST' });
        const data = await response.json();
        const allLogs = data.log_data.split('\n');

        // Clone the existing Map
        const updatedLogs = new Map(logs);

        allLogs.forEach((logContent: string) => {
          if (!updatedLogs.has(logContent)) {
            const type = logContent.split(":")[0].toLowerCase();
            updatedLogs.set(logContent, { content: logContent, isNew: true, type });
          }
        });

        setLogs(updatedLogs);

        // Remove the 'new' flag after 2 seconds
        setTimeout(() => {
          setLogs(prevLogs => {
            const newMap = new Map(prevLogs);
            newMap.forEach((log, key) => {
              newMap.set(key, { ...log, isNew: false });
            });
            return newMap;
          });
        }, 2000);

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
    return Array.from(logs.values()).map((log, index) => {
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
