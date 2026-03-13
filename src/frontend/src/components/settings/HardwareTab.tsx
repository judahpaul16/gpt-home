import React, { useEffect, useState } from "react";
import { Icons, Spinner } from "../Icons";
import { cn } from "../../lib/utils";
import type { DisplayStatus, ScreensaverSettings } from "../../hooks/useApi";
import type { ConfirmConfig } from "../ConfirmModal";

interface AudioState {
    devices: { card: number; name: string; device_name: string; id?: string }[];
    current: string | null;
    volume: number | null;
    inputDevices: { card: number; name: string; device_name: string }[];
    currentInputDevice: string | null;
    micGain: number | null;
    micCard: string | null;
    vadThreshold: number;
}

interface DisplayMode {
    value: string;
    label: string;
    description: string;
}

interface HardwareTabProps {
    settings: any;
    displayStatus: DisplayStatus | null;
    hardwareDisplayMode: "hdmi" | "piscreen" | "unknown" | "conflict";
    isChangingHardwareMode: boolean;
    isRefreshingDisplay: boolean;
    isPoweringDisplay: boolean;
    displayRotation: {
        piscreen_rotation: number;
        hdmi_rotation: number;
        i2c_rotation: number;
    };
    rotationRebootPending: boolean;
    resolutionConfigurable: boolean;
    availableResolutions: string[];
    currentResolution: string;
    resolutionRebootPending: boolean;
    audioState: AudioState;
    isChangingAudio: boolean;
    isChangingInputDevice: boolean;
    screensaverSettings: ScreensaverSettings & {
        is_active: boolean;
        available_styles: string[];
    };
    loadingStates: { audioDevices: boolean; audioInputDevices: boolean };
    displayModes: DisplayMode[];
    shouldShowDisplayModes: (status: DisplayStatus | null) => boolean;
    hasOnlySimpleDisplay: (status: DisplayStatus | null) => boolean;
    onHardwareModeChange: (mode: "hdmi" | "piscreen") => void;
    onRefreshDisplay: () => void;
    onPowerOnDisplay: () => void;
    onDisplayModeChange: (mode: string) => void;
    onDisplayEnable: (displayId: string, enabled: boolean) => void;
    onResolutionChange: (resolution: string) => void;
    onHdmiRotationChange: (rotation: number) => void;
    onPiscreenRotationChange: (rotation: number) => void;
    onI2cRotationChange: (rotation: number) => void;
    onScreensaverSettingChange: (
        key: "enabled" | "timeout" | "style",
        value: boolean | number | string,
    ) => void;
    onDisplayConnectorChange: (connector: string) => void;
    onAudioDeviceChange: (card: number, cardId?: string) => void;
    onInputDeviceChange: (card: number) => void;
    onVolumeChange: (volume: number) => void;
    onMicGainChange: (gain: number) => void;
    onVadThresholdChange: (threshold: number) => void;
    setSettings: (s: any) => void;
    showConfirm: (
        title: string,
        message: string,
        onConfirm: () => void,
        options?: Partial<Pick<ConfirmConfig, "confirmText" | "cancelText" | "variant">>,
    ) => void;
}

const HardwareTab: React.FC<HardwareTabProps> = ({
    settings,
    displayStatus,
    hardwareDisplayMode,
    isChangingHardwareMode,
    isRefreshingDisplay,
    isPoweringDisplay,
    displayRotation,
    rotationRebootPending,
    resolutionConfigurable,
    availableResolutions,
    currentResolution,
    resolutionRebootPending,
    audioState,
    isChangingAudio,
    isChangingInputDevice,
    screensaverSettings,
    loadingStates,
    displayModes,
    shouldShowDisplayModes,
    hasOnlySimpleDisplay,
    onHardwareModeChange,
    onRefreshDisplay,
    onPowerOnDisplay,
    onDisplayModeChange,
    onDisplayEnable,
    onResolutionChange,
    onHdmiRotationChange,
    onPiscreenRotationChange,
    onI2cRotationChange,
    onScreensaverSettingChange,
    onDisplayConnectorChange,
    onAudioDeviceChange,
    onInputDeviceChange,
    onVolumeChange,
    onMicGainChange,
    onVadThresholdChange,
    setSettings,
    showConfirm,
}) => {
    const [rebootNeeded, setRebootNeeded] = useState<{
        needed: boolean;
        reason: string;
    }>({ needed: false, reason: "" });

    useEffect(() => {
        fetch("/api/system/reboot-needed")
            .then((r) => r.json())
            .then((data) => {
                if (data.reboot_needed) {
                    setRebootNeeded({
                        needed: true,
                        reason: data.reason || "Hardware configuration changed",
                    });
                }
            })
            .catch(() => {});
    }, []);

    return (
        <div>
            {rebootNeeded.needed && (
                <div className="mb-4 flex items-center gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3">
                    <Icons.AlertTriangle className="h-4 w-4 text-amber-400 shrink-0" />
                    <span className="text-sm text-amber-300">
                        {rebootNeeded.reason}
                    </span>
                    <button
                        onClick={() =>
                            showConfirm(
                                "Reboot System",
                                "Reboot the system now to apply hardware changes?",
                                () => {
                                    fetch("/reboot", { method: "POST" }).catch(
                                        () => {},
                                    );
                                },
                                { confirmText: "Reboot", variant: "danger" },
                            )
                        }
                        className="ml-auto shrink-0 rounded-md bg-amber-500/20 px-3 py-1 text-xs font-medium text-amber-300 hover:bg-amber-500/30 transition-colors"
                    >
                        Reboot Now
                    </button>
                </div>
            )}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Display Column */}
                <div className="rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
                    <div className="bg-slate-50 dark:bg-slate-800/70 px-4 py-2.5 flex flex-wrap items-center gap-2">
                        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mr-2">
                            Display
                        </h3>
                        <div className="inline-flex rounded-lg bg-slate-200 dark:bg-slate-700 p-0.5">
                            <button
                                onClick={() => onHardwareModeChange("hdmi")}
                                disabled={
                                    isChangingHardwareMode ||
                                    hardwareDisplayMode === "hdmi" ||
                                    hardwareDisplayMode === "unknown"
                                }
                                className={cn(
                                    "px-3 py-1 rounded-md text-xs font-medium transition-all",
                                    hardwareDisplayMode === "hdmi" ||
                                        hardwareDisplayMode === "unknown"
                                        ? "bg-white dark:bg-slate-600 text-slate-900 dark:text-white shadow-sm"
                                        : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200",
                                    isChangingHardwareMode &&
                                        "opacity-50 cursor-not-allowed",
                                )}
                            >
                                {isChangingHardwareMode &&
                                hardwareDisplayMode !== "hdmi" ? (
                                    <Spinner size="sm" />
                                ) : (
                                    "HDMI"
                                )}
                            </button>
                            <button
                                onClick={() => onHardwareModeChange("piscreen")}
                                disabled={
                                    isChangingHardwareMode ||
                                    hardwareDisplayMode === "piscreen"
                                }
                                className={cn(
                                    "px-3 py-1 rounded-md text-xs font-medium transition-all",
                                    hardwareDisplayMode === "piscreen"
                                        ? "bg-white dark:bg-slate-600 text-slate-900 dark:text-white shadow-sm"
                                        : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200",
                                    isChangingHardwareMode &&
                                        "opacity-50 cursor-not-allowed",
                                )}
                            >
                                {isChangingHardwareMode &&
                                hardwareDisplayMode !== "piscreen" ? (
                                    <Spinner size="sm" />
                                ) : (
                                    "PiScreen"
                                )}
                            </button>
                        </div>
                        {hardwareDisplayMode === "conflict" && (
                            <span className="text-xs px-2 py-0.5 rounded-full bg-rose-100 dark:bg-rose-900/30 text-rose-600 dark:text-rose-400">
                                Conflict
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
                        <div className="ml-auto flex items-center gap-1">
                            <button
                                onClick={onRefreshDisplay}
                                disabled={isRefreshingDisplay}
                                className="p-1 rounded-md hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
                                title="Refresh display detection"
                            >
                                {isRefreshingDisplay ? (
                                    <Spinner size="sm" />
                                ) : (
                                    <Icons.Refresh className="w-3.5 h-3.5 text-slate-400" />
                                )}
                            </button>
                            <button
                                onClick={onPowerOnDisplay}
                                disabled={isPoweringDisplay}
                                className="p-1 rounded-md hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
                                title="Power on display"
                            >
                                {isPoweringDisplay ? (
                                    <Spinner size="sm" />
                                ) : (
                                    <Icons.Power className="w-3.5 h-3.5 text-slate-400" />
                                )}
                            </button>
                        </div>
                    </div>

                    {hardwareDisplayMode === "conflict" && (
                        <div className="px-4 py-2 bg-rose-50 dark:bg-rose-900/10 border-t border-rose-200 dark:border-rose-800">
                            <p className="text-xs text-rose-600 dark:text-rose-400">
                                Both HDMI and PiScreen overlays are active.
                                Select one to fix.
                            </p>
                        </div>
                    )}

                    <div className="px-4 py-3">
                        {displayStatus && !displayStatus.available && (
                            <p className="text-sm text-slate-500 dark:text-slate-400">
                                Connect a display (HDMI or PiScreen).
                            </p>
                        )}

                        {displayStatus &&
                            displayStatus.displays.filter(
                                (d) => d.type === "hdmi",
                            ).length > 0 &&
                            (hardwareDisplayMode === "hdmi" ||
                                hardwareDisplayMode === "unknown") && (
                                <div className="mb-3">
                                    <label className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-1 block">
                                        Connector
                                    </label>
                                    <div className="relative">
                                        <select
                                            value={
                                                displayStatus.displays.find(
                                                    (d) => d.type === "hdmi",
                                                )?.connector || ""
                                            }
                                            onChange={(e) =>
                                                onDisplayConnectorChange(
                                                    e.target.value,
                                                )
                                            }
                                            className="select-field text-sm"
                                        >
                                            {displayStatus.displays
                                                .filter(
                                                    (d) => d.type === "hdmi",
                                                )
                                                .map((d) => (
                                                    <option
                                                        key={
                                                            d.connector || d.id
                                                        }
                                                        value={
                                                            d.connector || ""
                                                        }
                                                    >
                                                        {d.connector || "HDMI"}{" "}
                                                        ({d.width}x{d.height})
                                                    </option>
                                                ))}
                                        </select>
                                        <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none w-4 h-4" />
                                    </div>
                                </div>
                            )}

                        {displayStatus &&
                            displayStatus.displays.filter(
                                (d) => d.supports_modes,
                            ).length > 1 && (
                                <div className="mb-3">
                                    <label className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-2 block">
                                        Enabled Displays
                                    </label>
                                    <div className="space-y-2">
                                        {displayStatus.displays
                                            .filter((d) => d.supports_modes)
                                            .map((display) => (
                                                <div
                                                    key={display.id}
                                                    className="flex items-center justify-between p-2 rounded-lg bg-slate-50 dark:bg-slate-800/50"
                                                >
                                                    <div className="flex items-center gap-2">
                                                        <Icons.Monitor className="w-4 h-4 text-slate-400" />
                                                        <span className="text-sm text-slate-700 dark:text-slate-300">
                                                            {display.name}
                                                        </span>
                                                    </div>
                                                    <button
                                                        onClick={() =>
                                                            onDisplayEnable(
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
                                        Disabled displays show TTY console
                                    </p>
                                </div>
                            )}

                        {displayStatus &&
                            displayStatus.available &&
                            shouldShowDisplayModes(displayStatus) && (
                                <div className="flex flex-wrap gap-3">
                                    <div className="flex-1 min-w-[120px]">
                                        <label className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-1 block">
                                            Mode
                                        </label>
                                        <div className="relative">
                                            <select
                                                value={
                                                    settings.display_mode ||
                                                    "smart"
                                                }
                                                onChange={(e) =>
                                                    onDisplayModeChange(
                                                        e.target.value,
                                                    )
                                                }
                                                className="select-field text-sm"
                                            >
                                                {displayModes.map((mode) => (
                                                    <option
                                                        key={mode.value}
                                                        value={mode.value}
                                                    >
                                                        {mode.label}
                                                    </option>
                                                ))}
                                            </select>
                                            <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none w-4 h-4" />
                                        </div>
                                        {settings.display_mode ===
                                            "gallery" && (
                                            <div className="mt-1.5 flex items-center gap-2">
                                                <label className="text-xs text-slate-500 dark:text-slate-400 whitespace-nowrap">
                                                    Interval
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
                                                    className="input-field w-16 text-sm"
                                                />
                                                <span className="text-xs text-slate-400">
                                                    sec
                                                </span>
                                            </div>
                                        )}
                                    </div>

                                    {resolutionConfigurable && (
                                        <div className="flex-1 min-w-[120px]">
                                            <label className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-1 block">
                                                Resolution
                                            </label>
                                            <div className="relative">
                                                <select
                                                    value={currentResolution}
                                                    onChange={(e) =>
                                                        onResolutionChange(
                                                            e.target.value,
                                                        )
                                                    }
                                                    className="select-field text-sm"
                                                >
                                                    {availableResolutions.map(
                                                        (res) => (
                                                            <option
                                                                key={res}
                                                                value={res}
                                                            >
                                                                {res}
                                                            </option>
                                                        ),
                                                    )}
                                                    {currentResolution &&
                                                        !availableResolutions.includes(
                                                            currentResolution,
                                                        ) && (
                                                            <option
                                                                value={
                                                                    currentResolution
                                                                }
                                                            >
                                                                {
                                                                    currentResolution
                                                                }
                                                            </option>
                                                        )}
                                                </select>
                                                <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none w-4 h-4" />
                                            </div>
                                            {resolutionRebootPending && (
                                                <p className="text-xs text-amber-500 mt-1">
                                                    Reboot required
                                                </p>
                                            )}
                                        </div>
                                    )}

                                    {!resolutionConfigurable &&
                                        currentResolution && (
                                            <div className="flex-1 min-w-[120px]">
                                                <label className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-1 block">
                                                    Resolution
                                                </label>
                                                <p className="text-sm text-slate-500 dark:text-slate-400 py-2">
                                                    {currentResolution} (fixed)
                                                </p>
                                            </div>
                                        )}

                                    <div className="w-24">
                                        <label className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-1 block">
                                            Rotation
                                        </label>
                                        <div className="relative">
                                            <select
                                                value={
                                                    hardwareDisplayMode ===
                                                        "hdmi" ||
                                                    hardwareDisplayMode ===
                                                        "unknown"
                                                        ? displayRotation.hdmi_rotation
                                                        : displayRotation.piscreen_rotation
                                                }
                                                onChange={(e) => {
                                                    const val = parseInt(
                                                        e.target.value,
                                                        10,
                                                    );
                                                    if (
                                                        hardwareDisplayMode ===
                                                            "hdmi" ||
                                                        hardwareDisplayMode ===
                                                            "unknown"
                                                    ) {
                                                        onHdmiRotationChange(
                                                            val,
                                                        );
                                                    } else {
                                                        onPiscreenRotationChange(
                                                            val,
                                                        );
                                                    }
                                                }}
                                                className="select-field text-sm"
                                            >
                                                <option value={0}>0°</option>
                                                <option value={90}>90°</option>
                                                <option value={180}>
                                                    180°
                                                </option>
                                                <option value={270}>
                                                    270°
                                                </option>
                                            </select>
                                            <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none w-4 h-4" />
                                        </div>
                                        {rotationRebootPending && (
                                            <p className="text-xs text-amber-500 mt-1">
                                                Reboot required
                                            </p>
                                        )}
                                    </div>
                                </div>
                            )}
                    </div>

                    <div className="border-t border-dashed border-slate-200 dark:border-slate-700 px-4 py-2.5">
                        <div className="flex items-center gap-2 mb-2">
                            <Icons.Cpu className="w-3.5 h-3.5 text-slate-400" />
                            <span className="text-xs font-medium text-slate-600 dark:text-slate-300">
                                SPI Display
                            </span>
                        </div>
                        <div className="grid grid-cols-3 gap-2">
                            <div>
                                <label className="text-[10px] text-slate-400 block">
                                    Width
                                </label>
                                <input
                                    type="number"
                                    value={settings.st7789?.width ?? 240}
                                    onChange={(e) =>
                                        setSettings({
                                            ...settings,
                                            st7789: {
                                                ...(settings.st7789 || {}),
                                                width:
                                                    parseInt(
                                                        e.target.value,
                                                        10,
                                                    ) || 240,
                                            },
                                        })
                                    }
                                    className="input-field w-full text-xs py-1"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-slate-400 block">
                                    Height
                                </label>
                                <input
                                    type="number"
                                    value={settings.st7789?.height ?? 280}
                                    onChange={(e) =>
                                        setSettings({
                                            ...settings,
                                            st7789: {
                                                ...(settings.st7789 || {}),
                                                height:
                                                    parseInt(
                                                        e.target.value,
                                                        10,
                                                    ) || 280,
                                            },
                                        })
                                    }
                                    className="input-field w-full text-xs py-1"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-slate-400 block">
                                    Rotation
                                </label>
                                <div className="relative">
                                    <select
                                        value={settings.st7789?.rotation ?? 0}
                                        onChange={(e) =>
                                            setSettings({
                                                ...settings,
                                                st7789: {
                                                    ...(settings.st7789 || {}),
                                                    rotation: parseInt(
                                                        e.target.value,
                                                        10,
                                                    ),
                                                },
                                            })
                                        }
                                        className="select-field text-xs py-1"
                                    >
                                        <option value={0}>0°</option>
                                        <option value={90}>90°</option>
                                        <option value={180}>180°</option>
                                        <option value={270}>270°</option>
                                    </select>
                                    <Icons.ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none w-3.5 h-3.5" />
                                </div>
                            </div>
                            <div>
                                <label className="text-[10px] text-slate-400 block">
                                    DC Pin
                                </label>
                                <input
                                    type="number"
                                    value={settings.st7789?.gpio_dc ?? 27}
                                    onChange={(e) =>
                                        setSettings({
                                            ...settings,
                                            st7789: {
                                                ...(settings.st7789 || {}),
                                                gpio_dc: parseInt(
                                                    e.target.value,
                                                    10,
                                                ),
                                            },
                                        })
                                    }
                                    className="input-field w-full text-xs py-1"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-slate-400 block">
                                    RST Pin
                                </label>
                                <input
                                    type="number"
                                    value={settings.st7789?.gpio_rst ?? 4}
                                    onChange={(e) =>
                                        setSettings({
                                            ...settings,
                                            st7789: {
                                                ...(settings.st7789 || {}),
                                                gpio_rst: parseInt(
                                                    e.target.value,
                                                    10,
                                                ),
                                            },
                                        })
                                    }
                                    className="input-field w-full text-xs py-1"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-slate-400 block">
                                    BL Pin
                                </label>
                                <input
                                    type="number"
                                    value={settings.st7789?.gpio_bl ?? 22}
                                    onChange={(e) =>
                                        setSettings({
                                            ...settings,
                                            st7789: {
                                                ...(settings.st7789 || {}),
                                                gpio_bl: parseInt(
                                                    e.target.value,
                                                    10,
                                                ),
                                            },
                                        })
                                    }
                                    className="input-field w-full text-xs py-1"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-slate-400 block">
                                    SPI Bus
                                </label>
                                <input
                                    type="number"
                                    min="0"
                                    max="6"
                                    value={settings.st7789?.spi_bus ?? 0}
                                    onChange={(e) =>
                                        setSettings({
                                            ...settings,
                                            st7789: {
                                                ...(settings.st7789 || {}),
                                                spi_bus: parseInt(
                                                    e.target.value,
                                                    10,
                                                ),
                                            },
                                        })
                                    }
                                    className="input-field w-full text-xs py-1"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-slate-400 block">
                                    SPI CS
                                </label>
                                <input
                                    type="number"
                                    min="0"
                                    max="2"
                                    value={settings.st7789?.spi_cs ?? 0}
                                    onChange={(e) =>
                                        setSettings({
                                            ...settings,
                                            st7789: {
                                                ...(settings.st7789 || {}),
                                                spi_cs: parseInt(
                                                    e.target.value,
                                                    10,
                                                ),
                                            },
                                        })
                                    }
                                    className="input-field w-full text-xs py-1"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-slate-400 block">
                                    Speed (Hz)
                                </label>
                                <input
                                    type="number"
                                    value={
                                        settings.st7789?.spi_speed_hz ??
                                        62500000
                                    }
                                    onChange={(e) =>
                                        setSettings({
                                            ...settings,
                                            st7789: {
                                                ...(settings.st7789 || {}),
                                                spi_speed_hz: parseInt(
                                                    e.target.value,
                                                    10,
                                                ),
                                            },
                                        })
                                    }
                                    className="input-field w-full text-xs py-1"
                                />
                            </div>
                        </div>
                    </div>

                    <div className="border-t border-dashed border-slate-200 dark:border-slate-700 px-4 py-2.5 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <Icons.Cpu className="w-3.5 h-3.5 text-slate-400" />
                            <span className="text-xs font-medium text-slate-600 dark:text-slate-300">
                                I2C Display
                            </span>
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="text-[10px] text-slate-400 dark:text-slate-500">
                                Rotation
                            </span>
                            <div className="relative w-20">
                                <select
                                    value={displayRotation.i2c_rotation}
                                    onChange={(e) =>
                                        onI2cRotationChange(
                                            parseInt(e.target.value, 10),
                                        )
                                    }
                                    className="select-field text-xs py-1"
                                >
                                    <option value={0}>0°</option>
                                    <option value={1}>90°</option>
                                    <option value={2}>180°</option>
                                    <option value={3}>270°</option>
                                </select>
                                <Icons.ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none w-3.5 h-3.5" />
                            </div>
                        </div>
                    </div>

                    {/* Screensaver */}
                    <div className="border-t border-dashed border-slate-200 dark:border-slate-700 px-4 py-3 space-y-3">
                        <div className="flex items-center gap-2">
                            <Icons.Moon className="w-3.5 h-3.5 text-slate-400" />
                            <span className="text-xs font-medium text-slate-600 dark:text-slate-300">
                                Screensaver
                            </span>
                            <button
                                onClick={() =>
                                    onScreensaverSettingChange(
                                        "enabled",
                                        !screensaverSettings.enabled,
                                    )
                                }
                                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                                    screensaverSettings.enabled
                                        ? "bg-primary-500"
                                        : "bg-slate-300 dark:bg-slate-600"
                                }`}
                            >
                                <span
                                    className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                                        screensaverSettings.enabled
                                            ? "translate-x-4"
                                            : "translate-x-1"
                                    }`}
                                />
                            </button>
                        </div>
                        <div className="flex flex-wrap gap-3">
                            <div className="flex-1 min-w-[120px]">
                                <label className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-1 block">
                                    Style
                                </label>
                                <div className="relative">
                                    <select
                                        value={screensaverSettings.style}
                                        onChange={(e) =>
                                            onScreensaverSettingChange(
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
                            </div>
                            <div className="w-24">
                                <label className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-1 block">
                                    Timeout
                                </label>
                                <input
                                    type="number"
                                    min="1"
                                    max="3600"
                                    step="1"
                                    value={screensaverSettings.timeout}
                                    onChange={(e) =>
                                        onScreensaverSettingChange(
                                            "timeout",
                                            parseInt(e.target.value, 10) || 300,
                                        )
                                    }
                                    className="input-field w-full text-sm"
                                />
                                <p className="text-xs text-slate-400 mt-1">
                                    {Math.floor(
                                        screensaverSettings.timeout / 60,
                                    )}{" "}
                                    min{" "}
                                    {screensaverSettings.timeout % 60 > 0
                                        ? `${screensaverSettings.timeout % 60} sec`
                                        : ""}
                                </p>
                            </div>
                        </div>
                        {screensaverSettings.style === "bounce" && (
                            <div>
                                <label className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-1 block">
                                    Text
                                </label>
                                <input
                                    type="text"
                                    value={
                                        settings.screensaver_bounce_text ??
                                        "GPT Home"
                                    }
                                    onChange={(e) =>
                                        setSettings({
                                            ...settings,
                                            screensaver_bounce_text:
                                                e.target.value,
                                        })
                                    }
                                    className="input-field w-full text-sm"
                                    placeholder="GPT Home"
                                />
                            </div>
                        )}
                    </div>
                </div>

                {/* Audio Column */}
                <div className="rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
                    <div className="bg-slate-50 dark:bg-slate-800/70 px-4 py-2.5">
                        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                            Audio
                        </h3>
                    </div>
                    <div className="px-4 py-3 space-y-3">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-1">
                            Output
                        </p>
                        <div className="flex flex-wrap items-center gap-2">
                            <Icons.Volume2 className="w-4 h-4 text-slate-500 flex-shrink-0" />
                            {loadingStates.audioDevices ? (
                                <Spinner size="sm" />
                            ) : audioState.devices.length > 0 ? (
                                <div className="relative flex-1">
                                    <select
                                        value={
                                            audioState.current !== null
                                                ? String(audioState.current)
                                                : ""
                                        }
                                        onChange={(e) => {
                                            const selectedCard = parseInt(
                                                e.target.value,
                                                10,
                                            );
                                            const selectedDevice =
                                                audioState.devices.find(
                                                    (d) =>
                                                        d.card === selectedCard,
                                                );
                                            onAudioDeviceChange(
                                                selectedCard,
                                                selectedDevice?.id,
                                            );
                                        }}
                                        disabled={isChangingAudio}
                                        className="select-field text-sm"
                                    >
                                        {audioState.devices.map((device) => (
                                            <option
                                                key={device.card}
                                                value={String(device.card)}
                                            >
                                                {device.name} (
                                                {device.device_name})
                                            </option>
                                        ))}
                                    </select>
                                    <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none w-4 h-4" />
                                </div>
                            ) : (
                                <span className="text-sm text-slate-500 dark:text-slate-400">
                                    No output devices
                                </span>
                            )}
                            {audioState.current !== null && (
                                <span className="text-xs text-slate-400">
                                    Card {audioState.current}
                                </span>
                            )}
                        </div>

                        {audioState.volume !== null && (
                            <div>
                                <div className="flex items-center justify-between mb-1">
                                    <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
                                        Volume
                                    </span>
                                    <span className="text-xs font-mono text-slate-500 dark:text-slate-400">
                                        {audioState.volume}%
                                    </span>
                                </div>
                                <input
                                    type="range"
                                    min="0"
                                    max="100"
                                    value={audioState.volume}
                                    onChange={(e) =>
                                        onVolumeChange(
                                            parseInt(e.target.value, 10),
                                        )
                                    }
                                    className="w-full h-2 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-cyan-500"
                                />
                            </div>
                        )}

                        {/* Divider */}
                        <div className="border-t border-dashed border-slate-200 dark:border-slate-700" />

                        <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-1">
                            Input
                        </p>
                        <div className="flex flex-wrap items-center gap-2">
                            <Icons.Mic className="w-4 h-4 text-slate-500 flex-shrink-0" />
                            {loadingStates.audioInputDevices ? (
                                <Spinner size="sm" />
                            ) : audioState.inputDevices.length > 0 ? (
                                <div className="relative flex-1">
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
                                            onInputDeviceChange(
                                                parseInt(e.target.value, 10),
                                            )
                                        }
                                        disabled={isChangingInputDevice}
                                        className="select-field text-sm"
                                    >
                                        {audioState.inputDevices.map(
                                            (device) => (
                                                <option
                                                    key={device.card}
                                                    value={String(device.card)}
                                                >
                                                    {device.name} (
                                                    {device.device_name})
                                                </option>
                                            ),
                                        )}
                                    </select>
                                    <Icons.ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none w-4 h-4" />
                                </div>
                            ) : null}
                            {audioState.micCard && (
                                <span className="text-xs text-slate-400">
                                    Card {audioState.micCard}
                                </span>
                            )}
                        </div>

                        {audioState.micGain !== null && (
                            <div>
                                <div className="flex items-center justify-between mb-1">
                                    <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
                                        Gain
                                    </span>
                                    <span className="text-xs font-mono text-slate-500 dark:text-slate-400">
                                        {audioState.micGain}%
                                    </span>
                                </div>
                                <input
                                    type="range"
                                    min="0"
                                    max="100"
                                    value={audioState.micGain}
                                    onChange={(e) =>
                                        onMicGainChange(
                                            parseInt(e.target.value, 10),
                                        )
                                    }
                                    className="w-full h-2 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-emerald-500"
                                />
                            </div>
                        )}

                        <div>
                            <div className="flex items-center justify-between mb-1">
                                <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
                                    VAD (Voice Activity Detection)
                                </span>
                                <span className="text-xs font-mono text-slate-500 dark:text-slate-400">
                                    {audioState.vadThreshold} dB
                                </span>
                            </div>
                            <input
                                type="range"
                                min="-80"
                                max="0"
                                value={audioState.vadThreshold}
                                onChange={(e) =>
                                    onVadThresholdChange(
                                        parseInt(e.target.value, 10),
                                    )
                                }
                                className="w-full h-2 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-amber-500"
                            />
                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                                Lower = more sensitive, Higher = rejects noise
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default HardwareTab;
