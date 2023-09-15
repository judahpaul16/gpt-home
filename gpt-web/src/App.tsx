import React, { useState } from 'react';
import './css/App.css';
import Integration from './components/Integration';

interface IntegrationStatus {
  [key: string]: boolean;
}

const App: React.FC = () => {
  const [integrations, setIntegrations] = useState<IntegrationStatus>({
    Spotify: false,
    GoogleCalendar: false,
    PhilipsHue: false,
  });

  const toggleStatus = (name: string) => {
    setIntegrations({ ...integrations, [name]: !integrations[name] });
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>GPT Home - Integrations Dashboard</h1>
        <div className="integrations-dashboard">
          <Integration
            name="Spotify"
            status={integrations.Spotify}
            toggleStatus={toggleStatus}
          />
          <Integration
            name="Google Calendar"
            status={integrations.GoogleCalendar}
            toggleStatus={toggleStatus}
          />
          <Integration
            name="Philips Hue"
            status={integrations.PhilipsHue}
            toggleStatus={toggleStatus}
          />
        </div>
      </header>
    </div>
  );
};

export default App;
