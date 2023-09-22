import React, { useEffect, useState, useRef } from 'react';
import '../css/EventLogs.css';
import axios from 'axios';

interface Log {
  content: string;
  isNew: boolean;
  type: string;
}

const EventLogs: React.FC = () => {
  const [logs, setLogs] = useState<Log[]>([]);
  // eslint-disable-next-line
  const [currentLogLength, setCurrentLogLength] = useState<number | null>(null);
  const logContainerRef = useRef<HTMLPreElement>(null);
  const [lastLineNumber, setLastLineNumber] = useState<number>(0);
  const [activeFilters, setActiveFilters] = useState<{ [key: string]: boolean }>({
    warning: true,
    info: true,
    critical: true,
    success: true,
    error: true,
  });

  useEffect(() => {
    const fetchAllLogs = async () => {
      const response = await fetch('/logs', { method: 'POST' });
      const data = await response.json();
      const allLogs = data.log_data.split('\n').map((log: string) => ({
        content: log,
        isNew: false,
        type: log.split(":")[0].toLowerCase(),
      }));
      setLogs(allLogs);
      setCurrentLogLength(allLogs.length);
      setLastLineNumber(allLogs.length);
    };
  
    fetchAllLogs();
  }, []);
  
  useEffect(() => {
    const fetchLastLog = async () => {
      try {
        // Send last line number as a parameter
        const response = await fetch(`/last-logs?last_line_number=${lastLineNumber}`, { method: 'POST' });
        const data = await response.json();
        const newLogs = data.last_logs;
        const newLastLineNumber = data.new_last_line_number;
  
        if (newLogs.length > 0) {
          const formattedNewLogs = newLogs.map((log: string) => ({
            content: log.trim(),
            isNew: true,
            type: log.split(":")[0].toLowerCase().trim(),
          }));
          // Update logs state
          setLogs(prevLogs => [...prevLogs, ...formattedNewLogs]);
          // Update last line number state
          setLastLineNumber(newLastLineNumber);
  
          setTimeout(() => {
            setLogs(prevLogs => prevLogs.map(log => ({ ...log, isNew: false })));
          }, 2000);
        }
  
        if (logContainerRef.current) {
          logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
        }
      } catch (error) {
        console.error('Error fetching last log:', error);
      }
    };
  
    const intervalId = setInterval(fetchLastLog, 500);
    return () => clearInterval(intervalId);
  }, [logs, lastLineNumber]);
  
  const toggleFilter = (type: string) => {
    setActiveFilters({ ...activeFilters, [type]: !activeFilters[type] });
  };

  const renderLogs = () => {
    return logs
      .filter(log => activeFilters[log.type])
      .map((log, index) => {
        const key = `${log.content}-${index}`;
        const classes = [log.isNew ? 'new-entry' : 'old-entry', log.type].join(' entry ');

        return (
          <div className={classes} key={key}>
            {log.content}
          </div>
        );
      });
  };

  const clearLogs = () => {
    if (window.confirm('Are you sure you want to clear all logs?')) {
      axios.post('/clear-logs').then(() => {
        setLogs([]);
        setLastLineNumber(0);
      });
    };
  };

  return (
    <div className="dashboard log-dashboard">
      <h2>Event Logs</h2>
      <div className="filter-container">
        {['debug', 'success', 'info', 'warning', 'error', 'critical'].map(type => (
          <label key={type} className="filter-label">
            <input
              type="checkbox"
              checked={activeFilters[type]}
              onChange={() => toggleFilter(type)}
            />
            {type}
          </label>
        ))}
        <button 
          className="clear-logs-button"
          onClick={() => clearLogs()}
        >
          Clear Logs
        </button>
      </div>
      <pre className="log-container" ref={logContainerRef}>
        {renderLogs()}
      </pre>
    </div>
  );
};

export default EventLogs;