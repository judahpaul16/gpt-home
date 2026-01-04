import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import axios from 'axios';
import { Icons, Spinner } from './Icons';
import { cn } from '../lib/utils';
import AlertModal, { useAlert } from './AlertModal';
import ConfirmModal, { useConfirm } from './ConfirmModal';

// Provider detection patterns for API keys
const PROVIDER_PATTERNS: Record<string, RegExp> = {
  openai: /^sk-[a-zA-Z0-9-_]{20,}$/,
  anthropic: /^sk-ant-[a-zA-Z0-9-_]+$/,
  google: /^AIza[a-zA-Z0-9-_]{35}$/,
  cohere: /^[a-zA-Z0-9]{40}$/,
  mistral: /^[a-zA-Z0-9]{32}$/,
  groq: /^gsk_[a-zA-Z0-9]{52}$/,
  together: /^[a-f0-9]{64}$/,
  deepseek: /^sk-[a-f0-9]{32}$/,
};

// Chat/completion model prefixes for each provider (excludes embedding, TTS, image models)
const PROVIDER_CHAT_PREFIXES: Record<string, string[]> = {
  openai: ['gpt-', 'o1-', 'o3-', 'chatgpt-'],
  anthropic: ['claude-'],
  google: ['gemini/', 'gemini-'],
  cohere: ['command'],
  mistral: ['mistral/', 'mistral-', 'codestral', 'pixtral', 'ministral'],
  groq: ['groq/', 'llama', 'mixtral', 'gemma'],
  together: ['together/', 'together_ai/'],
  deepseek: ['deepseek/', 'deepseek-'],
};

// Patterns to exclude from chat models (embedding, TTS, STT, image generation)
const NON_CHAT_PATTERNS = [
  'text-embedding', 'embed-', 'embedding',
  'tts-', 'whisper', 'dall-e', 'image',
  'moderation', 'davinci', 'babbage', 'ada-', 'curie'
];

// Providers that support LiteLLM TTS
const LITELLM_TTS_PROVIDERS = ['openai', 'google'];
// Providers that support LiteLLM STT
const LITELLM_STT_PROVIDERS = ['openai', 'groq', 'google'];

// Embedding models by provider
const EMBEDDING_MODELS: Record<string, string[]> = {
  openai: ['openai:text-embedding-3-small', 'openai:text-embedding-3-large', 'openai:text-embedding-ada-002'],
  anthropic: ['anthropic:voyage-3', 'anthropic:voyage-3-lite', 'anthropic:voyage-code-2'],
  google: ['google:text-embedding-004', 'google:text-multilingual-embedding-002'],
  cohere: ['cohere:embed-english-v3.0', 'cohere:embed-multilingual-v3.0', 'cohere:embed-english-light-v3.0'],
  mistral: ['mistral:mistral-embed'],
  together: ['together:togethercomputer/m2-bert-80M-8k-retrieval'],
  deepseek: ['openai:text-embedding-3-small'], // DeepSeek uses OpenAI-compatible embeddings
  groq: ['openai:text-embedding-3-small'], // Groq doesn't have embeddings, fallback to OpenAI
};

const detectProvider = (apiKey: string): string | null => {
  if (!apiKey) return null;
  for (const [provider, pattern] of Object.entries(PROVIDER_PATTERNS)) {
    if (pattern.test(apiKey)) return provider;
  }
  return null;
};

const Settings: React.FC = () => {
  const [settings, setSettings] = useState<any>({});
  const [isLoading, setLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [allModels, setAllModels] = useState<string[]>([]);
  const [filteredModels, setFilteredModels] = useState<string[]>([]);
  const [embeddingModels, setEmbeddingModels] = useState<string[]>([]);
  const [detectedProvider, setDetectedProvider] = useState<string | null>(null);
  const [oldPassword, setOldPassword] = useState<string>('');
  const [newPassword, setNewPassword] = useState<string>('');
  const [confirmInput, setConfirmInput] = useState<string>('');
  const { alertConfig, showAlert, closeAlert } = useAlert();
  const { confirmConfig, showConfirm, closeConfirm } = useConfirm();

  // Detect provider when API key changes
  useEffect(() => {
    const provider = detectProvider(settings.litellm_api_key || '');
    setDetectedProvider(provider);
    
    // Helper to check if model is a chat/completion model (not embedding/TTS/image)
    const isChatModel = (model: string): boolean => {
      const lowerModel = model.toLowerCase();
      return !NON_CHAT_PATTERNS.some(pattern => lowerModel.includes(pattern));
    };
    
    if (provider && allModels.length > 0) {
      const prefixes = PROVIDER_CHAT_PREFIXES[provider] || [];
      const filtered = allModels.filter(model => {
        const lowerModel = model.toLowerCase();
        const matchesProvider = prefixes.some(prefix => lowerModel.startsWith(prefix.toLowerCase()));
        return matchesProvider && isChatModel(model);
      });
      setFilteredModels(filtered.length > 0 ? filtered : allModels.filter(isChatModel));
      setEmbeddingModels(EMBEDDING_MODELS[provider] || EMBEDDING_MODELS.openai);
    } else {
      setFilteredModels(allModels.filter(isChatModel));
      setEmbeddingModels(Object.values(EMBEDDING_MODELS).flat());
    }
  }, [settings.litellm_api_key, allModels]);

  useEffect(() => {
    Promise.all([
      axios.post('/api/settings', { action: 'read' }),
      axios.post('/availableModels')
    ]).then(([settingsRes, modelsRes]) => {
      setSettings(settingsRes.data);
      if (modelsRes.data.models) {
        setAllModels(modelsRes.data.models);
      }
    }).catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const updateSettings = async () => {
    if (oldPassword !== '' || newPassword !== '' || confirmInput !== '') {
      if (oldPassword === '') {
        showAlert('warning', 'Validation Error', 'Old password is required');
        return;
      } else if (newPassword === '') {
        showAlert('warning', 'Validation Error', 'New password is required');
        return;
      } else if (newPassword.length < 6) {
        showAlert('warning', 'Validation Error', 'New password must be at least 6 characters');
        return;
      } else if (newPassword === oldPassword) {
        showAlert('warning', 'Validation Error', 'New password must be different');
        return;
      } else if (newPassword !== confirmInput) {
        showAlert('warning', 'Validation Error', 'Passwords do not match');
        return;
      } else {
        await changePassword();
      }
    }

    setIsSaving(true);
    axios.post('/api/settings', { action: 'update', data: settings })
      .then((response) => {
        setSettings(response.data);
        showAlert('success', 'Settings Saved', 'Your settings have been saved successfully.');
      })
      .catch(console.error)
      .finally(() => setIsSaving(false));
  };

  const changePassword = () => {
    return axios.post('/changePassword', { oldPassword, newPassword })
      .then(() => {
        showAlert('success', 'Password Changed', 'Your password has been changed successfully.');
        setOldPassword('');
        setNewPassword('');
        setConfirmInput('');
      })
      .catch(() => showAlert('error', 'Password Change Failed', 'Failed to change password. Please check your old password.'));
  };

  const gptRestart = () => {
    showConfirm(
      'Restart GPT Home',
      'Are you sure you want to restart the GPT Home service?',
      () => {
        axios.post('/gptRestart')
          .then(() => showAlert('success', 'Service Restarted', 'GPT Home service has been restarted.'))
          .catch(() => showAlert('error', 'Restart Failed', 'Failed to restart GPT Home service.'));
      },
      { confirmText: 'Restart' }
    );
  };

  const spotifyRestart = () => {
    showConfirm(
      'Restart Spotifyd',
      'Are you sure you want to restart the Spotifyd service?',
      () => {
        axios.post('/spotifyRestart')
          .then(() => showAlert('success', 'Service Restarted', 'Spotifyd service has been restarted.'))
          .catch(() => showAlert('error', 'Restart Failed', 'Failed to restart Spotifyd service.'));
      },
      { confirmText: 'Restart' }
    );
  };

  const shutdown = () => {
    showConfirm(
      'Shutdown System',
      'Are you sure you want to shutdown the system? You will need physical access to turn it back on.',
      () => {
        axios.post('/shutdown')
          .then(() => showAlert('info', 'Shutting Down', 'The system is shutting down...'))
          .catch(() => showAlert('error', 'Shutdown Failed', 'Failed to shutdown the system.'));
      },
      { confirmText: 'Shutdown', variant: 'danger' }
    );
  };

  const reboot = () => {
    showConfirm(
      'Reboot System',
      'Are you sure you want to reboot the system?',
      () => {
        axios.post('/reboot')
          .then(() => showAlert('info', 'Rebooting', 'The system is rebooting...'))
          .catch(() => showAlert('error', 'Reboot Failed', 'Failed to reboot the system.'));
      },
      { confirmText: 'Reboot', variant: 'danger' }
    );
  };

  const clearMemory = () => {
    showConfirm(
      'Clear Memory',
      'Are you sure you want to clear all conversation history and memories? This action cannot be undone.',
      () => {
        axios.post('/clearMemory')
          .then(() => showAlert('success', 'Memory Cleared', 'All conversation history and memories have been cleared.'))
          .catch(() => showAlert('error', 'Clear Memory Failed', 'Failed to clear memory.'));
      },
      { confirmText: 'Clear Memory', variant: 'danger' }
    );
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <>
      <AlertModal config={alertConfig} onClose={closeAlert} />
      <ConfirmModal config={confirmConfig} onClose={closeConfirm} />
      <div className="space-y-8">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Settings</h1>
          <p className="text-slate-500 dark:text-slate-400 mt-1">Configure your GPT Home assistant</p>
        </div>
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={updateSettings}
          disabled={isSaving}
          className="btn-primary flex items-center gap-2"
        >
          {isSaving ? <Spinner size="sm" /> : <Icons.Save />}
          Save Changes
        </motion.button>
      </div>

      {/* Quick Actions */}
      <div className="card p-6">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Quick Actions</h2>
        <div className="flex flex-wrap gap-3">
          <button onClick={gptRestart} className="btn-secondary flex items-center gap-2">
            <Icons.Refresh className="w-4 h-4" />
            Restart GPT Home
          </button>
          <button onClick={spotifyRestart} className="btn-secondary flex items-center gap-2">
            <Icons.Music className="w-4 h-4" />
            Restart Spotifyd
          </button>
          <button onClick={reboot} className="btn-icon group relative">
            <Icons.RotateCw />
            <span className="tooltip">Reboot System</span>
          </button>
          <button onClick={shutdown} className="btn-icon group relative text-rose-500">
            <Icons.Power />
            <span className="tooltip">Shutdown</span>
          </button>
          <button onClick={clearMemory} className="btn-secondary flex items-center gap-2 text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-900/20">
            <Icons.Trash className="w-4 h-4" />
            Clear Memory
          </button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* API Key & LLM Settings Combined */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="card p-6 lg:col-span-2"
        >
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 rounded-xl bg-gradient-to-br from-primary-100 to-violet-100 dark:from-primary-900/30 dark:to-violet-900/30">
              <Icons.Key className="w-5 h-5 text-primary-600 dark:text-primary-400" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-slate-900 dark:text-white">LLM Configuration</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">Powered by LiteLLM — supports 100+ providers</p>
            </div>
            <a
              href="https://docs.litellm.ai/docs/providers"
              target="_blank"
              rel="noreferrer"
              className="ml-auto text-primary-500 hover:text-primary-600 flex items-center gap-1 text-sm"
            >
              View supported providers
              <Icons.ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>

          <div className="space-y-6">
            {/* API Key - Full Width */}
            <div>
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                API Key
              </label>
              <input
                type="password"
                value={settings.litellm_api_key || ''}
                onChange={(e) => setSettings({ ...settings, litellm_api_key: e.target.value })}
                className="input-field"
                placeholder="Enter your API key (OpenAI, Anthropic, etc.)"
              />
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                {detectedProvider ? (
                  <span className="flex items-center gap-1">
                    <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                    Detected: <span className="font-medium capitalize">{detectedProvider}</span> — model lists filtered automatically
                  </span>
                ) : (
                  'Works with OpenAI, Anthropic, Google, Cohere, Mistral, Groq, and more'
                )}
              </p>
            </div>

            {/* Model Selectors Row */}
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                  Chat Model {detectedProvider && <span className="text-xs text-slate-400 font-normal">({filteredModels.length} available)</span>}
                </label>
                <div className="relative">
                  {filteredModels.length > 0 ? (
                    <>
                      <select
                        value={settings.model || ''}
                        onChange={(e) => setSettings({ ...settings, model: e.target.value })}
                        className="select-field"
                      >
                        {filteredModels.map((model) => (
                          <option key={model} value={model}>{model}</option>
                        ))}
                      </select>
                      <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                    </>
                  ) : (
                    <div className="input-field text-slate-400">Loading models...</div>
                  )}
                </div>
              </div>

              <div>
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                  Embedding Model {detectedProvider && <span className="text-xs text-slate-400 font-normal">({embeddingModels.length} available)</span>}
                </label>
                <div className="relative">
                  <select
                    value={settings.embedding_model || ''}
                    onChange={(e) => setSettings({ ...settings, embedding_model: e.target.value })}
                    className="select-field"
                  >
                    {embeddingModels.map((model) => (
                      <option key={model} value={model}>{model}</option>
                    ))}
                  </select>
                  <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                </div>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">For memory &amp; semantic search</p>
              </div>
            </div>

            {/* Parameters Row */}
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                  Max Tokens
                </label>
                <input
                  type="number"
                  value={settings.max_tokens || ''}
                  onChange={(e) => setSettings({ ...settings, max_tokens: parseInt(e.target.value, 10) })}
                  className="input-field"
                  placeholder="e.g., 1024"
                />
              </div>

              <div className="flex flex-col justify-center items-center">
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mt-6 block">
                  Temperature <span className="text-xs text-slate-400 font-normal">(0 = focused, 2 = creative)</span>
                </label>
                <div className="flex items-center gap-3 h-[42px] w-[90%]">
                  <input
                    type="range"
                    min="0"
                    max="2"
                    step="0.1"
                    value={settings.temperature || 0}
                    onChange={(e) => setSettings({ ...settings, temperature: parseFloat(e.target.value) })}
                    className="flex-1 h-2 bg-slate-200 dark:bg-dark-600 rounded-lg appearance-none cursor-pointer accent-primary-500"
                  />
                  <span className="text-sm font-mono text-slate-600 dark:text-slate-400 w-8 text-right">
                    {settings.temperature?.toFixed(1) || '0.0'}
                  </span>
                </div>
              </div>
            </div>

            {/* Custom Instructions - Full Width */}
            <div>
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                Custom Instructions
              </label>
              <textarea
                value={settings.custom_instructions || ''}
                onChange={(e) => setSettings({ ...settings, custom_instructions: e.target.value })}
                className="input-field min-h-[80px] resize-y"
                placeholder="Add any custom instructions for the assistant..."
              />
            </div>
          </div>
        </motion.div>

        {/* General Settings */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="card p-6"
        >
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 rounded-xl bg-emerald-100 dark:bg-emerald-900/30">
              <Icons.Settings className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
            </div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">General</h2>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                Wake Word
              </label>
              <input
                type="text"
                value={settings.keyword || ''}
                onChange={(e) => setSettings({ ...settings, keyword: e.target.value })}
                className="input-field"
              />
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                Speech Engine
              </label>
              <div className="relative">
                <select
                  value={settings.speechEngine || ''}
                  onChange={(e) => setSettings({ ...settings, speechEngine: e.target.value })}
                  className="select-field"
                >
                  <option value="pyttsx3">pyttsx3 (Offline)</option>
                  <option value="gtts">gTTS (Google TTS)</option>
                  <option 
                    value="litellm"
                    disabled={!detectedProvider || !LITELLM_TTS_PROVIDERS.includes(detectedProvider)}
                  >
                    LiteLLM {detectedProvider && LITELLM_TTS_PROVIDERS.includes(detectedProvider) 
                      ? `(${detectedProvider})` 
                      : '(requires OpenAI/Google key)'}
                  </option>
                </select>
                <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
              </div>
              {settings.speechEngine === 'litellm' && detectedProvider && (
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                  TTS: {LITELLM_TTS_PROVIDERS.includes(detectedProvider) ? '✓' : '✗'} | 
                  STT: {LITELLM_STT_PROVIDERS.includes(detectedProvider) ? '✓' : '✗ (fallback to Google)'}
                </p>
              )}
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                Repeat Input
              </label>
              <div className="relative">
                <select
                  value={settings.sayHeard || ''}
                  onChange={(e) => setSettings({ ...settings, sayHeard: e.target.value })}
                  className="select-field"
                >
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
                <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
              </div>
            </div>
          </div>
        </motion.div>

        {/* Change Password */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="card p-6"
        >
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 rounded-xl bg-amber-100 dark:bg-amber-900/30">
              <Icons.Lock className="w-5 h-5 text-amber-600 dark:text-amber-400" />
            </div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Change Password</h2>
          </div>

          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                Current Password
              </label>
              <input
                type="password"
                value={oldPassword}
                onChange={(e) => setOldPassword(e.target.value)}
                className="input-field"
              />
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                New Password
              </label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="input-field"
              />
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                Confirm New Password
              </label>
              <input
                type="password"
                value={confirmInput}
                onChange={(e) => setConfirmInput(e.target.value)}
                className={cn(
                  "input-field",
                  confirmInput && newPassword !== confirmInput && "border-rose-500 focus:ring-rose-500/50"
                )}
              />
              {confirmInput && newPassword !== confirmInput && (
                <p className="text-xs text-rose-500 mt-1">Passwords do not match</p>
              )}
            </div>
          </div>
        </motion.div>
      </div>
    </div>
    </>
  );
};

export default Settings;
