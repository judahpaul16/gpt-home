import React, { useState, useEffect } from 'react';
import axios from 'axios';
import '../css/Integration.css';

interface IntegrationProps {
  name: string;
  status: boolean;
  usage: string[];
  toggleStatus: (name: string) => void;
  setShowOverlay: (visible: boolean) => void;
}

const Integration: React.FC<IntegrationProps> = ({ name, status, usage, toggleStatus, setShowOverlay }) => {
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({ apiKey: '' });
  const [error, setError] = useState('');
  const apiRefs: { [key: string]: string[] } = {
    Spotify: ['https://developer.spotify.com/documentation/web-api/'],
    GoogleCalendar: ['https://developers.google.com/calendar/api/quickstart/python'],
    PhilipsHue: [],
  };
  const requiredFields: { [key: string]: string[] } = {
    Spotify: ['API Key'],
    GoogleCalendar: ['API Key'],
    PhilipsHue: ['Bridge IP Address', 'Username'],
  };

  useEffect(() => {
    // Function to fetch initial service status
    const fetchInitialStatus = async () => {
      try {
        const response = await axios.post(`/is-service-connected`, { fields: requiredFields[name] });
        if (response.data.success) {
          toggleStatus(name);
        }
      } catch (error) {
        console.log('Error fetching initial status:', error);
      }
    };
    fetchInitialStatus();
    // eslint-disable-next-line
  }, []);

  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    setFormData({ ...formData, [name]: value });
    setError('');
  };

  const connectService = async () => {
    setShowOverlay(true);
    for (const field of requiredFields[name]) {
      if (!formData[field as keyof typeof formData]) {
        setError(`Please enter a value for ${field}`);
        setShowOverlay(false);
        return;
      }
    }

    let fields: { [key: string]: string } = {};
    for (const field of requiredFields[name]) {
      fields[field] = formData[field as keyof typeof formData];
    }

    axios.post('/connect-service', { fields }).then((response) => {
      if (response.data.success) {
        toggleStatus(name);
        setShowOverlay(false);
      } else {
        setError(`Error connecting to ${name}: ${response.data.error}`);
        console.log(response.data.traceback);
        setShowOverlay(false);
      }
    }).catch((error) => {
      setError(`Error connecting to ${name}: ${error}`);
      console.log("Error: ", error);
      console.log("Error Response: ", error.response);
      setShowOverlay(false);
    });
  };

  const disconnectService = async () => {
    setShowOverlay(true);
    axios.post('/disconnect-service', { name }).then((response) => {
      if (response.data.success) {
        toggleStatus(name);
        setShowOverlay(false);
      } else {
        setError(`Error disconnecting from ${name}: ${response.data.error}`);
        console.log(response.data.traceback);
        setShowOverlay(false);
      }
    }).catch((error) => {
      setError(`Error disconnecting from ${name}: ${error}`);
      console.log("Error: ", error);
      console.log("Error Response: ", error.response);
      setShowOverlay(false);
    });
  };

  const editService = async () => {
    setShowOverlay(true);
    for (const field of requiredFields[name]) {
      if (!formData[field as keyof typeof formData]) {
        setError(`Please enter a value for ${field}`);
        setShowOverlay(false);
        return;
      }
    }

    let fields: { [key: string]: string } = {};
    for (const field of requiredFields[name]) {
      fields[field] = formData[field as keyof typeof formData];
    }

    axios.post('/connect-service', { fields }).then((response) => {
      if (response.data.success) {
        toggleStatus(name);
        setShowOverlay(false);
      } else {
        setError(`Error editing ${name}: ${response.data.error}`);
        console.log(response.data.traceback);
        setShowOverlay(false);
      }
    }).catch((error) => {
      setError(`Error editing ${name}: ${error}`);
      console.log("Error: ", error);
      console.log("Error Response: ", error.response);
      setShowOverlay(false);
    });
  };

  return (
    <div className="integration">
      {usage.map((phrase) => (
        <h4 key={phrase}>{phrase}</h4>
      ))}
      {status && 
        <button className="btn-edit" onClick={editService}>
          Edit
        </button>
      }
      {showForm &&
        <div className="overlay">
          <div className="form-container">
            { apiRefs[name] && apiRefs[name].length > 0 &&
              <h4>{name} API Integration Reference:<hr/>
                {apiRefs[name].map((link) => (
                  <a key={link} target='_blank' rel='noopener noreferrer' href={link}>{link}<br/></a>
                ))}
              </h4>
            }
            {requiredFields[name].map((field) => (
              <div key={field}>
                <input
                  type="text"
                  name={field}
                  placeholder={field}
                  value={formData[field as keyof typeof formData]}
                  onChange={handleInputChange}
                />
              </div>
            ))}
            <button onClick={connectService}>Submit</button>
            <button onClick={() => setShowForm(false)}>Cancel</button>
            {error && <div className="error-text">{error}</div>}
          </div>
        </div>
      }
      <button
        className={status ? 'btn-disconnect' : 'btn-connect'}
        onClick={status ? disconnectService : () => setShowForm(true)}
      >
        {status ? 'Disconnect' : 'Connect'}
      </button>
    </div>
  );
};

export default Integration;
