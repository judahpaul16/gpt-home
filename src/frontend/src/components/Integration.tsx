import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import axios from "axios";
import { useQueryClient } from "@tanstack/react-query";
import { Icons, Spinner } from "./Icons";
import { cn } from "../lib/utils";
import ConfirmModal, { useConfirm } from "./ConfirmModal";
import { queryKeys } from "../hooks/useApi";

interface SpotifyAuthStatus {
    has_credentials: boolean;
    needs_auth?: boolean;
}

interface IntegrationProps {
    name: string;
    status: boolean;
    usage: string[];
    requiredFields: { [key: string]: string[] };
    toggleStatus: (name: string) => void;
    setShowOverlay: (visible: boolean) => void;
    spotifyAuthStatus?: SpotifyAuthStatus | null;
    onSpotifyConnected?: () => void;
}

const Integration: React.FC<IntegrationProps> = ({
    name,
    status,
    requiredFields,
    toggleStatus,
    setShowOverlay,
    spotifyAuthStatus,
    onSpotifyConnected,
}) => {
    const queryClient = useQueryClient();
    const [showForm, setShowForm] = useState(false);
    const [formData, setFormData] = useState({} as { [key: string]: string });
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const [authLoading, setAuthLoading] = useState(false);
    const [authPolling, setAuthPolling] = useState(false);
    const { confirmConfig, showConfirm, closeConfirm } = useConfirm();

    const handleSpotifyAuthorize = async () => {
        setAuthLoading(true);
        setError("");
        try {
            const response = await axios.get("/api/spotify/auth-url");
            if (response.data.auth_url) {
                // Open auth URL in new window
                const authWindow = window.open(
                    response.data.auth_url,
                    "spotify-auth",
                    "width=500,height=700,menubar=no,toolbar=no",
                );

                // Start polling for authorization completion
                setAuthPolling(true);
                const pollInterval = setInterval(async () => {
                    try {
                        const pollResponse = await axios.get(
                            "/api/spotify/auth-poll",
                        );
                        if (pollResponse.data.status === "authorized") {
                            clearInterval(pollInterval);
                            setAuthPolling(false);
                            setAuthLoading(false);
                            // Close the auth window if still open
                            if (authWindow && !authWindow.closed) {
                                authWindow.close();
                            }
                            // Refresh the page to update status
                            window.location.reload();
                        } else if (pollResponse.data.status === "error") {
                            clearInterval(pollInterval);
                            setAuthPolling(false);
                            setAuthLoading(false);
                            setError(
                                pollResponse.data.error ||
                                    "Authorization failed",
                            );
                            if (authWindow && !authWindow.closed) {
                                authWindow.close();
                            }
                        }
                    } catch {
                        // Continue polling on network errors
                    }
                }, 2000);

                // Stop polling after 5 minutes
                setTimeout(
                    () => {
                        clearInterval(pollInterval);
                        if (authPolling) {
                            setAuthPolling(false);
                            setAuthLoading(false);
                            setError(
                                "Authorization timed out. Please try again.",
                            );
                        }
                    },
                    5 * 60 * 1000,
                );
            } else {
                setError(
                    response.data.error || "Failed to get authorization URL",
                );
                setAuthLoading(false);
            }
        } catch (err: any) {
            setError(
                err.response?.data?.error ||
                    err.message ||
                    "Failed to get authorization URL",
            );
            setAuthLoading(false);
        }
    };

    const apiRefs: { [key: string]: string[] } = {
        Spotify: ["https://developer.spotify.com/documentation/web-api/"],
        OpenWeather: ["https://openweathermap.org/api/one-call-3"],
        PhilipsHue: [
            "https://developers.meethue.com/develop/get-started-2/",
            "https://github.com/studioimaginaire/phue",
        ],
        CalDAV: [
            "https://en.wikipedia.org/wiki/CalDAV",
            "https://caldav.readthedocs.io/stable/",
        ],
    };

    const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        const { name, value } = event.target;
        setFormData({ ...formData, [name]: value });
        setError("");
    };

    const connectService = async () => {
        setLoading(true);
        for (const field of requiredFields[name]) {
            if (!formData[field as keyof typeof formData]) {
                setError(`Please enter ${field.toLowerCase()}`);
                setLoading(false);
                return;
            }
        }

        let fields: { [key: string]: string } = {};
        for (const field of requiredFields[name]) {
            fields[field] = formData[field as keyof typeof formData];
        }

        axios
            .post("/connect-service", { name, fields })
            .then(async (response) => {
                if (response.data.redirect_url) {
                    window.location.replace(response.data.redirect_url);
                } else if (response.data.success) {
                    // Invalidate the service statuses cache to force refetch
                    queryClient.invalidateQueries({
                        queryKey: queryKeys.serviceStatuses,
                    });
                    if (!status) toggleStatus(name);
                    setShowOverlay(false);
                    setShowForm(false);
                    if (name !== "PhilipsHue") setFormData({});

                    // For Spotify, immediately trigger OAuth flow after credentials are saved
                    if (name === "Spotify") {
                        // Notify parent to refresh status
                        if (onSpotifyConnected) {
                            onSpotifyConnected();
                        }
                        // Automatically start OAuth authorization flow
                        setLoading(false);
                        await handleSpotifyAuthorize();
                    }
                } else {
                    setError(
                        response.data.message ||
                            response.data.error ||
                            "Connection failed",
                    );
                    setShowOverlay(false);
                }
                setLoading(false);
            })
            .catch((error) => {
                const errorMsg =
                    error.response?.data?.message ||
                    error.response?.data?.error ||
                    error.message ||
                    "Connection failed";
                setError(errorMsg);
                setShowOverlay(false);
                setLoading(false);
            });
    };

    const disconnectService = async () => {
        showConfirm(
            "Disconnect Service",
            `Are you sure you want to disconnect from ${name}?`,
            () => {
                axios
                    .post("/disconnect-service", { name })
                    .then((response) => {
                        if (response.data.success) {
                            // Invalidate the service statuses cache to force refetch
                            queryClient.invalidateQueries({
                                queryKey: queryKeys.serviceStatuses,
                            });
                            toggleStatus(name);
                            setShowOverlay(false);
                            setShowForm(false);
                            setFormData({});
                            // For Spotify, refresh auth status to clear any stale state
                            if (name === "Spotify" && onSpotifyConnected) {
                                onSpotifyConnected();
                            }
                        } else {
                            setError(
                                `Error disconnecting: ${response.data.error}`,
                            );
                        }
                    })
                    .catch((error) => {
                        setError(`Error disconnecting: ${error.message}`);
                    });
            },
            { confirmText: "Disconnect", variant: "danger" },
        );
    };

    const handlePaste = (event: React.ClipboardEvent<HTMLInputElement>) => {
        event.preventDefault();
        const text = event.clipboardData
            .getData("text/plain")
            .replace(/\s+/g, "");
        const { name } = event.currentTarget;
        setFormData({ ...formData, [name]: text });
    };

    const disallowSpace = (event: React.KeyboardEvent<HTMLInputElement>) => {
        if (event.key === " ") event.preventDefault();
    };

    return (
        <>
            <ConfirmModal config={confirmConfig} onClose={closeConfirm} />
            {/* Action buttons */}
            <div className="flex flex-wrap gap-2">
                {status && (
                    <button
                        onClick={() => setShowForm(true)}
                        className="btn-secondary flex items-center gap-2 text-sm"
                    >
                        <Icons.Edit className="w-4 h-4" />
                        Edit
                    </button>
                )}
                {/* Spotify: Show Authorize button when connected but needs OAuth */}
                {name === "Spotify" &&
                    status &&
                    spotifyAuthStatus &&
                    spotifyAuthStatus.needs_auth && (
                        <button
                            onClick={handleSpotifyAuthorize}
                            disabled={authLoading}
                            className="btn-primary flex items-center gap-2 text-sm"
                        >
                            {authLoading ? (
                                <>
                                    <Spinner size="sm" />
                                    {authPolling
                                        ? "Waiting for authorization..."
                                        : "Loading..."}
                                </>
                            ) : (
                                <>
                                    <Icons.Music className="w-4 h-4" />
                                    Authorize
                                </>
                            )}
                        </button>
                    )}
                <button
                    onClick={
                        status ? disconnectService : () => setShowForm(true)
                    }
                    className={cn(
                        "flex items-center gap-2 text-sm",
                        status ? "btn-danger" : "btn-success",
                    )}
                >
                    {status ? (
                        <>
                            <Icons.Unlink className="w-4 h-4" />
                            Disconnect
                        </>
                    ) : (
                        <>
                            <Icons.Link className="w-4 h-4" />
                            Connect
                        </>
                    )}
                </button>
            </div>

            {/* Modal */}
            <AnimatePresence>
                {showForm && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
                        onClick={(e) =>
                            e.target === e.currentTarget && setShowForm(false)
                        }
                    >
                        <motion.div
                            initial={{ scale: 0.95, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.95, opacity: 0 }}
                            className="w-full max-w-lg glass-card overflow-hidden"
                        >
                            {/* Modal header */}
                            <div className="flex items-center justify-between p-6 border-b border-slate-200 dark:border-dark-700">
                                <div>
                                    <h3 className="text-xl font-semibold text-slate-900 dark:text-white">
                                        Configure {name}
                                    </h3>
                                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                                        Enter your credentials to connect
                                    </p>
                                </div>
                                <button
                                    onClick={() => setShowForm(false)}
                                    className="btn-icon"
                                >
                                    <Icons.X />
                                </button>
                            </div>

                            {/* Modal body */}
                            <div className="p-6 space-y-4 max-h-[60vh] overflow-y-auto">
                                {/* API References */}
                                {apiRefs[name]?.length > 0 && (
                                    <div className="p-4 rounded-xl bg-slate-100 dark:bg-dark-700/50">
                                        <h4 className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                                            API Documentation
                                        </h4>
                                        <div className="space-y-1">
                                            {apiRefs[name].map((link) => (
                                                <a
                                                    key={link}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    href={link}
                                                    className="flex items-center gap-2 text-sm text-primary-600 dark:text-primary-400 hover:underline"
                                                >
                                                    <Icons.ExternalLink className="w-3.5 h-3.5" />
                                                    <span className="truncate">
                                                        {link}
                                                    </span>
                                                </a>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {/* Service-specific notes */}
                                {name === "Spotify" && (
                                    <div className="space-y-4">
                                        <div className="p-4 rounded-xl bg-emerald-100 dark:bg-emerald-900/20 text-emerald-800 dark:text-emerald-300 text-sm">
                                            <p>
                                                Get credentials from the{" "}
                                                <a
                                                    href="https://developer.spotify.com/dashboard/"
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="underline font-medium"
                                                >
                                                    Spotify Developer Dashboard
                                                </a>
                                            </p>
                                        </div>
                                        <div className="p-4 rounded-xl bg-amber-100 dark:bg-amber-900/20 text-amber-800 dark:text-amber-300 text-sm">
                                            <p className="font-medium mb-1">
                                                Redirect URI Setup
                                            </p>
                                            <p className="mb-2 opacity-90">
                                                In your Spotify app settings,
                                                add this Redirect URI:
                                            </p>
                                            <code className="block bg-amber-200/50 dark:bg-amber-800/30 px-3 py-2 rounded-lg text-xs font-mono break-all">
                                                https://gpt-home.judahpaul.com/spotify/callback
                                            </code>
                                        </div>
                                    </div>
                                )}

                                {name === "PhilipsHue" && (
                                    <div className="p-4 rounded-xl bg-amber-100 dark:bg-amber-900/20 text-amber-800 dark:text-amber-300 text-sm">
                                        <strong>Note:</strong> Press the button
                                        on the bridge before submitting if
                                        connecting for the first time.
                                    </div>
                                )}

                                {name === "OpenWeather" && (
                                    <div className="p-4 rounded-xl bg-emerald-100 dark:bg-emerald-900/20 text-emerald-800 dark:text-emerald-300 text-sm">
                                        <p className="text-sm opacity-75">
                                            Get credentials from the{" "}
                                            <a
                                                href="https://home.openweathermap.org/api_keys"
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="underline"
                                            >
                                                OpenWeather Dashboard
                                            </a>
                                        </p>
                                    </div>
                                )}

                                {name === "CalDAV" && (
                                    <div className="p-4 rounded-xl bg-primary-100 dark:bg-primary-900/20 text-primary-800 dark:text-primary-300 text-sm">
                                        <strong>Note:</strong> CalDAV requests
                                        must be made over HTTPS.{" "}
                                        <a
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            href="https://caldav.readthedocs.io/stable/about.html#some-notes-on-caldav-urls"
                                            className="underline"
                                        >
                                            Learn more
                                        </a>
                                    </div>
                                )}

                                {/* Form fields */}
                                {requiredFields[name].map((field) => (
                                    <div key={field}>
                                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                                            {field}
                                        </label>
                                        <input
                                            type={
                                                field === "PASSWORD"
                                                    ? "password"
                                                    : "text"
                                            }
                                            name={field}
                                            placeholder={`Enter ${field.toLowerCase()}`}
                                            value={
                                                formData[
                                                    field as keyof typeof formData
                                                ] || ""
                                            }
                                            onChange={handleInputChange}
                                            onKeyDown={disallowSpace}
                                            onPaste={handlePaste}
                                            className="input-field"
                                            autoFocus={
                                                requiredFields[name].indexOf(
                                                    field,
                                                ) === 0
                                            }
                                        />
                                    </div>
                                ))}

                                {/* Error message */}
                                {error && (
                                    <motion.div
                                        initial={{ opacity: 0, y: -10 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        className="flex items-center gap-2 p-3 rounded-xl bg-rose-100 dark:bg-rose-900/20 text-rose-600 dark:text-rose-400 text-sm"
                                    >
                                        <Icons.AlertCircle className="flex-shrink-0" />
                                        <span>{error}</span>
                                    </motion.div>
                                )}
                            </div>

                            {/* Modal footer */}
                            <div className="flex justify-end gap-3 p-6 border-t border-slate-200 dark:border-dark-700 bg-slate-50 dark:bg-dark-800/50">
                                <button
                                    onClick={() => setShowForm(false)}
                                    className="btn-secondary"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={connectService}
                                    disabled={loading}
                                    className="btn-primary flex items-center gap-2"
                                >
                                    {loading ? (
                                        <Spinner size="sm" />
                                    ) : (
                                        <>
                                            <Icons.Check className="w-4 h-4" />
                                            Submit
                                        </>
                                    )}
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </>
    );
};

export default Integration;
