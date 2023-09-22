import React, { useState, useEffect } from 'react';
import axios from 'axios';
import '../css/Settings.css';

const Settings: React.FC = () => {
  const [settings, setSettings] = useState<any>({});
  const [isLoading, setLoading] = useState(true);
  const [availableModels, setAvailableModels] = useState<string[]>([]);

  useEffect(() => {
    // Fetch settings and available models from backend when component mounts
    axios.post('/settings', { action: 'read' }).then((response) => {
      setSettings(response.data);
      setLoading(false);
    }).catch((error) => {
      console.log("Error: ", error);
      console.log("Error Response: ", error.response);
    });
  
    axios.post('/availableModels').then((response) => {
      if (response.data.models) {
        setAvailableModels(response.data.models);
      }
    }).catch((error) => {
      console.log("Error: ", error);
      console.log("Error Response: ", error.response);
    });
  }, []);  

  const updateSettings = () => {
    // Send updated settings to backend
    axios.post('/settings', { action: 'update', data: settings }).then((response) => {
      setSettings(response.data);
      alert('Settings updated!');
    }).catch((error) => {
      console.log("Error: ", error);
      console.log("Error Response: ", error.response);
    });
  };

  if (isLoading) {
    return <div>Loading...</div>;
  }

  return (
    <div className="dashboard settings-dashboard">
      <h2>Settings</h2>
      <div className="settings-container">
        
        <div className="settings-section">
          <div className="settings-section-header">General Settings</div>
          <label>
            Keyword:
            <input
              type="text"
              id='keyword-input'
              value={settings.keyword || ''}
              onChange={(e) => setSettings({ ...settings, keyword: e.target.value })}
            />
          </label>
        </div>

        <div className="settings-section">
          <div className="settings-section-header">OpenAI Settings</div>
          <div className="settings-group">
            <label>
              Model:<br/>
              {availableModels.length > 0 ? (
                <select
                  value={settings.model || ''}
                  onChange={(e) => setSettings({ ...settings, model: e.target.value })}
                >
                  {availableModels.map((model, index) => (
                    <option key={index} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
              ) : (
                <p>Loading models...</p>
              )}
            </label>
            <label>
              Max Tokens:<br/>
              <input
                type="number"
                value={settings.max_tokens || ''}
                onChange={(e) => setSettings({ ...settings, max_tokens: parseInt(e.target.value, 10) })}
              />
            </label>
            <label>
              Temperature:<br/>
              <input
                type="number"
                step="0.01"
                value={settings.temperature || ''}
                onChange={(e) => setSettings({ ...settings, temperature: parseFloat(e.target.value) })}
              />
            </label>
            <label>
              Custom Instructions:<br/>
              <textarea
                value={settings.custom_instructions || ''}
                onChange={(e) => setSettings({ ...settings, custom_instructions: e.target.value })}
              />
            </label>
          </div>
        </div>
        
        <button onClick={updateSettings}>Update</button>
      </div>
    </div>
  );
};

export default Settings;