import React, { useState, useEffect } from 'react';
import './css/App.css';
import Integration from './components/Integration';
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
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';

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
          <Drawer
            variant="persistent"
            open={sidebarVisible}
            className={sidebarVisible ? 'sidebar open' : 'sidebar closed'}
          >
            <div className={sidebarVisible ? 'MuiPaper-root open' : 'MuiPaper-root closed'}>
              <h1 className="sidebar-title">GPT Home</h1>
              <List>
                <ButtonBase>
                  <ListItem key="Integrations">
                    <ListItemIcon>
                      <IntegrationIcon />
                    </ListItemIcon>
                    <ListItemText primary="Integrations" />
                  </ListItem>
                </ButtonBase>
                <ButtonBase>
                  <ListItem key="Chat Logs">
                    <ListItemIcon>
                      <ChatIcon />
                    </ListItemIcon>
                    <ListItemText primary="Chat Logs" />
                  </ListItem>
                </ButtonBase>
                <ButtonBase>
                  <ListItem key="Settings">
                    <ListItemIcon>
                      <SettingsIcon />
                    </ListItemIcon>
                    <ListItemText primary="Settings" />
                  </ListItem>
                </ButtonBase>
                <ButtonBase>
                  <ListItem key="About">
                    <ListItemIcon>
                      <InfoIcon />
                    </ListItemIcon>
                    <ListItemText primary="About" />
                  </ListItem>
                </ButtonBase>
              </List>
            </div>
          </Drawer>
          <div className="integrations-dashboard">
            <h2>Integrations Dashboard</h2>
            <IconButton
              className="menu-toggle"
              edge="start"
              color="inherit"
              aria-label="menu"
              onClick={() => setSidebarVisible(!sidebarVisible)}
            >
              <MenuIcon />
            </IconButton>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Action</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {Object.keys(integrations).map((name) => (
                  <TableRow key={name}>
                    <TableCell>{name}</TableCell>
                    <TableCell>
                      {integrations[name as keyof IntegrationStatus]
                        ? 'Connected'
                        : 'Disconnected'}
                    </TableCell>
                    <TableCell>
                      <Integration
                        name={name}
                        status={integrations[name as keyof IntegrationStatus]}
                        toggleStatus={toggleStatus}
                        setShowOverlay={setShowOverlay}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      </header>
    </div>
  );  
};

export default App;
