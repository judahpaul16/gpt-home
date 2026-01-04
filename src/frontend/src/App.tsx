import React, { useState, useEffect, useMemo } from 'react';
import { Route, Routes, Link, Navigate, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import PasswordModal from './components/PasswordModal';
import EventLogs from './components/EventLogs';
import Settings from './components/Settings';
import About from './components/About';
import Integrations from './components/Integrations';
import { Icons } from './components/Icons';
import { cn } from './lib/utils';

const App: React.FC = () => {
  const location = useLocation();
  const [darkMode, setDarkMode] = useState<boolean>(true);
  const [sidebarOpen, setSidebarOpen] = useState(window.innerWidth >= 768);
  const [showOverlay, setShowOverlay] = useState(false);
  const [unlocked, setUnlocked] = useState(false);

  const [integrations, setIntegrations] = useState<{
    Spotify: { status: boolean; usage: string[] };
    OpenWeather: { status: boolean; usage: string[] };
    PhilipsHue: { status: boolean; usage: string[] };
    CalDAV: { status: boolean; usage: string[] };
  }>({
    Spotify: { status: false, usage: [] },
    OpenWeather: { status: false, usage: [] },
    PhilipsHue: { status: false, usage: [] },
    CalDAV: { status: false, usage: [] }
  });

  const memoizedIntegrations = useMemo(() => integrations, [integrations]);

  useEffect(() => {
    getMode();
  }, []);

  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [darkMode]);

  const getMode = async () => {
    try {
      const response = await fetch('/api/settings/dark-mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await response.json();
      setDarkMode(data.darkMode);
    } catch (error) {
      console.error("Failed to fetch dark mode setting", error);
      setDarkMode(true);
    }
  };

  const toggleDarkMode = () => {
    const newMode = !darkMode;
    setDarkMode(newMode);
    fetch('/api/settings/dark-mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ darkMode: newMode })
    });
  };

  const setStatus = (name: string, status: boolean) => {
    setIntegrations(prev => ({
      ...prev,
      [name]: { ...prev[name as keyof typeof prev], status }
    }));
  };

  const toggleStatus = (name: string) => {
    if (name in integrations) {
      setIntegrations(prev => ({
        ...prev,
        [name]: {
          ...prev[name as keyof typeof prev],
          status: !prev[name as keyof typeof prev].status
        }
      }));
    }
  };

  const toggleOverlay = (visible: boolean) => setShowOverlay(visible);

  // Handle resize
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 768) {
        setSidebarOpen(false);
      } else {
        setSidebarOpen(true);
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const navItems = [
    { path: '/integrations', label: 'Integrations', icon: Icons.Integrations },
    { path: '/event-logs', label: 'Event Logs', icon: Icons.Logs },
    { path: '/settings', label: 'Settings', icon: Icons.Settings },
    { path: '/about', label: 'About', icon: Icons.Info },
  ];

  if (process.env.NODE_ENV !== 'development' && !unlocked) {
    return <PasswordModal unlockApp={() => setUnlocked(true)} darkMode={darkMode} toggleDarkMode={toggleDarkMode} />;
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-dark-900 transition-colors duration-300">
      {/* Overlay */}
      <AnimatePresence>
        {showOverlay && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40"
            onClick={() => setShowOverlay(false)}
          />
        )}
      </AnimatePresence>

      {/* Mobile menu button */}
      <button
        onClick={() => setSidebarOpen(!sidebarOpen)}
        className={cn(
          "fixed top-4 left-4 z-50 p-2.5 rounded-xl bg-white dark:bg-dark-800 shadow-lg",
          "border border-slate-200 dark:border-dark-700 lg:hidden transition-all hover:scale-105",
          sidebarOpen && "opacity-0 pointer-events-none"
        )}
      >
        <Icons.Menu />
      </button>

      {/* Theme toggle */}
      <button
        onClick={toggleDarkMode}
        className="fixed top-4 right-4 z-50 p-2.5 rounded-xl bg-white dark:bg-dark-800 shadow-lg 
                   border border-slate-200 dark:border-dark-700 transition-all hover:scale-105 group"
      >
        <motion.div
          initial={false}
          animate={{ rotate: darkMode ? 180 : 0 }}
          transition={{ duration: 0.3 }}
        >
          {darkMode ? (
            <Icons.Sun className="text-amber-500" />
          ) : (
            <Icons.Moon className="text-slate-600" />
          )}
        </motion.div>
      </button>

      {/* Sidebar */}
      <AnimatePresence mode="wait">
        {sidebarOpen && (
          <>
            {/* Mobile overlay */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setSidebarOpen(false)}
              className="fixed inset-0 bg-black/20 backdrop-blur-sm z-30 lg:hidden"
            />

            {/* Sidebar panel */}
            <motion.aside
              initial={{ x: -280 }}
              animate={{ x: 0 }}
              exit={{ x: -280 }}
              transition={{ type: "spring", damping: 25, stiffness: 200 }}
              className="fixed left-0 top-0 bottom-0 w-72 z-40 lg:z-30"
            >
              <div className="h-auto m-4 glass-card overflow-hidden flex flex-col">
                {/* Mobile close button */}
                <button
                  onClick={() => setSidebarOpen(false)}
                  className="lg:hidden absolute top-6 right-6 p-2 rounded-lg bg-slate-100 dark:bg-dark-700 
                             hover:bg-slate-200 dark:hover:bg-dark-600 transition-colors z-10"
                >
                  <Icons.X className="w-5 h-5 text-slate-500 dark:text-slate-400" />
                </button>

                {/* Logo */}
                <Link 
                  to="/integrations" 
                  className="flex items-center gap-3 p-6 pb-4 hover:opacity-80 transition-opacity"
                  onClick={() => window.innerWidth < 768 && setSidebarOpen(false)}
                >
                  <div className="p-2 rounded-xl bg-gradient-to-br from-primary-500 to-accent-violet shadow-lg shadow-primary-500/25 flex-shrink-0">
                    <Icons.Home className="text-white" />
                  </div>
                  <div className="min-w-0">
                    <h1 className="text-xl font-bold text-slate-900 dark:text-white whitespace-nowrap">GPT Home</h1>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Smart Assistant</p>
                  </div>
                </Link>

                {/* Nav items */}
                <nav className="flex-1 px-4 py-2 space-y-1">
                  {navItems.map((item) => {
                    const isActive = location.pathname === item.path;
                    const Icon = item.icon;
                    return (
                      <Link
                        key={item.path}
                        to={item.path}
                        onClick={() => window.innerWidth < 768 && setSidebarOpen(false)}
                        className={cn(
                          "flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200",
                          isActive
                            ? "bg-primary-500/10 text-primary-600 dark:text-primary-400 font-medium"
                            : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-dark-700"
                        )}
                      >
                        <Icon className={cn(isActive && "text-primary-500")} />
                        <span>{item.label}</span>
                        {isActive && (
                          <motion.div
                            layoutId="activeIndicator"
                            className="ml-auto w-1.5 h-1.5 rounded-full bg-primary-500"
                          />
                        )}
                      </Link>
                    );
                  })}
                </nav>
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* Main content */}
      <main 
        className={cn(
          "min-h-screen transition-all duration-300 p-4 md:p-8",
          sidebarOpen ? "lg:ml-80" : ""
        )}
      >
        <div className="max-w-6xl mx-auto pt-14 lg:pt-0">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.2 }}
            >
              <Routes>
                <Route path="/event-logs" element={<EventLogs />} />
                <Route 
                  path="/integrations" 
                  element={
                    <Integrations 
                      setStatus={setStatus} 
                      toggleStatus={toggleStatus} 
                      toggleOverlay={toggleOverlay} 
                      integrations={memoizedIntegrations} 
                    />
                  } 
                />
                <Route path="/settings" element={<Settings />} />
                <Route path="/about" element={<About />} />
                <Route index element={<Navigate to="/integrations" />} />
              </Routes>
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
};

export default App;
