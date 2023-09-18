import React, { useEffect, useState } from 'react';
import '../css/EventLogs.css';

const EventLogs: React.FC = () => {
  const [logs, setLogs] = useState<string[]>([]);
  const [isNew, setIsNew] = useState<boolean[]>([]);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await fetch('/logs', { method: 'POST' });
        const data = await response.json();
        const newLogs = data.log_data.split('\n');

        // Mark new logs
        const newFlags = newLogs.map((_: any, index: any) => index >= logs.length);

        setLogs(newLogs);
        setIsNew(newFlags);

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
        <div className={isNew[index] ? 'new-entry' : 'old-entry'} key={index}>
          {log}
        </div>
      ))}
    </pre>
  );
};

export default EventLogs;
