import React, {
    useState,
    useEffect,
    useRef,
    useCallback,
    useMemo,
} from "react";
import { motion } from "framer-motion";
import axios from "axios";
import { Icons, Spinner } from "../Icons";
import { cn } from "../../lib/utils";
import AlertModal, { useAlert } from "../AlertModal";
import ConfirmModal, { useConfirm } from "../ConfirmModal";
import ImageViewer from "../ImageViewer";
import {
    useSettingsPageData,
    useInvalidateQueries,
    queryKeys,
    type DisplayStatus,
    type GalleryImage,
    type AudioDevice,
    type SpeechTiming,
    type ScreensaverSettings,
} from "../../hooks/useApi";
import { useQueryClient } from "@tanstack/react-query";
import QuickActions from "./QuickActions";
import GeneralTab from "./GeneralTab";
import LLMTab from "./LLMTab";
import HardwareTab from "./HardwareTab";
import GalleryTab from "./GalleryTab";

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
    deepseek: ["openai:text-embedding-3-small"],
    groq: ["openai:text-embedding-3-small"],
};

const detectProvider = (apiKey: string): string | null => {
    if (!apiKey) return null;
    for (const [provider, pattern] of Object.entries(PROVIDER_PATTERNS)) {
        if (pattern.test(apiKey)) return provider;
    }
    return null;
};

const shouldShowDisplayModes = (status: DisplayStatus | null): boolean => {
    if (!status || !status.available) return false;
    if (typeof status.supports_modes === "boolean") {
        return status.supports_modes;
    }
    if (typeof status.has_full_display === "boolean") {
        return status.has_full_display;
    }
    return status.displays.some((d) => d.type !== "i2c" && d.type !== "I2C");
};

const hasOnlySimpleDisplay = (status: DisplayStatus | null): boolean => {
    if (!status || !status.available) return false;
    if (
        typeof status.has_simple_display === "boolean" &&
        typeof status.has_full_display === "boolean"
    ) {
        return status.has_simple_display && !status.has_full_display;
    }
    return (
        status.displays.length > 0 &&
        status.displays.every((d) => d.type === "i2c" || d.type === "I2C")
    );
};

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

const TABS = [
    { id: "general", label: "General", icon: Icons.Settings },
    { id: "llm", label: "LLM", icon: Icons.Key },
    { id: "hardware", label: "Hardware", icon: Icons.Cpu },
    { id: "gallery", label: "Gallery", icon: Icons.Image },
] as const;

const Settings: React.FC = () => {
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

    const [activeTab, setActiveTab] = useState("general");
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
        "hdmi" | "piscreen" | "unknown" | "conflict"
    >("unknown");
    const [isChangingHardwareMode, setIsChangingHardwareMode] = useState(false);
    const [displayRotation, setDisplayRotation] = useState({
        piscreen_rotation: 0,
        hdmi_rotation: 0,
        i2c_rotation: 2,
    });
    const [rotationRebootPending, setRotationRebootPending] = useState(false);
    const [availableResolutions, setAvailableResolutions] = useState<string[]>(
        [],
    );
    const [currentResolution, setCurrentResolution] = useState("");
    const [resolutionConfigurable, setResolutionConfigurable] = useState(false);
    const [resolutionRebootPending, setResolutionRebootPending] =
        useState(false);
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
    const [isChangingInputDevice, setIsChangingInputDevice] = useState(false);
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

    const [isInitialized, setIsInitialized] = useState(false);
    const [isScrolled, setIsScrolled] = useState(false);
    const headerRef = useRef<HTMLDivElement>(null);

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

    useEffect(() => {
        const handleScroll = () => {
            if (headerRef.current) {
                const headerBottom =
                    headerRef.current.getBoundingClientRect().bottom;
                setIsScrolled(headerBottom < 0);
            }
        };
        window.addEventListener("scroll", handleScroll);
        return () => window.removeEventListener("scroll", handleScroll);
    }, []);

    useEffect(() => {
        const provider = detectProvider(settings.litellm_api_key || "");
        setDetectedProvider(provider);

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

    useEffect(() => {
        if (!isCriticalLoading && !isInitialized) {
            if (fetchedSettings) {
                setSettings(fetchedSettings);
                setOriginalSettings(fetchedSettings);
            }
            if (fetchedModels) {
                setAllModels(fetchedModels);
            }
            setIsInitialized(true);
        }
    }, [isCriticalLoading, isInitialized, fetchedSettings, fetchedModels]);

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
        const fetchResolutions = async () => {
            try {
                const response = await axios.get("/api/display/resolutions");
                setAvailableResolutions(response.data.resolutions || []);
                setCurrentResolution(response.data.current || "");
                setResolutionConfigurable(response.data.configurable || false);
            } catch (err) {
                console.error("Failed to fetch display resolutions:", err);
            }
        };
        fetchHardwareMode();
        fetchRotation();
        fetchResolutions();
    }, []);

    useEffect(() => {
        if (fetchedGalleryImages) {
            setGalleryImages(fetchedGalleryImages);
        }
    }, [fetchedGalleryImages]);

    useEffect(() => {
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

    const handlePowerOnDisplay = async () => {
        setIsPoweringDisplay(true);
        try {
            const response = await axios.post("/api/display/power-on");
            if (response.data && response.data.success) {
                const msg =
                    response.data.message ||
                    "Power-on command sent. Check logs or the debug endpoint for details.";
                showAlert("info", "Power On Results", msg);
                try {
                    const result = await refetch.displayStatus();
                    if (result.data) {
                        setDisplayStatus(result.data);
                    }
                } catch (e) {
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

    const handleHardwareModeChange = (mode: "hdmi" | "piscreen") => {
        const modeLabel = mode === "hdmi" ? "HDMI" : "PiScreen";
        const otherMode = mode === "hdmi" ? "PiScreen" : "HDMI";
        showConfirm(
            `Switch to ${modeLabel} Display`,
            `This will configure the Raspberry Pi for ${modeLabel} display output and disable ${otherMode}. ` +
                `The system will reboot to apply changes.\n\n` +
                `Note: HDMI and PiScreen displays cannot work simultaneously due to kernel driver limitations.`,
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

    const handlePiscreenRotationChange = async (rotation: number) => {
        try {
            const response = await axios.post("/api/display/rotation", {
                piscreen_rotation: rotation,
            });
            if (response.data.success) {
                setDisplayRotation((prev) => ({
                    ...prev,
                    piscreen_rotation: rotation,
                }));
                if (response.data.reboot_required) {
                    setRotationRebootPending(true);
                }
            }
        } catch (err) {
            console.error("Failed to set PiScreen rotation:", err);
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

    const handleHdmiRotationChange = async (rotation: number) => {
        try {
            const response = await axios.post("/api/display/rotation", {
                hdmi_rotation: rotation,
            });
            if (response.data.success) {
                setDisplayRotation((prev) => ({
                    ...prev,
                    hdmi_rotation: rotation,
                }));
                if (response.data.reboot_required) {
                    setRotationRebootPending(true);
                }
            }
        } catch (err) {
            console.error("Failed to set HDMI rotation:", err);
        }
    };

    const handleResolutionChange = async (resolution: string) => {
        try {
            const response = await axios.post("/api/display/resolution", {
                resolution,
            });
            if (response.data.success) {
                setCurrentResolution(resolution);
                if (response.data.reboot_required) {
                    setResolutionRebootPending(true);
                }
            }
        } catch (err) {
            console.error("Failed to set resolution:", err);
        }
    };

    const handleDisplayConnectorChange = async (connector: string) => {
        try {
            await axios.post("/api/display/resolution", {
                resolution: currentResolution,
                connector,
            });
            const response = await axios.get(
                `/api/display/resolutions?connector=${encodeURIComponent(connector)}`,
            );
            setAvailableResolutions(response.data.resolutions || []);
            setCurrentResolution(response.data.current || "");
            setResolutionConfigurable(response.data.configurable || false);
        } catch (err) {
            console.error("Failed to change display connector:", err);
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

    const volumeDebounceRef = useRef<NodeJS.Timeout | null>(null);
    const pendingVolumeRef = useRef<number | null>(null);

    const handleVolumeChange = useCallback((volume: number) => {
        setAudioState((prev) => ({ ...prev, volume }));
        pendingVolumeRef.current = volume;
        if (volumeDebounceRef.current) {
            clearTimeout(volumeDebounceRef.current);
        }
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

    const handleSpeechTimingChange = useCallback(
        (key: keyof typeof speechTiming, value: number) => {
            setSpeechTiming((prev) => ({ ...prev, [key]: value }));
        },
        [],
    );

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
            queryClient.invalidateQueries({ queryKey: queryKeys.settings });

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
            "Clear Memories",
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
                            "Clear Memories Failed",
                            "Failed to clear memories.",
                        ),
                    );
            },
            { confirmText: "Clear Memories", variant: "danger" },
        );
    };

    const showGalleryTab =
        displayStatus &&
        displayStatus.available &&
        shouldShowDisplayModes(displayStatus);

    const visibleTabs = showGalleryTab
        ? TABS
        : TABS.filter((t) => t.id !== "gallery");

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

            <div className="space-y-6">
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
                <QuickActions
                    onGptRestart={gptRestart}
                    onSpotifyRestart={spotifyRestart}
                    onPasswordChange={() => setIsPasswordModalOpen(true)}
                    onClearMemory={clearMemory}
                    onReboot={reboot}
                    onShutdown={shutdown}
                />

                {/* Tabbed Settings */}
                <div className="card overflow-hidden">
                    <div className="border-b border-slate-200 dark:border-slate-700 px-4 sm:px-6">
                        <nav className="flex gap-1 overflow-x-auto scrollbar-none -mb-px">
                            {visibleTabs.map((tab) => (
                                <button
                                    key={tab.id}
                                    onClick={() => setActiveTab(tab.id)}
                                    className={cn(
                                        "flex items-center gap-2 px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors",
                                        activeTab === tab.id
                                            ? "border-primary-500 text-primary-600 dark:text-primary-400"
                                            : "border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 hover:border-slate-300 dark:hover:border-slate-600",
                                    )}
                                >
                                    <tab.icon className="w-4 h-4" />
                                    <span className="hidden sm:inline">
                                        {tab.label}
                                    </span>
                                </button>
                            ))}
                        </nav>
                    </div>
                    <div className="p-4 sm:p-6">
                        {activeTab === "general" && (
                            <GeneralTab
                                settings={settings}
                                setSettings={setSettings}
                                detectedProvider={detectedProvider}
                                speechTiming={speechTiming}
                                onSpeechTimingChange={handleSpeechTimingChange}
                            />
                        )}
                        {activeTab === "llm" && (
                            <LLMTab
                                settings={settings}
                                setSettings={setSettings}
                                detectedProvider={detectedProvider}
                                filteredModels={filteredModels}
                                embeddingModels={embeddingModels}
                            />
                        )}
                        {activeTab === "hardware" && (
                            <HardwareTab
                                settings={settings}
                                displayStatus={displayStatus}
                                hardwareDisplayMode={hardwareDisplayMode}
                                isChangingHardwareMode={isChangingHardwareMode}
                                isRefreshingDisplay={isRefreshingDisplay}
                                isPoweringDisplay={isPoweringDisplay}
                                displayRotation={displayRotation}
                                rotationRebootPending={rotationRebootPending}
                                resolutionConfigurable={resolutionConfigurable}
                                availableResolutions={availableResolutions}
                                currentResolution={currentResolution}
                                resolutionRebootPending={
                                    resolutionRebootPending
                                }
                                audioState={audioState}
                                isChangingAudio={isChangingAudio}
                                isChangingInputDevice={isChangingInputDevice}
                                screensaverSettings={screensaverSettings}
                                loadingStates={loadingStates}
                                displayModes={DISPLAY_MODES}
                                shouldShowDisplayModes={shouldShowDisplayModes}
                                hasOnlySimpleDisplay={hasOnlySimpleDisplay}
                                onHardwareModeChange={handleHardwareModeChange}
                                onRefreshDisplay={handleRefreshDisplay}
                                onPowerOnDisplay={handlePowerOnDisplay}
                                onDisplayModeChange={handleDisplayModeChange}
                                onDisplayEnable={handleDisplayEnable}
                                onResolutionChange={handleResolutionChange}
                                onHdmiRotationChange={handleHdmiRotationChange}
                                onPiscreenRotationChange={handlePiscreenRotationChange}
                                onI2cRotationChange={handleI2cRotationChange}
                                onScreensaverSettingChange={
                                    handleScreensaverSettingChange
                                }
                                onDisplayConnectorChange={
                                    handleDisplayConnectorChange
                                }
                                onAudioDeviceChange={handleAudioDeviceChange}
                                onInputDeviceChange={handleInputDeviceChange}
                                onVolumeChange={handleVolumeChange}
                                onMicGainChange={handleMicGainChange}
                                onVadThresholdChange={handleVadThresholdChange}
                                setSettings={setSettings}
                                showConfirm={showConfirm}
                            />
                        )}
                        {activeTab === "gallery" && showGalleryTab && (
                            <GalleryTab
                                galleryImages={galleryImages}
                                isUploadingImage={isUploadingImage}
                                isDraggingOver={isDraggingOver}
                                onDragOver={handleDragOver}
                                onDragLeave={handleDragLeave}
                                onDrop={handleDrop}
                                onImageUpload={handleImageUpload}
                                onDeleteImage={handleDeleteImage}
                                onSelectImage={setSelectedImage}
                            />
                        )}
                    </div>
                </div>

                {/* Image Viewer Modal */}
                <ImageViewer
                    src={selectedImage?.path || ""}
                    alt={selectedImage?.name || ""}
                    isOpen={!!selectedImage}
                    onClose={() => setSelectedImage(null)}
                />

                <div className="h-20" />
            </div>
        </>
    );
};

export default Settings;
