import React, {
    useState,
    useEffect,
    useRef,
    useCallback,
    useMemo,
} from "react";
import { motion } from "framer-motion";
import axios from "axios";
import { Icons, Spinner } from "./Icons";
import { cn } from "../lib/utils";
import AlertModal, { useAlert } from "./AlertModal";
import ConfirmModal, { useConfirm } from "./ConfirmModal";
import ImageViewer from "./ImageViewer";
import {
    useSettingsPageData,
    useInvalidateQueries,
    queryKeys,
    type DisplayStatus,
    type GalleryImage,
    type AudioDevice,
    type SpeechTiming,
    type ScreensaverSettings,
} from "../hooks/useApi";
import { useQueryClient } from "@tanstack/react-query";

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
    openai: ["gpt-", "o1-", "o3-", "chatgpt-"],
    anthropic: ["claude-"],
    google: ["gemini/", "gemini-"],
    cohere: ["command"],
    mistral: ["mistral/", "mistral-", "codestral", "pixtral", "ministral"],
    groq: ["groq/", "llama", "mixtral", "gemma"],
    together: ["together/", "together_ai/"],
    deepseek: ["deepseek/", "deepseek-"],
};

// Patterns to exclude from chat models (embedding, TTS, STT, image generation)
const NON_CHAT_PATTERNS = [
    "text-embedding",
    "embed-",
    "embedding",
    "tts-",
    "whisper",
    "dall-e",
    "image",
    "moderation",
    "davinci",
    "babbage",
    "ada-",
    "curie",
];

// Providers that support LiteLLM TTS
const LITELLM_TTS_PROVIDERS = ["openai", "google"];
// Providers that support LiteLLM STT
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

// Embedding models by provider
const EMBEDDING_MODELS: Record<string, string[]> = {
    openai: [
        "openai:text-embedding-3-small",
        "openai:text-embedding-3-large",
        "openai:text-embedding-ada-002",
    ],
    anthropic: [
        "anthropic:voyage-3",
        "anthropic:voyage-3-lite",
        "anthropic:voyage-code-2",
    ],
    google: [
        "google:text-embedding-004",
        "google:text-multilingual-embedding-002",
    ],
    cohere: [
        "cohere:embed-english-v3.0",
        "cohere:embed-multilingual-v3.0",
        "cohere:embed-english-light-v3.0",
    ],
    mistral: ["mistral:mistral-embed"],
    together: ["together:togethercomputer/m2-bert-80M-8k-retrieval"],
    deepseek: ["openai:text-embedding-3-small"], // DeepSeek uses OpenAI-compatible embeddings
    groq: ["openai:text-embedding-3-small"], // Groq doesn't have embeddings, fallback to OpenAI
};

const detectProvider = (apiKey: string): string | null => {
    if (!apiKey) return null;
    for (const [provider, pattern] of Object.entries(PROVIDER_PATTERNS)) {
        if (pattern.test(apiKey)) return provider;
    }
    return null;
};

// DisplayStatus type is now imported from useApi

// Helper to determine if display modes should be shown
// Handles both new API (supports_modes field) and legacy API (check display type)
const shouldShowDisplayModes = (status: DisplayStatus | null): boolean => {
    if (!status || !status.available) return false;

    // Use new API field if available
    if (typeof status.supports_modes === "boolean") {
        return status.supports_modes;
    }
    if (typeof status.has_full_display === "boolean") {
        return status.has_full_display;
    }

    // Fallback: check display types directly (for backwards compatibility)
    // I2C display is text-only, all other types support modes
    return status.displays.some((d) => d.type !== "i2c" && d.type !== "I2C");
};

// Helper to check if only simple display is connected
const hasOnlySimpleDisplay = (status: DisplayStatus | null): boolean => {
    if (!status || !status.available) return false;

    // Use new API fields if available
    if (
        typeof status.has_simple_display === "boolean" &&
        typeof status.has_full_display === "boolean"
    ) {
        return status.has_simple_display && !status.has_full_display;
    }

    // Fallback: check if all displays are I2C
    return (
        status.displays.length > 0 &&
        status.displays.every((d) => d.type === "i2c" || d.type === "I2C")
    );
};

// GalleryImage and AudioDevice types are now imported from useApi

interface AudioState {
    devices: AudioDevice[];
    current: string | null;
    volume: number | null;
    inputDevices: AudioDevice[];
    currentInputDevice: string | null;
    micGain: number | null;
    micCard: string | null;
    vadThreshold: number;
}

const DISPLAY_MODES = [
    {
        value: "smart",
        label: "Smart (Contextual)",
        description: "Shows user message, then tool-specific animations",
    },
    { value: "clock", label: "Clock", description: "Digital clock with date" },
    {
        value: "weather",
        label: "Weather",
        description: "Current weather animation",
    },
    {
        value: "gallery",
        label: "Photo Gallery",
        description: "Slideshow of uploaded images",
    },
    {
        value: "waveform",
        label: "Audio Waveform",
        description: "Real-time audio visualization",
    },
    { value: "off", label: "Display Off", description: "Turn off the display" },
];

const Settings: React.FC = () => {
    // React Query hooks for data fetching with caching
    const queryClient = useQueryClient();
    const { invalidateGalleryImages } = useInvalidateQueries();
    const {
        settings: fetchedSettings,
        models: fetchedModels,
        displayStatus: fetchedDisplayStatus,
        galleryImages: fetchedGalleryImages,
        audioDevices: fetchedAudioDevices,
        audioInputDevices: fetchedAudioInputDevices,
        audioVolume: fetchedAudioVolume,
        micGain: fetchedMicGain,
        vadThreshold: fetchedVadThreshold,
        speechTiming: fetchedSpeechTiming,
        screensaver: fetchedScreensaver,
        isCriticalLoading,
        loadingStates,
        refetch,
    } = useSettingsPageData();

    // Local state for form editing (initialized from fetched data)
    const [settings, setSettings] = useState<any>({});
    const [isSaving, setIsSaving] = useState(false);
    const [allModels, setAllModels] = useState<string[]>([]);
    const [filteredModels, setFilteredModels] = useState<string[]>([]);
    const [embeddingModels, setEmbeddingModels] = useState<string[]>([]);
    const [detectedProvider, setDetectedProvider] = useState<string | null>(
        null,
    );
    const [oldPassword, setOldPassword] = useState<string>("");
    const [newPassword, setNewPassword] = useState<string>("");
    const [confirmInput, setConfirmInput] = useState<string>("");
    const [displayStatus, setDisplayStatus] = useState<DisplayStatus | null>(
        null,
    );
    const [galleryImages, setGalleryImages] = useState<GalleryImage[]>([]);
    const [isUploadingImage, setIsUploadingImage] = useState(false);
    const [isDraggingOver, setIsDraggingOver] = useState(false);
    const [selectedImage, setSelectedImage] = useState<GalleryImage | null>(
        null,
    );
    const [isRefreshingDisplay, setIsRefreshingDisplay] = useState(false);
    const [isPoweringDisplay, setIsPoweringDisplay] = useState(false);
    const [hardwareDisplayMode, setHardwareDisplayMode] = useState<
        "hdmi" | "tft" | "unknown" | "conflict"
    >("unknown");
    const [isChangingHardwareMode, setIsChangingHardwareMode] = useState(false);
    const [displayRotation, setDisplayRotation] = useState({
        tft_rotation: 0,
        i2c_rotation: 2,
    });
    const [rotationRebootPending, setRotationRebootPending] = useState(false);
    const [audioState, setAudioState] = useState<AudioState>({
        devices: [],
        current: null,
        volume: null,
        inputDevices: [],
        currentInputDevice: null,
        micGain: null,
        micCard: null,
        vadThreshold: -50,
    });
    const [isChangingAudio, setIsChangingAudio] = useState(false);
    const [speechTiming, setSpeechTiming] = useState<SpeechTiming>({
        pauseThreshold: 1.2,
        phraseTimeLimit: 30,
        nonSpeakingDuration: 0.8,
    });
    const [screensaverSettings, setScreensaverSettings] = useState<
        ScreensaverSettings & { is_active: boolean; available_styles: string[] }
    >({
        enabled: true,
        timeout: 300,
        style: "starfield",
        is_active: false,
        available_styles: ["starfield", "matrix", "bounce", "fade"],
    });
    const { alertConfig, showAlert, closeAlert } = useAlert();
    const { confirmConfig, showConfirm, closeConfirm } = useConfirm();
    const [isPasswordModalOpen, setIsPasswordModalOpen] = useState(false);

    // Track original settings for dirty detection
    const [originalSettings, setOriginalSettings] = useState<any>({});
    const [originalScreensaver, setOriginalScreensaver] = useState({
        enabled: true,
        timeout: 300,
        style: "starfield",
    });
    const [originalSpeechTiming, setOriginalSpeechTiming] =
        useState<SpeechTiming>({
            pauseThreshold: 1.2,
            phraseTimeLimit: 30,
            nonSpeakingDuration: 0.8,
        });

    // Track if we've initialized from fetched data
    const [isInitialized, setIsInitialized] = useState(false);

    // Track scroll position for floating save button
    const [isScrolled, setIsScrolled] = useState(false);
    const headerRef = useRef<HTMLDivElement>(null);

    // Detect if settings have changed
    const hasChanges = useMemo(() => {
        const settingsChanged =
            JSON.stringify(settings) !== JSON.stringify(originalSettings);
        const screensaverChanged =
            screensaverSettings.enabled !== originalScreensaver.enabled ||
            screensaverSettings.timeout !== originalScreensaver.timeout ||
            screensaverSettings.style !== originalScreensaver.style;
        const speechTimingChanged =
            speechTiming.pauseThreshold !==
                originalSpeechTiming.pauseThreshold ||
            speechTiming.phraseTimeLimit !==
                originalSpeechTiming.phraseTimeLimit ||
            speechTiming.nonSpeakingDuration !==
                originalSpeechTiming.nonSpeakingDuration;
        const passwordChanged =
            oldPassword !== "" || newPassword !== "" || confirmInput !== "";
        return (
            settingsChanged ||
            screensaverChanged ||
            speechTimingChanged ||
            passwordChanged
        );
    }, [
        settings,
        originalSettings,
        screensaverSettings,
        originalScreensaver,
        speechTiming,
        originalSpeechTiming,
        oldPassword,
        newPassword,
        confirmInput,
    ]);

    // Track scroll position
    useEffect(() => {
        const handleScroll = () => {
            if (headerRef.current) {
                const headerBottom =
                    headerRef.current.getBoundingClientRect().bottom;
                setIsScrolled(headerBottom < 0);
            }
        };

        window.addEventListener("scroll", handleScroll, { passive: true });
        return () => window.removeEventListener("scroll", handleScroll);
    }, []);

    // Detect provider when API key changes
    useEffect(() => {
        const provider = detectProvider(settings.litellm_api_key || "");
        setDetectedProvider(provider);

        // Helper to check if model is a chat/completion model (not embedding/TTS/image)
        const isChatModel = (model: string): boolean => {
            const lowerModel = model.toLowerCase();
            return !NON_CHAT_PATTERNS.some((pattern) =>
                lowerModel.includes(pattern),
            );
        };

        if (provider && allModels.length > 0) {
            const prefixes = PROVIDER_CHAT_PREFIXES[provider] || [];
            const filtered = allModels.filter((model) => {
                const lowerModel = model.toLowerCase();
                const matchesProvider = prefixes.some((prefix) =>
                    lowerModel.startsWith(prefix.toLowerCase()),
                );
                return matchesProvider && isChatModel(model);
            });
            setFilteredModels(filtered.length > 0 ? filtered : allModels);
            setEmbeddingModels(
                EMBEDDING_MODELS[provider] ||
                    Array.from(new Set(Object.values(EMBEDDING_MODELS).flat())),
            );
        } else {
            setFilteredModels(allModels.filter(isChatModel));
            setEmbeddingModels(
                Array.from(new Set(Object.values(EMBEDDING_MODELS).flat())),
            );
        }
    }, [settings.litellm_api_key, allModels]);

    // Initialize critical data (settings, models) as soon as available
    // This allows the page to render quickly while slower queries load
    useEffect(() => {
        if (!isCriticalLoading && !isInitialized) {
            // Settings
            if (fetchedSettings) {
                setSettings(fetchedSettings);
                setOriginalSettings(fetchedSettings);
            }

            // Models
            if (fetchedModels) {
                setAllModels(fetchedModels);
            }

            setIsInitialized(true);
        }
    }, [isCriticalLoading, isInitialized, fetchedSettings, fetchedModels]);

    // Progressively initialize other data as it arrives
    useEffect(() => {
        if (fetchedDisplayStatus) {
            setDisplayStatus(fetchedDisplayStatus);
        }
    }, [fetchedDisplayStatus]);

    useEffect(() => {
        const fetchHardwareMode = async () => {
            try {
                const response = await axios.get("/api/display/hardware-mode");
                if (response.data.mode) {
                    setHardwareDisplayMode(response.data.mode);
                }
            } catch (err) {
                console.error("Failed to fetch hardware display mode:", err);
            }
        };
        const fetchRotation = async () => {
            try {
                const response = await axios.get("/api/display/rotation");
                setDisplayRotation(response.data);
            } catch (err) {
                console.error("Failed to fetch display rotation:", err);
            }
        };
        fetchHardwareMode();
        fetchRotation();
    }, []);

    useEffect(() => {
        if (fetchedGalleryImages) {
            setGalleryImages(fetchedGalleryImages);
        }
    }, [fetchedGalleryImages]);

    useEffect(() => {
        // Update audio state progressively as data arrives
        setAudioState((prev) => ({
            ...prev,
            devices: fetchedAudioDevices?.devices ?? prev.devices,
            current: fetchedAudioDevices?.current ?? prev.current,
        }));
    }, [fetchedAudioDevices]);

    useEffect(() => {
        setAudioState((prev) => ({
            ...prev,
            inputDevices:
                fetchedAudioInputDevices?.devices ?? prev.inputDevices,
            currentInputDevice:
                fetchedAudioInputDevices?.current ?? prev.currentInputDevice,
        }));
    }, [fetchedAudioInputDevices]);

    useEffect(() => {
        if (fetchedAudioVolume !== undefined) {
            setAudioState((prev) => ({
                ...prev,
                volume: fetchedAudioVolume ?? prev.volume,
            }));
        }
    }, [fetchedAudioVolume]);

    useEffect(() => {
        if (fetchedMicGain) {
            setAudioState((prev) => ({
                ...prev,
                micGain: fetchedMicGain.gain ?? prev.micGain,
                micCard: fetchedMicGain.card ?? prev.micCard,
            }));
        }
    }, [fetchedMicGain]);

    useEffect(() => {
        if (fetchedVadThreshold !== undefined) {
            setAudioState((prev) => ({
                ...prev,
                vadThreshold: fetchedVadThreshold ?? prev.vadThreshold,
            }));
        }
    }, [fetchedVadThreshold]);

    useEffect(() => {
        if (fetchedSpeechTiming) {
            setSpeechTiming(fetchedSpeechTiming);
            setOriginalSpeechTiming(fetchedSpeechTiming);
        }
    }, [fetchedSpeechTiming]);

    useEffect(() => {
        if (fetchedScreensaver) {
            setScreensaverSettings({
                enabled: fetchedScreensaver.enabled,
                timeout: fetchedScreensaver.timeout,
                style: fetchedScreensaver.style,
                is_active: fetchedScreensaver.is_active,
                available_styles: fetchedScreensaver.available_styles,
            });
            setOriginalScreensaver({
                enabled: fetchedScreensaver.enabled,
                timeout: fetchedScreensaver.timeout,
                style: fetchedScreensaver.style,
            });
        }
    }, [fetchedScreensaver]);

    const handleRefreshDisplay = async () => {
        setIsRefreshingDisplay(true);
        try {
            const response = await axios.post("/api/display/refresh");
            if (response.data.success) {
                // Refresh display status via React Query
                const result = await refetch.displayStatus();
                if (result.data) {
                    setDisplayStatus(result.data);
                }
                if (response.data.supports_modes) {
                    showAlert(
                        "success",
                        "Display Detected",
                        response.data.message,
                    );
                } else {
                    showAlert(
                        "info",
                        "Display Refresh Complete",
                        response.data.message,
                    );
                }
            } else {
                showAlert(
                    "error",
                    "Display Refresh Failed",
                    response.data.message || "Could not refresh display",
                );
            }
        } catch (err) {
            console.error("Display refresh error:", err);
            showAlert(
                "error",
                "Display Refresh Failed",
                err instanceof Error ? err.message : "Unknown error",
            );
        } finally {
            setIsRefreshingDisplay(false);
        }
    };

    // Simplified and robust power-on handler (avoids complex string templating to prevent TS parsing issues)
    const handlePowerOnDisplay = async () => {
        setIsPoweringDisplay(true);
        try {
            const response = await axios.post("/api/display/power-on");
            if (response.data && response.data.success) {
                // Show a short user-friendly result message
                const msg =
                    response.data.message ||
                    "Power-on command sent. Check logs or the debug endpoint for details.";
                showAlert("info", "Power On Results", msg);

                // Refresh status via React Query
                try {
                    const result = await refetch.displayStatus();
                    if (result.data) {
                        setDisplayStatus(result.data);
                    }
                } catch (e) {
                    // Ignore refresh errors but log them
                    console.error("Failed to refresh display status:", e);
                }
            } else {
                showAlert(
                    "error",
                    "Power On Failed",
                    response.data?.message || "Could not power on display",
                );
            }
        } catch (err) {
            console.error("Display power-on error:", err);
            const message =
                err instanceof Error ? err.message : "Unknown error";
            showAlert("error", "Power On Failed", message);
        } finally {
            setIsPoweringDisplay(false);
        }
    };

    const handleDisplayModeChange = (mode: string) => {
        setSettings({ ...settings, display_mode: mode });
    };

    const handleMirrorToggle = async (enabled: boolean) => {
        try {
            const response = await axios.post("/api/display/mirror", {
                enabled,
            });
            if (response.data.success) {
                const result = await refetch.displayStatus();
                if (result.data) {
                    setDisplayStatus(result.data);
                }
                showAlert(
                    "success",
                    "Mirror Mode",
                    `Display mirroring ${enabled ? "enabled" : "disabled"}`,
                );
            }
        } catch (err) {
            console.error("Mirror toggle error:", err);
            showAlert("error", "Failed", "Could not change mirror mode");
        }
    };

    const handleDisplayEnable = async (displayId: string, enabled: boolean) => {
        try {
            const response = await axios.post("/api/display/enable", {
                id: displayId,
                enabled,
            });
            if (response.data.success) {
                const result = await refetch.displayStatus();
                if (result.data) {
                    setDisplayStatus(result.data);
                }
            }
        } catch (err) {
            console.error("Display enable error:", err);
            showAlert("error", "Failed", "Could not change display state");
        }
    };

    const handleHardwareModeChange = (mode: "hdmi" | "tft") => {
        const modeLabel = mode === "hdmi" ? "HDMI" : "TFT (SPI)";
        const otherMode = mode === "hdmi" ? "TFT" : "HDMI";
        showConfirm(
            `Switch to ${modeLabel} Display`,
            `This will configure the Raspberry Pi for ${modeLabel} display output and disable ${otherMode}. ` +
                `The system will reboot to apply changes.\n\n` +
                `Note: HDMI and TFT displays cannot work simultaneously due to kernel driver limitations.`,
            async () => {
                setIsChangingHardwareMode(true);
                try {
                    const response = await axios.post(
                        "/api/display/hardware-mode",
                        {
                            mode,
                            auto_reboot: true,
                        },
                    );
                    if (response.data.success) {
                        setHardwareDisplayMode(mode);
                        showAlert(
                            "info",
                            "Rebooting",
                            response.data.message ||
                                "System is rebooting to apply display changes...",
                        );
                    } else {
                        showAlert(
                            "error",
                            "Failed",
                            response.data.message ||
                                "Could not change display mode",
                        );
                    }
                } catch (err) {
                    console.error("Hardware mode change error:", err);
                    const message =
                        err instanceof Error ? err.message : "Unknown error";
                    showAlert("error", "Failed", message);
                } finally {
                    setIsChangingHardwareMode(false);
                }
            },
            { confirmText: "Switch & Reboot", variant: "danger" },
        );
    };

    const handleTftRotationChange = async (rotation: number) => {
        try {
            const response = await axios.post("/api/display/rotation", {
                tft_rotation: rotation,
            });
            if (response.data.success) {
                setDisplayRotation((prev) => ({
                    ...prev,
                    tft_rotation: rotation,
                }));
                if (response.data.reboot_required) {
                    setRotationRebootPending(true);
                }
            }
        } catch (err) {
            console.error("Failed to set TFT rotation:", err);
        }
    };

    const handleI2cRotationChange = async (rotation: number) => {
        try {
            const response = await axios.post("/api/display/rotation", {
                i2c_rotation: rotation,
            });
            if (response.data.success) {
                setDisplayRotation((prev) => ({
                    ...prev,
                    i2c_rotation: rotation,
                }));
            }
        } catch (err) {
            console.error("Failed to set I2C rotation:", err);
        }
    };

    const handleScreensaverSettingChange = (
        key: "enabled" | "timeout" | "style",
        value: boolean | number | string,
    ) => {
        setScreensaverSettings((prev) => ({ ...prev, [key]: value }));
    };

    const handleAudioDeviceChange = async (card: number, cardId?: string) => {
        setIsChangingAudio(true);
        try {
            const response = await axios.post("/api/audio/device", {
                card,
                card_id: cardId,
                auto_restart: true,
            });
            if (response.data.success) {
                setAudioState((prev) => ({
                    ...prev,
                    current: String(card),
                    volume: response.data.volume ?? prev.volume,
                }));
                if (response.data.restarting) {
                    showAlert(
                        "info",
                        "Audio Device Changed",
                        "Audio device changed. Container is restarting to apply changes...",
                    );
                } else {
                    showAlert(
                        "success",
                        "Audio Device Changed",
                        response.data.message,
                    );
                }
            } else {
                showAlert(
                    "error",
                    "Failed to Change Audio Device",
                    response.data.message || "Unknown error",
                );
            }
        } catch (err) {
            console.error("Audio device change error:", err);
            const message =
                err instanceof Error ? err.message : "Unknown error";
            showAlert("error", "Failed to Change Audio Device", message);
        } finally {
            setIsChangingAudio(false);
        }
    };

    const [isChangingInputDevice, setIsChangingInputDevice] = useState(false);

    const handleInputDeviceChange = async (card: number) => {
        setIsChangingInputDevice(true);
        try {
            const response = await axios.post("/api/audio/input-device", {
                card,
            });
            if (response.data.success) {
                setAudioState((prev) => ({
                    ...prev,
                    currentInputDevice: String(card),
                }));
                showAlert(
                    "info",
                    "Input Device Changed",
                    response.data.message ||
                        "Input device saved. Restart the backend to apply.",
                );
            } else {
                showAlert(
                    "error",
                    "Failed to Change Input Device",
                    response.data.message || "Unknown error",
                );
            }
        } catch (err) {
            console.error("Input device change error:", err);
            const message =
                err instanceof Error ? err.message : "Unknown error";
            showAlert("error", "Failed to Change Input Device", message);
        } finally {
            setIsChangingInputDevice(false);
        }
    };

    // Debounce volume changes to avoid flooding the server
    const volumeDebounceRef = useRef<NodeJS.Timeout | null>(null);
    const pendingVolumeRef = useRef<number | null>(null);

    const handleVolumeChange = useCallback((volume: number) => {
        // Update UI immediately for responsiveness
        setAudioState((prev) => ({ ...prev, volume }));

        // Store the pending volume
        pendingVolumeRef.current = volume;

        // Clear any existing debounce timer
        if (volumeDebounceRef.current) {
            clearTimeout(volumeDebounceRef.current);
        }

        // Set a new debounce timer (300ms delay)
        volumeDebounceRef.current = setTimeout(async () => {
            if (pendingVolumeRef.current !== null) {
                try {
                    await axios.post("/api/audio/volume", {
                        volume: pendingVolumeRef.current,
                    });
                } catch (err) {
                    console.error("Volume change error:", err);
                }
                pendingVolumeRef.current = null;
            }
        }, 300);
    }, []);

    // Debounce mic gain changes
    const micGainDebounceRef = useRef<NodeJS.Timeout | null>(null);
    const pendingMicGainRef = useRef<number | null>(null);

    const handleMicGainChange = useCallback((gain: number) => {
        setAudioState((prev) => ({ ...prev, micGain: gain }));
        pendingMicGainRef.current = gain;

        if (micGainDebounceRef.current) {
            clearTimeout(micGainDebounceRef.current);
        }

        micGainDebounceRef.current = setTimeout(async () => {
            if (pendingMicGainRef.current !== null) {
                try {
                    await axios.post("/api/audio/mic-gain", {
                        gain: pendingMicGainRef.current,
                    });
                } catch (err) {
                    console.error("Mic gain change error:", err);
                }
                pendingMicGainRef.current = null;
            }
        }, 300);
    }, []);

    // Debounce VAD threshold changes
    const vadDebounceRef = useRef<NodeJS.Timeout | null>(null);
    const pendingVadRef = useRef<number | null>(null);

    const handleVadThresholdChange = useCallback((threshold: number) => {
        setAudioState((prev) => ({ ...prev, vadThreshold: threshold }));
        pendingVadRef.current = threshold;

        if (vadDebounceRef.current) {
            clearTimeout(vadDebounceRef.current);
        }

        vadDebounceRef.current = setTimeout(async () => {
            if (pendingVadRef.current !== null) {
                try {
                    await axios.post("/api/audio/vad-threshold", {
                        threshold: pendingVadRef.current,
                    });
                } catch (err) {
                    console.error("VAD threshold change error:", err);
                }
                pendingVadRef.current = null;
            }
        }, 300);
    }, []);

    // Debounce speech timing changes
    const handleSpeechTimingChange = useCallback(
        (key: keyof typeof speechTiming, value: number) => {
            setSpeechTiming((prev) => ({ ...prev, [key]: value }));
        },
        [],
    );

    // Cleanup debounce timers on unmount
    useEffect(() => {
        return () => {
            if (volumeDebounceRef.current) {
                clearTimeout(volumeDebounceRef.current);
            }
            if (micGainDebounceRef.current) {
                clearTimeout(micGainDebounceRef.current);
            }
            if (vadDebounceRef.current) {
                clearTimeout(vadDebounceRef.current);
            }
        };
    }, []);

    const uploadFile = async (file: File): Promise<boolean> => {
        const allowedTypes = [
            "image/jpeg",
            "image/png",
            "image/gif",
            "image/bmp",
            "image/webp",
        ];
        if (!allowedTypes.includes(file.type)) {
            showAlert(
                "error",
                "Invalid File Type",
                `${file.name} is not a supported image format`,
            );
            return false;
        }

        const formData = new FormData();
        formData.append("file", file);

        try {
            const response = await axios.post("/api/gallery/upload", formData, {
                headers: { "Content-Type": "multipart/form-data" },
            });
            if (response.data.success) {
                setGalleryImages((prev) => [
                    {
                        name: response.data.name,
                        path: response.data.path,
                        size: file.size,
                    },
                    ...prev,
                ]);
                return true;
            } else {
                console.error("Upload failed:", response.data);
                showAlert(
                    "error",
                    "Upload Failed",
                    response.data.message || `Could not upload ${file.name}`,
                );
            }
        } catch (err: unknown) {
            console.error("Upload error:", err);
            let title = "Upload Failed";
            let message = `Could not upload ${file.name}`;

            if (err && typeof err === "object" && "response" in err) {
                const axiosErr = err as {
                    response?: { status?: number; data?: { message?: string } };
                };
                const status = axiosErr.response?.status;
                if (status === 413) {
                    title = "File Too Large";
                    message = `"${file.name}" exceeds the 50MB limit. Try compressing the image or using a smaller file.`;
                } else if (status === 400) {
                    title = "Invalid File";
                    message =
                        axiosErr.response?.data?.message ||
                        `"${file.name}" is not a valid image file.`;
                } else if (status === 500) {
                    message = `Server error while uploading "${file.name}". Check logs for details.`;
                }
            } else if (err instanceof Error) {
                message = err.message;
            }

            showAlert("error", title, message);
        }
        return false;
    };

    const handleImageUpload = async (
        event: React.ChangeEvent<HTMLInputElement>,
    ) => {
        const files = event.target.files;
        if (!files || files.length === 0) return;

        setIsUploadingImage(true);
        let successCount = 0;

        for (const file of Array.from(files)) {
            const success = await uploadFile(file);
            if (success) successCount++;
        }

        if (successCount > 0) {
            showAlert(
                "success",
                "Images Uploaded",
                `${successCount} image${successCount > 1 ? "s" : ""} added to gallery`,
            );
        }

        setIsUploadingImage(false);
        event.target.value = "";
    };

    const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
        event.preventDefault();
        event.stopPropagation();
        setIsDraggingOver(true);
    };

    const handleDragLeave = (event: React.DragEvent<HTMLDivElement>) => {
        event.preventDefault();
        event.stopPropagation();
        // Only set to false if we're leaving the drop zone entirely
        const rect = event.currentTarget.getBoundingClientRect();
        const x = event.clientX;
        const y = event.clientY;
        if (
            x < rect.left ||
            x >= rect.right ||
            y < rect.top ||
            y >= rect.bottom
        ) {
            setIsDraggingOver(false);
        }
    };

    const handleDrop = async (event: React.DragEvent<HTMLDivElement>) => {
        event.preventDefault();
        event.stopPropagation();
        setIsDraggingOver(false);

        const files = event.dataTransfer.files;
        if (!files || files.length === 0) return;

        setIsUploadingImage(true);
        let successCount = 0;

        for (const file of Array.from(files)) {
            const success = await uploadFile(file);
            if (success) successCount++;
        }

        if (successCount > 0) {
            showAlert(
                "success",
                "Images Uploaded",
                `${successCount} image${successCount > 1 ? "s" : ""} added to gallery`,
            );
        }

        setIsUploadingImage(false);
    };

    const handleDeleteImage = (filename: string) => {
        showConfirm(
            "Delete Image",
            `Are you sure you want to delete "${filename}"?`,
            async () => {
                try {
                    await axios.delete(`/api/gallery/images/${filename}`);
                    setGalleryImages((prev) =>
                        prev.filter((img) => img.name !== filename),
                    );
                    // Invalidate React Query cache
                    invalidateGalleryImages();
                    showAlert(
                        "success",
                        "Image Deleted",
                        "Image removed from gallery",
                    );
                } catch {
                    showAlert(
                        "error",
                        "Delete Failed",
                        "Could not delete image",
                    );
                }
            },
            { confirmText: "Delete", variant: "danger" },
        );
    };

    const updateSettings = async () => {
        if (oldPassword !== "" || newPassword !== "" || confirmInput !== "") {
            if (oldPassword === "") {
                showAlert(
                    "warning",
                    "Validation Error",
                    "Old password is required",
                );
                return;
            } else if (newPassword === "") {
                showAlert(
                    "warning",
                    "Validation Error",
                    "New password is required",
                );
                return;
            } else if (newPassword.length < 6) {
                showAlert(
                    "warning",
                    "Validation Error",
                    "New password must be at least 6 characters",
                );
                return;
            } else if (newPassword === oldPassword) {
                showAlert(
                    "warning",
                    "Validation Error",
                    "New password must be different",
                );
                return;
            } else if (newPassword !== confirmInput) {
                showAlert(
                    "warning",
                    "Validation Error",
                    "Passwords do not match",
                );
                return;
            } else {
                await changePassword();
            }
        }

        setIsSaving(true);
        try {
            const {
                screensaver_enabled,
                screensaver_timeout,
                screensaver_style,
                ...mainSettings
            } = settings;

            const response = await axios.post("/api/settings", {
                action: "update",
                data: mainSettings,
            });
            setSettings(response.data);
            setOriginalSettings(response.data);
            // Invalidate React Query cache so other components get fresh data
            queryClient.invalidateQueries({ queryKey: queryKeys.settings });

            // Apply display mode if it changed
            if (settings.display_mode !== originalSettings.display_mode) {
                try {
                    const modeResponse = await axios.post("/api/display/mode", {
                        mode: settings.display_mode,
                    });
                    if (modeResponse.data.success) {
                        setDisplayStatus((prev) =>
                            prev
                                ? {
                                      ...prev,
                                      current_mode: settings.display_mode,
                                  }
                                : null,
                        );
                    }
                } catch (modeErr) {
                    console.error("Display mode apply error:", modeErr);
                    showAlert(
                        "warning",
                        "Partial Save",
                        "Settings saved, but display mode failed to apply.",
                    );
                }
            }

            try {
                const ssResponse = await axios.post(
                    "/api/display/screensaver/settings",
                    {
                        enabled: screensaverSettings.enabled,
                        timeout: screensaverSettings.timeout,
                        style: screensaverSettings.style,
                    },
                );

                if (ssResponse.data.success) {
                    const savedSettings = ssResponse.data.settings || {
                        enabled: screensaverSettings.enabled,
                        timeout: screensaverSettings.timeout,
                        style: screensaverSettings.style,
                    };
                    setScreensaverSettings((prev) => ({
                        ...prev,
                        enabled: savedSettings.enabled,
                        timeout: savedSettings.timeout,
                        style: savedSettings.style,
                    }));
                    setOriginalScreensaver({
                        enabled: savedSettings.enabled,
                        timeout: savedSettings.timeout,
                        style: savedSettings.style,
                    });
                }
            } catch (ssErr) {
                showAlert(
                    "warning",
                    "Partial Save",
                    "Main settings saved, but screensaver settings failed to save.",
                );
                setIsSaving(false);
                return;
            }

            try {
                await axios.post("/api/audio/speech-timing", speechTiming);
                setOriginalSpeechTiming({ ...speechTiming });
            } catch (stErr) {
                showAlert(
                    "warning",
                    "Partial Save",
                    "Main settings saved, but speech timing settings failed to save.",
                );
                setIsSaving(false);
                return;
            }

            showAlert(
                "success",
                "Settings Saved",
                "Your settings have been saved successfully.",
            );
        } catch (err: unknown) {
            console.error("Failed to save settings:", err);
            let message = "Could not save settings. Please try again.";
            if (err && typeof err === "object" && "response" in err) {
                const axiosErr = err as {
                    response?: { data?: { error?: string } };
                };
                if (axiosErr.response?.data?.error) {
                    message = axiosErr.response.data.error;
                }
            } else if (err instanceof Error) {
                message = err.message;
            }
            showAlert("error", "Save Failed", message);
        } finally {
            setIsSaving(false);
        }
    };

    const changePassword = () => {
        return axios
            .post("/changePassword", { oldPassword, newPassword })
            .then(() => {
                showAlert(
                    "success",
                    "Password Changed",
                    "Your password has been changed successfully.",
                );
                setOldPassword("");
                setNewPassword("");
                setConfirmInput("");
            })
            .catch(() =>
                showAlert(
                    "error",
                    "Password Change Failed",
                    "Failed to change password. Please check your old password.",
                ),
            );
    };

    const gptRestart = () => {
        showConfirm(
            "Restart GPT Home",
            "Are you sure you want to restart the GPT Home service?",
            () => {
                axios
                    .post("/gptRestart")
                    .then(() =>
                        showAlert(
                            "success",
                            "Service Restarted",
                            "GPT Home service has been restarted.",
                        ),
                    )
                    .catch(() =>
                        showAlert(
                            "error",
                            "Restart Failed",
                            "Failed to restart GPT Home service.",
                        ),
                    );
            },
            { confirmText: "Restart" },
        );
    };

    const spotifyRestart = () => {
        showConfirm(
            "Restart Spotifyd",
            "Are you sure you want to restart the Spotifyd service?",
            () => {
                axios
                    .post("/spotifyRestart")
                    .then(() =>
                        showAlert(
                            "success",
                            "Service Restarted",
                            "Spotifyd service has been restarted.",
                        ),
                    )
                    .catch(() =>
                        showAlert(
                            "error",
                            "Restart Failed",
                            "Failed to restart Spotifyd service.",
                        ),
                    );
            },
            { confirmText: "Restart" },
        );
    };

    const shutdown = () => {
        showConfirm(
            "Shutdown System",
            "Are you sure you want to shutdown the system? You will need physical access to turn it back on.",
            () => {
                axios
                    .post("/shutdown")
                    .then(() =>
                        showAlert(
                            "info",
                            "Shutting Down",
                            "The system is shutting down...",
                        ),
                    )
                    .catch(() =>
                        showAlert(
                            "error",
                            "Shutdown Failed",
                            "Failed to shutdown the system.",
                        ),
                    );
            },
            { confirmText: "Shutdown", variant: "danger" },
        );
    };

    const reboot = () => {
        showConfirm(
            "Reboot System",
            "Are you sure you want to reboot the system?",
            () => {
                axios
                    .post("/reboot")
                    .then(() =>
                        showAlert(
                            "info",
                            "Rebooting",
                            "The system is rebooting...",
                        ),
                    )
                    .catch(() =>
                        showAlert(
                            "error",
                            "Reboot Failed",
                            "Failed to reboot the system.",
                        ),
                    );
            },
            { confirmText: "Reboot", variant: "danger" },
        );
    };

    const clearMemory = () => {
        showConfirm(
            "Clear Memory",
            "Are you sure you want to clear all conversation history and memories? This action cannot be undone.",
            () => {
                axios
                    .post("/clearMemory")
                    .then(() =>
                        showAlert(
                            "success",
                            "Memory Cleared",
                            "All conversation history and memories have been cleared.",
                        ),
                    )
                    .catch(() =>
                        showAlert(
                            "error",
                            "Clear Memory Failed",
                            "Failed to clear memory.",
                        ),
                    );
            },
            { confirmText: "Clear Memory", variant: "danger" },
        );
    };

    // Show loading spinner only for critical data (settings, models)
    // Other sections will show inline loading states while data loads progressively
    if (isCriticalLoading && !isInitialized) {
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

            {/* Change Password Modal */}
            {isPasswordModalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center">
                    <div
                        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
                        onClick={() => setIsPasswordModalOpen(false)}
                    />
                    <motion.div
                        initial={{ opacity: 0, scale: 0.95 }}
                        animate={{ opacity: 1, scale: 1 }}
                        className="relative bg-white dark:bg-dark-800 rounded-2xl shadow-xl p-6 w-full max-w-md mx-4"
                    >
                        <div className="flex items-center gap-3 mb-6">
                            <div className="p-2 rounded-xl bg-amber-100 dark:bg-amber-900/30">
                                <Icons.Lock className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                            </div>
                            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
                                Change Password
                            </h2>
                            <button
                                onClick={() => setIsPasswordModalOpen(false)}
                                className="ml-auto p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-dark-700"
                            >
                                <Icons.X className="w-5 h-5 text-slate-500" />
                            </button>
                        </div>

                        <div className="space-y-4">
                            <div>
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                                    Current Password
                                </label>
                                <input
                                    type="password"
                                    value={oldPassword}
                                    onChange={(e) =>
                                        setOldPassword(e.target.value)
                                    }
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
                                    onChange={(e) =>
                                        setNewPassword(e.target.value)
                                    }
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
                                    onChange={(e) =>
                                        setConfirmInput(e.target.value)
                                    }
                                    className={cn(
                                        "input-field",
                                        confirmInput &&
                                            newPassword !== confirmInput &&
                                            "border-rose-500 focus:ring-rose-500/50",
                                    )}
                                />
                                {confirmInput &&
                                    newPassword !== confirmInput && (
                                        <p className="text-xs text-rose-500 mt-1">
                                            Passwords do not match
                                        </p>
                                    )}
                            </div>

                            <div className="flex gap-3 pt-2">
                                <button
                                    onClick={() =>
                                        setIsPasswordModalOpen(false)
                                    }
                                    className="btn-secondary flex-1"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={() => {
                                        changePassword();
                                        setIsPasswordModalOpen(false);
                                    }}
                                    disabled={
                                        !oldPassword ||
                                        !newPassword ||
                                        newPassword !== confirmInput
                                    }
                                    className={cn(
                                        "btn-primary flex-1",
                                        (!oldPassword ||
                                            !newPassword ||
                                            newPassword !== confirmInput) &&
                                            "opacity-50 cursor-not-allowed",
                                    )}
                                >
                                    Change Password
                                </button>
                            </div>
                        </div>
                    </motion.div>
                </div>
            )}
            <div className="space-y-8">
                {/* Header */}
                <div
                    ref={headerRef}
                    className="flex flex-col md:flex-row md:items-center md:justify-between gap-4"
                >
                    <div>
                        <h1 className="text-3xl font-bold text-slate-900 dark:text-white">
                            Settings
                        </h1>
                        <p className="text-slate-500 dark:text-slate-400 mt-1">
                            Configure your GPT Home assistant
                        </p>
                    </div>
                    <motion.button
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                        onClick={updateSettings}
                        disabled={isSaving || !hasChanges}
                        className={cn(
                            "btn-primary flex items-center gap-2",
                            !hasChanges && "opacity-50 cursor-not-allowed",
                        )}
                    >
                        {isSaving ? <Spinner size="sm" /> : <Icons.Save />}
                        Save Changes
                    </motion.button>
                </div>

                {/* Floating Save Button */}
                {isScrolled && (
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: 20 }}
                        className="fixed bottom-5 right-4 sm:right-auto sm:left-5 z-40"
                    >
                        <motion.button
                            whileHover={{ scale: 1.02 }}
                            whileTap={{ scale: 0.98 }}
                            onClick={updateSettings}
                            disabled={isSaving || !hasChanges}
                            className={cn(
                                "btn-primary flex items-center gap-2 shadow-lg shadow-primary-500/25",
                                !hasChanges && "opacity-50 cursor-not-allowed",
                            )}
                        >
                            {isSaving ? <Spinner size="sm" /> : <Icons.Save />}
                            <span className="hidden sm:flex">Save Changes</span>
                            <span className="flex sm:hidden">Save</span>
                            {hasChanges && (
                                <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
                            )}
                        </motion.button>
                    </motion.div>
                )}

                {/* Quick Actions */}
                <div className="card p-6">
                    <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">
                        Quick Actions
                    </h2>
                    <div className="flex flex-wrap gap-3">
                        <button
                            onClick={gptRestart}
                            className="btn-secondary flex items-center gap-2"
                        >
                            <Icons.Refresh className="w-4 h-4" />
                            Restart GPT Home
                        </button>
                        <button
                            onClick={spotifyRestart}
                            className="btn-secondary flex items-center gap-2"
                        >
                            <Icons.Music className="w-4 h-4" />
                            Restart Spotifyd
                        </button>
                        <button
                            onClick={() => setIsPasswordModalOpen(true)}
                            className="btn-secondary flex items-center gap-2"
                        >
                            <Icons.Lock className="w-4 h-4" />
                            Change Password
                        </button>
                        <button
                            onClick={clearMemory}
                            className="btn-secondary flex items-center gap-2 text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-900/20"
                        >
                            <Icons.Trash className="w-4 h-4" />
                            Clear Memory
                        </button>
                        <button
                            onClick={reboot}
                            className="btn-icon group relative"
                        >
                            <Icons.RotateCw />
                            <span className="tooltip">Reboot System</span>
                        </button>
                        <button
                            onClick={shutdown}
                            className="btn-icon group relative text-rose-500"
                        >
                            <Icons.Power />
                            <span className="tooltip">Shutdown</span>
                        </button>
                    </div>
                </div>

                <div className="grid gap-6 lg:grid-cols-2">
                    {/* LLM Configuration */}
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.1 }}
                        className="card p-6"
                    >
                        <div className="flex items-center gap-3 mb-6">
                            <div className="p-2 rounded-xl bg-gradient-to-br from-primary-100 to-violet-100 dark:from-primary-900/30 dark:to-violet-900/30">
                                <Icons.Key className="w-5 h-5 text-primary-600 dark:text-primary-400" />
                            </div>
                            <div>
                                <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
                                    LLM Configuration
                                </h2>
                                <p className="text-xs text-slate-500 dark:text-slate-400">
                                    Powered by LiteLLM
                                </p>
                            </div>
                            <a
                                href="https://docs.litellm.ai/docs/providers"
                                target="_blank"
                                rel="noreferrer"
                                className="ml-auto text-primary-500 hover:text-primary-600"
                                title="View supported providers"
                            >
                                <Icons.ExternalLink className="w-4 h-4" />
                            </a>
                        </div>

                        <div className="space-y-4">
                            <div>
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                                    API Key
                                </label>
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
                                            <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
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

                            <div>
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                                    Chat Model{" "}
                                    {detectedProvider && (
                                        <span className="text-xs text-slate-400 font-normal">
                                            ({filteredModels.length})
                                        </span>
                                    )}
                                </label>
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

                            <div>
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                                    Embedding Model
                                </label>
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
                                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                                    For memory &amp; semantic search
                                </p>
                            </div>

                            <div className="flex flex-col sm:grid gap-4 grid-cols-2">
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
                                                max_tokens: parseInt(
                                                    e.target.value,
                                                    10,
                                                ),
                                            })
                                        }
                                        className="input-field"
                                        placeholder="1024"
                                    />
                                </div>

                                <div>
                                    <div className="flex flex-col items-center gap-3 h-[42px]">
                                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 block">
                                            Temperature{" "}
                                        </label>
                                        <div className="flex items-center gap-2  w-[90%]">
                                            <input
                                                type="range"
                                                min="0"
                                                max="2"
                                                step="0.1"
                                                value={
                                                    settings.temperature || 0
                                                }
                                                onChange={(e) =>
                                                    setSettings({
                                                        ...settings,
                                                        temperature: parseFloat(
                                                            e.target.value,
                                                        ),
                                                    })
                                                }
                                                className="flex-1 h-2 bg-slate-200 dark:bg-dark-600 rounded-lg appearance-none cursor-pointer accent-primary-500"
                                            />
                                            <span className="text-sm font-mono text-slate-600 dark:text-slate-400 w-8 text-right">
                                                {settings.temperature?.toFixed(
                                                    1,
                                                ) || "0.0"}
                                            </span>
                                        </div>
                                        <span className="text-xs text-slate-400 font-normal">
                                            (0 = focused, 2 = creative)
                                        </span>
                                    </div>
                                </div>
                            </div>

                            <div>
                                <label className="pt-10 sm:pt-0 text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                                    Custom Instructions
                                </label>
                                <textarea
                                    value={settings.custom_instructions || ""}
                                    onChange={(e) =>
                                        setSettings({
                                            ...settings,
                                            custom_instructions: e.target.value,
                                        })
                                    }
                                    className="input-field min-h-[80px] resize-y"
                                    placeholder="Add any custom instructions..."
                                />
                            </div>
                        </div>
                    </motion.div>

                    {/* General Settings */}
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.15 }}
                        className="card p-6"
                    >
                        <div className="flex items-center gap-3 mb-6">
                            <div className="p-2 rounded-xl bg-emerald-100 dark:bg-emerald-900/30">
                                <Icons.Settings className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                            </div>
                            <div>
                                <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
                                    General Settings
                                </h2>
                                <p className="text-xs text-slate-500 dark:text-slate-400">
                                    Voice &amp; speech configuration
                                </p>
                            </div>
                        </div>

                        <div className="space-y-4">
                            <div className="grid gap-4 grid-cols-2">
                                <div>
                                    <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                                        Wake Word
                                    </label>
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
                                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                                        Say this to activate assistant
                                    </p>
                                </div>

                                <div>
                                    <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                                        Repeat Input
                                    </label>
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
                                                        e.target.value ===
                                                        "true",
                                                })
                                            }
                                            className="select-field"
                                        >
                                            <option value="true">Yes</option>
                                            <option value="false">No</option>
                                        </select>
                                        <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                                    </div>
                                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                                        Say "Heard: ..." before responding
                                    </p>
                                </div>
                            </div>

                            <div className="pt-3 border-t border-slate-200 dark:border-dark-600">
                                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-3 block uppercase tracking-wide">
                                    Text-to-Speech (TTS)
                                </label>
                                <div className="grid gap-4 grid-cols-2">
                                    <div>
                                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                                            Engine
                                        </label>
                                        <div className="relative">
                                            <select
                                                value={
                                                    settings.ttsEngine || "gtts"
                                                }
                                                onChange={(e) =>
                                                    setSettings({
                                                        ...settings,
                                                        ttsEngine:
                                                            e.target.value,
                                                    })
                                                }
                                                className="select-field"
                                            >
                                                <option value="pyttsx3">
                                                    pyttsx3 (Offline)
                                                </option>
                                                <option value="gtts">
                                                    gTTS (Google)
                                                </option>
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
                                                value={
                                                    settings.ttsVoice || "alloy"
                                                }
                                                onChange={(e) =>
                                                    setSettings({
                                                        ...settings,
                                                        ttsVoice:
                                                            e.target.value,
                                                    })
                                                }
                                                className="select-field"
                                                disabled={
                                                    settings.ttsEngine !==
                                                    "litellm"
                                                }
                                            >
                                                {detectedProvider &&
                                                TTS_VOICES[detectedProvider]
                                                    ? TTS_VOICES[
                                                          detectedProvider
                                                      ].map((v) => (
                                                          <option
                                                              key={v.value}
                                                              value={v.value}
                                                          >
                                                              {v.label}
                                                          </option>
                                                      ))
                                                    : TTS_VOICES.openai.map(
                                                          (v) => (
                                                              <option
                                                                  key={v.value}
                                                                  value={
                                                                      v.value
                                                                  }
                                                              >
                                                                  {v.label}
                                                              </option>
                                                          ),
                                                      )}
                                            </select>
                                            <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div className="pt-3 border-t border-slate-200 dark:border-dark-600">
                                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-3 block uppercase tracking-wide">
                                    Speech-to-Text (STT)
                                </label>
                                <div className="grid gap-4 grid-cols-2">
                                    <div>
                                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                                            Engine
                                        </label>
                                        <div className="relative">
                                            <select
                                                value={
                                                    settings.sttEngine ||
                                                    "google"
                                                }
                                                onChange={(e) =>
                                                    setSettings({
                                                        ...settings,
                                                        sttEngine:
                                                            e.target.value,
                                                    })
                                                }
                                                className="select-field"
                                            >
                                                <option value="google">
                                                    Google (Free)
                                                </option>
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
                                                value={
                                                    settings.sttLanguage || "en"
                                                }
                                                onChange={(e) =>
                                                    setSettings({
                                                        ...settings,
                                                        sttLanguage:
                                                            e.target.value,
                                                    })
                                                }
                                                className="select-field"
                                            >
                                                {STT_LANGUAGES.map((lang) => (
                                                    <option
                                                        key={lang.value}
                                                        value={lang.value}
                                                    >
                                                        {lang.label}
                                                    </option>
                                                ))}
                                            </select>
                                            <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div className="pt-3 border-t border-slate-200 dark:border-dark-600">
                                <label className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-3 block uppercase tracking-wide">
                                    Speech Timing
                                </label>
                                <div className="grid gap-4 grid-cols-3">
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
                                                handleSpeechTimingChange(
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
                                                handleSpeechTimingChange(
                                                    "phraseTimeLimit",
                                                    parseInt(
                                                        e.target.value,
                                                        10,
                                                    ),
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
                                            value={
                                                speechTiming.nonSpeakingDuration
                                            }
                                            onChange={(e) =>
                                                handleSpeechTimingChange(
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
                    </motion.div>

                    {/* Hardware Settings - Display and Audio */}
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.2 }}
                        className="card p-4 sm:p-6"
                    >
                        <div className="flex items-center gap-2 sm:gap-3 mb-4 sm:mb-6">
                            <div className="p-1.5 sm:p-2 rounded-xl bg-cyan-100 dark:bg-cyan-900/30">
                                <Icons.Settings className="w-4 h-4 sm:w-5 sm:h-5 text-cyan-600 dark:text-cyan-400" />
                            </div>
                            <div className="min-w-0 flex-1">
                                <h2 className="text-base sm:text-lg font-semibold text-slate-900 dark:text-white">
                                    Hardware
                                </h2>
                                <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                                    Display and audio configuration
                                </p>
                            </div>
                        </div>

                        {/* Display subsection */}
                        <div className="mb-4 sm:mb-6">
                            <div className="flex flex-wrap items-center gap-2 mb-3">
                                <div className="flex items-center gap-2">
                                    <Icons.Monitor className="w-4 h-4 text-slate-500 flex-shrink-0" />
                                    <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300">
                                        Display
                                    </h3>
                                </div>
                                {displayStatus &&
                                    displayStatus.displays.length > 0 && (
                                        <span className="text-xs text-slate-500 dark:text-slate-400 hidden sm:inline">
                                            {displayStatus.displays.find(
                                                (d) =>
                                                    d.type ===
                                                    displayStatus.current_display_type,
                                            )?.name ||
                                                displayStatus.displays[0]
                                                    .name ||
                                                `${displayStatus.displays[0].width}x${displayStatus.displays[0].height} ${displayStatus.displays[0].type}`}
                                        </span>
                                    )}
                                {displayStatus &&
                                    hasOnlySimpleDisplay(displayStatus) && (
                                        <span className="text-xs px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400">
                                            Text Only
                                        </span>
                                    )}
                                {displayStatus &&
                                    displayStatus.active &&
                                    shouldShowDisplayModes(displayStatus) && (
                                        <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400">
                                            Active
                                        </span>
                                    )}
                                {displayStatus && !displayStatus.available && (
                                    <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400">
                                        No Display
                                    </span>
                                )}
                                <div className="ml-auto flex items-center gap-1 sm:gap-2">
                                    <button
                                        onClick={handleRefreshDisplay}
                                        disabled={isRefreshingDisplay}
                                        className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-dark-600 transition-colors"
                                        title="Refresh display detection"
                                    >
                                        {isRefreshingDisplay ? (
                                            <Spinner size="sm" />
                                        ) : (
                                            <Icons.Refresh className="w-4 h-4 text-slate-400" />
                                        )}
                                    </button>
                                    <button
                                        onClick={handlePowerOnDisplay}
                                        disabled={isPoweringDisplay}
                                        className="btn-secondary text-xs flex items-center gap-1 sm:gap-1.5 px-2 sm:px-3"
                                        title="Power on display"
                                    >
                                        {isPoweringDisplay ? (
                                            <Spinner size="sm" />
                                        ) : (
                                            <Icons.Power className="w-3.5 h-3.5" />
                                        )}
                                        <span className="hidden xs:inline">
                                            Power
                                        </span>{" "}
                                        On
                                    </button>
                                </div>
                            </div>

                            {displayStatus && !displayStatus.available && (
                                <p className="text-sm text-slate-500 dark:text-slate-400 mb-3">
                                    Connect an HDMI display, SPI/TFT LCD, or I2C
                                    display.
                                </p>
                            )}

                            {displayStatus &&
                                hasOnlySimpleDisplay(displayStatus) && (
                                    <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 mb-3">
                                        <p className="text-xs text-amber-600 dark:text-amber-400">
                                            I2C display detected - text output
                                            only. Display modes require HDMI or
                                            TFT LCD.
                                        </p>
                                    </div>
                                )}

                            {/* Multi-display controls - show when multiple full displays detected */}
                            {displayStatus &&
                                displayStatus.displays.filter(
                                    (d) => d.supports_modes,
                                ).length > 1 && (
                                    <div className="mb-4 space-y-3">
                                        {/* Mirror Mode Toggle */}
                                        <div className="flex items-center justify-between">
                                            <div>
                                                <label className="text-xs font-medium text-slate-600 dark:text-slate-400 block">
                                                    Mirror Displays
                                                </label>
                                                <p className="text-xs text-slate-500 dark:text-slate-500">
                                                    Show same content on all
                                                    displays
                                                </p>
                                            </div>
                                            <button
                                                onClick={() =>
                                                    handleMirrorToggle(
                                                        !displayStatus.mirror_enabled,
                                                    )
                                                }
                                                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                                                    displayStatus.mirror_enabled
                                                        ? "bg-indigo-600"
                                                        : "bg-slate-200 dark:bg-slate-700"
                                                }`}
                                            >
                                                <span
                                                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                                                        displayStatus.mirror_enabled
                                                            ? "translate-x-6"
                                                            : "translate-x-1"
                                                    }`}
                                                />
                                            </button>
                                        </div>

                                        {/* Per-display enable/disable */}
                                        <div>
                                            <label className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-2 block">
                                                Enabled Displays
                                            </label>
                                            <div className="space-y-2">
                                                {displayStatus.displays
                                                    .filter(
                                                        (d) => d.supports_modes,
                                                    )
                                                    .map((display) => (
                                                        <div
                                                            key={display.id}
                                                            className="flex items-center justify-between p-2 rounded-lg bg-slate-50 dark:bg-slate-800/50"
                                                        >
                                                            <div className="flex items-center gap-2">
                                                                <Icons.Monitor className="w-4 h-4 text-slate-400" />
                                                                <span className="text-sm text-slate-700 dark:text-slate-300">
                                                                    {
                                                                        display.name
                                                                    }
                                                                </span>
                                                            </div>
                                                            <button
                                                                onClick={() =>
                                                                    handleDisplayEnable(
                                                                        display.id,
                                                                        !display.enabled,
                                                                    )
                                                                }
                                                                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                                                                    display.enabled !==
                                                                    false
                                                                        ? "bg-emerald-500"
                                                                        : "bg-slate-300 dark:bg-slate-600"
                                                                }`}
                                                            >
                                                                <span
                                                                    className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                                                                        display.enabled !==
                                                                        false
                                                                            ? "translate-x-4"
                                                                            : "translate-x-1"
                                                                    }`}
                                                                />
                                                            </button>
                                                        </div>
                                                    ))}
                                            </div>
                                            <p className="text-xs text-slate-500 mt-1">
                                                Disabled displays show TTY
                                                console
                                            </p>
                                        </div>
                                    </div>
                                )}

                            {displayStatus &&
                                displayStatus.available &&
                                shouldShowDisplayModes(displayStatus) && (
                                    <div className="flex items-center gap-5">
                                        <div className="w-full">
                                            <label className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-1 block">
                                                Display Mode
                                            </label>
                                            <div className="relative">
                                                <select
                                                    value={
                                                        settings.display_mode ||
                                                        "smart"
                                                    }
                                                    onChange={(e) =>
                                                        handleDisplayModeChange(
                                                            e.target.value,
                                                        )
                                                    }
                                                    className="select-field text-sm mr-4 w-full"
                                                >
                                                    {DISPLAY_MODES.map(
                                                        (mode) => (
                                                            <option
                                                                key={mode.value}
                                                                value={
                                                                    mode.value
                                                                }
                                                            >
                                                                {mode.label}
                                                            </option>
                                                        ),
                                                    )}
                                                </select>
                                                <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none w-4 h-4" />
                                            </div>
                                        </div>

                                        {settings.display_mode ===
                                            "gallery" && (
                                            <div className="w-full">
                                                <label className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-1 block">
                                                    Interval (seconds)
                                                </label>
                                                <input
                                                    type="number"
                                                    min="3"
                                                    max="60"
                                                    value={
                                                        settings.gallery_interval ||
                                                        10
                                                    }
                                                    onChange={(e) =>
                                                        setSettings({
                                                            ...settings,
                                                            gallery_interval:
                                                                parseInt(
                                                                    e.target
                                                                        .value,
                                                                    10,
                                                                ),
                                                        })
                                                    }
                                                    className="input-field w-24 text-sm w-full"
                                                />
                                            </div>
                                        )}
                                    </div>
                                )}

                            {/* Hardware Display Mode Toggle */}
                            <div className="mt-4 p-3 rounded-lg bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700">
                                <div className="flex items-center justify-between mb-2">
                                    <div>
                                        <label className="text-xs font-medium text-slate-600 dark:text-slate-400 block">
                                            Hardware Display Mode
                                        </label>
                                        <p className="text-xs text-slate-500 dark:text-slate-500">
                                            Switch between HDMI and TFT display
                                            (requires reboot)
                                        </p>
                                    </div>
                                    {hardwareDisplayMode === "conflict" && (
                                        <span className="text-xs px-2 py-0.5 rounded-full bg-rose-100 dark:bg-rose-900/30 text-rose-600 dark:text-rose-400">
                                            Conflict
                                        </span>
                                    )}
                                </div>
                                <div className="flex gap-2">
                                    <button
                                        onClick={() =>
                                            handleHardwareModeChange("hdmi")
                                        }
                                        disabled={
                                            isChangingHardwareMode ||
                                            hardwareDisplayMode === "hdmi" ||
                                            hardwareDisplayMode === "unknown"
                                        }
                                        className={cn(
                                            "flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-colors",
                                            hardwareDisplayMode === "hdmi" ||
                                                hardwareDisplayMode ===
                                                    "unknown"
                                                ? "bg-primary-500 text-white"
                                                : "bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-600 border border-slate-200 dark:border-slate-600",
                                            (isChangingHardwareMode ||
                                                hardwareDisplayMode ===
                                                    "hdmi" ||
                                                hardwareDisplayMode ===
                                                    "unknown") &&
                                                "cursor-not-allowed",
                                            isChangingHardwareMode &&
                                                "opacity-50",
                                        )}
                                    >
                                        {isChangingHardwareMode ? (
                                            <Spinner size="sm" />
                                        ) : (
                                            <>
                                                <Icons.Monitor className="w-4 h-4 inline mr-1.5" />
                                                HDMI
                                            </>
                                        )}
                                    </button>
                                    <button
                                        onClick={() =>
                                            handleHardwareModeChange("tft")
                                        }
                                        disabled={
                                            isChangingHardwareMode ||
                                            hardwareDisplayMode === "tft"
                                        }
                                        className={cn(
                                            "flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-colors",
                                            hardwareDisplayMode === "tft"
                                                ? "bg-primary-500 text-white"
                                                : "bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-600 border border-slate-200 dark:border-slate-600",
                                            (isChangingHardwareMode ||
                                                hardwareDisplayMode ===
                                                    "tft") &&
                                                "cursor-not-allowed",
                                            isChangingHardwareMode &&
                                                "opacity-50",
                                        )}
                                    >
                                        {isChangingHardwareMode ? (
                                            <Spinner size="sm" />
                                        ) : (
                                            <>
                                                <Icons.Cpu className="w-4 h-4 inline mr-1.5" />
                                                TFT (SPI)
                                            </>
                                        )}
                                    </button>
                                </div>
                                {hardwareDisplayMode === "conflict" && (
                                    <p className="text-xs text-rose-500 mt-2">
                                        Both HDMI and TFT overlays are active.
                                        This will cause boot issues. Select one
                                        mode to fix.
                                    </p>
                                )}
                            </div>
                        </div>

                        {/* Display Rotation */}
                        <div className="mt-4 p-3 rounded-lg bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700">
                            <label className="text-xs font-medium text-slate-600 dark:text-slate-400 block mb-2">
                                Display Rotation
                            </label>
                            <div className="space-y-2">
                                {(hardwareDisplayMode === "tft" ||
                                    hardwareDisplayMode === "conflict") && (
                                    <div className="flex items-center justify-between">
                                        <span className="text-xs text-slate-500 dark:text-slate-400">
                                            TFT / HDMI
                                        </span>
                                        <select
                                            value={displayRotation.tft_rotation}
                                            onChange={(e) =>
                                                handleTftRotationChange(
                                                    parseInt(
                                                        e.target.value,
                                                        10,
                                                    ),
                                                )
                                            }
                                            className="input-field text-sm w-32"
                                        >
                                            <option value={0}>0°</option>
                                            <option value={90}>90°</option>
                                            <option value={180}>180°</option>
                                            <option value={270}>270°</option>
                                        </select>
                                    </div>
                                )}
                                <div className="flex items-center justify-between">
                                    <span className="text-xs text-slate-500 dark:text-slate-400">
                                        I2C OLED
                                    </span>
                                    <select
                                        value={displayRotation.i2c_rotation}
                                        onChange={(e) =>
                                            handleI2cRotationChange(
                                                parseInt(e.target.value, 10),
                                            )
                                        }
                                        className="input-field text-sm w-32"
                                    >
                                        <option value={0}>0°</option>
                                        <option value={1}>90°</option>
                                        <option value={2}>180°</option>
                                        <option value={3}>270°</option>
                                    </select>
                                </div>
                            </div>
                            {rotationRebootPending && (
                                <p className="text-xs text-amber-500 mt-2">
                                    TFT rotation changed. Reboot required to
                                    apply.
                                </p>
                            )}
                        </div>

                        {/* Divider */}
                        <div className="border-t border-slate-200 dark:border-slate-700 my-4"></div>

                        {/* Screensaver subsection */}
                        <div className="mb-4 sm:mb-6">
                            <div className="space-y-3">
                                <div className="flex flex-wrap items-center gap-2 sm:gap-4">
                                    <div className="flex items-center gap-2">
                                        <Icons.Moon className="w-4 h-4 text-slate-500 flex-shrink-0" />
                                        <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300">
                                            Screensaver
                                        </h3>
                                    </div>
                                    {/* Enable/Disable Toggle */}
                                    <button
                                        onClick={() =>
                                            handleScreensaverSettingChange(
                                                "enabled",
                                                !screensaverSettings.enabled,
                                            )
                                        }
                                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors flex-shrink-0 ${
                                            screensaverSettings.enabled
                                                ? "bg-primary-500"
                                                : "bg-slate-300 dark:bg-slate-600"
                                        }`}
                                    >
                                        <span
                                            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                                                screensaverSettings.enabled
                                                    ? "translate-x-6"
                                                    : "translate-x-1"
                                            }`}
                                        />
                                    </button>
                                </div>
                                <div className="flex flex-col sm:flex-row gap-3 sm:gap-4">
                                    {/* Style */}
                                    <div className="flex-1 min-w-0">
                                        <label className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-1 block">
                                            Style
                                        </label>
                                        <div className="relative">
                                            <select
                                                value={
                                                    screensaverSettings.style
                                                }
                                                onChange={(e) =>
                                                    handleScreensaverSettingChange(
                                                        "style",
                                                        e.target.value,
                                                    )
                                                }
                                                className="select-field text-sm"
                                            >
                                                {screensaverSettings.available_styles.map(
                                                    (style) => (
                                                        <option
                                                            key={style}
                                                            value={style}
                                                        >
                                                            {style
                                                                .charAt(0)
                                                                .toUpperCase() +
                                                                style.slice(1)}
                                                        </option>
                                                    ),
                                                )}
                                            </select>
                                            <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none w-4 h-4" />
                                        </div>
                                        <p className="text-xs text-slate-400 mt-1">
                                            {screensaverSettings.style ===
                                                "starfield" &&
                                                "Stars flying through space"}
                                            {screensaverSettings.style ===
                                                "matrix" &&
                                                "Matrix digital rain effect"}
                                            {screensaverSettings.style ===
                                                "bounce" &&
                                                "Bouncing logo (DVD style)"}
                                            {screensaverSettings.style ===
                                                "fade" &&
                                                "Smooth color cycling with clock"}
                                        </p>
                                    </div>
                                    {/* Timeout */}
                                    <div className="w-full sm:w-auto">
                                        <label className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-1 block">
                                            Timeout (seconds)
                                        </label>
                                        <input
                                            type="number"
                                            min="1"
                                            max="3600"
                                            step="1"
                                            value={screensaverSettings.timeout}
                                            onChange={(e) =>
                                                handleScreensaverSettingChange(
                                                    "timeout",
                                                    parseInt(
                                                        e.target.value,
                                                        10,
                                                    ) || 300,
                                                )
                                            }
                                            className="input-field w-24 text-sm"
                                        />
                                        <p className="text-xs text-slate-400 mt-1">
                                            {Math.floor(
                                                screensaverSettings.timeout /
                                                    60,
                                            )}{" "}
                                            min{" "}
                                            {screensaverSettings.timeout % 60 >
                                            0
                                                ? `${screensaverSettings.timeout % 60} sec`
                                                : ""}
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Divider */}
                        <div className="border-t border-slate-200 dark:border-slate-700 my-4"></div>

                        {/* Audio subsection */}
                        <div>
                            <div className="flex flex-wrap items-center gap-2 mb-3">
                                <Icons.Volume2 className="w-4 h-4 text-slate-500 flex-shrink-0" />
                                <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300">
                                    Audio Output
                                </h3>
                                {loadingStates.audioDevices && (
                                    <Spinner size="sm" />
                                )}
                                {audioState.current !== null && (
                                    <span className="text-xs text-slate-500 dark:text-slate-400">
                                        Card {audioState.current}
                                    </span>
                                )}
                            </div>

                            {loadingStates.audioDevices ? (
                                <div className="text-sm text-slate-500 dark:text-slate-400">
                                    Detecting audio devices...
                                </div>
                            ) : audioState.devices.length > 0 ? (
                                <div className="space-y-3">
                                    <div>
                                        <label className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-1 block">
                                            Output Device
                                        </label>
                                        <div className="relative">
                                            <select
                                                value={
                                                    audioState.current !== null
                                                        ? String(
                                                              audioState.current,
                                                          )
                                                        : ""
                                                }
                                                onChange={(e) => {
                                                    const selectedCard =
                                                        parseInt(
                                                            e.target.value,
                                                            10,
                                                        );
                                                    const selectedDevice =
                                                        audioState.devices.find(
                                                            (d) =>
                                                                d.card ===
                                                                selectedCard,
                                                        );
                                                    handleAudioDeviceChange(
                                                        selectedCard,
                                                        selectedDevice?.id,
                                                    );
                                                }}
                                                disabled={isChangingAudio}
                                                className="select-field text-sm"
                                            >
                                                {audioState.devices.map(
                                                    (device) => (
                                                        <option
                                                            key={device.card}
                                                            value={String(
                                                                device.card,
                                                            )}
                                                        >
                                                            {device.name} (
                                                            {device.device_name}
                                                            )
                                                        </option>
                                                    ),
                                                )}
                                            </select>
                                            <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none w-4 h-4" />
                                        </div>
                                    </div>

                                    {audioState.volume !== null && (
                                        <div>
                                            <label className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-1 block">
                                                Volume: {audioState.volume}%
                                            </label>
                                            <input
                                                type="range"
                                                min="0"
                                                max="100"
                                                value={audioState.volume}
                                                onChange={(e) =>
                                                    handleVolumeChange(
                                                        parseInt(
                                                            e.target.value,
                                                            10,
                                                        ),
                                                    )
                                                }
                                                className="w-full h-2 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-cyan-500"
                                            />
                                        </div>
                                    )}
                                </div>
                            ) : (
                                <p className="text-sm text-slate-500 dark:text-slate-400">
                                    No audio output devices detected.
                                </p>
                            )}
                        </div>

                        {/* Divider */}
                        <div className="border-t border-slate-200 dark:border-slate-700 my-4"></div>

                        {/* Microphone Input Section */}
                        <div>
                            <div className="flex flex-wrap items-center gap-2 mb-3">
                                <Icons.Mic className="w-4 h-4 text-slate-500 flex-shrink-0" />
                                <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300">
                                    Microphone Input
                                </h3>
                                {loadingStates.audioInputDevices && (
                                    <Spinner size="sm" />
                                )}
                                {audioState.micCard && (
                                    <span className="text-xs text-slate-500 dark:text-slate-400">
                                        Card {audioState.micCard}
                                    </span>
                                )}
                            </div>

                            {/* Input Device Dropdown */}
                            {loadingStates.audioInputDevices ? (
                                <div className="text-sm text-slate-500 dark:text-slate-400 mb-3">
                                    Detecting input devices...
                                </div>
                            ) : audioState.inputDevices.length > 0 ? (
                                <div className="mb-3">
                                    <label className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-1 block">
                                        Input Device
                                    </label>
                                    <div className="relative">
                                        <select
                                            value={
                                                audioState.currentInputDevice !==
                                                null
                                                    ? String(
                                                          audioState.currentInputDevice,
                                                      )
                                                    : ""
                                            }
                                            onChange={(e) =>
                                                handleInputDeviceChange(
                                                    parseInt(
                                                        e.target.value,
                                                        10,
                                                    ),
                                                )
                                            }
                                            disabled={isChangingInputDevice}
                                            className="select-field text-sm"
                                        >
                                            {audioState.inputDevices.map(
                                                (device) => (
                                                    <option
                                                        key={device.card}
                                                        value={String(
                                                            device.card,
                                                        )}
                                                    >
                                                        {device.name} (
                                                        {device.device_name})
                                                    </option>
                                                ),
                                            )}
                                        </select>
                                        <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none w-4 h-4" />
                                    </div>
                                </div>
                            ) : null}

                            {audioState.micGain !== null && (
                                <div className="mb-3">
                                    <label className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-1 block">
                                        Mic Gain: {audioState.micGain}%
                                    </label>
                                    <input
                                        type="range"
                                        min="0"
                                        max="100"
                                        value={audioState.micGain}
                                        onChange={(e) =>
                                            handleMicGainChange(
                                                parseInt(e.target.value, 10),
                                            )
                                        }
                                        className="w-full h-2 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-emerald-500"
                                    />
                                </div>
                            )}

                            <div>
                                <label className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-1 block">
                                    Voice Detection Threshold:{" "}
                                    {audioState.vadThreshold} dB
                                </label>
                                <input
                                    type="range"
                                    min="-80"
                                    max="0"
                                    value={audioState.vadThreshold}
                                    onChange={(e) =>
                                        handleVadThresholdChange(
                                            parseInt(e.target.value, 10),
                                        )
                                    }
                                    className="w-full h-2 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-amber-500"
                                />
                                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                                    Lower = more sensitive (picks up quiet
                                    speech), Higher = less sensitive (rejects
                                    background noise)
                                </p>
                            </div>
                        </div>
                    </motion.div>

                    {/* Gallery Images - Side by side with Hardware */}
                    {displayStatus &&
                        displayStatus.available &&
                        shouldShowDisplayModes(displayStatus) && (
                            <motion.div
                                initial={{ opacity: 0, y: 20 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: 0.3 }}
                                className="card p-4 sm:p-6"
                            >
                                <div className="flex items-center gap-2 sm:gap-3 mb-4">
                                    <div className="p-1.5 sm:p-2 rounded-xl bg-violet-100 dark:bg-violet-900/30 flex-shrink-0">
                                        <Icons.Image className="w-4 h-4 sm:w-5 sm:h-5 text-violet-600 dark:text-violet-400" />
                                    </div>
                                    <div className="min-w-0">
                                        <h2 className="text-base sm:text-lg font-semibold text-slate-900 dark:text-white">
                                            Gallery Images
                                        </h2>
                                        <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                                            Upload images for gallery mode
                                        </p>
                                    </div>
                                </div>

                                {/* Dropzone */}
                                <div
                                    onDragOver={handleDragOver}
                                    onDragLeave={handleDragLeave}
                                    onDrop={handleDrop}
                                    className={cn(
                                        "text-center py-6 border-2 border-dashed rounded-xl cursor-pointer transition-all duration-200 mb-4",
                                        isDraggingOver
                                            ? "border-violet-500 bg-violet-50 dark:bg-violet-900/20 scale-[1.02]"
                                            : "border-slate-200 dark:border-dark-600 hover:border-slate-300 dark:hover:border-dark-500",
                                    )}
                                    onClick={() =>
                                        document
                                            .getElementById(
                                                "gallery-file-input",
                                            )
                                            ?.click()
                                    }
                                >
                                    {isUploadingImage ? (
                                        <>
                                            <Spinner
                                                size="md"
                                                className="mx-auto mb-2"
                                            />
                                            <p className="text-sm text-slate-500 dark:text-slate-400">
                                                Uploading...
                                            </p>
                                        </>
                                    ) : isDraggingOver ? (
                                        <>
                                            <Icons.Upload className="w-8 h-8 mx-auto text-violet-500 mb-2 animate-bounce" />
                                            <p className="text-sm font-medium text-violet-600 dark:text-violet-400">
                                                Drop images here
                                            </p>
                                        </>
                                    ) : (
                                        <>
                                            <Icons.Upload className="w-8 h-8 mx-auto text-slate-300 dark:text-dark-500 mb-2" />
                                            <p className="text-sm text-slate-500 dark:text-slate-400">
                                                {galleryImages.length === 0
                                                    ? "No images uploaded yet"
                                                    : "Drag & drop images here, or click to browse"}
                                            </p>
                                            {galleryImages.length === 0 && (
                                                <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                                                    Drag & drop images here, or
                                                    click to browse
                                                </p>
                                            )}
                                            <p className="text-xs text-slate-400 dark:text-slate-500 mt-2">
                                                Accepted: JPEG, PNG, GIF, BMP,
                                                WebP (max 50MB)
                                            </p>
                                        </>
                                    )}
                                    <input
                                        id="gallery-file-input"
                                        type="file"
                                        accept="image/jpeg,image/png,image/gif,image/bmp,image/webp"
                                        multiple
                                        onChange={handleImageUpload}
                                        className="hidden"
                                        disabled={isUploadingImage}
                                    />
                                </div>

                                {/* Gallery Images Grid */}
                                {galleryImages.length > 0 && (
                                    <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-3 lg:grid-cols-4 gap-2 sm:gap-3">
                                        {galleryImages.map((image) => (
                                            <div
                                                key={image.name}
                                                className="relative group aspect-square rounded-lg overflow-hidden bg-slate-100 dark:bg-dark-700 cursor-pointer"
                                                onClick={() =>
                                                    setSelectedImage(image)
                                                }
                                            >
                                                <img
                                                    src={image.path}
                                                    alt={image.name}
                                                    className="w-full h-full object-cover transition-transform duration-200 group-hover:scale-105"
                                                />
                                                <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors" />
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        handleDeleteImage(
                                                            image.name,
                                                        );
                                                    }}
                                                    className="absolute top-1 right-1 p-1.5 rounded-lg bg-black/50 text-white opacity-0 group-hover:opacity-100 transition-opacity hover:bg-rose-500"
                                                >
                                                    <Icons.X className="w-3 h-3" />
                                                </button>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </motion.div>
                        )}

                    {/* Image Viewer Modal */}
                    <ImageViewer
                        src={selectedImage?.path || ""}
                        alt={selectedImage?.name || ""}
                        isOpen={!!selectedImage}
                        onClose={() => setSelectedImage(null)}
                    />
                </div>
            </div>
        </>
    );
};

export default Settings;
