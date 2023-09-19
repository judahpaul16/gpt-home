import React, { useEffect, useState, useRef } from 'react';
import '../css/EventLogs.css';

interface Log {
  content: string;
  isNew: boolean;
  type: string;
  timestamp: string;
}

const EventLogs: React.FC = () => {
  const [logs, setLogs] = useState<Log[]>([]);
  const prevLogLengthRef = useRef<number | null>(null);
  const logContainerRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    const fetchAllLogs = async () => {
      const response = await fetch('/logs', { method: 'POST' });
      const data = await response.json();
      const allLogs = data.log_data.split('\n').map((log: string) => ({
        content: log,
        isNew: false,
        type: log.split(":")[0].toLowerCase(),
        timestamp: ''
      }));
      setLogs(allLogs);
      prevLogLengthRef.current = allLogs.length;
    };

    fetchAllLogs();
  }, []);

  useEffect(() => {
    const fetchLastLog = async () => {
      try {
        const response = await fetch('/logs', { method: 'POST' });
        const data = await response.json();
        const allLogs = data.log_data.split('\n');
        const currentLogLength = allLogs.length;

        if (prevLogLengthRef.current !== null && prevLogLengthRef.current < currentLogLength) {
          const lastLog = allLogs[allLogs.length - 1];
          const timestamp = new Date().toISOString();

          setLogs(prevLogs => [...prevLogs, {
            content: lastLog,
            isNew: true,
            type: lastLog.split(":")[0].toLowerCase(),
            timestamp: timestamp
          }]);

          setTimeout(() => {
            setLogs(prevLogs => prevLogs.map(log => ({ ...log, isNew: false })));
          }, 2000);

          prevLogLengthRef.current = currentLogLength;
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
