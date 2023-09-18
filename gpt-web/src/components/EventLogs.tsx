import React, { useEffect, useState } from 'react';
import '../css/EventLogs.css';

const EventLogs: React.FC = () => {
  const [logs, setLogs] = useState<string[]>([]);
  const [newEntries, setNewEntries] = useState<number>(0);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await fetch('/logs', { method: 'POST' });
        const data = await response.json();
        const newLogs = data.log_data.split('\n');

        if (logs.length === 0) {
          setLogs(newLogs);
        } else {
          const lastLog = logs[0];
          const lastLogIndex = newLogs.indexOf(lastLog);

          if (lastLogIndex !== -1) {
            const logsToAdd = newLogs.slice(0, lastLogIndex);
            setNewEntries(logsToAdd.length);
            setLogs(prevLogs => [...logsToAdd, ...prevLogs]);
          } else {
            setNewEntries(newLogs.length);
            setLogs(newLogs);
          }
        }
      } catch (error) {
        console.error('Error fetching logs:', error);
      }
    };

    // Fetch logs initially
    fetchLogs();

    // Set an interval to fetch logs every 1 second
    const intervalId = setInterval(fetchLogs, 1000);

    // Clear the interval when the component is unmounted
    return () => clearInterval(intervalId);
  }, [logs]);

  return (
    <pre className="log-container">
      {logs.map((log, index) => (
        <div className={index < newEntries ? 'new-entry' : 'old-entry'} key={index}>
          {log}
        </div>
      ))}
    </pre>
  );
};

export default EventLogs;
