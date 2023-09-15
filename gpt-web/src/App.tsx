import React, { useState, useEffect } from 'react';
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
  const [showOverlay, setShowOverlay] = useState(false);

  const toggleStatus = (name: string) => {
    setIntegrations({ ...integrations, [name]: !integrations[name] });
  };

  return (
    <div className="App">
      {showOverlay && <div className="overlay"></div>}
      <header className="App-header">
        <h1 className='page-title'>GPT Home - Integrations Dashboard</h1>
        <div className="integrations-dashboard">
          <Integration
            name="Spotify"
            status={integrations.Spotify}
            toggleStatus={toggleStatus}
            setShowOverlay={setShowOverlay}
          />
          <Integration
            name="Google Calendar"
            status={integrations.GoogleCalendar}
            toggleStatus={toggleStatus}
            setShowOverlay={setShowOverlay}
          />
          <Integration
            name="Philips Hue"
            status={integrations.PhilipsHue}
            toggleStatus={toggleStatus}
            setShowOverlay={setShowOverlay}
          />
        </div>
      </header>
    </div>
  );
};

export default App;
