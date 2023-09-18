import React, { useEffect, useState } from 'react';

const EventLogs: React.FC = () => {
  const [logs, setLogs] = useState<string>('');

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await fetch('/logs', { method: 'POST' });
        const data = await response.json();
        setLogs(data.log_data);
      } catch (error) {
        console.error('Error fetching logs:', error);
      }
    };

    // Fetch logs initially
    fetchLogs();

    // Set an interval to fetch logs every 5 seconds
    const intervalId = setInterval(fetchLogs, 5000);

    // Clear the interval when the component is unmounted
    return () => clearInterval(intervalId);
  }, []);

  return (
    <pre>
      {logs}
    </pre>
  );
};

export default EventLogs;
