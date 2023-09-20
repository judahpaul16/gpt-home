import React, { useState, useEffect } from 'react';
import axios from 'axios';
import '../css/Settings.css';

const Settings: React.FC = () => {
  const [settings, setSettings] = useState<any>({});
  const [isLoading, setLoading] = useState(true);

  useEffect(() => {
    // Fetch settings from backend when component mounts
    axios.post('/settings', { action: 'read' }).then((response) => {
      setSettings(response.data);
      setLoading(false);
    });
  }, []);

  const updateSettings = () => {
    // Send updated settings to backend
    axios.post('/settings', { action: 'update', data: settings }).then((response) => {
      setSettings(response.data);
      alert('Settings updated!');
    });
  };

  if (isLoading) {
    return <div>Loading...</div>;
  }

  return (
    <div className="dashboard settings-dashboard">
      <h2>Settings</h2>
      <div className="settings-container">
        <label>
          Max Tokens:
          <input
            type="number"
            value={settings.max_tokens || ''}
            onChange={(e) => setSettings({ ...settings, max_tokens: parseInt(e.target.value, 10) })}
          />
        </label>
        <label>
          Temperature:
          <input
            type="number"
            step="0.01"
            value={settings.temperature || ''}
            onChange={(e) => setSettings({ ...settings, temperature: parseFloat(e.target.value) })}
          />
        </label>
        <button onClick={updateSettings}>Update</button>
      </div>
    </div>
  );
};

export default Settings;
