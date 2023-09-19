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
    const fetchLastLog = async () => {
      try {
        const response = await fetch('/last-log', { method: 'POST' });
        const data = await response.json();
        const lastLog = data.last_log;

        setLogs(prevLogs => {
          const existingLogContents = new Set(prevLogs.map(log => log.content));

          if (!existingLogContents.has(lastLog)) {
            return [...prevLogs, {
              content: lastLog,
              isNew: true,
              type: lastLog.split(":")[0].toLowerCase(),
            }];
          }

          return prevLogs;
        });

        // Remove the 'new' flag after 2 seconds
        setTimeout(() => {
          setLogs(prevLogs => prevLogs.map(log => ({ ...log, isNew: false })));
        }, 2000);

        // Scroll to the bottom
        if (logContainerRef.current) {
          logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
        }

      } catch (error) {
        console.error('Error fetching logs:', error);
      }
    };

    const intervalId = setInterval(fetchLastLog, 2000);

    return () => {
      clearInterval(intervalId);
    };
  }, []);  

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
