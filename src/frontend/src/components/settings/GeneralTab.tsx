import React from "react";
import { Icons } from "../Icons";
import type { SpeechTiming } from "../../hooks/useApi";

interface GeneralTabProps {
    settings: any;
    setSettings: (s: any) => void;
    detectedProvider: string | null;
    speechTiming: SpeechTiming;
    onSpeechTimingChange: (key: keyof SpeechTiming, value: number) => void;
}

const LITELLM_TTS_PROVIDERS = ["openai", "google"];
const LITELLM_STT_PROVIDERS = ["openai", "groq", "google"];

const TTS_VOICES: Record<string, { value: string; label: string }[]> = {
    openai: [
        { value: "alloy", label: "Alloy" },
        { value: "echo", label: "Echo" },
        { value: "fable", label: "Fable" },
        { value: "onyx", label: "Onyx" },
        { value: "nova", label: "Nova" },
        { value: "shimmer", label: "Shimmer" },
    ],
    google: [
        { value: "en-US-Standard-A", label: "Standard A (Female)" },
        { value: "en-US-Standard-B", label: "Standard B (Male)" },
        { value: "en-US-Standard-C", label: "Standard C (Female)" },
        { value: "en-US-Standard-D", label: "Standard D (Male)" },
        { value: "en-US-Wavenet-A", label: "Wavenet A (Female)" },
        { value: "en-US-Wavenet-B", label: "Wavenet B (Male)" },
    ],
};

const STT_LANGUAGES = [
    { value: "en", label: "English" },
    { value: "es", label: "Spanish" },
    { value: "fr", label: "French" },
    { value: "de", label: "German" },
    { value: "it", label: "Italian" },
    { value: "pt", label: "Portuguese" },
    { value: "nl", label: "Dutch" },
    { value: "ja", label: "Japanese" },
    { value: "ko", label: "Korean" },
    { value: "zh", label: "Chinese" },
    { value: "ru", label: "Russian" },
    { value: "ar", label: "Arabic" },
    { value: "hi", label: "Hindi" },
    { value: "pl", label: "Polish" },
    { value: "tr", label: "Turkish" },
    { value: "vi", label: "Vietnamese" },
    { value: "th", label: "Thai" },
    { value: "id", label: "Indonesian" },
    { value: "sv", label: "Swedish" },
    { value: "da", label: "Danish" },
    { value: "fi", label: "Finnish" },
    { value: "no", label: "Norwegian" },
    { value: "cs", label: "Czech" },
    { value: "el", label: "Greek" },
    { value: "he", label: "Hebrew" },
    { value: "uk", label: "Ukrainian" },
];

const GeneralTab: React.FC<GeneralTabProps> = ({
    settings,
    setSettings,
    detectedProvider,
    speechTiming,
    onSpeechTimingChange,
}) => {
    return (
        <div className="space-y-6">
            {/* Voice */}
            <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">
                    Voice
                </h3>
                <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
                    <div className="sm:grid sm:grid-cols-3 sm:gap-4 sm:items-start">
                        <div className="flex items-center gap-2 mb-2 sm:mb-0 sm:pt-2">
                            <div className="p-1.5 rounded-lg bg-primary-100 dark:bg-primary-900/30">
                                <Icons.Mic className="w-3.5 h-3.5 text-primary-600 dark:text-primary-400" />
                            </div>
                            <div>
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
                                    Wake Word
                                </label>
                                <p className="text-xs text-slate-400">
                                    Say this to activate
                                </p>
                            </div>
                        </div>
                        <div className="sm:col-span-2">
                            <input
                                type="text"
                                value={settings.keyword || ""}
                                onChange={(e) =>
                                    setSettings({
                                        ...settings,
                                        keyword: e.target.value,
                                    })
                                }
                                className="input-field"
                            />
                        </div>
                    </div>

                    <div className="sm:grid sm:grid-cols-3 sm:gap-4 sm:items-start">
                        <div className="flex items-center gap-2 mb-2 sm:mb-0 sm:pt-2">
                            <div className="p-1.5 rounded-lg bg-emerald-100 dark:bg-emerald-900/30">
                                <Icons.Refresh className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                            </div>
                            <div>
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
                                    Repeat Input
                                </label>
                                <p className="text-xs text-slate-400">
                                    Echo before responding
                                </p>
                            </div>
                        </div>
                        <div className="sm:col-span-2">
                            <div className="relative">
                                <select
                                    value={
                                        settings.sayHeard === true ||
                                        settings.sayHeard === "true"
                                            ? "true"
                                            : "false"
                                    }
                                    onChange={(e) =>
                                        setSettings({
                                            ...settings,
                                            sayHeard:
                                                e.target.value === "true",
                                        })
                                    }
                                    className="select-field"
                                >
                                    <option value="true">Yes</option>
                                    <option value="false">No</option>
                                </select>
                                <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* TTS */}
            <div className="border-t border-slate-200 dark:border-slate-700 pt-6">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">
                    Text-to-Speech
                </h3>
                <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                            Engine
                        </label>
                        <div className="relative">
                            <select
                                value={settings.ttsEngine || "gtts"}
                                onChange={(e) =>
                                    setSettings({
                                        ...settings,
                                        ttsEngine: e.target.value,
                                    })
                                }
                                className="select-field"
                            >
                                <option value="pyttsx3">
                                    pyttsx3 (Offline)
                                </option>
                                <option value="gtts">gTTS (Google)</option>
                                <option
                                    value="litellm"
                                    disabled={
                                        !detectedProvider ||
                                        !LITELLM_TTS_PROVIDERS.includes(
                                            detectedProvider,
                                        )
                                    }
                                >
                                    LiteLLM{" "}
                                    {detectedProvider &&
                                    LITELLM_TTS_PROVIDERS.includes(
                                        detectedProvider,
                                    )
                                        ? `(${detectedProvider})`
                                        : "(unavailable)"}
                                </option>
                            </select>
                            <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                        </div>
                    </div>

                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                            Voice
                        </label>
                        <div className="relative">
                            <select
                                value={settings.ttsVoice || "alloy"}
                                onChange={(e) =>
                                    setSettings({
                                        ...settings,
                                        ttsVoice: e.target.value,
                                    })
                                }
                                className="select-field"
                                disabled={settings.ttsEngine !== "litellm"}
                            >
                                {detectedProvider &&
                                TTS_VOICES[detectedProvider]
                                    ? TTS_VOICES[detectedProvider].map((v) => (
                                          <option key={v.value} value={v.value}>
                                              {v.label}
                                          </option>
                                      ))
                                    : TTS_VOICES.openai.map((v) => (
                                          <option key={v.value} value={v.value}>
                                              {v.label}
                                          </option>
                                      ))}
                            </select>
                            <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                        </div>
                    </div>
                </div>
            </div>

            {/* STT */}
            <div className="border-t border-slate-200 dark:border-slate-700 pt-6">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">
                    Speech-to-Text
                </h3>
                <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                            Engine
                        </label>
                        <div className="relative">
                            <select
                                value={settings.sttEngine || "google"}
                                onChange={(e) =>
                                    setSettings({
                                        ...settings,
                                        sttEngine: e.target.value,
                                    })
                                }
                                className="select-field"
                            >
                                <option value="google">Google (Free)</option>
                                <option
                                    value="litellm"
                                    disabled={
                                        !detectedProvider ||
                                        !LITELLM_STT_PROVIDERS.includes(
                                            detectedProvider,
                                        )
                                    }
                                >
                                    LiteLLM{" "}
                                    {detectedProvider &&
                                    LITELLM_STT_PROVIDERS.includes(
                                        detectedProvider,
                                    )
                                        ? `(${detectedProvider})`
                                        : "(unavailable)"}
                                </option>
                            </select>
                            <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                        </div>
                    </div>

                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                            Language
                        </label>
                        <div className="relative">
                            <select
                                value={settings.sttLanguage || "en"}
                                onChange={(e) =>
                                    setSettings({
                                        ...settings,
                                        sttLanguage: e.target.value,
                                    })
                                }
                                className="select-field"
                            >
                                {STT_LANGUAGES.map((lang) => (
                                    <option key={lang.value} value={lang.value}>
                                        {lang.label}
                                    </option>
                                ))}
                            </select>
                            <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                        </div>
                    </div>
                </div>
            </div>

            {/* Timing */}
            <div className="border-t border-slate-200 dark:border-slate-700 pt-6">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">
                    Speech Timing
                </h3>
                <div className="grid gap-4 grid-cols-1 sm:grid-cols-3">
                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                            Pause
                        </label>
                        <input
                            type="number"
                            min="0.3"
                            max="5.0"
                            step="0.1"
                            value={speechTiming.pauseThreshold}
                            onChange={(e) =>
                                onSpeechTimingChange(
                                    "pauseThreshold",
                                    parseFloat(e.target.value),
                                )
                            }
                            className="input-field"
                        />
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                            Seconds of silence to end phrase
                        </p>
                    </div>

                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                            Max Time
                        </label>
                        <input
                            type="number"
                            min="5"
                            max="120"
                            step="5"
                            value={speechTiming.phraseTimeLimit}
                            onChange={(e) =>
                                onSpeechTimingChange(
                                    "phraseTimeLimit",
                                    parseInt(e.target.value, 10),
                                )
                            }
                            className="input-field"
                        />
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                            Max seconds per phrase
                        </p>
                    </div>

                    <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                            Pre-silence
                        </label>
                        <input
                            type="number"
                            min="0.1"
                            max="3.0"
                            step="0.1"
                            value={speechTiming.nonSpeakingDuration}
                            onChange={(e) =>
                                onSpeechTimingChange(
                                    "nonSpeakingDuration",
                                    parseFloat(e.target.value),
                                )
                            }
                            className="input-field"
                        />
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                            Silence before phrase starts
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default GeneralTab;
