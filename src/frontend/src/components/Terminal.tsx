import React, { useEffect, useRef, useCallback } from "react";
import { Terminal as XTerm } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";

interface TerminalProps {
    className?: string;
}

const Terminal: React.FC<TerminalProps> = ({ className }) => {
    const terminalRef = useRef<HTMLDivElement>(null);
    const xtermRef = useRef<XTerm | null>(null);
    const fitAddonRef = useRef<FitAddon | null>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const reconnectAttempts = useRef(0);
    const mountedRef = useRef(true);
    const hasConnectedRef = useRef(false);
    const connectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    const connect = useCallback(() => {
        if (!mountedRef.current) return;
        if (wsRef.current?.readyState === WebSocket.OPEN) return;

        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${protocol}//${window.location.host}/api/terminal/ws`;

        const ws = new WebSocket(wsUrl);
        ws.binaryType = "arraybuffer";
        wsRef.current = ws;

        ws.onopen = () => {
            reconnectAttempts.current = 0;
            hasConnectedRef.current = true;

            if (fitAddonRef.current && xtermRef.current) {
                fitAddonRef.current.fit();
                const dims = fitAddonRef.current.proposeDimensions();
                if (dims) {
                    ws.send(
                        JSON.stringify({
                            type: "resize",
                            rows: dims.rows,
                            cols: dims.cols,
                        }),
                    );
                }
            }
        };

        ws.onmessage = (event) => {
            if (event.data instanceof ArrayBuffer) {
                const text = new TextDecoder().decode(event.data);
                xtermRef.current?.write(text);
            } else {
                xtermRef.current?.write(event.data);
            }
        };

        ws.onclose = (event) => {
            if (!mountedRef.current) return;
            if (event.code !== 1000 && reconnectAttempts.current < 5) {
                reconnectAttempts.current++;
                if (hasConnectedRef.current) {
                    xtermRef.current?.write(
                        `\r\n\x1b[33mConnection lost. Reconnecting (${reconnectAttempts.current}/5)...\x1b[0m\r\n`,
                    );
                }
                reconnectTimeoutRef.current = setTimeout(() => {
                    connect();
                }, 2000);
            } else if (reconnectAttempts.current >= 5) {
                xtermRef.current?.write(
                    "\r\n\x1b[31mFailed to connect after 5 attempts. Press Enter to retry.\x1b[0m\r\n",
                );
            }
        };

        ws.onerror = () => {};
    }, []);

    const sendResize = useCallback(() => {
        if (
            wsRef.current?.readyState === WebSocket.OPEN &&
            fitAddonRef.current
        ) {
            const dims = fitAddonRef.current.proposeDimensions();
            if (dims) {
                wsRef.current.send(
                    JSON.stringify({
                        type: "resize",
                        rows: dims.rows,
                        cols: dims.cols,
                    }),
                );
            }
        }
    }, []);

    useEffect(() => {
        if (!terminalRef.current) return;
        mountedRef.current = true;

        const terminal = new XTerm({
            cursorBlink: true,
            cursorStyle: "block",
            fontFamily:
                "'JetBrains Mono', 'Fira Code', 'Cascadia Code', Menlo, Monaco, 'Courier New', monospace",
            fontSize: 14,
            lineHeight: 1.2,
            theme: {
                background: "#0f172a",
                foreground: "#e2e8f0",
                cursor: "#22d3ee",
                cursorAccent: "#0f172a",
                selectionBackground: "#334155",
                selectionForeground: "#f8fafc",
                black: "#1e293b",
                red: "#f87171",
                green: "#4ade80",
                yellow: "#facc15",
                blue: "#60a5fa",
                magenta: "#c084fc",
                cyan: "#22d3ee",
                white: "#f1f5f9",
                brightBlack: "#475569",
                brightRed: "#fca5a5",
                brightGreen: "#86efac",
                brightYellow: "#fde047",
                brightBlue: "#93c5fd",
                brightMagenta: "#d8b4fe",
                brightCyan: "#67e8f9",
                brightWhite: "#f8fafc",
            },
            allowProposedApi: true,
            scrollback: 5000,
        });

        const fitAddon = new FitAddon();
        terminal.loadAddon(fitAddon);

        terminal.open(terminalRef.current);
        fitAddon.fit();

        xtermRef.current = terminal;
        fitAddonRef.current = fitAddon;

        terminal.onData((data: string) => {
            if (wsRef.current?.readyState === WebSocket.OPEN) {
                wsRef.current.send(data);
            } else if (data === "\r" || data === "\n") {
                reconnectAttempts.current = 0;
                connect();
            }
        });

        terminal.onResize(() => {
            sendResize();
        });

        connectTimeoutRef.current = setTimeout(() => {
            connect();
        }, 100);

        const handleResize = () => {
            if (fitAddonRef.current) {
                fitAddonRef.current.fit();
                sendResize();
            }
        };

        window.addEventListener("resize", handleResize);

        const resizeObserver = new ResizeObserver(() => {
            handleResize();
        });
        resizeObserver.observe(terminalRef.current);

        return () => {
            mountedRef.current = false;
            window.removeEventListener("resize", handleResize);
            resizeObserver.disconnect();

            if (connectTimeoutRef.current) {
                clearTimeout(connectTimeoutRef.current);
            }

            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
            }

            if (wsRef.current) {
                wsRef.current.close(1000);
                wsRef.current = null;
            }

            terminal.dispose();
        };
    }, [connect, sendResize]);

    return (
        <div
            ref={terminalRef}
            className={className}
            style={{
                height: "100%",
                width: "100%",
                padding: "8px",
                boxSizing: "border-box",
            }}
        />
    );
};

export default Terminal;
