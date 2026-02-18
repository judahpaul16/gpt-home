import React from "react";
import { Icons } from "../Icons";

interface QuickActionsProps {
    onGptRestart: () => void;
    onSpotifyRestart: () => void;
    onPasswordChange: () => void;
    onClearMemory: () => void;
    onReboot: () => void;
    onShutdown: () => void;
}

const QuickActions: React.FC<QuickActionsProps> = ({
    onGptRestart,
    onSpotifyRestart,
    onPasswordChange,
    onClearMemory,
    onReboot,
    onShutdown,
}) => {
    return (
        <div className="card p-4 sm:p-5">
            <h2 className="text-sm font-semibold text-slate-900 dark:text-white mb-3">
                Quick Actions
            </h2>
            <div className="flex items-center gap-2 flex-wrap">
                <button
                    onClick={onGptRestart}
                    className="px-3 py-2 rounded-xl text-sm font-medium flex items-center gap-2 bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 hover:bg-primary-200 dark:hover:bg-primary-900/50 transition-colors"
                >
                    <Icons.Refresh className="w-4 h-4" />
                    Restart GPT Home
                </button>
                <button
                    onClick={onSpotifyRestart}
                    className="px-3 py-2 rounded-xl text-sm font-medium flex items-center gap-2 bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-200 dark:hover:bg-emerald-900/50 transition-colors"
                >
                    <Icons.Music className="w-4 h-4" />
                    Restart Spotifyd
                </button>
                <button
                    onClick={onPasswordChange}
                    className="px-3 py-2 rounded-xl text-sm font-medium flex items-center gap-2 bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 hover:bg-amber-200 dark:hover:bg-amber-900/50 transition-colors"
                >
                    <Icons.Lock className="w-4 h-4" />
                    Password
                </button>
                <button
                    onClick={onClearMemory}
                    className="px-3 py-2 rounded-xl text-sm font-medium flex items-center gap-2 bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-300 hover:bg-rose-200 dark:hover:bg-rose-900/50 transition-colors"
                >
                    <Icons.Brain className="w-4 h-4" />
                    Clear Memories
                </button>
                <a
                    href="https://smith.langchain.com"
                    target="_blank"
                    rel="noreferrer"
                    className="px-3 py-2 rounded-xl text-sm font-medium flex items-center gap-2 bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 hover:bg-violet-200 dark:hover:bg-violet-900/50 transition-colors"
                >
                    <Icons.ExternalLink className="w-4 h-4" />
                    LangSmith
                </a>
                <button
                    onClick={onReboot}
                    className="px-3 py-2 rounded-xl text-sm font-medium flex items-center gap-2 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
                >
                    <Icons.RotateCw className="w-4 h-4" />
                    Reboot
                </button>
                <button
                    onClick={onShutdown}
                    className="px-3 py-2 rounded-xl text-sm font-medium flex items-center gap-2 bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-300 hover:bg-rose-200 dark:hover:bg-rose-900/50 transition-colors"
                >
                    <Icons.Power className="w-4 h-4" />
                    Shutdown
                </button>
            </div>
        </div>
    );
};

export default QuickActions;
