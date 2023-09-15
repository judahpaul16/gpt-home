import React, { useState } from 'react';
import '../css/Integration.css';

interface IntegrationProps {
  name: string;
  status: boolean;
  toggleStatus: (name: string) => void;
  setShowOverlay: (visible: boolean) => void;
}

const Integration: React.FC<IntegrationProps> = ({ name, status, toggleStatus, setShowOverlay }) => {
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({ apiKey: '' });
  const [error, setError] = useState('');

  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    setFormData({ ...formData, [name]: value });
    setError('');
  };

  const connectService = async () => {
    setShowOverlay(true);
    if (!formData.apiKey)
      setError('API Key cannot be empty');
    setShowOverlay(false);
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
        <button onClick={status ? connectService : () => setShowForm(true)}>
          {status ? 'Disconnect' : 'Connect'}
        </button>
      )}
    </div>
  );
};

export default Integration;
