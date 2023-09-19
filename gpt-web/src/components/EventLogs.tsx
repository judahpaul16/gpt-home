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
    const fetchLogs = async () => {
      try {
        const response = await fetch('/logs', { method: 'POST' });
        const data = await response.json();
        const allLogs = data.log_data.split('\n');
  
        setLogs(prevLogs => {
          // Create a set of existing log contents based on the current state
          const existingLogContents = new Set(prevLogs.map(log => log.content));
    
          // Filter out the logs that already exist in the state
          const newLogs = allLogs
            .filter((log: string) => !existingLogContents.has(log))
            .map((log: string) => ({
              content: log,
              isNew: true,
              type: log.split(":")[0].toLowerCase(),
            }));
    
          // If there are new logs, update the state
          if (newLogs.length > 0) {
            return [...newLogs.reverse(), ...prevLogs]; // Reverse the new logs to maintain chronological order
          }
    
          // If no new logs, return the existing logs
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
  
    const intervalId = setInterval(fetchLogs, 2000);
  
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
