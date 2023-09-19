import React from 'react';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Integration from './Integration';

interface IntegrationStatus {
  [key: string]: boolean;
}

interface IntegrationsProps {
    toggleStatus: (name: string) => void;
    toggleOverlay: (visible: boolean) => void;
}

const Integrations: React.FC<IntegrationsProps> = ({ toggleStatus, toggleOverlay }) => {
  const [integrations] = React.useState<IntegrationStatus>({
    Spotify: false,
    GoogleCalendar: false,
    PhilipsHue: false,
  });

  return (
    <div className="dashboard integrations-dashboard">
      <h2>Integrations Dashboard</h2>
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
                {integrations[name as keyof IntegrationStatus] ? 'Connected' : 'Disconnected'}
              </TableCell>
              <TableCell>
              <Integration
                name={name}
                status={integrations[name as keyof IntegrationStatus]}
                toggleStatus={toggleStatus}
                setShowOverlay={(visible) => toggleOverlay(visible)}
                />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
};

export default Integrations;
