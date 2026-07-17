import { renderHook, act } from "@testing-library/react";

import {
    cn,
    usePrefersReducedMotion,
    useReducedMotionTransition,
    useReducedMotionVariants,
} from "./utils";

describe("cn", () => {
    it("joins class names", () => {
        expect(cn("a", "b")).toBe("a b");
    });

    it("drops falsy values", () => {
        expect(cn("a", false && "b", null, undefined, "c")).toBe("a c");
    });

    it("resolves conflicting tailwind utilities so the last one wins", () => {
        expect(cn("px-2", "px-4")).toBe("px-4");
    });

    it("supports conditional object syntax", () => {
        expect(cn("base", { active: true, disabled: false })).toBe("base active");
    });
});

interface FakeMediaQueryList {
    matches: boolean;
    media: string;
    addEventListener: (type: string, cb: (e: { matches: boolean }) => void) => void;
    removeEventListener: (type: string, cb: (e: { matches: boolean }) => void) => void;
    emit: (matches: boolean) => void;
}

function mockMatchMedia(initial: boolean): FakeMediaQueryList {
    const listeners = new Set<(e: { matches: boolean }) => void>();
    const mql: FakeMediaQueryList = {
        matches: initial,
        media: "(prefers-reduced-motion: reduce)",
        addEventListener: (_type, cb) => {
            listeners.add(cb);
        },
        removeEventListener: (_type, cb) => {
            listeners.delete(cb);
        },
        emit: (matches) => {
            mql.matches = matches;
            listeners.forEach((cb) => cb({ matches }));
        },
    };
    window.matchMedia = jest.fn().mockReturnValue(mql) as unknown as typeof window.matchMedia;
    return mql;
}

afterEach(() => {
    delete (window as { matchMedia?: unknown }).matchMedia;
});

describe("usePrefersReducedMotion", () => {
    it("reports true when the user prefers reduced motion", () => {
        mockMatchMedia(true);
        const { result } = renderHook(() => usePrefersReducedMotion());
        expect(result.current).toBe(true);
    });

    it("reports false otherwise", () => {
        mockMatchMedia(false);
        const { result } = renderHook(() => usePrefersReducedMotion());
        expect(result.current).toBe(false);
    });

    it("updates when the preference changes", () => {
        const mql = mockMatchMedia(false);
        const { result } = renderHook(() => usePrefersReducedMotion());
        expect(result.current).toBe(false);
        act(() => mql.emit(true));
        expect(result.current).toBe(true);
    });
});

describe("useReducedMotionTransition", () => {
    it("collapses to an instant transition under reduced motion", () => {
        mockMatchMedia(true);
        const { result } = renderHook(() =>
            useReducedMotionTransition({ duration: 0.5 }),
        );
        expect(result.current).toEqual({ duration: 0 });
    });

    it("passes the normal transition through otherwise", () => {
        mockMatchMedia(false);
        const { result } = renderHook(() =>
            useReducedMotionTransition({ duration: 0.5 }),
        );
        expect(result.current).toEqual({ duration: 0.5 });
    });
});

describe("useReducedMotionVariants", () => {
    it("falls back to opacity-only variants under reduced motion", () => {
        mockMatchMedia(true);
        const normal = { hidden: { x: -100 }, visible: { x: 0 } };
        const { result } = renderHook(() => useReducedMotionVariants(normal));
        expect(result.current).toEqual({
            hidden: { opacity: 0 },
            visible: { opacity: 1 },
            exit: { opacity: 0 },
        });
    });

    it("returns the provided variants otherwise", () => {
        mockMatchMedia(false);
        const normal = { hidden: { x: -100 }, visible: { x: 0 } };
        const { result } = renderHook(() => useReducedMotionVariants(normal));
        expect(result.current).toBe(normal);
    });
});
