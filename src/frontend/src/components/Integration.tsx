import React, { useState, useEffect } from 'react';
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
  const [ipAddress, setIpAddress] = useState<string>("");
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({} as { [key: string]: string });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [spotifyTokenExists, setSpotifyTokenExists] = useState(false);
  const apiRefs: { [key: string]: string[] } = {
    Spotify: ['https://developer.spotify.com/documentation/web-api/', 'https://developer.spotify.com/dashboard/'],
    OpenWeather: ['https://openweathermap.org/api/one-call-3', 'https://home.openweathermap.org/api_keys'],
    PhilipsHue: ['https://developers.meethue.com/develop/get-started-2/', 'https://github.com/studioimaginaire/phue'],
    CalDAV: ['https://en.wikipedia.org/wiki/CalDAV', 'https://caldav.readthedocs.io/en/latest/'],
  };

  const fetchIPAddress = async () => {
    try {
      const response = await axios.post('/get-local-ip');
      if (response.status === 200 && response.data.ip) {
        setIpAddress(response.data.ip);
      } else {
        setIpAddress("{raspberry_pi_local_ip}");
      }
    } catch (error: any) {
      if (error.response && error.response.status === 404) {
        setIpAddress("{raspberry_pi_local_ip}");
      }
    }
  };

  useEffect(() => {
    // fetch IP address on mount
    if (name === "Spotify") fetchIPAddress();
    if (name === "Spotify") {
      // check if token exists
      axios.post('/spotify-token-exists').then((response) => {
        if (response.data.token_exists) {
          setSpotifyTokenExists(true);
        }
      }).catch((error) => {
        console.log("Error: ", error);
        console.log("Error Response: ", error.response);
      });
    }
  }, [name]);
  
  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    setFormData({ ...formData, [name]: value });
    setError('');
  };

  const connectService = async () => {
    // Validate that all required fields have values
    setLoading(true);
    for (const field of requiredFields[name]) {
      if (!formData[field as keyof typeof formData]) {
        setError(`Please enter a value for ${field}`);
        setShowOverlay(false);
        setLoading(false);
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
          window.location.replace(response.data.redirect_url);
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
        setLoading(false);
      })
      .catch((error) => {
        // Handle network or server errors
        setError(`Error connecting to ${name}: ${error}`);
        console.log("Error: ", error);
        console.log("Error Response: ", error.response);
        setShowOverlay(false);
        setLoading(false);
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

  const reauthSpotify = async () => {
      axios.post('/reauthorize-spotify', { name }).then((response) => {
        if (response.data.redirect_url) {
          window.location.replace(response.data.redirect_url)
        } else {
          // Handle errors returned from the server
          setError(`Error reauthorizing ${name}: ${response.data.error}`);
          console.log(response.data.traceback);
        }
      }).catch((error) => {
        // Handle network or server errors
        setError(`Error reauthorizing ${name}: ${error}`);
        console.log("Error: ", error);
        console.log("Error Response: ", error.response);
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
      {!status && name === 'Spotify' && spotifyTokenExists &&
        <button className="btn-reauthorize" onClick={reauthSpotify}>
          Reauthorize
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
                  http://gpt-home.local/api/callback</span><br />
                For networks without mDNS, use the IP address instead:<br />
                <span style={{ color: 'green', fontFamily: 'monospace' }}>
                  http://{ipAddress}/api/callback</span><br />
              </div>
            }
            {name === 'CalDAV' &&
              <div style={{ color: 'red' }}>
                NOTE: CalDAV requests must be made over HTTPS.<br />
                More information on CalDAV URLs can be found <a target='_blank' rel='noopener noreferrer' href='https://caldav.readthedocs.io/en/latest/#some-notes-on-caldav-urls'>here</a>.
              </div>
            }
            {requiredFields[name].map((field) => (
              <div key={field}>
                <input
                  type={field === 'PASSWORD' ? 'password' : 'text'}
                  name={field}
                  placeholder={field}
                  value={formData[field as keyof typeof formData]}
                  onChange={handleInputChange}
                  onKeyDown={disallowSpace}
                  onPaste={handlePaste}
                  autoFocus={requiredFields[name].indexOf(field) === 0}
                />
              </div>
            ))}
            <button onClick={connectService} disabled={loading} className="submit">
              {loading ? <div className="spinner"></div> : 'Submit'}
            </button>
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
