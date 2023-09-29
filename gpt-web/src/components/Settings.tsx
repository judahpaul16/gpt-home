import React, { useState, useEffect } from 'react';
import axios from 'axios';
import '../css/Settings.css';

const Settings: React.FC = () => {
  const [settings, setSettings] = useState<any>({});
  const [isLoading, setLoading] = useState(true);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [oldPassword, setOldPassword] = useState<string>('');
  const [newPassword, setNewPassword] = useState<string>('');
  const [confirmInput, setConfirmInput] = useState<string>('');

  useEffect(() => {
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
    // if old or new password is not empty, then change password
    if (oldPassword !== '' || newPassword !== '' || confirmInput !== '') {
      if (oldPassword === '') {
        alert('Old password cannot be empty');
        return;
      } else if (newPassword === '') {
        alert('New password cannot be empty');
        return;
      } else if (newPassword.length < 6) {
        alert('New password must be at least 6 characters long');
        return;
      } else if (newPassword === oldPassword) {
        alert('New password cannot be the same as old password');
        return;
      } else if (newPassword !== confirmInput) {
        alert('New password and confirm password must match');
        return;
      } else {
        changePassword();
      }
    }

    axios.post('/settings', { action: 'update', data: settings }).then((response) => {
      setSettings(response.data);
      alert('Settings updated!');
    }).catch((error) => {
      console.log("Error: ", error);
      console.log("Error Response: ", error.response);
    });
  };

  const changePassword = () => {
    axios.post('/changePassword', { oldPassword, newPassword }).then((response) => {
      alert('Password changed successfully');
    }).catch((error) => {
      console.log("Error: ", error);
      alert('Failed to change password');
    });
  };

  const gptRestart = () => {
    axios.post('/gptRestart').then((response) => {
      alert('GPT Home service restarted');
    }).catch((error) => {
      console.log("Error: ", error);
      alert('Failed to restart GPT Home service');
    });
  };

  const spotifyRestart = () => {
    axios.post('/spotifyRestart').then((response) => {
      alert('Spotifyd service restarted');
    }).catch((error) => {
      console.log("Error: ", error);
      alert('Failed to restart Spotifyd service');
    });
  };

  const shutdown = () => {
    axios.post('/shutdown').then((response) => {
      alert('System shutting down');
    }).catch((error) => {
      console.log("Error: ", error);
      alert('Failed to shutdown system');
    });
  };

  const reboot = () => {
    axios.post('/reboot').then((response) => {
      alert('System rebooting');
    }).catch((error) => {
      console.log("Error: ", error);
      alert('Failed to reboot system');
    });
  };

  if (isLoading) {
    return <div>Loading...</div>;
  }

  return (
    <div className="dashboard settings-dashboard">
      <h2>Settings</h2>

      <button className="settings-top-btn" onClick={() => {
        if (window.confirm('Are you sure you want to restart GPT Home service?'))
          {gptRestart();}
        }
      }>Restart GPT Home Service</button>
      <button className="settings-top-btn" onClick={() => {
        if (window.confirm('Are you sure you want to restart Spotifyd service?'))
          {spotifyRestart();}
        }
      }>Restart Spotifyd Service</button>
      <button className="settings-top-btn system-btn" onClick={() => {
        if (window.confirm('Are you sure you want to shutdown?'))
          {shutdown();}
        }
      }>Shutdown System</button>
      <button className="settings-top-btn system-btn" onClick={() => {
        if (window.confirm('Are you sure you want to reboot?'))
          {reboot();}
        }
      }>Reboot System</button>

      <div className="settings-container">
        
        {/* General Settings */}
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

        {/* OpenAI Settings */}
        <div className="settings-section">
          <div className="settings-section-header">OpenAI Settings</div>
          <div className="settings-group">
            <label>
              Model:<br />
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
              Max Tokens:<br />
              <input
                type="number"
                value={settings.max_tokens || ''}
                onChange={(e) => setSettings({ ...settings, max_tokens: parseInt(e.target.value, 10) })}
              />
            </label>
            <label>
              Temperature:<br />
              <input
                type="number"
                step="0.01"
                value={settings.temperature || ''}
                onChange={(e) => setSettings({ ...settings, temperature: parseFloat(e.target.value) })}
              />
            </label>
            <label>
              Custom Instructions:<br />
              <textarea
                value={settings.custom_instructions || ''}
                onChange={(e) => setSettings({ ...settings, custom_instructions: e.target.value })}
              />
            </label>
          </div>
        </div>
        
        {/* Change Password */}
        <div className="settings-section">
          <div className="settings-section-header">Change Password</div>
            <div className="settings-group">
              <label>
                Old Password:<br />
                <input
                  type="password"
                  value={oldPassword}
                  onChange={(e) => setOldPassword(e.target.value)}
                />
              </label>
              <label>
                New Password:<br />
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
              </label>
              <label>
                Confirm New Password:<br />
                <input
                  type="password"
                  value={confirmInput}
                  onChange={(e) => setConfirmInput(e.target.value)}
                />
              </label>
            </div>
        </div>

        {/* Update Settings Button */}
        <button onClick={updateSettings}>Update</button>
      </div>
    </div>
  );
};

export default Settings;
