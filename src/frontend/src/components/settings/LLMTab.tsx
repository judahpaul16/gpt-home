import React from "react";
import { Icons } from "../Icons";

interface LLMTabProps {
    settings: any;
    setSettings: (s: any) => void;
    detectedProvider: string | null;
    filteredModels: string[];
    embeddingModels: string[];
}

const LLMTab: React.FC<LLMTabProps> = ({
    settings,
    setSettings,
    detectedProvider,
    filteredModels,
    embeddingModels,
}) => {
    return (
        <div className="space-y-6">
            {/* Provider */}
            <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">
                    Provider
                </h3>
                <div className="sm:grid sm:grid-cols-3 sm:gap-4 sm:items-center">
                    <div className="flex items-center gap-2 mb-2 sm:mb-0">
                        <div className="p-1.5 rounded-lg bg-amber-100 dark:bg-amber-900/30">
                            <Icons.Key className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
                        </div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
                            API Key
                        </label>
                        <a
                            href="https://docs.litellm.ai/docs/providers"
                            target="_blank"
                            rel="noreferrer"
                            className="text-primary-500 hover:text-primary-600"
                        >
                            <Icons.ExternalLink className="w-3.5 h-3.5" />
                        </a>
                    </div>
                    <div className="sm:col-span-2">
                        <input
                            type="password"
                            value={settings.litellm_api_key || ""}
                            onChange={(e) =>
                                setSettings({
                                    ...settings,
                                    litellm_api_key: e.target.value,
                                })
                            }
                            className="input-field"
                            placeholder="Enter your API key"
                        />
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                            {detectedProvider ? (
                                <span className="flex items-center gap-1">
                                    <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                                    Detected:{" "}
                                    <span className="font-medium capitalize">
                                        {detectedProvider}
                                    </span>
                                </span>
                            ) : (
                                "OpenAI, Anthropic, Google, Groq, etc."
                            )}
                        </p>
                    </div>
                </div>
            </div>

            {/* Models */}
            <div className="border-t border-slate-200 dark:border-slate-700 pt-6">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">
                    Models
                </h3>
                <div className="space-y-4">
                    <div className="sm:grid sm:grid-cols-3 sm:gap-4 sm:items-center">
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 sm:mb-0 block">
                            Chat Model{" "}
                            {detectedProvider && (
                                <span className="text-xs text-slate-400 font-normal">
                                    ({filteredModels.length})
                                </span>
                            )}
                        </label>
                        <div className="sm:col-span-2">
                            <div className="relative">
                                {filteredModels.length > 0 ? (
                                    <>
                                        <select
                                            value={settings.model || ""}
                                            onChange={(e) =>
                                                setSettings({
                                                    ...settings,
                                                    model: e.target.value,
                                                })
                                            }
                                            className="select-field"
                                        >
                                            {filteredModels.map((model) => (
                                                <option
                                                    key={model}
                                                    value={model}
                                                >
                                                    {model}
                                                </option>
                                            ))}
                                        </select>
                                        <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                                    </>
                                ) : (
                                    <div className="input-field text-slate-400">
                                        Loading models...
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    <div className="sm:grid sm:grid-cols-3 sm:gap-4 sm:items-center">
                        <div>
                            <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 sm:mb-0 block">
                                Embedding Model
                            </label>
                            <p className="text-xs text-slate-400 hidden sm:block">
                                For memory &amp; semantic search
                            </p>
                        </div>
                        <div className="sm:col-span-2">
                            <div className="relative">
                                <select
                                    value={settings.embedding_model || ""}
                                    onChange={(e) =>
                                        setSettings({
                                            ...settings,
                                            embedding_model: e.target.value,
                                        })
                                    }
                                    className="select-field"
                                >
                                    {embeddingModels.map((model) => (
                                        <option key={model} value={model}>
                                            {model}
                                        </option>
                                    ))}
                                </select>
                                <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Parameters */}
            <div className="border-t border-slate-200 dark:border-slate-700 pt-6">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">
                    Parameters
                </h3>
                <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                            Max Tokens
                        </label>
                        <input
                            type="number"
                            value={settings.max_tokens || ""}
                            onChange={(e) =>
                                setSettings({
                                    ...settings,
                                    max_tokens: parseInt(e.target.value, 10),
                                })
                            }
                            className="input-field"
                            placeholder="1024"
                        />
                    </div>

                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                            Temperature
                        </label>
                        <div className="flex items-center gap-3">
                            <input
                                type="range"
                                min="0"
                                max="2"
                                step="0.1"
                                value={settings.temperature || 0}
                                onChange={(e) =>
                                    setSettings({
                                        ...settings,
                                        temperature: parseFloat(e.target.value),
                                    })
                                }
                                className="flex-1 h-2 bg-slate-200 dark:bg-dark-600 rounded-lg appearance-none cursor-pointer accent-primary-500"
                            />
                            <span className="text-sm font-mono text-slate-600 dark:text-slate-400 w-8 text-right">
                                {settings.temperature?.toFixed(1) || "0.0"}
                            </span>
                        </div>
                        <p className="text-xs text-slate-400 mt-1">
                            0 = focused, 2 = creative
                        </p>
                    </div>
                </div>
            </div>

            {/* Instructions */}
            <div className="border-t border-slate-200 dark:border-slate-700 pt-6">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">
                    Instructions
                </h3>
                <textarea
                    value={settings.custom_instructions || ""}
                    onChange={(e) =>
                        setSettings({
                            ...settings,
                            custom_instructions: e.target.value,
                        })
                    }
                    className="input-field min-h-[100px] resize-y"
                    placeholder="Add any custom instructions for the assistant..."
                />
            </div>
        </div>
    );
};

export default LLMTab;
