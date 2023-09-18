import React, { useEffect, useState } from 'react';

const EventLogs: React.FC = () => {
  const [logs, setLogs] = useState<string>('');

  useEffect(() => {
    const fetchLogs = async () => {
      const response = await fetch('/logs');
      const data = await response.text();
      setLogs(data);
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
