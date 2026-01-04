import React, { useEffect, useMemo } from 'react';
import { motion } from 'framer-motion';
import Integration from './Integration';
import { Icons } from './Icons';
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

const serviceIcons: { [key: string]: React.FC<{ className?: string }> } = {
  Spotify: Icons.Music,
  OpenWeather: Icons.Cloud,
  PhilipsHue: Icons.Lightbulb,
  CalDAV: Icons.Calendar,
};

const serviceColors: { [key: string]: string } = {
  Spotify: 'from-emerald-500 to-emerald-600',
  OpenWeather: 'from-amber-500 to-orange-500',
  PhilipsHue: 'from-violet-500 to-purple-600',
  CalDAV: 'from-primary-500 to-cyan-500',
};

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

  useEffect(() => {
    fetchStatuses();
    // eslint-disable-next-line
  }, []);

  const containerVariants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: { staggerChildren: 0.1 }
    }
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0 }
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Integrations</h1>
          <p className="text-slate-500 dark:text-slate-400 mt-1">Connect your services to enable voice commands</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="badge-success">
            <span className="w-2 h-2 rounded-full bg-emerald-500 mr-2 animate-pulse" />
            {Object.values(integrations).filter(i => i.status).length} Active
          </span>
          <span className="badge-error">
            <span className="w-2 h-2 rounded-full bg-rose-500 mr-2" />
            {Object.values(integrations).filter(i => !i.status).length} Inactive
          </span>
        </div>
      </div>

      {/* Integration cards */}
      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="show"
        className="grid gap-6 md:grid-cols-2"
      >
        {Object.keys(integrations).map((name) => {
          const ServiceIcon = serviceIcons[name];
          const colorClass = serviceColors[name];
          const isActive = integrations[name as keyof typeof integrations].status;

          return (
            <motion.div
              key={name}
              variants={itemVariants}
              className="card overflow-hidden group"
            >
              {/* Header section */}
              <div className={`bg-gradient-to-r ${colorClass} p-6 relative overflow-hidden`}>
                <div className="absolute inset-0 bg-black/10" />
                <div className="absolute -right-8 -top-8 w-32 h-32 bg-white/10 rounded-full" />
                <div className="absolute -right-4 -bottom-4 w-20 h-20 bg-white/10 rounded-full" />
                
                <div className="relative flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="p-3 bg-white/20 backdrop-blur-sm rounded-xl">
                      <ServiceIcon className="w-7 h-7 text-white" />
                    </div>
                    <div>
                      <h3 className="text-xl font-semibold text-white">{name}</h3>
                      <div className="flex items-center gap-2 mt-1">
                        <span className={`w-2 h-2 rounded-full ${isActive ? 'bg-white animate-pulse' : 'bg-white/50'}`} />
                        <span className="text-sm text-white/80">
                          {isActive ? 'Connected' : 'Not connected'}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Content section */}
              <div className="p-6">
                {/* Usage examples */}
                <div className="mb-6">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-3">
                    Example Commands
                  </h4>
                  <div className="space-y-2">
                    {usage[name].map((phrase, idx) => (
                      <div
                        key={idx}
                        className="flex items-center gap-3 text-sm text-slate-600 dark:text-slate-300"
                      >
                        <Icons.Mic className="w-4 h-4 text-slate-400 flex-shrink-0" />
                        <span>"{phrase}"</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Action buttons */}
                <Integration
                  name={name}
                  status={isActive}
                  usage={usage[name]}
                  requiredFields={requiredFields}
                  toggleStatus={toggleStatus}
                  setShowOverlay={toggleOverlay}
                />
              </div>
            </motion.div>
          );
        })}
      </motion.div>
    </div>
  );
};

export default Integrations;
