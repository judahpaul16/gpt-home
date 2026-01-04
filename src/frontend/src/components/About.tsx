import React from 'react';
import { motion } from 'framer-motion';
import { Icons } from './Icons';
import { VERSION_INFO } from '../version';

const About: React.FC = () => {
  const formatDate = (dateString: string) => {
    if (dateString === 'N/A') return 'N/A';
    try {
      return new Date(dateString).toLocaleString();
    } catch {
      return dateString;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-slate-900 dark:text-white">About</h1>
        <p className="text-slate-500 dark:text-slate-400 mt-1">Learn more about GPT Home</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Left column */}
        <div className="space-y-6">
          {/* Main info card */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="card overflow-hidden"
          >
            <div className="bg-gradient-to-br from-primary-500 via-accent-violet to-accent-cyan p-8 relative">
              <div className="absolute inset-0 bg-black/10" />
              <div className="absolute -right-16 -top-16 w-48 h-48 bg-white/10 rounded-full blur-2xl" />
              <div className="absolute -left-8 -bottom-8 w-32 h-32 bg-white/10 rounded-full blur-xl" />
              
              <div className="relative text-center">
                <div className="inline-flex p-4 rounded-2xl bg-white/20 backdrop-blur-sm mb-4">
                  <Icons.Home className="w-12 h-12 text-white" />
                </div>
                <h2 className="text-2xl font-bold text-white mb-2">GPT Home</h2>
                <p className="text-white/80">Smart Assistant for Raspberry Pi</p>
              </div>
            </div>

            <div className="p-6 space-y-4">
              <p className="text-slate-600 dark:text-slate-300 leading-relaxed">
                ChatGPT at home! A better alternative to commercial smart home assistants,
                built on the Raspberry Pi using the OpenAI API.
              </p>

              <div className="flex flex-wrap gap-2">
                <span className="badge-info">Voice Controlled</span>
                <span className="badge-success">Open Source</span>
                <span className="badge-warning">Raspberry Pi</span>
              </div>

              <div className="pt-4 border-t border-slate-200 dark:border-dark-700">
                <p className="flex items-center gap-2 text-slate-600 dark:text-slate-400">
                  Made with <Icons.Heart className="w-4 h-4 text-rose-500" /> by Judah Paul
                </p>
              </div>
            </div>
          </motion.div>

          {/* Version Info Section */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="card p-6"
          >
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
              <Icons.Info className="w-5 h-5 text-primary-500" />
              Version Information
            </h3>
            <div className="space-y-3">
              <div className="flex justify-between items-center py-2 border-b border-slate-100 dark:border-dark-700">
                <span className="text-slate-500 dark:text-slate-400">Version</span>
                <span className="font-mono text-sm bg-primary-500/10 text-primary-600 dark:text-primary-400 px-2 py-1 rounded">
                  v{VERSION_INFO.version}
                </span>
              </div>
              <div className="flex justify-between items-center py-2 border-b border-slate-100 dark:border-dark-700">
                <span className="text-slate-500 dark:text-slate-400">Last Commit</span>
                <span className="font-mono text-sm bg-slate-100 dark:bg-dark-700 text-slate-600 dark:text-slate-300 px-2 py-1 rounded">
                  {VERSION_INFO.lastCommit}
                </span>
              </div>
              <div className="flex justify-between items-center py-2 border-b border-slate-100 dark:border-dark-700">
                <span className="text-slate-500 dark:text-slate-400">Commit Date</span>
                <span className="text-sm text-slate-600 dark:text-slate-300">
                  {formatDate(VERSION_INFO.commitDate)}
                </span>
              </div>
              <div className="flex justify-between items-center py-2">
                <span className="text-slate-500 dark:text-slate-400">Build Timestamp</span>
                <span className="text-sm text-slate-600 dark:text-slate-300">
                  {formatDate(VERSION_INFO.buildTimestamp)}
                </span>
              </div>
            </div>
          </motion.div>
        </div>

        {/* Right column */}
        <div className="space-y-6">
          {/* Links & Resources */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
            className="card p-6"
          >
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
              <Icons.Link className="w-5 h-5 text-primary-500" />
              Links & Resources
            </h3>
            <div className="space-y-3">
              <a
                href="https://github.com/judahpaul16/gpt-home"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 p-3 rounded-lg hover:bg-slate-100 dark:hover:bg-dark-700 transition-colors group"
              >
                <Icons.Github className="w-5 h-5 text-slate-600 dark:text-slate-400" />
                <span className="flex-1 text-slate-700 dark:text-slate-300 group-hover:text-primary-500 transition-colors">Source Code</span>
                <Icons.ExternalLink className="w-4 h-4 text-slate-400" />
              </a>
              <a
                href="https://github.com/judahpaul16/gpt-home/wiki"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 p-3 rounded-lg hover:bg-slate-100 dark:hover:bg-dark-700 transition-colors group"
              >
                <Icons.Info className="w-5 h-5 text-slate-600 dark:text-slate-400" />
                <span className="flex-1 text-slate-700 dark:text-slate-300 group-hover:text-primary-500 transition-colors">Documentation</span>
                <Icons.ExternalLink className="w-4 h-4 text-slate-400" />
              </a>
              <a
                href="https://github.com/judahpaul16/gpt-home/issues"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 p-3 rounded-lg hover:bg-slate-100 dark:hover:bg-dark-700 transition-colors group"
              >
                <Icons.AlertCircle className="w-5 h-5 text-slate-600 dark:text-slate-400" />
                <span className="flex-1 text-slate-700 dark:text-slate-300 group-hover:text-primary-500 transition-colors">Report an Issue</span>
                <Icons.ExternalLink className="w-4 h-4 text-slate-400" />
              </a>
              <a
                href="https://github.com/judahpaul16/gpt-home/releases"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 p-3 rounded-lg hover:bg-slate-100 dark:hover:bg-dark-700 transition-colors group"
              >
                <Icons.ArrowDown className="w-5 h-5 text-slate-600 dark:text-slate-400" />
                <span className="flex-1 text-slate-700 dark:text-slate-300 group-hover:text-primary-500 transition-colors">Releases & Updates</span>
                <Icons.ExternalLink className="w-4 h-4 text-slate-400" />
              </a>
            </div>
          </motion.div>

          {/* License */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="card p-6"
          >
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
              <Icons.Key className="w-5 h-5 text-primary-500" />
              License
            </h3>
            <p className="text-slate-600 dark:text-slate-300 text-sm leading-relaxed mb-3">
              This project is licensed under the MIT License. You are free to use, modify, and distribute 
              this software in accordance with the license terms.
            </p>
            <a
              href="https://github.com/judahpaul16/gpt-home/blob/main/LICENSE"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-primary-500 hover:text-primary-600 transition-colors inline-flex items-center gap-1"
            >
              View full license <Icons.ExternalLink className="w-3 h-3" />
            </a>
          </motion.div>

          {/* Support */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25 }}
            className="card p-6 bg-gradient-to-br from-primary-500/5 to-accent-violet/5 border-primary-500/20"
          >
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">
              Support the Project
            </h3>
            <p className="text-slate-600 dark:text-slate-300 text-sm mb-4">
              If you find GPT Home useful, consider sponsoring!
            </p>
            <a
              href="https://github.com/sponsors/judahpaul16"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-900 dark:bg-white text-white dark:text-slate-900 text-sm font-medium hover:opacity-90 transition-opacity"
            >
              <Icons.Github className="w-4 h-4" />
              Sponsor
            </a>
          </motion.div>
        </div>
      </div>
    </div>
  );
};

export default About;
