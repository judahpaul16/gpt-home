import React, { useEffect, useState, useRef } from 'react';
import '../css/EventLogs.css';

const EventLogs: React.FC = () => {
  const [logs, setLogs] = useState<string[]>([]);
  const logContainerRef = useRef<HTMLPreElement>(null);
  const lastLogCount = useRef<number>(0); // Store the last log count

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await fetch('/logs', { method: 'POST' });
        const data = await response.json();
        const newLogs = data.log_data.split('\n');

        setLogs(newLogs);

        if (logContainerRef.current) {
          logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
        }

        lastLogCount.current = newLogs.length; // Update the last log count
      } catch (error) {
        console.error('Error fetching logs:', error);
      }
    };

    // Fetch logs initially
    fetchLogs();

    // Set an interval to fetch logs every 2 seconds
    const intervalId = setInterval(fetchLogs, 2000);

    // Clear the interval when the component is unmounted
    return () => clearInterval(intervalId);
  }, []);

  const renderLogs = () => {
    return logs.map((log, index) => {
      const key = `${log}-${index}`;
      // Identify new log entries based on last log count
      const isNewEntry = index >= lastLogCount.current;

      return (
        <div className={isNewEntry ? 'new-entry' : 'old-entry'} key={key}>
          {log}
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
