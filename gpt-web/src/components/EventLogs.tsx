import React, { useEffect, useState, useRef } from 'react';
import '../css/EventLogs.css';

interface Log {
  content: string;
  isNew: boolean;
  type: string;
}

const EventLogs: React.FC = () => {
  const [logs, setLogs] = useState<Log[]>([]);
  const [currentLogLength, setCurrentLogLength] = useState<number | null>(null);
  const logContainerRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    const fetchAllLogs = async () => {
      const response = await fetch('/logs', { method: 'POST' });
      const data = await response.json();
      const allLogs = data.log_data.split('\n').map((log: string) => ({
        content: log,
        isNew: false,
        type: log.split(":")[0].toLowerCase(),
      }));
      setLogs(allLogs);
      setCurrentLogLength(allLogs.length);
    };

    fetchAllLogs();
  }, []);

  useEffect(() => {
    const fetchLastLog = async () => {
      try {
        const response = await fetch('/last-log', { method: 'POST' });
        const data = await response.json();
        const lastLog = data.last_log;

        const response2 = await fetch('/logs', { method: 'POST' });
        const data2 = await response2.json();
        const fullLog = data2.log_data.split('\n');

        if (currentLogLength !== null && fullLog.length > currentLogLength) {
          const newLogs = fullLog.slice(currentLogLength).map((log: string) => ({
            content: log,
            isNew: true,
            type: log.split(":")[0].toLowerCase(),
          }));
          setCurrentLogLength(fullLog.length);

          setLogs(prevLogs => [...prevLogs, ...newLogs]);

          setTimeout(() => {
            setLogs(prevLogs => prevLogs.map(log => ({ ...log, isNew: false })));
          }, 2000);
        } else if (currentLogLength === null) {
          setCurrentLogLength(fullLog.length);
        }

        if (logContainerRef.current) {
          logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
        }
      } catch (error) {
        console.error('Error fetching last log:', error);
      }
    };

    if (logs.length > 0) {
      const intervalId = setInterval(fetchLastLog, 2000);
      return () => clearInterval(intervalId);
    }
  }, [logs, currentLogLength]);

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
