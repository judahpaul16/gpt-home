import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';
import { Icons, Spinner } from './Icons';
import { cn } from '../lib/utils';
import ConfirmModal, { useConfirm } from './ConfirmModal';

interface IntegrationProps {
  name: string;
  status: boolean;
  usage: string[];
  requiredFields: { [key: string]: string[] };
  toggleStatus: (name: string) => void;
  setShowOverlay: (visible: boolean) => void;
}

const Integration: React.FC<IntegrationProps> = ({ name, status, requiredFields, toggleStatus, setShowOverlay }) => {
  const [ipAddress, setIpAddress] = useState<string>("");
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({} as { [key: string]: string });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [spotifyTokenExists, setSpotifyTokenExists] = useState(false);
  const { confirmConfig, showConfirm, closeConfirm } = useConfirm();

  const apiRefs: { [key: string]: string[] } = {
    Spotify: ['https://developer.spotify.com/documentation/web-api/', 'https://developer.spotify.com/dashboard/'],
    OpenWeather: ['https://openweathermap.org/api/one-call-3', 'https://home.openweathermap.org/api_keys'],
    PhilipsHue: ['https://developers.meethue.com/develop/get-started-2/', 'https://github.com/studioimaginaire/phue'],
    CalDAV: ['https://en.wikipedia.org/wiki/CalDAV', 'https://caldav.readthedocs.io/en/latest/'],
  };

  useEffect(() => {
    if (name === "Spotify") {
      axios.post('/get-local-ip').then(response => {
        setIpAddress(response.data.ip || "{raspberry_pi_local_ip}");
      }).catch(() => setIpAddress("{raspberry_pi_local_ip}"));

      axios.post('/spotify-token-exists').then(response => {
        if (response.data.token_exists) setSpotifyTokenExists(true);
      }).catch(console.error);
    }
  }, [name]);

  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    setFormData({ ...formData, [name]: value });
    setError('');
  };

  const connectService = async () => {
    setLoading(true);
    for (const field of requiredFields[name]) {
      if (!formData[field as keyof typeof formData]) {
        setError(`Please enter ${field.toLowerCase()}`);
        setLoading(false);
        return;
      }
    }

    let fields: { [key: string]: string } = {};
    for (const field of requiredFields[name]) {
      fields[field] = formData[field as keyof typeof formData];
    }

    axios.post('/connect-service', { name, fields })
      .then((response) => {
        if (response.data.redirect_url) {
          window.location.replace(response.data.redirect_url);
        } else if (response.data.success) {
          if (!status) toggleStatus(name);
          setShowOverlay(false);
          setShowForm(false);
          if (name !== "PhilipsHue") setFormData({});
        } else {
          setError(response.data.message || response.data.error || 'Connection failed');
          setShowOverlay(false);
        }
        setLoading(false);
      })
      .catch((error) => {
        const errorMsg = error.response?.data?.message || error.response?.data?.error || error.message || 'Connection failed';
        setError(errorMsg);
        setShowOverlay(false);
        setLoading(false);
      });
  };

  const disconnectService = async () => {
    showConfirm(
      'Disconnect Service',
      `Are you sure you want to disconnect from ${name}?`,
      () => {
        axios.post('/disconnect-service', { name }).then((response) => {
          if (response.data.success) {
            toggleStatus(name);
            setShowOverlay(false);
            setShowForm(false);
            setFormData({});
          } else {
            setError(`Error disconnecting: ${response.data.error}`);
          }
        }).catch((error) => {
          setError(`Error disconnecting: ${error.message}`);
        });
      },
      { confirmText: 'Disconnect', variant: 'danger' }
    );
  };

  const reauthSpotify = async () => {
    axios.post('/reauthorize-spotify', { name }).then((response) => {
      if (response.data.redirect_url) {
        window.location.replace(response.data.redirect_url);
      } else {
        setError(`Error reauthorizing: ${response.data.error}`);
      }
    }).catch((error) => {
      setError(`Error reauthorizing: ${error.message}`);
    });
  };

  const handlePaste = (event: React.ClipboardEvent<HTMLInputElement>) => {
    event.preventDefault();
    const text = event.clipboardData.getData('text/plain').replace(/\s+/g, '');
    const { name } = event.currentTarget;
    setFormData({ ...formData, [name]: text });
  };

  const disallowSpace = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === ' ') event.preventDefault();
  };

  return (
    <>
      <ConfirmModal config={confirmConfig} onClose={closeConfirm} />
      {/* Action buttons */}
      <div className="flex flex-wrap gap-2">
        {status && (
          <button
            onClick={() => setShowForm(true)}
            className="btn-secondary flex items-center gap-2 text-sm"
          >
            <Icons.Edit className="w-4 h-4" />
            Edit
          </button>
        )}
        {!status && name === 'Spotify' && spotifyTokenExists && (
          <button
            onClick={reauthSpotify}
            className="btn-secondary flex items-center gap-2 text-sm"
          >
            <Icons.Refresh className="w-4 h-4" />
            Reauthorize
          </button>
        )}
        <button
          onClick={status ? disconnectService : () => setShowForm(true)}
          className={cn(
            "flex items-center gap-2 text-sm",
            status ? "btn-danger" : "btn-success"
          )}
        >
          {status ? (
            <>
              <Icons.Unlink className="w-4 h-4" />
              Disconnect
            </>
          ) : (
            <>
              <Icons.Link className="w-4 h-4" />
              Connect
            </>
          )}
        </button>
      </div>

      {/* Modal */}
      <AnimatePresence>
        {showForm && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
            onClick={(e) => e.target === e.currentTarget && setShowForm(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="w-full max-w-lg glass-card overflow-hidden"
            >
              {/* Modal header */}
              <div className="flex items-center justify-between p-6 border-b border-slate-200 dark:border-dark-700">
                <div>
                  <h3 className="text-xl font-semibold text-slate-900 dark:text-white">
                    Configure {name}
                  </h3>
                  <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                    Enter your credentials to connect
                  </p>
                </div>
                <button
                  onClick={() => setShowForm(false)}
                  className="btn-icon"
                >
                  <Icons.X />
                </button>
              </div>

              {/* Modal body */}
              <div className="p-6 space-y-4 max-h-[60vh] overflow-y-auto">
                {/* API References */}
                {apiRefs[name]?.length > 0 && (
                  <div className="p-4 rounded-xl bg-slate-100 dark:bg-dark-700/50">
                    <h4 className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                      API Documentation
                    </h4>
                    <div className="space-y-1">
                      {apiRefs[name].map((link) => (
                        <a
                          key={link}
                          target='_blank'
                          rel='noopener noreferrer'
                          href={link}
                          className="flex items-center gap-2 text-sm text-primary-600 dark:text-primary-400 hover:underline"
                        >
                          <Icons.ExternalLink className="w-3.5 h-3.5" />
                          <span className="truncate">{link}</span>
                        </a>
                      ))}
                    </div>
                  </div>
                )}

                {/* Service-specific notes */}
                {name === 'PhilipsHue' && (
                  <div className="p-4 rounded-xl bg-amber-100 dark:bg-amber-900/20 text-amber-800 dark:text-amber-300 text-sm">
                    <strong>Note:</strong> Press the button on the bridge before submitting if connecting for the first time.
                  </div>
                )}

                {name === 'Spotify' && (
                  <div className="p-4 rounded-xl bg-emerald-100 dark:bg-emerald-900/20 text-emerald-800 dark:text-emerald-300 text-sm space-y-2">
                    <p><strong>Redirect URI Setup:</strong></p>
                    <code className="block p-2 bg-emerald-200/50 dark:bg-emerald-900/30 rounded-lg text-xs font-mono">
                      http://gpt-home.local/api/callback
                    </code>
                    <p className="text-xs opacity-75">For networks without mDNS:</p>
                    <code className="block p-2 bg-emerald-200/50 dark:bg-emerald-900/30 rounded-lg text-xs font-mono">
                      http://{ipAddress}/api/callback
                    </code>
                  </div>
                )}

                {name === 'CalDAV' && (
                  <div className="p-4 rounded-xl bg-primary-100 dark:bg-primary-900/20 text-primary-800 dark:text-primary-300 text-sm">
                    <strong>Note:</strong> CalDAV requests must be made over HTTPS.{' '}
                    <a 
                      target='_blank' 
                      rel='noopener noreferrer' 
                      href='https://caldav.readthedocs.io/en/latest/#some-notes-on-caldav-urls'
                      className="underline"
                    >
                      Learn more
                    </a>
                  </div>
                )}

                {/* Form fields */}
                {requiredFields[name].map((field) => (
                  <div key={field}>
                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                      {field}
                    </label>
                    <input
                      type={field === 'PASSWORD' ? 'password' : 'text'}
                      name={field}
                      placeholder={`Enter ${field.toLowerCase()}`}
                      value={formData[field as keyof typeof formData] || ''}
                      onChange={handleInputChange}
                      onKeyDown={disallowSpace}
                      onPaste={handlePaste}
                      className="input-field"
                      autoFocus={requiredFields[name].indexOf(field) === 0}
                    />
                  </div>
                ))}

                {/* Error message */}
                {error && (
                  <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="flex items-center gap-2 p-3 rounded-xl bg-rose-100 dark:bg-rose-900/20 text-rose-600 dark:text-rose-400 text-sm"
                  >
                    <Icons.AlertCircle className="flex-shrink-0" />
                    <span>{error}</span>
                  </motion.div>
                )}
              </div>

              {/* Modal footer */}
              <div className="flex justify-end gap-3 p-6 border-t border-slate-200 dark:border-dark-700 bg-slate-50 dark:bg-dark-800/50">
                <button
                  onClick={() => setShowForm(false)}
                  className="btn-secondary"
                >
                  Cancel
                </button>
                <button
                  onClick={connectService}
                  disabled={loading}
                  className="btn-primary flex items-center gap-2"
                >
                  {loading ? (
                    <Spinner size="sm" />
                  ) : (
                    <>
                      <Icons.Check className="w-4 h-4" />
                      Submit
                    </>
                  )}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
};

export default Integration;
