import React from 'react';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Integration from './Integration';
import '../css/Integrations.css';

interface IntegrationsProps {
  toggleStatus: (name: string) => void;
  toggleOverlay: (visible: boolean) => void;
  integrations: {
    Spotify: { status: boolean; usage: string[] };
    GoogleCalendar: { status: boolean; usage: string[] };
    PhilipsHue: { status: boolean; usage: string[] };
  };
}

const Integrations: React.FC<IntegrationsProps> = ({ toggleStatus, toggleOverlay, integrations }) => {
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
                    usage={integrations[name as keyof typeof integrations]?.usage}
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
