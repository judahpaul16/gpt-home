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
    // Fetch all logs initially
    const fetchAllLogs = async () => {
      const response = await fetch('/logs', { method: 'POST' });
      const data = await response.json();
      const allLogs = data.log_data.split('\n').map((log: string) => ({
        content: log,
        isNew: false,
        type: log.split(":")[0].toLowerCase(),
      }));
      setLogs(allLogs);
    };

    fetchAllLogs();
  }, []);

  useEffect(() => {
    const fetchLastLog = async () => {
      try {
        const response = await fetch('/last-log', { method: 'POST' });
        const data = await response.json();
        const lastLog = data.last_log;
        const response2 = await fetch('/logs', { method: 'POST' });
        const data2 = await response2.json();
        const fullLog = data2.log_data.split('\n').map((log: string) => ({
          content: log,
          isNew: false,
          type: log.split(":")[0].toLowerCase(),
        }));
    
        if (lastLog && fullLog && fullLog.length > logs.length) {
          setLogs(prevLogs => [...prevLogs, {
            content: lastLog,
            isNew: true,
            type: lastLog.split(":")[0].toLowerCase(),
          }]);
    
          // Remove the 'new' flag after 2 seconds
          setTimeout(() => {
            setLogs(prevLogs => prevLogs.map(log => ({ ...log, isNew: false })));
          }, 2000);
        }
    
        // Scroll to the bottom
        if (logContainerRef.current) {
          logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
        }
      } catch (error) {
        console.error('Error fetching last log:', error);
      }
    };    
  
    // Fetch the last log every 2 seconds, only after the initial logs are fetched
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
