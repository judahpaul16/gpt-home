import React, { useState, useEffect } from 'react';
import { Route, Routes, Link, Navigate } from 'react-router-dom';
import './css/App.css';
import EventLogs from './components/EventLogs';
import Integrations from './components/Integrations';
import Drawer from '@mui/material/Drawer';
import ButtonBase from '@mui/material/ButtonBase';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import SettingsIcon from '@mui/icons-material/Settings';
import ChatIcon from '@mui/icons-material/Chat';
import InfoIcon from '@mui/icons-material/Info';
import IntegrationIcon from '@mui/icons-material/IntegrationInstructions';
import IconButton from '@mui/material/IconButton';
import MenuIcon from '@mui/icons-material/Menu';

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
  const [sidebarVisible, setSidebarVisible] = useState(window.innerWidth >= 768);

  const toggleStatus = (name: string) => {
    setIntegrations({ ...integrations, [name]: !integrations[name] });
  };

  const toggleOverlay = (visible: boolean) => {
    setShowOverlay(visible);
  };

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 768) {
        setSidebarVisible(false);
      } else {
        setSidebarVisible(true);
      }
    };
    window.addEventListener('resize', handleResize);
    // Clean up the event listener when the component unmounts
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  return (
    <div className="App">
      {showOverlay && <div className="overlay"></div>}
      <header className="App-header">
        <div className="dashboard-container">
          <IconButton
            edge="start"
            color="inherit"
            aria-label="menu"
            className="menu-toggle"
            onClick={() => setSidebarVisible(!sidebarVisible)}
          >
            <MenuIcon />
          </IconButton>
          <Drawer
            variant="persistent"
            open={sidebarVisible}
            className={sidebarVisible ? 'sidebar open' : 'sidebar closed'}
          >
            <div className={sidebarVisible ? 'MuiPaper-root open' : 'MuiPaper-root closed'}>
              <h1 className="sidebar-title">GPT Home</h1>
              <List>
                <Link to="/integrations">
                  <ButtonBase>
                    <ListItem key="Integrations">
                      <ListItemIcon>
                        <IntegrationIcon />
                      </ListItemIcon>
                      <ListItemText primary="Integrations" />
                    </ListItem>
                  </ButtonBase>
                </Link>
                <Link to="/event-logs">
                  <ButtonBase>
                    <ListItem key="Event Logs">
                      <ListItemIcon>
                        <ChatIcon />
                      </ListItemIcon>
                      <ListItemText primary="Event Logs" />
                    </ListItem>
                  </ButtonBase>
                </Link>
                <Link to="/settings">
                  <ButtonBase>
                    <ListItem key="Settings">
                      <ListItemIcon>
                        <SettingsIcon />
                      </ListItemIcon>
                      <ListItemText primary="Settings" />
                    </ListItem>
                  </ButtonBase>
                </Link>
                <Link to="/about">
                  <ButtonBase>
                    <ListItem key="About">
                      <ListItemIcon>
                        <InfoIcon />
                      </ListItemIcon>
                      <ListItemText primary="About" />
                    </ListItem>
                  </ButtonBase>
                </Link>
              </List>
            </div>
          </Drawer>
          <Routes>
            <Route path="/event-logs" element={<EventLogs />} />
            <Route path="/integrations" element={<Integrations toggleStatus={toggleStatus} toggleOverlay={toggleOverlay} />} />
            <Route index element={<Navigate to="/integrations" />} />
          </Routes>
        </div>
      </header>
    </div>
  );  
};

export default App;
