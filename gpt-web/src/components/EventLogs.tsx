import React, { useEffect, useState, useRef } from 'react';
import '../css/EventLogs.css';

const EventLogs: React.FC = () => {
  const [logs, setLogs] = useState<string[]>([]);
  const [newEntryIndex, setNewEntryIndex] = useState<number | null>(null);
  const logContainerRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await fetch('/logs', { method: 'POST' });
        const data = await response.json();
        const newLogs = data.log_data.split('\n');
        
        if (newLogs.length !== logs.length) {
          setNewEntryIndex(newLogs.length - 1);
          setTimeout(() => setNewEntryIndex(null), 2000);  // Reset after 2 seconds
        }
        
        setLogs(newLogs);

        // Scroll to the bottom
        if (logContainerRef.current) {
          logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
        }
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
  }, [logs]);

  return (
    <div className="dashboard log-dashboard">
      <pre className="log-container" ref={logContainerRef}>
        {logs.map((log, index) => (
          <div className={index === newEntryIndex ? 'new-entry' : 'old-entry'} key={index}>
            {log}
          </div>
        ))}
      </pre>
    </div>
  );
};

export default EventLogs;
