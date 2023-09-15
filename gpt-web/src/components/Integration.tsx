import React, { useState } from 'react';
import axios from 'axios';
import '../css/Integration.css';

interface IntegrationProps {
  name: string;
  status: boolean;
  toggleStatus: (name: string) => void;
}

const Integration: React.FC<IntegrationProps> = ({ name, status, toggleStatus }) => {
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({ apiKey: '' });
  const [error, setError] = useState('');

  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    setFormData({ ...formData, [name]: value });
    setError(''); // Clear error when the user types
  };

  const connectService = async () => {
    if (!formData.apiKey) {
      setError('API Key cannot be empty');
      return;
    }

    try {
      const response = await axios.post(`/api/connect/${name}`, formData);
      if (response.status === 200) {
        toggleStatus(name);
        setShowForm(false);
        setError(''); // Clear error on successful connection
      }
    } catch (error) {
      setError('Failed to connect');
      console.error(`Failed to connect ${name}`, error);
    }
  };

  const disconnectService = async () => {
    try {
      const response = await axios.post(`/api/disconnect/${name}`);
      if (response.status === 200) {
        toggleStatus(name);
      }
    } catch (error) {
      setError('Failed to disconnect');
      console.error(`Failed to disconnect ${name}`, error);
    }
  };

  return (
    <div className="integration">
      <h3>{name}</h3>
      {showForm ? (
        <div className="overlay">
          <div className="form-container">
            <input
              type="text"
              name="apiKey"
              placeholder="API Key"
              value={formData.apiKey}
              onChange={handleInputChange}
            />
            <button onClick={connectService}>Submit</button>
            <button onClick={() => setShowForm(false)}>Cancel</button>
            {error && <div className="error-text">{error}</div>}
          </div>
        </div>
      ) : (
        <button onClick={status ? disconnectService : () => setShowForm(true)}>
          {status ? 'Disconnect' : 'Connect'}
        </button>
      )}
    </div>
  );
};

export default Integration;
