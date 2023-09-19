import React, { useEffect, useState, useRef } from 'react';
import '../css/EventLogs.css';

const EventLogs: React.FC = () => {
  const [logs, setLogs] = useState<Array<{ content: string, isNew: boolean }>>([]);
  const [newLogs, setNewLogs] = useState<Array<{ content: string, isNew: boolean }>>([]);
  const logContainerRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await fetch('/logs', { method: 'POST' });
        const data = await response.json();
        const fetchedLogs = data.log_data.split('\n').map((log: string) => ({ content: log, isNew: false }));

        // Identify new logs
        const newEntries = fetchedLogs.filter(
          (fetchedLog: any) => !logs.some(existingLog => existingLog.content === fetchedLog.content)
        ).map((log: any) => ({ ...log, isNew: true }));

        setNewLogs(newEntries);

        // Combine old logs with new logs
        const combinedLogs = [...logs, ...newEntries];

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
      const isNewEntry = newLogs.some(newLog => newLog.content === log.content);
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
