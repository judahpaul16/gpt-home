import React from "react";
import { cn } from "../lib/utils";

// Icons using SVG for crisp rendering at any size
export const Icons = {
    // Navigation
    Menu: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-6 h-6", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 6h16M4 12h16M4 18h16"
            />
        </svg>
    ),

    Clipboard: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-6 h-6", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
            />
        </svg>
    ),

    X: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-6 h-6", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
            />
        </svg>
    ),

    ChevronDown: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 9l-7 7-7-7"
            />
        </svg>
    ),

    ChevronRight: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 5l7 7-7 7"
            />
        </svg>
    ),

    // Theme
    Sun: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"
            />
        </svg>
    ),

    Moon: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
            />
        </svg>
    ),

    // Nav Items
    Integrations: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M11 4a2 2 0 114 0v1a1 1 0 001 1h3a1 1 0 011 1v3a1 1 0 01-1 1h-1a2 2 0 100 4h1a1 1 0 011 1v3a1 1 0 01-1 1h-3a1 1 0 01-1-1v-1a2 2 0 10-4 0v1a1 1 0 01-1 1H7a1 1 0 01-1-1v-3a1 1 0 00-1-1H4a2 2 0 110-4h1a1 1 0 001-1V7a1 1 0 011-1h3a1 1 0 001-1V4z"
            />
        </svg>
    ),

    Logs: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
            />
        </svg>
    ),

    Settings: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
            />
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
            />
        </svg>
    ),

    Info: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
        </svg>
    ),

    // Actions
    Link: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"
            />
        </svg>
    ),

    Unlink: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"
            />
        </svg>
    ),

    Edit: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
            />
        </svg>
    ),

    Refresh: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
        </svg>
    ),

    Power: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M18.364 5.636a9 9 0 11-12.728 0M12 3v9"
            />
        </svg>
    ),

    RotateCw: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
        </svg>
    ),

    Save: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"
            />
        </svg>
    ),

    Trash: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
            />
        </svg>
    ),

    Brain: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-4 h-4", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9.5 2a3.5 3.5 0 00-3.4 4.35A3.5 3.5 0 004 9.5a3.5 3.5 0 002.1 3.15A3.5 3.5 0 006 14.5a3.5 3.5 0 003.5 3.5h1V2h-1zm5 0a3.5 3.5 0 013.4 4.35A3.5 3.5 0 0120 9.5a3.5 3.5 0 01-2.1 3.15 3.5 3.5 0 01.1 1.85 3.5 3.5 0 01-3.5 3.5h-1V2h1z"
            />
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 18v4M8 22h8"
            />
        </svg>
    ),

    ExternalLink: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-4 h-4", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
            />
        </svg>
    ),

    Lock: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
            />
        </svg>
    ),

    Eye: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
            />
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
            />
        </svg>
    ),

    EyeOff: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"
            />
        </svg>
    ),

    ArrowDown: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 14l-7 7m0 0l-7-7m7 7V3"
            />
        </svg>
    ),

    Check: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M5 13l4 4L19 7"
            />
        </svg>
    ),

    CheckCircle: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
            />
        </svg>
    ),

    AlertCircle: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
        </svg>
    ),

    AlertTriangle: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
        </svg>
    ),

    Key: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z"
            />
        </svg>
    ),

    Cpu: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"
            />
        </svg>
    ),

    Mic: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
            />
        </svg>
    ),

    Terminal: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
            />
        </svg>
    ),

    // Service Icons
    Music: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-6 h-6", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"
            />
        </svg>
    ),

    Cloud: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-6 h-6", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z"
            />
        </svg>
    ),

    Lightbulb: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-6 h-6", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
            />
        </svg>
    ),

    Calendar: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-6 h-6", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
            />
        </svg>
    ),

    Github: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-6 h-6", className)}
            fill="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                fillRule="evenodd"
                clipRule="evenodd"
                d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
            />
        </svg>
    ),

    Heart: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="currentColor"
            viewBox="0 0 24 24"
        >
            <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
        </svg>
    ),

    Robot: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-8 h-8", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611l-.974.162a7.5 7.5 0 01-7.322 0l-.974-.162c-1.717-.293-2.3-2.379-1.067-3.61L5 14.5"
            />
        </svg>
    ),

    Home: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-6 h-6", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"
            />
        </svg>
    ),

    Monitor: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
            />
        </svg>
    ),

    Upload: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"
            />
        </svg>
    ),

    Image: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
            />
        </svg>
    ),
    Volume2: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M11 5L6 9H2v6h4l5 4V5zM19.07 4.93a10 10 0 010 14.14M15.54 8.46a5 5 0 010 7.07"
            />
        </svg>
    ),
    ZoomIn: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v6m3-3H7"
            />
        </svg>
    ),
    ZoomOut: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM13 10H7"
            />
        </svg>
    ),
    RotateCcw: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M1 4v6h6M3.51 15a9 9 0 102.13-9.36L1 10"
            />
        </svg>
    ),
    Maximize: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3"
            />
        </svg>
    ),
    Minimize: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 3v3a2 2 0 01-2 2H3m18 0h-3a2 2 0 01-2-2V3m0 18v-3a2 2 0 012-2h3M3 16h3a2 2 0 012 2v3"
            />
        </svg>
    ),
    Pencil: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"
            />
        </svg>
    ),
    Activity: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M22 12h-4l-3 9L9 3l-3 9H2"
            />
        </svg>
    ),
    Database: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <ellipse cx="12" cy="5" rx="9" ry="3" strokeWidth={2} />
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"
            />
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"
            />
        </svg>
    ),
    Wifi: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M5 12.55a11 11 0 0114 0M8.53 16.11a6 6 0 016.95 0M12 20h.01"
            />
        </svg>
    ),
    HardDrive: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <rect
                x="2"
                y="2"
                width="20"
                height="8"
                rx="2"
                ry="2"
                strokeWidth={2}
            />
            <rect
                x="2"
                y="14"
                width="20"
                height="8"
                rx="2"
                ry="2"
                strokeWidth={2}
            />
            <circle cx="6" cy="6" r="1" fill="currentColor" />
            <circle cx="6" cy="18" r="1" fill="currentColor" />
        </svg>
    ),
    Thermometer: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M14 14.76V3.5a2.5 2.5 0 00-5 0v11.26a4.5 4.5 0 105 0z"
            />
        </svg>
    ),
    Play: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <polygon
                points="5 3 19 12 5 21 5 3"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
            />
        </svg>
    ),
    Pause: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <rect x="6" y="4" width="4" height="16" strokeWidth={2} rx="1" />
            <rect x="14" y="4" width="4" height="16" strokeWidth={2} rx="1" />
        </svg>
    ),
    Square: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <rect
                x="3"
                y="3"
                width="18"
                height="18"
                rx="2"
                ry="2"
                strokeWidth={2}
            />
        </svg>
    ),
    Filter: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <polygon
                points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
            />
        </svg>
    ),
    Crop: ({ className }: { className?: string }) => (
        <svg
            className={cn("w-5 h-5", className)}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
        >
            <path
                d="M6 2v4M6 10v12M2 6h4M10 6h12M18 22v-4M18 14V2M22 18h-4M14 18H2"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
            />
        </svg>
    ),
};

// Loading Spinner Component
export const Spinner = ({
    size = "md",
    className,
}: {
    size?: "sm" | "md" | "lg";
    className?: string;
}) => {
    const sizes = {
        sm: "w-4 h-4 border-2",
        md: "w-6 h-6 border-2",
        lg: "w-10 h-10 border-[3px]",
    };

    return (
        <div
            className={cn(
                sizes[size],
                "rounded-full border-primary-500/30 border-t-primary-500 animate-spin",
                className,
            )}
        />
    );
};

export default Icons;
