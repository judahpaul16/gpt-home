import React, { useEffect, useState, useRef } from 'react';
import '../css/EventLogs.css';

const EventLogs: React.FC = () => {
  const [logs, setLogs] = useState<string[]>([]);
  const [newEntries, setNewEntries] = useState<number>(0);
  const lastLogRef = useRef<string | null>(null);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await fetch('/logs', { method: 'POST' });
        const data = await response.json();
        const newLogs = data.log_data.split('\n');

        if (!lastLogRef.current) {
          lastLogRef.current = newLogs[0];
          setLogs(newLogs);
        } else {
          const lastLogIndex = newLogs.indexOf(lastLogRef.current);

          if (lastLogIndex !== -1) {
            const logsToAdd = newLogs.slice(0, lastLogIndex);
            setNewEntries(logsToAdd.length);
            setLogs(prevLogs => [...logsToAdd, ...prevLogs]);
            lastLogRef.current = newLogs[0];
          } else {
            setNewEntries(newLogs.length);
            setLogs(newLogs);
            lastLogRef.current = newLogs[0];
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
  }, []);

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
