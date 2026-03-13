import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";

// ============================================================================
// Types
// ============================================================================

export interface DisplayInfo {
    id: string;
    type: string;
    name: string;
    width: number;
    height: number;
    driver: string | null;
    device_path: string | null;
    connector?: string | null;
    supports_modes?: boolean;
    enabled?: boolean;
}

export interface DisplayStatus {
    available: boolean;
    displays: DisplayInfo[];
    active: boolean;
    current_mode: string | null;
    current_display_type: string | null;
    saved_display_type: string | null;
    has_full_display?: boolean;
    has_simple_display?: boolean;
    supports_modes?: boolean;
    note?: string | null;
}

export interface GalleryImage {
    name: string;
    path: string;
    size: number;
}

export interface AudioDevice {
    card: number;
    device: number;
    id: string;
    name: string;
    device_name: string;
    alsa_name: string;
}

export interface AudioDevicesResponse {
    devices: AudioDevice[];
    current: string | null;
}

export interface SpeechTiming {
    pauseThreshold: number;
    phraseTimeLimit: number;
    nonSpeakingDuration: number;
}

export interface ScreensaverSettings {
    enabled: boolean;
    timeout: number;
    style: string;
    is_active: boolean;
    available_styles: string[];
}

export interface ServiceStatuses {
    [key: string]: boolean;
}

// ============================================================================
// Query Keys - Centralized for easy invalidation
// ============================================================================

export const queryKeys = {
    settings: ["settings"] as const,
    models: ["models"] as const,
    displayStatus: ["display", "status"] as const,
    galleryImages: ["gallery", "images"] as const,
    audioDevices: ["audio", "devices"] as const,
    audioInputDevices: ["audio", "inputDevices"] as const,
    audioVolume: ["audio", "volume"] as const,
    micGain: ["audio", "micGain"] as const,
    vadThreshold: ["audio", "vadThreshold"] as const,
    speechTiming: ["audio", "speechTiming"] as const,
    screensaver: ["display", "screensaver"] as const,
    serviceStatuses: ["services", "statuses"] as const,
    systemStats: ["system", "stats"] as const,
    systemInfo: ["system", "info"] as const,
    processes: ["system", "processes"] as const,
    logs: ["logs"] as const,
};

// ============================================================================
// Default stale times - How long data is considered "fresh"
// ============================================================================

const STALE_TIMES = {
    // Settings rarely change - 5 minutes
    settings: 5 * 60 * 1000,
    // Models list is static - 10 minutes
    models: 10 * 60 * 1000,
    // Display status might change - 30 seconds
    displayStatus: 30 * 1000,
    // Gallery images - 1 minute
    galleryImages: 60 * 1000,
    // Audio devices rarely change - 2 minutes
    audioDevices: 2 * 60 * 1000,
    audioInputDevices: 2 * 60 * 1000,
    // Volume/gain can change - 30 seconds
    audioVolume: 30 * 1000,
    // Service statuses - 1 minute
    serviceStatuses: 60 * 1000,
    // Screensaver - 30 seconds
    screensaver: 30 * 1000,
    // Speech timing - 5 minutes
    speechTiming: 5 * 60 * 1000,
};

// ============================================================================
// API Fetcher Functions
// ============================================================================

const fetchSettings = async () => {
    const response = await axios.post("/api/settings", { action: "read" });
    return response.data;
};

const fetchModels = async () => {
    const response = await axios.post("/availableModels");
    return response.data.models || [];
};

const fetchDisplayStatus = async (): Promise<DisplayStatus | null> => {
    try {
        const response = await axios.get("/api/display/status");
        return response.data;
    } catch {
        return null;
    }
};

const fetchGalleryImages = async (): Promise<GalleryImage[]> => {
    try {
        const response = await axios.get("/api/gallery/images");
        return response.data.images || [];
    } catch {
        return [];
    }
};

const fetchAudioDevices = async (): Promise<AudioDevicesResponse> => {
    try {
        const response = await axios.get("/api/audio/devices");
        return {
            devices: response.data.devices || [],
            current: response.data.current || null,
        };
    } catch {
        return { devices: [], current: null };
    }
};

const fetchAudioInputDevices = async (): Promise<AudioDevicesResponse> => {
    try {
        const response = await axios.get("/api/audio/input-devices");
        return {
            devices: response.data.devices || [],
            current: response.data.current || null,
        };
    } catch {
        return { devices: [], current: null };
    }
};

const fetchAudioVolume = async (): Promise<number | null> => {
    try {
        const response = await axios.get("/api/audio/volume");
        return response.data.volume ?? null;
    } catch {
        return null;
    }
};

const fetchMicGain = async (): Promise<{
    gain: number | null;
    card: string | null;
}> => {
    try {
        const response = await axios.get("/api/audio/mic-gain");
        return {
            gain: response.data.gain ?? null,
            card: response.data.card ?? null,
        };
    } catch {
        return { gain: null, card: null };
    }
};

const fetchVadThreshold = async (): Promise<number> => {
    try {
        const response = await axios.get("/api/audio/vad-threshold");
        return response.data.threshold ?? -50;
    } catch {
        return -50;
    }
};

const fetchSpeechTiming = async (): Promise<SpeechTiming> => {
    try {
        const response = await axios.get("/api/audio/speech-timing");
        return {
            pauseThreshold: response.data.pauseThreshold ?? 1.2,
            phraseTimeLimit: response.data.phraseTimeLimit ?? 30,
            nonSpeakingDuration: response.data.nonSpeakingDuration ?? 0.8,
        };
    } catch {
        return {
            pauseThreshold: 1.2,
            phraseTimeLimit: 30,
            nonSpeakingDuration: 0.8,
        };
    }
};

const fetchScreensaver = async (): Promise<ScreensaverSettings | null> => {
    try {
        const response = await axios.get("/api/display/screensaver/status");
        return {
            enabled: response.data.enabled ?? true,
            timeout: response.data.timeout ?? 300,
            style: response.data.style ?? "starfield",
            is_active: response.data.is_active ?? false,
            available_styles: response.data.available_styles ?? [
                "starfield",
                "matrix",
                "bounce",
                "fade",
            ],
        };
    } catch {
        return null;
    }
};

const fetchServiceStatuses = async (): Promise<ServiceStatuses> => {
    try {
        const response = await axios.post("/get-service-statuses");
        return response.data.statuses || {};
    } catch {
        return {};
    }
};

// ============================================================================
// Query Hooks
// ============================================================================

export function useSettings() {
    return useQuery({
        queryKey: queryKeys.settings,
        queryFn: fetchSettings,
        staleTime: STALE_TIMES.settings,
    });
}

export function useModels() {
    return useQuery({
        queryKey: queryKeys.models,
        queryFn: fetchModels,
        staleTime: STALE_TIMES.models,
    });
}

export function useDisplayStatus() {
    return useQuery({
        queryKey: queryKeys.displayStatus,
        queryFn: fetchDisplayStatus,
        staleTime: STALE_TIMES.displayStatus,
    });
}

export function useGalleryImages() {
    return useQuery({
        queryKey: queryKeys.galleryImages,
        queryFn: fetchGalleryImages,
        staleTime: STALE_TIMES.galleryImages,
    });
}

export function useAudioDevices() {
    return useQuery({
        queryKey: queryKeys.audioDevices,
        queryFn: fetchAudioDevices,
        staleTime: STALE_TIMES.audioDevices,
    });
}

export function useAudioInputDevices() {
    return useQuery({
        queryKey: queryKeys.audioInputDevices,
        queryFn: fetchAudioInputDevices,
        staleTime: STALE_TIMES.audioInputDevices,
    });
}

export function useAudioVolume() {
    return useQuery({
        queryKey: queryKeys.audioVolume,
        queryFn: fetchAudioVolume,
        staleTime: STALE_TIMES.audioVolume,
    });
}

export function useMicGain() {
    return useQuery({
        queryKey: queryKeys.micGain,
        queryFn: fetchMicGain,
        staleTime: STALE_TIMES.audioVolume,
    });
}

export function useVadThreshold() {
    return useQuery({
        queryKey: queryKeys.vadThreshold,
        queryFn: fetchVadThreshold,
        staleTime: STALE_TIMES.speechTiming,
    });
}

export function useSpeechTiming() {
    return useQuery({
        queryKey: queryKeys.speechTiming,
        queryFn: fetchSpeechTiming,
        staleTime: STALE_TIMES.speechTiming,
    });
}

export function useScreensaver() {
    return useQuery({
        queryKey: queryKeys.screensaver,
        queryFn: fetchScreensaver,
        staleTime: STALE_TIMES.screensaver,
    });
}

export function useServiceStatuses() {
    return useQuery({
        queryKey: queryKeys.serviceStatuses,
        queryFn: fetchServiceStatuses,
        staleTime: STALE_TIMES.serviceStatuses,
    });
}

// ============================================================================
// Combined hook for Settings page - fetches all data in parallel
// ============================================================================

export function useSettingsPageData() {
    const settings = useSettings();
    const models = useModels();
    const displayStatus = useDisplayStatus();
    const galleryImages = useGalleryImages();
    const audioDevices = useAudioDevices();
    const audioInputDevices = useAudioInputDevices();
    const audioVolume = useAudioVolume();
    const micGain = useMicGain();
    const vadThreshold = useVadThreshold();
    const speechTiming = useSpeechTiming();
    const screensaver = useScreensaver();

    // Critical data required for initial render (fast queries)
    const isCriticalLoading = settings.isLoading || models.isLoading;

    // All data loading (for backwards compatibility)
    const isLoading =
        settings.isLoading ||
        models.isLoading ||
        displayStatus.isLoading ||
        galleryImages.isLoading ||
        audioDevices.isLoading ||
        audioInputDevices.isLoading ||
        audioVolume.isLoading ||
        micGain.isLoading ||
        vadThreshold.isLoading ||
        speechTiming.isLoading ||
        screensaver.isLoading;

    const isError = settings.isError || models.isError;

    return {
        settings: settings.data,
        models: models.data,
        displayStatus: displayStatus.data,
        galleryImages: galleryImages.data,
        audioDevices: audioDevices.data,
        audioInputDevices: audioInputDevices.data,
        audioVolume: audioVolume.data,
        micGain: micGain.data,
        vadThreshold: vadThreshold.data,
        speechTiming: speechTiming.data,
        screensaver: screensaver.data,
        isLoading,
        isCriticalLoading,
        isError,
        // Expose individual loading states for progressive rendering
        loadingStates: {
            settings: settings.isLoading,
            models: models.isLoading,
            displayStatus: displayStatus.isLoading,
            galleryImages: galleryImages.isLoading,
            audioDevices: audioDevices.isLoading,
            audioInputDevices: audioInputDevices.isLoading,
            audioVolume: audioVolume.isLoading,
            micGain: micGain.isLoading,
            vadThreshold: vadThreshold.isLoading,
            speechTiming: speechTiming.isLoading,
            screensaver: screensaver.isLoading,
        },
        // Expose refetch functions for manual refresh
        refetch: {
            settings: settings.refetch,
            models: models.refetch,
            displayStatus: displayStatus.refetch,
            galleryImages: galleryImages.refetch,
            audioDevices: audioDevices.refetch,
            audioInputDevices: audioInputDevices.refetch,
            audioVolume: audioVolume.refetch,
            micGain: micGain.refetch,
            vadThreshold: vadThreshold.refetch,
            speechTiming: speechTiming.refetch,
            screensaver: screensaver.refetch,
        },
    };
}

// ============================================================================
// Mutation Hooks
// ============================================================================

export function useSaveSettings() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (data: any) => {
            const response = await axios.post("/api/settings", {
                action: "update",
                data,
            });
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: queryKeys.settings });
        },
    });
}

export function useSetDisplayMode() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (mode: string) => {
            const response = await axios.post("/api/display/mode", { mode });
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({
                queryKey: queryKeys.displayStatus,
            });
        },
    });
}

export function useSetScreensaver() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (settings: {
            enabled?: boolean;
            timeout?: number;
            style?: string;
        }) => {
            const response = await axios.post(
                "/api/display/screensaver/configure",
                settings,
            );
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: queryKeys.screensaver });
        },
    });
}

export function useSetAudioDevice() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (deviceId: string) => {
            const response = await axios.post("/api/audio/device", {
                device_id: deviceId,
                auto_restart: true,
            });
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: queryKeys.audioDevices });
            queryClient.invalidateQueries({ queryKey: queryKeys.audioVolume });
        },
    });
}

export function useSetVolume() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (volume: number) => {
            const response = await axios.post("/api/audio/volume", { volume });
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: queryKeys.audioVolume });
        },
    });
}

export function useSetMicGain() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (gain: number) => {
            const response = await axios.post("/api/audio/mic-gain", { gain });
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: queryKeys.micGain });
        },
    });
}

export function useSetVadThreshold() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (threshold: number) => {
            const response = await axios.post("/api/audio/vad-threshold", {
                threshold,
            });
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: queryKeys.vadThreshold });
        },
    });
}

export function useSetSpeechTiming() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (timing: SpeechTiming) => {
            const response = await axios.post(
                "/api/audio/speech-timing",
                timing,
            );
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: queryKeys.speechTiming });
        },
    });
}

export function useUploadGalleryImage() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (formData: FormData) => {
            const response = await axios.post("/api/gallery/upload", formData, {
                headers: { "Content-Type": "multipart/form-data" },
            });
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({
                queryKey: queryKeys.galleryImages,
            });
        },
    });
}

export function useDeleteGalleryImage() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (filename: string) => {
            const response = await axios.delete(
                `/api/gallery/images/${filename}`,
            );
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({
                queryKey: queryKeys.galleryImages,
            });
        },
    });
}

export function useRefreshDisplay() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async () => {
            const response = await axios.post("/api/display/refresh");
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({
                queryKey: queryKeys.displayStatus,
            });
        },
    });
}

export function usePowerOnDisplay() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async () => {
            const response = await axios.post("/api/display/power-on");
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({
                queryKey: queryKeys.displayStatus,
            });
        },
    });
}

// ============================================================================
// Utility hook for invalidating queries
// ============================================================================

export function useInvalidateQueries() {
    const queryClient = useQueryClient();

    return {
        invalidateSettings: () =>
            queryClient.invalidateQueries({ queryKey: queryKeys.settings }),
        invalidateDisplayStatus: () =>
            queryClient.invalidateQueries({
                queryKey: queryKeys.displayStatus,
            }),
        invalidateGalleryImages: () =>
            queryClient.invalidateQueries({
                queryKey: queryKeys.galleryImages,
            }),
        invalidateAudio: () => {
            queryClient.invalidateQueries({ queryKey: queryKeys.audioDevices });
            queryClient.invalidateQueries({ queryKey: queryKeys.audioVolume });
            queryClient.invalidateQueries({ queryKey: queryKeys.micGain });
        },
        invalidateAll: () => queryClient.invalidateQueries(),
    };
}
