import React, { useEffect, useState, useRef } from 'react';
import '../css/EventLogs.css';

const EventLogs: React.FC = () => {
  const [logs, setLogs] = useState<string[]>([]);
  const [prevLogsLength, setPrevLogsLength] = useState<number>(0);
  const logContainerRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await fetch('/logs', { method: 'POST' });
        const data = await response.json();
        const newLogs = data.log_data.split('\n');
        
        setPrevLogsLength(logs.length);
        setLogs(newLogs);

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
  }, [logs]);  // add dependency on logs

  const renderLogs = () => {
    return logs.map((log, index) => {
      const key = `${log}-${index}`;
      return (
        <div className={index >= prevLogsLength ? 'new-entry' : 'old-entry'} key={key}>
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
