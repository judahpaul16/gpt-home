import React from 'react';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Integration from './Integration';
import '../css/Integrations.css';

interface IndividualIntegration {
  status: boolean;
  usage: string[];
}

interface IntegrationStatus {
  [key: string]: IndividualIntegration;
}

interface IntegrationsProps {
  toggleStatus: (name: string) => void;
  toggleOverlay: (visible: boolean) => void;
  integrations: {Spotify: boolean, GoogleCalendar: boolean, PhilipsHue: boolean};
}

const Integrations: React.FC<IntegrationsProps> = ({ toggleStatus, toggleOverlay }) => {
  const [integrations] = React.useState<IntegrationStatus>({
    Spotify: { status: false, usage: ["Play....on Spotify", "Next Song / Go Back", "Play / Pause / Stop"] },
    GoogleCalendar: { status: false, usage: ["Schedule a meeting for...", "Delete event on..."] },
    PhilipsHue: { status: false, usage: ["Turn on lights", "Turn off lights", "Dim the lights to..."] },
  });

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
                  {integrations[name].status ? 'Connected' : 'Not Connected'}
                </TableCell>
                <TableCell>
                  <Integration
                    name={name}
                    status={integrations[name].status}
                    usage={integrations[name].usage}
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
