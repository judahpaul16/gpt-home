import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import axios from "axios";
import { Icons, Spinner } from "./Icons";
import { cn } from "../lib/utils";

interface PasswordModalProps {
    unlockApp: () => void;
    darkMode: boolean;
    toggleDarkMode: () => void;
}

const MIN_PASSWORD_LENGTH = 6;

const PasswordModal: React.FC<PasswordModalProps> = ({
    unlockApp,
    darkMode,
    toggleDarkMode,
}) => {
    const [input, setInput] = useState<string>("");
    const [confirmInput, setConfirmInput] = useState<string>("");
    const [error, setError] = useState<string | null>(null);
    const [hashedPassword, setHashedPassword] = useState<string | null>(null);
    const [showPassword, setShowPassword] = useState(false);
    const [loading, setLoading] = useState(false);
    const [initialLoading, setInitialLoading] = useState(true);
    const [backendAvailable, setBackendAvailable] = useState(true);

    useEffect(() => {
        const fetchPassword = () => {
            axios
                .post("/getHashedPassword")
                .then((response) => {
                    if (response.data.success) {
                        setHashedPassword(response.data.hashedPassword);
                    } else {
                        setError(
                            `Error fetching hashed password: ${response.data.error}`,
                        );
                    }
                    setBackendAvailable(true);
                })
                .catch(() => {
                    setBackendAvailable(false);
                })
                .finally(() => setInitialLoading(false));
        };

        fetchPassword();
        const interval = setInterval(() => {
            if (!backendAvailable) fetchPassword();
        }, 5000);
        return () => clearInterval(interval);
    }, [backendAvailable]);

    const handleInput = (e: React.ChangeEvent<HTMLInputElement>) => {
        setInput(e.target.value);
        setError(null);
    };

    const handleConfirmInput = (e: React.ChangeEvent<HTMLInputElement>) => {
        setConfirmInput(e.target.value);
        setError(null);
    };

    const hashPassword = async (password: string) => {
        return await axios
            .post("/hashPassword", { password })
            .then((response) => {
                if (response.data.success) {
                    return response.data.hashedPassword;
                } else {
                    setError(`Error hashing password: ${response.data.error}`);
                    return null;
                }
            })
            .catch((error) => {
                console.error("Error hashing password:", error);
                setError(`Error hashing password: ${error}`);
                return null;
            });
    };

    const handleUnlock = async () => {
        if (input.length < MIN_PASSWORD_LENGTH) {
            setError(
                `Password must be at least ${MIN_PASSWORD_LENGTH} characters`,
            );
            return;
        }

        if (!input) {
            setError("Password is required");
            return;
        }

        setLoading(true);

        if (!hashedPassword) {
            if (input && confirmInput && input === confirmInput) {
                axios
                    .post("/setHashedPassword", { newPassword: input })
                    .then((response) => {
                        if (response.data.success) {
                            setHashedPassword("set");
                            unlockApp();
                        } else {
                            setError(
                                `Error saving password: ${response.data.error}`,
                            );
                        }
                    })
                    .catch((error) => {
                        console.error("Error saving hashed password:", error);
                        setError("Failed to save password");
                    })
                    .finally(() => setLoading(false));
            } else {
                setError("Passwords do not match");
                setLoading(false);
            }
        } else {
            const hashedInput = await hashPassword(input);
            if (hashedPassword === hashedInput) {
                unlockApp();
            } else {
                setError("Incorrect password");
            }
            setLoading(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter") {
            handleUnlock();
        }
    };

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-dark-900 flex items-center justify-center p-4 relative overflow-hidden">
            {/* Background decorations */}
            <div className="absolute inset-0 overflow-hidden">
                <div className="absolute -top-40 -right-40 w-80 h-80 bg-primary-500/10 rounded-full blur-3xl" />
                <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-accent-violet/10 rounded-full blur-3xl" />
            </div>

            {/* Theme toggle */}
            <button
                onClick={toggleDarkMode}
                className="absolute top-4 right-4 z-50 p-2.5 rounded-xl bg-white dark:bg-dark-800 shadow-lg
                   border border-slate-200 dark:border-dark-700 transition-all hover:scale-105"
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

            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="relative w-full max-w-md"
            >
                <div className="glass-card p-8 space-y-6">
                    {/* Header */}
                    <div className="text-center space-y-2">
                        <div className="inline-flex p-3 rounded-2xl bg-gradient-to-br from-primary-500 to-accent-violet shadow-lg shadow-primary-500/25 mb-4">
                            <Icons.Home className="w-10 h-10 text-white" />
                        </div>
                        <h1 className="text-2xl font-bold gradient-text">
                            GPT Home
                        </h1>
                        <p className="text-slate-500 dark:text-slate-400">
                            {hashedPassword
                                ? "Enter your password to continue"
                                : "Create a password to get started"}
                        </p>
                    </div>

                    {initialLoading ? (
                        <div className="flex justify-center py-8">
                            <Spinner size="lg" />
                        </div>
                    ) : !backendAvailable ? (
                        <div className="flex flex-col items-center justify-center py-8 space-y-3">
                            <Spinner size="md" />
                            <p className="text-slate-500 dark:text-slate-400 text-sm">
                                Waiting for backend...
                            </p>
                        </div>
                    ) : (
                        <div className="space-y-4">
                            {/* Password input */}
                            <div className="relative">
                                <div className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400">
                                    <Icons.Lock />
                                </div>
                                <input
                                    type={showPassword ? "text" : "password"}
                                    placeholder="Password"
                                    value={input}
                                    onChange={handleInput}
                                    onKeyDown={handleKeyDown}
                                    autoFocus
                                    className="input-field pl-12 pr-12"
                                />
                                <button
                                    type="button"
                                    onClick={() =>
                                        setShowPassword(!showPassword)
                                    }
                                    className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                                >
                                    {showPassword ? (
                                        <Icons.EyeOff />
                                    ) : (
                                        <Icons.Eye />
                                    )}
                                </button>
                            </div>

                            {/* Confirm password (only for new users) */}
                            {!hashedPassword && (
                                <motion.div
                                    initial={{ opacity: 0, height: 0 }}
                                    animate={{ opacity: 1, height: "auto" }}
                                    className="relative"
                                >
                                    <div className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400">
                                        <Icons.Lock />
                                    </div>
                                    <input
                                        type={
                                            showPassword ? "text" : "password"
                                        }
                                        placeholder="Confirm Password"
                                        value={confirmInput}
                                        onChange={handleConfirmInput}
                                        onKeyDown={handleKeyDown}
                                        className="input-field pl-12"
                                    />
                                </motion.div>
                            )}

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

                            {/* Submit button */}
                            <button
                                onClick={handleUnlock}
                                disabled={loading}
                                className={cn(
                                    "w-full btn-primary flex items-center justify-center gap-2",
                                    loading && "opacity-75 cursor-not-allowed",
                                )}
                            >
                                {loading ? (
                                    <Spinner size="sm" />
                                ) : (
                                    <>
                                        {hashedPassword
                                            ? "Unlock"
                                            : "Set Password"}
                                        <Icons.ChevronRight />
                                    </>
                                )}
                            </button>
                        </div>
                    )}
                </div>
            </motion.div>
        </div>
    );
};

export default PasswordModal;
