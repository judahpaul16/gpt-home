import React, { useEffect, useState } from 'react';

const EventLogs: React.FC = () => {
  const [logs, setLogs] = useState<string>('');

  useEffect(() => {
    const fetchLogs = async () => {
      const response = await fetch('/logs', { method: 'POST' });
      const data = await response.json();
      setLogs(data.log_data);
    };

    fetchLogs();
  }, []);

  return (
    <pre>
      {logs}
    </pre>
  );
};

export default EventLogs;
