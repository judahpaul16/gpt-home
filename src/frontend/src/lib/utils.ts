import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { useEffect, useState } from "react";
import type { Transition, Variants } from "framer-motion";

export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

/**
 * Hook to detect if user prefers reduced motion
 * Returns true if the user has enabled "reduce motion" in their OS settings
 */
export function usePrefersReducedMotion(): boolean {
    const [prefersReducedMotion, setPrefersReducedMotion] = useState(() => {
        // Default to false during SSR, will be updated on client
        if (typeof window === "undefined") return false;
        return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    });

    useEffect(() => {
        const mediaQuery = window.matchMedia(
            "(prefers-reduced-motion: reduce)",
        );

        const handleChange = (event: MediaQueryListEvent) => {
            setPrefersReducedMotion(event.matches);
        };

        // Listen for changes to the user's preference
        mediaQuery.addEventListener("change", handleChange);

        // Set initial value
        setPrefersReducedMotion(mediaQuery.matches);

        return () => {
            mediaQuery.removeEventListener("change", handleChange);
        };
    }, []);

    return prefersReducedMotion;
}

/**
 * Returns appropriate transition settings based on user's motion preference
 * Respects accessibility settings while maintaining visual feedback
 */
export function useReducedMotionTransition(
    normalTransition: Transition = { duration: 0.3 },
): Transition {
    const prefersReducedMotion = usePrefersReducedMotion();

    if (prefersReducedMotion) {
        return { duration: 0 };
    }

    return normalTransition;
}

/**
 * Returns appropriate animation variants based on user's motion preference
 * Falls back to instant opacity changes for reduced motion users
 */
export function useReducedMotionVariants(
    normalVariants: Variants,
    reducedVariants?: Variants,
): Variants {
    const prefersReducedMotion = usePrefersReducedMotion();

    if (prefersReducedMotion) {
        return (
            reducedVariants || {
                hidden: { opacity: 0 },
                visible: { opacity: 1 },
                exit: { opacity: 0 },
            }
        );
    }

    return normalVariants;
}

/**
 * Animation presets following best practices
 * - Uses transform and opacity (GPU-accelerated properties)
 * - Appropriate durations for different interaction types
 */
export const animationPresets = {
    // For page/route transitions
    page: {
        initial: { opacity: 0, y: 20 },
        animate: { opacity: 1, y: 0 },
        exit: { opacity: 0, y: -20 },
        transition: { duration: 0.2 },
    },

    // For modals and overlays
    modal: {
        overlay: {
            initial: { opacity: 0 },
            animate: { opacity: 1 },
            exit: { opacity: 0 },
        },
        content: {
            initial: { opacity: 0, scale: 0.95 },
            animate: { opacity: 1, scale: 1 },
            exit: { opacity: 0, scale: 0.95 },
            transition: { type: "spring", duration: 0.3 },
        },
    },

    // For sidebar/drawer
    slideIn: {
        left: {
            initial: { x: "-100%" },
            animate: { x: 0 },
            exit: { x: "-100%" },
            transition: { type: "spring", damping: 25, stiffness: 200 },
        },
        right: {
            initial: { x: "100%" },
            animate: { x: 0 },
            exit: { x: "100%" },
            transition: { type: "spring", damping: 25, stiffness: 200 },
        },
    },

    // For list items (stagger)
    stagger: {
        container: {
            hidden: { opacity: 0 },
            show: {
                opacity: 1,
                transition: { staggerChildren: 0.1 },
            },
        },
        item: {
            hidden: { opacity: 0, y: 20 },
            show: { opacity: 1, y: 0 },
        },
    },

    // For button interactions
    button: {
        whileHover: { scale: 1.02 },
        whileTap: { scale: 0.98 },
        transition: { duration: 0.1 },
    },

    // For error/notification messages
    notification: {
        initial: { opacity: 0, y: -10 },
        animate: { opacity: 1, y: 0 },
        exit: { opacity: 0, y: -10 },
        transition: { duration: 0.2 },
    },
} as const;

/**
 * Reduced motion safe versions of animation presets
 * Uses only opacity for minimal but accessible feedback
 */
export const reducedMotionPresets = {
    page: {
        initial: { opacity: 0 },
        animate: { opacity: 1 },
        exit: { opacity: 0 },
        transition: { duration: 0 },
    },

    modal: {
        overlay: {
            initial: { opacity: 0 },
            animate: { opacity: 1 },
            exit: { opacity: 0 },
        },
        content: {
            initial: { opacity: 0 },
            animate: { opacity: 1 },
            exit: { opacity: 0 },
            transition: { duration: 0 },
        },
    },

    slideIn: {
        left: {
            initial: { opacity: 0 },
            animate: { opacity: 1 },
            exit: { opacity: 0 },
            transition: { duration: 0 },
        },
        right: {
            initial: { opacity: 0 },
            animate: { opacity: 1 },
            exit: { opacity: 0 },
            transition: { duration: 0 },
        },
    },

    stagger: {
        container: {
            hidden: { opacity: 0 },
            show: { opacity: 1 },
        },
        item: {
            hidden: { opacity: 0 },
            show: { opacity: 1 },
        },
    },

    button: {
        whileHover: {},
        whileTap: {},
        transition: { duration: 0 },
    },

    notification: {
        initial: { opacity: 0 },
        animate: { opacity: 1 },
        exit: { opacity: 0 },
        transition: { duration: 0 },
    },
} as const;
