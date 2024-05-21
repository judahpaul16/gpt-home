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
    [key: string]: { status: boolean; usage: string[] };
    Spotify: { status: boolean; usage: string[] };
    OpenWeather: { status: boolean; usage: string[] };
    PhilipsHue: { status: boolean; usage: string[] };
    CalDAV: { status: boolean; usage: string[] };
  };
}

const Integrations: React.FC<IntegrationsProps> = ({ setStatus, toggleStatus, toggleOverlay, integrations }) => {
  const usage: { [key: string]: string[] } = {
    Spotify: ['Play.....on Spotify', 'Play / Pause / Stop', 'Next Song / Go Back'],
    OpenWeather: ['How\'s the weather?', 'What\'s the temperature in....'],
    PhilipsHue: ['Dim the lights to...', 'Turn on / off....lights', 'Change the lights to red'],
    CalDAV: ['What\'s on my calendar?', 'What\'s my next event?', 'Add an event to my calendar'],
  };

  const requiredFields: { [key: string]: string[] } = useMemo(() => ({
    Spotify: ['USERNAME', 'PASSWORD', 'CLIENT ID', 'CLIENT SECRET'],
    OpenWeather: ['API KEY'],
    PhilipsHue: ['BRIDGE IP ADDRESS'],
    CalDAV: ['URL', 'USERNAME', 'PASSWORD'],
  }), []);

  const fetchStatuses = async () => {
    try {
      const response = await axios.post('/get-service-statuses');
      const statuses = response.data.statuses;
  
      for (const name of Object.keys(integrations)) {
        if (statuses.hasOwnProperty(name)) {
          setStatus(name, statuses[name]);
        }
      }
    } catch (error) {}
  };
  
  // fetch statuses on mount
  useEffect(() => {
    fetchStatuses();
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
