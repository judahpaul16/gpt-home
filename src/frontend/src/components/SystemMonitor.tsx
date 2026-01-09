import React, {
    useState,
    useEffect,
    useRef,
    useCallback,
    useMemo,
} from "react";
import { motion } from "framer-motion";
import { Icons, Spinner } from "./Icons";
import { cn } from "../lib/utils";
import Terminal from "./Terminal";

interface SystemStats {
    cpu: {
        percent: number[];
        percent_total: number;
        count: number;
        count_logical: number;
        freq_current: number;
        freq_max: number;
        load_avg: number[];
    };
    memory: {
        total: number;
        available: number;
        used: number;
        percent: number;
        swap_total: number;
        swap_used: number;
        swap_percent: number;
    };
    disk: {
        total: number;
        used: number;
        free: number;
        percent: number;
        read_bytes: number;
        write_bytes: number;
    };
    network: {
        bytes_sent: number;
        bytes_recv: number;
        packets_sent: number;
        packets_recv: number;
    };
    temperatures: Record<string, number>;
    boot_time: number;
    timestamp: number;
}

interface ProcessInfo {
    pid: number;
    name: string;
    cpu_percent: number;
    memory_percent: number;
    status: string;
    username: string;
    create_time: number;
}

interface SystemInfo {
    system: string;
    node: string;
    release: string;
    version: string;
    machine: string;
    processor: string;
    python_version: string;
    boot_time: number;
    uptime: number;
}

interface HistoryPoint {
    timestamp: number;
    cpu: number;
    memory: number;
    disk_read: number;
    disk_write: number;
    network_in: number;
    network_out: number;
}

const MAX_HISTORY_POINTS = 60;
const POLL_INTERVAL = 2000;

const formatBytes = (bytes: number, decimals = 1): string => {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return (
        parseFloat((bytes / Math.pow(k, i)).toFixed(decimals)) + " " + sizes[i]
    );
};

const formatUptime = (seconds: number): string => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (days > 0) return `${days}d ${hours}h ${minutes}m`;
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
};

interface MiniChartProps {
    data: number[];
    color: string;
    height?: number;
    max?: number;
}

const MiniChart: React.FC<MiniChartProps> = ({
    data,
    color,
    height = 40,
    max = 100,
}) => {
    if (data.length === 0) {
        return (
            <svg
                viewBox={`0 0 100 ${height}`}
                className="w-full h-full"
                preserveAspectRatio="none"
                style={{ maxHeight: height }}
            />
        );
    }

    const divisor = data.length > 1 ? data.length - 1 : 1;
    const points = data
        .map((value, i) => {
            const x = (i / divisor) * 100;
            const y = height - (Math.min(value, max) / max) * height;
            return `${x},${y}`;
        })
        .join(" ");

    const areaPoints = `0,${height} ${points} 100,${height}`;

    return (
        <svg
            viewBox={`0 0 100 ${height}`}
            className="w-full h-full"
            preserveAspectRatio="none"
            style={{ maxHeight: height }}
        >
            <defs>
                <linearGradient
                    id={`gradient-${color}`}
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                >
                    <stop offset="0%" stopColor={color} stopOpacity="0.3" />
                    <stop offset="100%" stopColor={color} stopOpacity="0.05" />
                </linearGradient>
            </defs>
            <polygon points={areaPoints} fill={`url(#gradient-${color})`} />
            <polyline
                points={points}
                fill="none"
                stroke={color}
                strokeWidth="1.5"
                vectorEffect="non-scaling-stroke"
            />
        </svg>
    );
};

interface TooltipData {
    x: number;
    y: number;
    value: number;
    label: string;
    timestamp: number;
}

interface InteractiveChartProps {
    history: HistoryPoint[];
    metrics: {
        key: keyof HistoryPoint;
        color: string;
        label: string;
        enabled: boolean;
        unit?: string;
        max?: number;
    }[];
    height?: number;
}

const InteractiveChart: React.FC<InteractiveChartProps> = ({
    history,
    metrics,
    height = 200,
}) => {
    const [tooltip, setTooltip] = useState<TooltipData | null>(null);
    const svgRef = useRef<SVGSVGElement>(null);

    const enabledMetrics = metrics.filter((m) => m.enabled);

    const sharedRateMax = useMemo(() => {
        const rateKeys = enabledMetrics
            .filter(
                (m) =>
                    m.key.toString().startsWith("network") ||
                    m.key.toString().startsWith("disk"),
            )
            .map((m) => m.key);
        if (rateKeys.length === 0) return 0.001;
        let max = 0.001;
        for (const key of rateKeys) {
            for (const h of history) {
                const val = h[key] as number;
                if (val > max) max = val;
            }
        }
        return max;
    }, [history, enabledMetrics]);

    const handleMouseMove = useCallback(
        (e: React.MouseEvent<SVGSVGElement>) => {
            if (!svgRef.current || history.length === 0) return;

            const rect = svgRef.current.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const relX = x / rect.width;
            const index = Math.min(
                Math.floor(relX * history.length),
                history.length - 1,
            );
            const point = history[index];

            if (point && enabledMetrics.length > 0) {
                let closestMetric = enabledMetrics[0];
                let closestDistance = Infinity;

                for (const metric of enabledMetrics) {
                    const value = point[metric.key] as number;
                    const isRateMetric =
                        metric.key.toString().startsWith("network") ||
                        metric.key.toString().startsWith("disk");
                    const metricMax = isRateMetric
                        ? sharedRateMax
                        : metric.max || 100;
                    const metricY = height - (value / metricMax) * height;
                    const distance = Math.abs(y - metricY);
                    if (distance < closestDistance) {
                        closestDistance = distance;
                        closestMetric = metric;
                    }
                }

                const value = point[closestMetric.key] as number;
                setTooltip({
                    x: e.clientX - rect.left,
                    y: e.clientY - rect.top,
                    value,
                    label: closestMetric.label,
                    timestamp: point.timestamp,
                });
            }
        },
        [history, enabledMetrics, height, sharedRateMax],
    );

    const handleMouseLeave = useCallback(() => {
        setTooltip(null);
    }, []);

    if (history.length === 0) {
        return (
            <div className="relative">
                <svg
                    viewBox={`0 0 100 ${height}`}
                    className="w-full"
                    preserveAspectRatio="none"
                    style={{ height: `${height}px` }}
                />
            </div>
        );
    }

    return (
        <div className="relative">
            <svg
                ref={svgRef}
                viewBox={`0 0 100 ${height}`}
                className="w-full cursor-crosshair"
                preserveAspectRatio="none"
                style={{ height: `${height}px` }}
                onMouseMove={handleMouseMove}
                onMouseLeave={handleMouseLeave}
            >
                {[0, 25, 50, 75, 100].map((pct) => (
                    <line
                        key={pct}
                        x1="0"
                        y1={height - (pct / 100) * height}
                        x2="100"
                        y2={height - (pct / 100) * height}
                        stroke="currentColor"
                        strokeOpacity="0.1"
                        strokeWidth="0.5"
                        vectorEffect="non-scaling-stroke"
                    />
                ))}

                {enabledMetrics.map((metric) => {
                    const data = history.map((h) => h[metric.key] as number);
                    const divisor = data.length > 1 ? data.length - 1 : 1;
                    const isRateMetric =
                        metric.key.toString().startsWith("network") ||
                        metric.key.toString().startsWith("disk");
                    const metricMax = isRateMetric
                        ? sharedRateMax
                        : metric.max || 100;
                    const points = data
                        .map((value, i) => {
                            const x = (i / divisor) * 100;
                            const y =
                                height -
                                (Math.min(value, metricMax) / metricMax) *
                                    height;
                            return `${x},${y}`;
                        })
                        .join(" ");
                    const areaPoints = `0,${height} ${points} 100,${height}`;

                    return (
                        <g key={metric.key}>
                            <defs>
                                <linearGradient
                                    id={`area-${metric.key}`}
                                    x1="0"
                                    y1="0"
                                    x2="0"
                                    y2="1"
                                >
                                    <stop
                                        offset="0%"
                                        stopColor={metric.color}
                                        stopOpacity="0.2"
                                    />
                                    <stop
                                        offset="100%"
                                        stopColor={metric.color}
                                        stopOpacity="0"
                                    />
                                </linearGradient>
                            </defs>
                            <polygon
                                points={areaPoints}
                                fill={`url(#area-${metric.key})`}
                            />
                            <polyline
                                points={points}
                                fill="none"
                                stroke={metric.color}
                                strokeWidth="2"
                                vectorEffect="non-scaling-stroke"
                            />
                        </g>
                    );
                })}

                {tooltip && (
                    <line
                        x1={
                            (tooltip.x /
                                (svgRef.current?.getBoundingClientRect()
                                    .width || 1)) *
                            100
                        }
                        y1="0"
                        x2={
                            (tooltip.x /
                                (svgRef.current?.getBoundingClientRect()
                                    .width || 1)) *
                            100
                        }
                        y2={height}
                        stroke="currentColor"
                        strokeOpacity="0.3"
                        strokeWidth="1"
                        vectorEffect="non-scaling-stroke"
                        strokeDasharray="2,2"
                    />
                )}
            </svg>

            {tooltip && (
                <div
                    className="absolute z-50 px-3 py-2 text-xs bg-dark-800 dark:bg-dark-700 text-white rounded-lg shadow-lg pointer-events-none"
                    style={{
                        left: Math.min(
                            tooltip.x + 10,
                            (svgRef.current?.getBoundingClientRect().width ||
                                200) - 120,
                        ),
                        top: Math.max(tooltip.y - 40, 0),
                    }}
                >
                    <div className="font-medium">
                        {tooltip.label}: {tooltip.value.toFixed(2)}
                        {tooltip.label.includes("Network") ||
                        tooltip.label.includes("Disk")
                            ? " MB/s"
                            : "%"}
                    </div>
                    <div className="text-slate-400">
                        {new Date(
                            tooltip.timestamp * 1000,
                        ).toLocaleTimeString()}
                    </div>
                </div>
            )}
        </div>
    );
};

const SystemMonitor: React.FC = () => {
    const [stats, setStats] = useState<SystemStats | null>(null);
    const [processes, setProcesses] = useState<ProcessInfo[]>([]);
    const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
    const [history, setHistory] = useState<HistoryPoint[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isPaused, setIsPaused] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<
        "overview" | "processes" | "console"
    >("overview");

    const [filters, setFilters] = useState({
        cpu: true,
        memory: true,
        disk: false,
        network: false,
    });

    const [processSort, setProcessSort] = useState<{
        key: keyof ProcessInfo;
        desc: boolean;
    }>({ key: "cpu_percent", desc: true });

    const [processFilter, setProcessFilter] = useState("");

    const prevNetworkRef = useRef<{ sent: number; recv: number } | null>(null);
    const prevDiskRef = useRef<{ read: number; write: number } | null>(null);
    const [networkRate, setNetworkRate] = useState<{
        in: number;
        out: number;
    }>({ in: 0, out: 0 });
    const [diskRate, setDiskRate] = useState<{
        read: number;
        write: number;
    }>({ read: 0, write: 0 });

    const fetchStats = useCallback(async () => {
        try {
            const response = await fetch("/api/system/stats");
            if (!response.ok) throw new Error("Failed to fetch stats");
            const data: SystemStats = await response.json();
            setStats(data);

            let networkIn = 0;
            let networkOut = 0;
            if (prevNetworkRef.current) {
                networkIn =
                    (data.network.bytes_recv - prevNetworkRef.current.recv) /
                    (POLL_INTERVAL / 1000);
                networkOut =
                    (data.network.bytes_sent - prevNetworkRef.current.sent) /
                    (POLL_INTERVAL / 1000);
            }
            prevNetworkRef.current = {
                sent: data.network.bytes_sent,
                recv: data.network.bytes_recv,
            };
            setNetworkRate({ in: networkIn, out: networkOut });

            let diskRead = 0;
            let diskWrite = 0;
            if (prevDiskRef.current) {
                diskRead =
                    (data.disk.read_bytes - prevDiskRef.current.read) /
                    (POLL_INTERVAL / 1000);
                diskWrite =
                    (data.disk.write_bytes - prevDiskRef.current.write) /
                    (POLL_INTERVAL / 1000);
            }
            prevDiskRef.current = {
                read: data.disk.read_bytes,
                write: data.disk.write_bytes,
            };
            setDiskRate({ read: diskRead, write: diskWrite });

            setHistory((prev) => {
                const newPoint: HistoryPoint = {
                    timestamp: data.timestamp,
                    cpu: data.cpu.percent_total,
                    memory: data.memory.percent,
                    disk_read: diskRead / 1024 / 1024,
                    disk_write: diskWrite / 1024 / 1024,
                    network_in: networkIn / 1024 / 1024,
                    network_out: networkOut / 1024 / 1024,
                };
                const updated = [...prev, newPoint];
                return updated.slice(-MAX_HISTORY_POINTS);
            });

            setError(null);
        } catch (err) {
            const message =
                err instanceof Error ? err.message : "Unknown error";
            setError(message);
        }
    }, []);

    const fetchProcesses = useCallback(async () => {
        try {
            const response = await fetch("/api/system/processes");
            if (!response.ok) throw new Error("Failed to fetch processes");
            const data = await response.json();
            setProcesses(data.processes);
        } catch {
            // Silently handle fetch errors
        }
    }, []);

    const fetchSystemInfo = useCallback(async () => {
        try {
            const response = await fetch("/api/system/info");
            if (!response.ok) throw new Error("Failed to fetch system info");
            const data = await response.json();
            setSystemInfo(data);
        } catch {
            // Silently handle fetch errors
        }
    }, []);

    useEffect(() => {
        const init = async () => {
            setIsLoading(true);
            await Promise.all([
                fetchStats(),
                fetchProcesses(),
                fetchSystemInfo(),
            ]);
            setIsLoading(false);
        };
        init();
    }, [fetchStats, fetchProcesses, fetchSystemInfo]);

    useEffect(() => {
        if (isPaused) return;

        const interval = setInterval(() => {
            fetchStats();
            if (activeTab === "processes") {
                fetchProcesses();
            }
        }, POLL_INTERVAL);

        return () => clearInterval(interval);
    }, [isPaused, activeTab, fetchStats, fetchProcesses]);

    const sortedProcesses = [...processes]
        .filter(
            (p) =>
                processFilter === "" ||
                p.name.toLowerCase().includes(processFilter.toLowerCase()),
        )
        .sort((a, b) => {
            const aVal = a[processSort.key];
            const bVal = b[processSort.key];
            if (typeof aVal === "number" && typeof bVal === "number") {
                return processSort.desc ? bVal - aVal : aVal - bVal;
            }
            return processSort.desc
                ? String(bVal).localeCompare(String(aVal))
                : String(aVal).localeCompare(String(bVal));
        });

    const handleSort = (key: keyof ProcessInfo) => {
        setProcessSort((prev) => ({
            key,
            desc: prev.key === key ? !prev.desc : true,
        }));
    };

    const chartMetrics = [
        {
            key: "cpu" as const,
            color: "#3b82f6",
            label: "CPU",
            enabled: filters.cpu,
            unit: "%",
            max: 100,
        },
        {
            key: "memory" as const,
            color: "#10b981",
            label: "Memory",
            enabled: filters.memory,
            unit: "%",
            max: 100,
        },
        {
            key: "disk_read" as const,
            color: "#f59e0b",
            label: "Disk Read",
            enabled: filters.disk,
            unit: "MB/s",
            max: 10,
        },
        {
            key: "disk_write" as const,
            color: "#f97316",
            label: "Disk Write",
            enabled: filters.disk,
            unit: "MB/s",
            max: 10,
        },
        {
            key: "network_in" as const,
            color: "#8b5cf6",
            label: "Network In",
            enabled: filters.network,
            unit: "MB/s",
            max: 10,
        },
        {
            key: "network_out" as const,
            color: "#ec4899",
            label: "Network Out",
            enabled: filters.network,
            unit: "MB/s",
            max: 10,
        },
    ];

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Spinner className="w-8 h-8 text-primary-500" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
                        System Monitor
                    </h1>
                    <p className="text-slate-600 dark:text-slate-400">
                        Real-time hardware resource monitoring
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => setIsPaused(!isPaused)}
                        className={cn(
                            "btn-icon",
                            isPaused &&
                                "bg-amber-100 dark:bg-amber-900/30 text-amber-600",
                        )}
                        title={isPaused ? "Resume" : "Pause"}
                    >
                        {isPaused ? (
                            <Icons.Play className="w-5 h-5" />
                        ) : (
                            <Icons.Pause className="w-5 h-5" />
                        )}
                    </button>
                    <button
                        onClick={() => {
                            fetchStats();
                            fetchProcesses();
                            fetchSystemInfo();
                        }}
                        className="btn-icon"
                        title="Refresh"
                    >
                        <Icons.Refresh className="w-5 h-5" />
                    </button>
                </div>
            </div>

            {error && (
                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="bg-rose-50 dark:bg-rose-900/20 border border-rose-200 dark:border-rose-800 rounded-xl p-4"
                >
                    <div className="flex items-center gap-2 text-rose-600 dark:text-rose-400">
                        <Icons.AlertCircle className="w-5 h-5" />
                        <span>{error}</span>
                    </div>
                </motion.div>
            )}

            <div className="flex gap-2 border-b border-slate-200 dark:border-dark-700">
                {[
                    { id: "overview", label: "Overview", icon: Icons.Activity },
                    { id: "processes", label: "Processes", icon: Icons.Cpu },
                    { id: "console", label: "Console", icon: Icons.Terminal },
                ].map((tab) => (
                    <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id as typeof activeTab)}
                        className={cn(
                            "flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 -mb-[2px] transition-colors",
                            activeTab === tab.id
                                ? "border-primary-500 text-primary-600 dark:text-primary-400"
                                : "border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300",
                        )}
                    >
                        <tab.icon className="w-4 h-4" />
                        {tab.label}
                    </button>
                ))}
            </div>

            {activeTab === "overview" && stats && (
                <div className="space-y-6">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="grid grid-cols-2 lg:grid-cols-4 gap-4"
                    >
                        <div className="card p-4">
                            <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center gap-2">
                                    <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-900/30">
                                        <Icons.Cpu className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                                    </div>
                                    <span className="text-sm font-medium text-slate-600 dark:text-slate-400">
                                        CPU
                                    </span>
                                </div>
                                <span className="text-lg font-bold text-slate-900 dark:text-white">
                                    {stats.cpu.percent_total.toFixed(1)}%
                                </span>
                            </div>
                            <div className="h-10 overflow-hidden">
                                <MiniChart
                                    data={history.map((h) => h.cpu)}
                                    color="#3b82f6"
                                />
                            </div>
                            <div className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                                {stats.cpu.count_logical} cores @{" "}
                                {stats.cpu.freq_current.toFixed(0)} MHz
                            </div>
                        </div>

                        <div className="card p-4">
                            <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center gap-2">
                                    <div className="p-2 rounded-lg bg-emerald-100 dark:bg-emerald-900/30">
                                        <Icons.Database className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                                    </div>
                                    <span className="text-sm font-medium text-slate-600 dark:text-slate-400">
                                        Memory
                                    </span>
                                </div>
                                <span className="text-lg font-bold text-slate-900 dark:text-white">
                                    {stats.memory.percent.toFixed(1)}%
                                </span>
                            </div>
                            <div className="h-10 overflow-hidden">
                                <MiniChart
                                    data={history.map((h) => h.memory)}
                                    color="#10b981"
                                />
                            </div>
                            <div className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                                {formatBytes(stats.memory.used)} /{" "}
                                {formatBytes(stats.memory.total)}
                            </div>
                        </div>

                        <div className="card p-4">
                            <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center gap-2">
                                    <div className="p-2 rounded-lg bg-amber-100 dark:bg-amber-900/30">
                                        <Icons.HardDrive className="w-4 h-4 text-amber-600 dark:text-amber-400" />
                                    </div>
                                    <span className="text-sm font-medium text-slate-600 dark:text-slate-400">
                                        Disk
                                    </span>
                                </div>
                                <span className="text-lg font-bold text-slate-900 dark:text-white">
                                    {stats.disk.percent.toFixed(1)}%
                                </span>
                            </div>
                            <div className="space-y-1 mt-3">
                                <div className="flex justify-between text-xs">
                                    <span className="text-slate-500">
                                        ↓ Read
                                    </span>
                                    <span className="font-medium text-slate-700 dark:text-slate-300">
                                        {formatBytes(diskRate.read)}/s
                                    </span>
                                </div>
                                <div className="flex justify-between text-xs">
                                    <span className="text-slate-500">
                                        ↑ Write
                                    </span>
                                    <span className="font-medium text-slate-700 dark:text-slate-300">
                                        {formatBytes(diskRate.write)}/s
                                    </span>
                                </div>
                            </div>
                        </div>

                        <div className="card p-4">
                            <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center gap-2">
                                    <div className="p-2 rounded-lg bg-violet-100 dark:bg-violet-900/30">
                                        <Icons.Wifi className="w-4 h-4 text-violet-600 dark:text-violet-400" />
                                    </div>
                                    <span className="text-sm font-medium text-slate-600 dark:text-slate-400">
                                        Network
                                    </span>
                                </div>
                            </div>
                            <div className="space-y-1 mt-3">
                                <div className="flex justify-between text-xs">
                                    <span className="text-slate-500">↓ In</span>
                                    <span className="font-medium text-slate-700 dark:text-slate-300">
                                        {formatBytes(networkRate.in)}/s
                                    </span>
                                </div>
                                <div className="flex justify-between text-xs">
                                    <span className="text-slate-500">
                                        ↑ Out
                                    </span>
                                    <span className="font-medium text-slate-700 dark:text-slate-300">
                                        {formatBytes(networkRate.out)}/s
                                    </span>
                                </div>
                            </div>
                        </div>
                    </motion.div>

                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.1 }}
                        className="card p-6"
                    >
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="font-semibold text-slate-900 dark:text-white">
                                Resource History
                            </h2>
                            <div className="flex flex-wrap items-center gap-2">
                                <Icons.Filter className="w-4 h-4 text-slate-400" />
                                {Object.entries(filters).map(
                                    ([key, enabled]) => (
                                        <label
                                            key={key}
                                            className={cn(
                                                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg cursor-pointer transition-colors text-sm",
                                                enabled
                                                    ? "bg-slate-100 dark:bg-dark-700"
                                                    : "bg-transparent hover:bg-slate-50 dark:hover:bg-dark-700/50",
                                            )}
                                        >
                                            <input
                                                type="checkbox"
                                                checked={enabled}
                                                onChange={() =>
                                                    setFilters((prev) => ({
                                                        ...prev,
                                                        [key]: !prev[
                                                            key as keyof typeof prev
                                                        ],
                                                    }))
                                                }
                                                className="sr-only"
                                            />
                                            <div
                                                className={cn(
                                                    "w-3 h-3 rounded-sm transition-colors",
                                                    key === "cpu" &&
                                                        "bg-blue-500",
                                                    key === "memory" &&
                                                        "bg-emerald-500",
                                                    key === "disk" &&
                                                        "bg-amber-500",
                                                    key === "network" &&
                                                        "bg-violet-500",
                                                    !enabled && "opacity-30",
                                                )}
                                            />
                                            <span
                                                className={cn(
                                                    "capitalize",
                                                    enabled
                                                        ? "text-slate-700 dark:text-slate-300"
                                                        : "text-slate-400",
                                                )}
                                            >
                                                {key}
                                            </span>
                                        </label>
                                    ),
                                )}
                            </div>
                        </div>

                        <div className="h-[200px]">
                            <InteractiveChart
                                history={history}
                                metrics={chartMetrics}
                            />
                        </div>

                        <div className="flex items-center justify-center gap-4 mt-4">
                            {chartMetrics
                                .filter((m) => m.enabled)
                                .map((metric) => (
                                    <div
                                        key={metric.key}
                                        className="flex items-center gap-1.5 text-xs"
                                    >
                                        <div
                                            className="w-2.5 h-2.5 rounded-full"
                                            style={{
                                                backgroundColor: metric.color,
                                            }}
                                        />
                                        <span className="text-slate-600 dark:text-slate-400">
                                            {metric.label}
                                        </span>
                                    </div>
                                ))}
                        </div>
                    </motion.div>

                    {systemInfo && (
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.2 }}
                            className="card p-6"
                        >
                            <h2 className="font-semibold text-slate-900 dark:text-white mb-4">
                                System Information
                            </h2>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                                <div>
                                    <div className="text-slate-500 dark:text-slate-400">
                                        Hostname
                                    </div>
                                    <div className="font-medium text-slate-900 dark:text-white">
                                        {systemInfo.node}
                                    </div>
                                </div>
                                <div>
                                    <div className="text-slate-500 dark:text-slate-400">
                                        OS
                                    </div>
                                    <div className="font-medium text-slate-900 dark:text-white">
                                        {systemInfo.system} {systemInfo.release}
                                    </div>
                                </div>
                                <div>
                                    <div className="text-slate-500 dark:text-slate-400">
                                        Architecture
                                    </div>
                                    <div className="font-medium text-slate-900 dark:text-white">
                                        {systemInfo.machine}
                                    </div>
                                </div>
                                <div>
                                    <div className="text-slate-500 dark:text-slate-400">
                                        Uptime
                                    </div>
                                    <div className="font-medium text-slate-900 dark:text-white">
                                        {formatUptime(systemInfo.uptime)}
                                    </div>
                                </div>
                                {Object.entries(stats.temperatures).length >
                                    0 && (
                                    <div>
                                        <div className="text-slate-500 dark:text-slate-400">
                                            Temperature
                                        </div>
                                        <div className="font-medium text-slate-900 dark:text-white">
                                            {Object.entries(
                                                stats.temperatures,
                                            ).map(([name, temp]) => (
                                                <span key={name}>
                                                    {temp.toFixed(1)}°C
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                )}
                                <div>
                                    <div className="text-slate-500 dark:text-slate-400">
                                        Load Average
                                    </div>
                                    <div className="font-medium text-slate-900 dark:text-white">
                                        {stats.cpu.load_avg
                                            .map((l) => l.toFixed(2))
                                            .join(" / ")}
                                    </div>
                                </div>
                                <div>
                                    <div className="text-slate-500 dark:text-slate-400">
                                        Disk Usage
                                    </div>
                                    <div className="font-medium text-slate-900 dark:text-white">
                                        {formatBytes(stats.disk.free)} free of{" "}
                                        {formatBytes(stats.disk.total)} (
                                        {stats.disk.percent.toFixed(1)}%)
                                    </div>
                                </div>
                            </div>
                        </motion.div>
                    )}
                </div>
            )}

            {activeTab === "processes" && (
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="card overflow-hidden"
                >
                    <div className="p-4 border-b border-slate-200 dark:border-dark-700">
                        <div className="flex items-center gap-4">
                            <div className="relative flex-1 max-w-md">
                                <input
                                    type="text"
                                    placeholder="Filter processes..."
                                    value={processFilter}
                                    onChange={(e) =>
                                        setProcessFilter(e.target.value)
                                    }
                                    className="input-field pl-10"
                                />
                                <Icons.Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                            </div>
                            <div className="text-sm text-slate-500 dark:text-slate-400 self-center">
                                Showing {sortedProcesses.length} of{" "}
                                {processes.length} processes
                            </div>
                        </div>
                    </div>

                    <div className="overflow-x-auto">
                        <table className="w-full">
                            <thead className="bg-slate-50 dark:bg-dark-800">
                                <tr>
                                    {[
                                        { key: "pid", label: "PID" },
                                        { key: "name", label: "Name" },
                                        { key: "cpu_percent", label: "CPU %" },
                                        {
                                            key: "memory_percent",
                                            label: "Memory %",
                                        },
                                        { key: "status", label: "Status" },
                                        { key: "username", label: "User" },
                                    ].map((col) => (
                                        <th
                                            key={col.key}
                                            onClick={() =>
                                                handleSort(
                                                    col.key as keyof ProcessInfo,
                                                )
                                            }
                                            className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-400 cursor-pointer hover:bg-slate-100 dark:hover:bg-dark-700 transition-colors"
                                        >
                                            <div className="flex items-center gap-1">
                                                {col.label}
                                                {processSort.key ===
                                                    col.key && (
                                                    <Icons.ChevronDown
                                                        className={cn(
                                                            "w-4 h-4 transition-transform",
                                                            !processSort.desc &&
                                                                "rotate-180",
                                                        )}
                                                    />
                                                )}
                                            </div>
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-200 dark:divide-dark-700">
                                {processes.length === 0 ? (
                                    <tr>
                                        <td
                                            colSpan={6}
                                            className="px-4 py-12 text-center"
                                        >
                                            <div className="flex flex-col items-center gap-3">
                                                <Spinner className="w-8 h-8 text-primary-500" />
                                                <span className="text-slate-500 dark:text-slate-400">
                                                    Loading processes...
                                                </span>
                                            </div>
                                        </td>
                                    </tr>
                                ) : sortedProcesses.length === 0 ? (
                                    <tr>
                                        <td
                                            colSpan={6}
                                            className="px-4 py-12 text-center text-slate-500 dark:text-slate-400"
                                        >
                                            No processes match the filter
                                        </td>
                                    </tr>
                                ) : null}
                                {sortedProcesses.slice(0, 30).map((proc) => (
                                    <tr
                                        key={proc.pid}
                                        className="hover:bg-slate-50 dark:hover:bg-dark-700/30 transition-colors"
                                    >
                                        <td className="px-4 py-3 text-slate-600 dark:text-slate-400 font-mono text-sm">
                                            {proc.pid}
                                        </td>
                                        <td className="px-4 py-3 font-medium text-slate-900 dark:text-white">
                                            {proc.name}
                                        </td>
                                        <td className="px-4 py-3">
                                            <div className="flex items-center gap-2">
                                                <div className="w-16 h-1.5 bg-slate-200 dark:bg-dark-600 rounded-full overflow-hidden">
                                                    <div
                                                        className={cn(
                                                            "h-1.5 rounded-full",
                                                            proc.cpu_percent >
                                                                50
                                                                ? "bg-rose-500"
                                                                : proc.cpu_percent >
                                                                    20
                                                                  ? "bg-amber-500"
                                                                  : "bg-blue-500",
                                                        )}
                                                        style={{
                                                            width: `${Math.min(proc.cpu_percent, 100)}%`,
                                                        }}
                                                    />
                                                </div>
                                                <span className="text-slate-600 dark:text-slate-400 w-12 text-right">
                                                    {proc.cpu_percent.toFixed(
                                                        1,
                                                    )}
                                                </span>
                                            </div>
                                        </td>
                                        <td className="px-4 py-3">
                                            <div className="flex items-center gap-2">
                                                <div className="w-16 h-1.5 bg-slate-200 dark:bg-dark-600 rounded-full overflow-hidden">
                                                    <div
                                                        className={cn(
                                                            "h-1.5 rounded-full",
                                                            proc.memory_percent >
                                                                50
                                                                ? "bg-rose-500"
                                                                : proc.memory_percent >
                                                                    20
                                                                  ? "bg-amber-500"
                                                                  : "bg-emerald-500",
                                                        )}
                                                        style={{
                                                            width: `${Math.min(proc.memory_percent, 100)}%`,
                                                        }}
                                                    />
                                                </div>
                                                <span className="text-slate-600 dark:text-slate-400 w-12 text-right">
                                                    {proc.memory_percent.toFixed(
                                                        1,
                                                    )}
                                                </span>
                                            </div>
                                        </td>
                                        <td className="px-4 py-3">
                                            <span
                                                className={cn(
                                                    "px-2 py-0.5 rounded-full text-xs font-medium",
                                                    proc.status === "running" &&
                                                        "bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400",
                                                    proc.status ===
                                                        "sleeping" &&
                                                        "bg-slate-100 dark:bg-slate-700/50 text-slate-600 dark:text-slate-400",
                                                    proc.status === "stopped" &&
                                                        "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400",
                                                    proc.status === "zombie" &&
                                                        "bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-400",
                                                )}
                                            >
                                                {proc.status}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 text-slate-600 dark:text-slate-400">
                                            {proc.username}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </motion.div>
            )}

            <div className={activeTab === "console" ? "" : "hidden"}>
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="card overflow-hidden"
                >
                    <div className="p-4 border-b border-slate-200 dark:border-dark-700 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <Icons.Terminal className="w-5 h-5 text-slate-500" />
                            <h2 className="font-semibold text-slate-900 dark:text-white">
                                System Terminal
                            </h2>
                        </div>
                    </div>
                    <div className="h-[500px] bg-[#0f172a]">
                        <Terminal />
                    </div>
                </motion.div>
            </div>
        </div>
    );
};

export default SystemMonitor;
