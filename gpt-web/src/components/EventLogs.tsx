import React, { useEffect, useState, useRef } from 'react';
import '../css/EventLogs.css';

const EventLogs: React.FC = () => {
  const [logs, setLogs] = useState<Array<{ content: string, isNew: boolean, type: string }>>([]);
  const logContainerRef = useRef<HTMLPreElement>(null);
  const lastLogIndex = useRef(0); // Store the last log index
  
  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await fetch('/logs', { method: 'POST' });
        const data = await response.json();
        const allLogs = data.log_data.split('\n');
        
        const newLogs = allLogs.slice(lastLogIndex.current).map((log: string) => {
          const type = log.split(":")[0]; // Parse type from log string
          return { content: log, isNew: true, type: type.toLowerCase() };
        });
        
        // Only update if there are new logs
        if (newLogs.length > 0) {
          lastLogIndex.current = allLogs.length; // Update the last log index
          
          setLogs(prevLogs => [...prevLogs, ...newLogs]);
          
          // Remove the 'new' flag after 2 seconds
          setTimeout(() => {
            setLogs(prevLogs => prevLogs.map(log => ({ ...log, isNew: false })));
          }, 2000);
        }

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
