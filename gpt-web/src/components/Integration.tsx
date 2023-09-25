import React, { useState } from 'react';
import axios from 'axios';
import '../css/Integration.css';

interface IntegrationProps {
  name: string;
  status: boolean;
  usage: string[];
  requiredFields: { [key: string]: string[] };
  toggleStatus: (name: string) => void;
  setShowOverlay: (visible: boolean) => void;
}

const Integration: React.FC<IntegrationProps> = ({ name, usage, status, requiredFields, toggleStatus, setShowOverlay }) => {
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({} as { [key: string]: string });
  const [error, setError] = useState('');
  const apiRefs: { [key: string]: string[] } = {
    Spotify: ['https://developer.spotify.com/documentation/web-api/'],
    GoogleCalendar: ['https://developers.google.com/calendar/api/quickstart/python'],
    PhilipsHue: ['https://developers.meethue.com/develop/get-started-2/', 'https://github.com/studioimaginaire/phue'],
  };

  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    setFormData({ ...formData, [name]: value });
    setError('');
  };

  const connectService = async () => {
    // Validate that all required fields have values
    for (const field of requiredFields[name]) {
      if (!formData[field as keyof typeof formData]) {
        setError(`Please enter a value for ${field}`);
        setShowOverlay(false);
        return;
      }
    }
  
    // Prepare the payload with all the required fields
    let fields: { [key: string]: string } = {};
    for (const field of requiredFields[name]) {
      fields[field] = formData[field as keyof typeof formData];
    }
  
    // Make the Axios POST request
    axios.post('/connect-service', { name, fields })
    .then((response) => {
      if (response.data.redirect_url) {
        window.location.replace(response.data.redirect_url)
      } else if (response.data.success) {
          // If successfully connected, toggle the status and reset the form
          if (!status) toggleStatus(name); // only toggle if not already connected
          setShowOverlay(false);
          setShowForm(false);
          if (name !== "PhilipsHue") {
            // Clear all fields except for PhilipsHue
            setFormData({} as { [key: string]: string });
          }
        } else {
          // Handle errors returned from the server
          setError(`Error connecting to ${name}: ${response.data.error}`);
          console.log(response.data.traceback);
          setShowOverlay(false);
        }
      })
      .catch((error) => {
        // Handle network or server errors
        setError(`Error connecting to ${name}: ${error}`);
        console.log("Error: ", error);
        console.log("Error Response: ", error.response);
        setShowOverlay(false);
      });
  };  

  const disconnectService = async () => {
    if (window.confirm(`Are you sure you want to disconnect from ${name}?`))
      axios.post('/disconnect-service', { name }).then((response) => {
        if (response.data.success) {
          toggleStatus(name);
          setShowOverlay(false);
          setShowForm(false);
          // clear all fields
          setFormData({} as { [key: string]: string });
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

  const handlePaste = (event: React.ClipboardEvent<HTMLInputElement>) => {
    event.preventDefault();
    const text = event.clipboardData.getData('text/plain').replace(/\s+/g, '');
    const { name } = event.currentTarget;
    setFormData({ ...formData, [name]: text });
  };  

  const disallowSpace = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === ' ') {
      event.preventDefault();
    }
  };

  return (
    <div className="integration">
      {usage.map((phrase) => (
        <h4 key={phrase}>{phrase}</h4>
      ))}
      {status && 
        <button className="btn-edit" onClick={() => setShowForm(true)}>
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
            {name === 'PhilipsHue' && <div style={{ color: 'red' }}>NOTE: Press the button on the bridge before submitting if connecting for the first time.</div> }
            {name === 'Spotify' &&
              <div style={{ color: 'red' }}>
                NOTE: The REDIRECT URI is set by default but be sure to also set it in your Spotify application settings:<br />
                REDIRECT URI: <span style={{ color: 'green', fontFamily: 'monospace' }}><br />
                  http://&#123;your_raspbery_pi_ip&#125;/api/callback</span>
              </div>
            }
            {requiredFields[name].map((field) => (
              <div key={field}>
                <input
                  type="text"
                  name={field}
                  placeholder={field}
                  value={formData[field as keyof typeof formData]}
                  onChange={handleInputChange}
                  onKeyDown={disallowSpace}
                  onPaste={handlePaste}
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
