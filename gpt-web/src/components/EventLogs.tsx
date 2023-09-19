import React, { useEffect, useState, useRef } from 'react';
import '../css/EventLogs.css';

interface Log {
  content: string;
  isNew: boolean;
  type: string;
}

const EventLogs: React.FC = () => {
  const [logs, setLogs] = useState<Log[]>([]);
  const [newLogIndexes, setNewLogIndexes] = useState<number[]>([]);
  const logContainerRef = useRef<HTMLPreElement>(null);
  const lastLog = useRef<string | null>(null);  // Keep track of the last log

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await fetch('/logs', { method: 'POST' });
        const data = await response.json();
        const allLogs = data.log_data.split('\n');
        const newLogs: Log[] = [];

        for (let log of allLogs.reverse()) {
          if (log === lastLog.current) {
            break;
          }
          const type = log.split(":")[0].toLowerCase();
          newLogs.unshift({ content: log, isNew: true, type });
        }

        if (newLogs.length > 0) {
          lastLog.current = newLogs[newLogs.length - 1].content;

          setLogs(prevLogs => {
            const startIndex = prevLogs.length;
            const newIndexes = Array.from({ length: newLogs.length }, (_, i) => i + startIndex);

            setNewLogIndexes(newIndexes);

            // Remove the 'new' flag after 1 second
            setTimeout(() => {
              setNewLogIndexes([]);
            }, 1000);

            return [...prevLogs, ...newLogs];
          });
        }

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
  }, []);

  const renderLogs = () => {
    return logs.map((log, index) => {
      const key = `${log.content}-${index}`;
      const isNew = newLogIndexes.includes(index);
      const classes = [isNew ? 'new-entry' : 'old-entry', log.type].join(' ');

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
