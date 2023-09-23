import React, { useEffect, useMemo } from 'react';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Integration from './Integration';
import '../css/Integrations.css';
import axios from 'axios';

interface IntegrationsProps {
  setStatus: (name: string, status: boolean) => void;
  toggleStatus: (name: string) => void;
  toggleOverlay: (visible: boolean) => void;
  integrations: {
    Spotify: { status: boolean; usage: string[] };
    GoogleCalendar: { status: boolean; usage: string[] };
    PhilipsHue: { status: boolean; usage: string[] };
  };
}

const Integrations: React.FC<IntegrationsProps> = ({ setStatus, toggleStatus, toggleOverlay, integrations }) => {
  const usage: { [key: string]: string[] } = {
    Spotify: ['Play.....on Spotify', 'Play / Pause / Stop', 'Next Song / Go Back'],
    GoogleCalendar: ['Schedule an event', 'What\'s on my calendar?',],
    PhilipsHue: ['Dim the lights to...', 'Turn on / off....lights', 'Set the lights to red'],
  };

  const requiredFields: { [key: string]: string[] } = useMemo(() => ({
    Spotify: ['API Key'],
    GoogleCalendar: ['API Key'],
    PhilipsHue: ['Bridge IP Address', 'Username'],
  }), []);

  useEffect(() => {
    const fetchStatus = async (name: string) => {
      try {
        const response = await axios.post(`/get-service-status`, { name });
        const status = response.data.status;
        setStatus(name, status);
      } catch (error) {
        console.log('Error fetching initial status:', error);
      }
    };
    
    Object.keys(integrations).forEach((name) => {
      fetchStatus(name);
    });
    // eslint-disable-next-line
  }, []);  
  
  return (
    <div className="dashboard integrations-dashboard">
      <h2>Integrations Dashboard</h2>
      <div className="table-container">
        <Table>
          <TableHead className="TableHead">
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
                  {integrations[name as keyof typeof integrations].status ? 'Connected' : 'Not Connected'}
                </TableCell>
                <TableCell>
                <Integration
                  name={name}
                  status={integrations[name as keyof typeof integrations]?.status}
                  usage={usage[name as keyof typeof usage]}
                  requiredFields={requiredFields}
                  toggleStatus={toggleStatus}
                  setShowOverlay={(visible) => toggleOverlay(visible)}
                />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
};

export default Integrations;
