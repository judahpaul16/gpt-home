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
    let isCancelled = false; // Flag to keep track of component unmount

    const fetchLogs = async () => {
      try {
        const response = await fetch('/logs', { method: 'POST' });
        if (isCancelled) return; // Check if component unmounted

        const data = await response.json();
        if (isCancelled) return; // Check if component unmounted

        const allLogs = data.log_data.split('\n');
        const existingLogContents = new Set(logs.map(log => log.content));

        const newLogs = allLogs
          .filter((log: any) => !existingLogContents.has(log))
          .map((log: any) => ({
            content: log,
            isNew: true,
            type: log.split(":")[0].toLowerCase(),
          }));

        if (newLogs.length > 0) {
          setLogs([...logs, ...newLogs]);

          // Remove the 'new' flag after 2 seconds
          setTimeout(() => {
            setLogs(logs.map(log => ({ ...log, isNew: false })));
          }, 2000);
        }

        if (logContainerRef.current) {
          logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
        }
      } catch (error) {
        if (!isCancelled) {
          console.error('Error fetching logs:', error);
        }
      }
    };

    fetchLogs();
    const intervalId = setInterval(fetchLogs, 2000);

    return () => {
      isCancelled = true; // Update the flag when component unmounts
      clearInterval(intervalId); // Clear the interval
    };
  }, []); // Empty dependency array ensures this runs once when component mounts and cleans up when it unmounts

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
