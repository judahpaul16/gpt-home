import React, { useEffect, useState, useRef } from 'react';
import '../css/EventLogs.css';
import axios from 'axios';

interface Log {
  content: string;
  line_number: number;
  isNew: boolean;
  type: string;
}

const EventLogs: React.FC = () => {
  const [logs, setLogs] = useState<Log[]>([]);
  // eslint-disable-next-line
  const [currentLogLength, setCurrentLogLength] = useState<number | null>(null);
  const logContainerRef = useRef<HTMLPreElement>(null);
  const [userHasScrolled, setUserHasScrolled] = useState(false);
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
        const response = await fetch(`/new-logs?last_line_number=${lastLineNumber}`, { method: 'POST' });
        const data = await response.json();
        const newLogs = data.last_logs;
        const newLastLineNumber = data.new_last_line_number;
    
        if (newLogs.length > 0) {
          const formattedNewLogs = newLogs.map((log: string) => ({
            content: log,
            isNew: true,
            type: log.split(":")[0].toLowerCase(),
          }));
          setLogs(prevLogs => [...prevLogs, ...formattedNewLogs]);
          setLastLineNumber(newLastLineNumber);
    
          if (logContainerRef.current && !userHasScrolled) {
            logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
          }
    
          setTimeout(() => {
            setLogs(prevLogs => prevLogs.map(log => ({ ...log, isNew: false })));
          }, 2000);
        }
      } catch (error) {
        console.error('Error fetching last log:', error);
      }
    };    
  
    const intervalId = setInterval(fetchLastLog, 1500);
    return () => clearInterval(intervalId);
  }, [logs, lastLineNumber, userHasScrolled]);
  
  useEffect(() => {
    const handleScroll = () => {
      if (logContainerRef.current) {
        const { scrollTop, scrollHeight, clientHeight } = logContainerRef.current;
        const isAtBottom = scrollHeight - scrollTop === clientHeight;
        setUserHasScrolled(!isAtBottom);
      }
    };
  
    const newLogs = logs.filter(log => log.isNew);
    if (!userHasScrolled && logContainerRef.current && newLogs.length > 0) {
      scrollToBottom();
    }

    const logRef = logContainerRef.current;
    logRef?.addEventListener('scroll', handleScroll);
  
    return () => {
      logRef?.removeEventListener('scroll', handleScroll);
    };
    // eslint-disable-next-line
  }, []);  

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

  const scrollToBottom = () => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
      setUserHasScrolled(false);
    }
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
      <div className="scroll-bottom" onClick={scrollToBottom}>
        scroll bottom
      </div>
    </div>
  );
};

export default EventLogs;