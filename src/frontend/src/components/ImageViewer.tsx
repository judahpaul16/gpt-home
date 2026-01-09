import { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "../lib/utils";
import { Icons } from "./Icons";

interface ImageViewerProps {
    src: string;
    alt: string;
    isOpen: boolean;
    onClose: () => void;
}

const ImageViewer = ({ src, alt, isOpen, onClose }: ImageViewerProps) => {
    const [zoom, setZoom] = useState(1);
    const [rotation, setRotation] = useState(0);
    const [isDrawing, setIsDrawing] = useState(false);
    const [isCropping, setIsCropping] = useState(false);
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [position, setPosition] = useState({ x: 0, y: 0 });
    const [isDragging, setIsDragging] = useState(false);
    const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
    const [drawingPaths, setDrawingPaths] = useState<string[]>([]);
    const [currentPath, setCurrentPath] = useState<string>("");
    const [drawColor, setDrawColor] = useState("#ef4444");
    const [strokeWidth, setStrokeWidth] = useState(3);
    const [isSaving, setIsSaving] = useState(false);
    const [cropStart, setCropStart] = useState<{ x: number; y: number } | null>(
        null,
    );
    const [cropEnd, setCropEnd] = useState<{ x: number; y: number } | null>(
        null,
    );
    const [isCropDragging, setIsCropDragging] = useState(false);

    const containerRef = useRef<HTMLDivElement>(null);
    const canvasRef = useRef<SVGSVGElement>(null);
    const imageRef = useRef<HTMLImageElement>(null);

    const minZoom = 0.5;
    const maxZoom = 5;
    const zoomStep = 0.25;

    useEffect(() => {
        if (isOpen) {
            setZoom(1);
            setRotation(0);
            setPosition({ x: 0, y: 0 });
            setDrawingPaths([]);
            setCurrentPath("");
            setIsDrawing(false);
            setIsCropping(false);
            setCropStart(null);
            setCropEnd(null);
        }
    }, [isOpen, src]);

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (!isOpen) return;

            switch (e.key) {
                case "Escape":
                    if (isFullscreen) {
                        exitFullscreen();
                    } else {
                        onClose();
                    }
                    break;
                case "+":
                case "=":
                    handleZoomIn();
                    break;
                case "-":
                    handleZoomOut();
                    break;
                case "r":
                case "R":
                    handleRotate();
                    break;
            }
        };

        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, [isOpen, isFullscreen, onClose]);

    useEffect(() => {
        const handleFullscreenChange = () => {
            setIsFullscreen(!!document.fullscreenElement);
        };

        document.addEventListener("fullscreenchange", handleFullscreenChange);
        return () =>
            document.removeEventListener(
                "fullscreenchange",
                handleFullscreenChange,
            );
    }, []);

    const handleZoomIn = () => {
        setZoom((prev) => Math.min(prev + zoomStep, maxZoom));
    };

    const handleZoomOut = () => {
        setZoom((prev) => Math.max(prev - zoomStep, minZoom));
    };

    const handleRotate = () => {
        setRotation((prev) => (prev + 90) % 360);
    };

    const handleResetView = () => {
        setZoom(1);
        setRotation(0);
        setPosition({ x: 0, y: 0 });
    };

    const toggleFullscreen = async () => {
        if (!containerRef.current) return;

        try {
            if (!document.fullscreenElement) {
                await containerRef.current.requestFullscreen();
            } else {
                await document.exitFullscreen();
            }
        } catch (err) {
            console.error("Fullscreen error:", err);
        }
    };

    const exitFullscreen = async () => {
        if (document.fullscreenElement) {
            try {
                await document.exitFullscreen();
            } catch (err) {
                console.error("Exit fullscreen error:", err);
            }
        }
    };

    const handleWheel = useCallback(
        (e: React.WheelEvent) => {
            if (isDrawing) return;
            e.preventDefault();
            const delta = e.deltaY > 0 ? -zoomStep : zoomStep;
            setZoom((prev) =>
                Math.min(Math.max(prev + delta, minZoom), maxZoom),
            );
        },
        [isDrawing],
    );

    const handleMouseDown = (e: React.MouseEvent) => {
        if (isCropping) {
            const coords = getDrawCoordinates(e.clientX, e.clientY);
            if (coords) {
                setCropStart(coords);
                setCropEnd(coords);
                setIsCropDragging(true);
            }
        } else if (isDrawing) {
            startDrawing(e);
        } else if (zoom > 1) {
            setIsDragging(true);
            setDragStart({
                x: e.clientX - position.x,
                y: e.clientY - position.y,
            });
        }
    };

    const handleMouseMove = (e: React.MouseEvent) => {
        if (isCropping && isCropDragging) {
            const coords = getDrawCoordinates(e.clientX, e.clientY);
            if (coords) setCropEnd(coords);
        } else if (isDrawing && currentPath) {
            continueDrawing(e);
        } else if (isDragging && zoom > 1) {
            setPosition({
                x: e.clientX - dragStart.x,
                y: e.clientY - dragStart.y,
            });
        }
    };

    const handleMouseUp = () => {
        if (isDrawing && currentPath) {
            finishDrawing();
        }
        setIsDragging(false);
        setIsCropDragging(false);
    };

    const handleTouchStart = (e: React.TouchEvent) => {
        if (e.touches.length === 1) {
            const touch = e.touches[0];
            if (isDrawing) {
                startDrawingTouch(touch);
            } else if (zoom > 1) {
                setIsDragging(true);
                setDragStart({
                    x: touch.clientX - position.x,
                    y: touch.clientY - position.y,
                });
            }
        }
    };

    const handleTouchMove = (e: React.TouchEvent) => {
        if (e.touches.length === 1) {
            const touch = e.touches[0];
            if (isDrawing && currentPath) {
                continueDrawingTouch(touch);
            } else if (isDragging && zoom > 1) {
                setPosition({
                    x: touch.clientX - dragStart.x,
                    y: touch.clientY - dragStart.y,
                });
            }
        }
    };

    const handleTouchEnd = () => {
        if (isDrawing && currentPath) {
            finishDrawing();
        }
        setIsDragging(false);
    };

    const getDrawCoordinates = (
        clientX: number,
        clientY: number,
    ): { x: number; y: number } | null => {
        if (!imageRef.current) return null;

        const rect = imageRef.current.getBoundingClientRect();
        let x = ((clientX - rect.left) / rect.width) * 100;
        let y = ((clientY - rect.top) / rect.height) * 100;

        // Clamp to image bounds
        x = Math.max(0, Math.min(100, x));
        y = Math.max(0, Math.min(100, y));

        return { x, y };
    };

    const startDrawing = (e: React.MouseEvent) => {
        const coords = getDrawCoordinates(e.clientX, e.clientY);
        if (!coords) return;
        setCurrentPath(`M ${coords.x} ${coords.y}`);
    };

    const startDrawingTouch = (touch: React.Touch) => {
        const coords = getDrawCoordinates(touch.clientX, touch.clientY);
        if (!coords) return;
        setCurrentPath(`M ${coords.x} ${coords.y}`);
    };

    const continueDrawing = (e: React.MouseEvent) => {
        const coords = getDrawCoordinates(e.clientX, e.clientY);
        if (!coords) return;
        setCurrentPath((prev) => `${prev} L ${coords.x} ${coords.y}`);
    };

    const continueDrawingTouch = (touch: React.Touch) => {
        const coords = getDrawCoordinates(touch.clientX, touch.clientY);
        if (!coords) return;
        setCurrentPath((prev) => `${prev} L ${coords.x} ${coords.y}`);
    };

    const finishDrawing = () => {
        if (currentPath) {
            setDrawingPaths((prev) => [
                ...prev,
                JSON.stringify({
                    path: currentPath,
                    color: drawColor,
                    width: strokeWidth,
                }),
            ]);
            setCurrentPath("");
        }
    };

    const clearDrawings = () => {
        setDrawingPaths([]);
        setCurrentPath("");
    };

    const undoLastDrawing = () => {
        setDrawingPaths((prev) => prev.slice(0, -1));
    };

    const applyCrop = async () => {
        if (!cropStart || !cropEnd || !imageRef.current) return;

        const img = imageRef.current;
        const minX = Math.min(cropStart.x, cropEnd.x);
        const maxX = Math.max(cropStart.x, cropEnd.x);
        const minY = Math.min(cropStart.y, cropEnd.y);
        const maxY = Math.max(cropStart.y, cropEnd.y);

        const cropX = (minX / 100) * img.naturalWidth;
        const cropY = (minY / 100) * img.naturalHeight;
        const cropW = ((maxX - minX) / 100) * img.naturalWidth;
        const cropH = ((maxY - minY) / 100) * img.naturalHeight;

        if (cropW < 10 || cropH < 10) {
            setCropStart(null);
            setCropEnd(null);
            return;
        }

        const canvas = document.createElement("canvas");
        canvas.width = cropW;
        canvas.height = cropH;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        ctx.drawImage(img, cropX, cropY, cropW, cropH, 0, 0, cropW, cropH);

        setIsSaving(true);
        try {
            const blob = await new Promise<Blob | null>((resolve) =>
                canvas.toBlob(resolve, "image/png"),
            );
            if (!blob) throw new Error("Failed to create blob");

            const formData = new FormData();
            formData.append("file", blob, alt || "image.png");

            const response = await fetch(
                `/api/gallery/save?path=${encodeURIComponent(src)}`,
                {
                    method: "POST",
                    body: formData,
                },
            );

            if (!response.ok) throw new Error("Failed to save");

            // Force reload image
            if (imageRef.current) {
                imageRef.current.src = src + "?t=" + Date.now();
            }
        } catch (error) {
            console.error("Crop failed:", error);
        } finally {
            setIsSaving(false);
            setIsCropping(false);
            setCropStart(null);
            setCropEnd(null);
        }
    };

    const cancelCrop = () => {
        setCropStart(null);
        setCropEnd(null);
        setIsCropping(false);
    };

    const renderToCanvas = (): HTMLCanvasElement | null => {
        if (!imageRef.current) return null;

        const canvas = document.createElement("canvas");
        const img = imageRef.current;
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;

        const ctx = canvas.getContext("2d");
        if (!ctx) return null;

        // Draw the original image
        ctx.drawImage(img, 0, 0);

        // Draw all paths
        drawingPaths.forEach((pathData) => {
            const { path, color, width } = JSON.parse(pathData);
            const pathCommands = path.split(/(?=[ML])/);

            ctx.beginPath();
            ctx.strokeStyle = color;
            ctx.lineWidth = (width || 3) * (img.naturalWidth / 100);
            ctx.lineCap = "round";
            ctx.lineJoin = "round";

            pathCommands.forEach((cmd: string) => {
                const parts = cmd.trim().split(" ");
                if (parts[0] === "M") {
                    const x = (parseFloat(parts[1]) / 100) * img.naturalWidth;
                    const y = (parseFloat(parts[2]) / 100) * img.naturalHeight;
                    ctx.moveTo(x, y);
                } else if (parts[0] === "L") {
                    const x = (parseFloat(parts[1]) / 100) * img.naturalWidth;
                    const y = (parseFloat(parts[2]) / 100) * img.naturalHeight;
                    ctx.lineTo(x, y);
                }
            });
            ctx.stroke();
        });

        return canvas;
    };

    const downloadImage = () => {
        const canvas = renderToCanvas();
        if (!canvas) return;

        const link = document.createElement("a");
        link.download = `edited-${alt || "image"}.png`;
        link.href = canvas.toDataURL("image/png");
        link.click();
    };

    const saveToServer = async () => {
        const canvas = renderToCanvas();
        if (!canvas) return;

        setIsSaving(true);
        try {
            const blob = await new Promise<Blob | null>((resolve) =>
                canvas.toBlob(resolve, "image/png"),
            );
            if (!blob) throw new Error("Failed to create blob");

            const formData = new FormData();
            formData.append("file", blob, alt || "image.png");

            const response = await fetch(
                `/api/gallery/save?path=${encodeURIComponent(src)}`,
                {
                    method: "POST",
                    body: formData,
                },
            );

            if (!response.ok) throw new Error("Failed to save");

            setDrawingPaths([]);
            setCurrentPath("");
        } catch (error) {
            console.error("Save failed:", error);
        } finally {
            setIsSaving(false);
        }
    };

    const colors = [
        "#ef4444",
        "#f97316",
        "#eab308",
        "#22c55e",
        "#3b82f6",
        "#8b5cf6",
        "#ec4899",
        "#ffffff",
        "#000000",
    ];

    if (!isOpen) return null;

    return (
        <AnimatePresence>
            {isOpen && (
                <motion.div
                    ref={containerRef}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="fixed inset-0 z-50 bg-black/95 flex flex-col"
                    onClick={(e) => {
                        if (e.target === e.currentTarget) onClose();
                    }}
                >
                    {/* Top Toolbar */}
                    <div className="flex items-center justify-between p-2 sm:p-4 bg-black/50 backdrop-blur-sm">
                        <div className="flex items-center gap-1 sm:gap-2">
                            {/* Zoom Controls */}
                            <button
                                onClick={handleZoomOut}
                                disabled={zoom <= minZoom}
                                className="p-2 sm:p-2.5 rounded-lg bg-white/10 hover:bg-white/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                title="Zoom Out (-)"
                            >
                                <Icons.ZoomOut className="w-4 h-4 sm:w-5 sm:h-5 text-white" />
                            </button>
                            <span className="text-white text-xs sm:text-sm font-medium min-w-[3rem] sm:min-w-[4rem] text-center">
                                {Math.round(zoom * 100)}%
                            </span>
                            <button
                                onClick={handleZoomIn}
                                disabled={zoom >= maxZoom}
                                className="p-2 sm:p-2.5 rounded-lg bg-white/10 hover:bg-white/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                title="Zoom In (+)"
                            >
                                <Icons.ZoomIn className="w-4 h-4 sm:w-5 sm:h-5 text-white" />
                            </button>

                            <div className="w-px h-6 bg-white/20 mx-1 sm:mx-2 hidden xs:block" />

                            {/* Rotate */}
                            <button
                                onClick={handleRotate}
                                className="p-2 sm:p-2.5 rounded-lg bg-white/10 hover:bg-white/20 transition-colors"
                                title="Rotate (R)"
                            >
                                <Icons.RotateCw className="w-4 h-4 sm:w-5 sm:h-5 text-white" />
                            </button>

                            {/* Reset View */}
                            <button
                                onClick={handleResetView}
                                className="p-2 sm:p-2.5 rounded-lg bg-white/10 hover:bg-white/20 transition-colors"
                                title="Reset View"
                            >
                                <Icons.Refresh className="w-4 h-4 sm:w-5 sm:h-5 text-white" />
                            </button>

                            <div className="w-px h-6 bg-white/20 mx-1 sm:mx-2 hidden xs:block" />

                            {/* Draw Toggle */}
                            <button
                                onClick={() => {
                                    setIsDrawing(!isDrawing);
                                    if (!isDrawing) setIsCropping(false);
                                }}
                                className={cn(
                                    "p-2 sm:p-2.5 rounded-lg transition-colors",
                                    isDrawing
                                        ? "bg-violet-500 hover:bg-violet-600"
                                        : "bg-white/10 hover:bg-white/20",
                                )}
                                title="Draw Mode"
                            >
                                <Icons.Pencil className="w-4 h-4 sm:w-5 sm:h-5 text-white" />
                            </button>

                            {/* Crop Toggle */}
                            <button
                                onClick={() => {
                                    setIsCropping(!isCropping);
                                    if (!isCropping) {
                                        setIsDrawing(false);
                                        setCropStart(null);
                                        setCropEnd(null);
                                    }
                                }}
                                className={cn(
                                    "p-2 sm:p-2.5 rounded-lg transition-colors",
                                    isCropping
                                        ? "bg-orange-500 hover:bg-orange-600"
                                        : "bg-white/10 hover:bg-white/20",
                                )}
                                title="Crop Mode"
                            >
                                <Icons.Crop className="w-4 h-4 sm:w-5 sm:h-5 text-white" />
                            </button>
                        </div>

                        <div className="flex items-center gap-1 sm:gap-2">
                            {/* Fullscreen */}
                            <button
                                onClick={toggleFullscreen}
                                className="p-2 sm:p-2.5 rounded-lg bg-white/10 hover:bg-white/20 transition-colors"
                                title="Toggle Fullscreen"
                            >
                                {isFullscreen ? (
                                    <Icons.Minimize className="w-4 h-4 sm:w-5 sm:h-5 text-white" />
                                ) : (
                                    <Icons.Maximize className="w-4 h-4 sm:w-5 sm:h-5 text-white" />
                                )}
                            </button>

                            {/* Close */}
                            <button
                                onClick={onClose}
                                className="p-2 sm:p-2.5 rounded-lg bg-white/10 hover:bg-rose-500 transition-colors"
                                title="Close (Esc)"
                            >
                                <Icons.X className="w-4 h-4 sm:w-5 sm:h-5 text-white" />
                            </button>
                        </div>
                    </div>

                    {/* Drawing Tools (shown when draw mode is active) */}
                    <AnimatePresence>
                        {isDrawing && (
                            <motion.div
                                initial={{ opacity: 0, y: -10 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, y: -10 }}
                                className="flex items-center justify-center gap-2 sm:gap-3 p-2 bg-black/50 backdrop-blur-sm"
                            >
                                <div className="flex items-center gap-1">
                                    {colors.map((color) => (
                                        <button
                                            key={color}
                                            onClick={() => setDrawColor(color)}
                                            className={cn(
                                                "w-6 h-6 sm:w-7 sm:h-7 rounded-full border-2 transition-transform hover:scale-110",
                                                drawColor === color
                                                    ? "border-white scale-110"
                                                    : "border-transparent",
                                            )}
                                            style={{ backgroundColor: color }}
                                        />
                                    ))}
                                </div>

                                <div className="w-px h-6 bg-white/20" />

                                {/* Stroke Width */}
                                <div className="flex items-center gap-2">
                                    <span className="text-white/70 text-xs hidden sm:inline">
                                        Width:
                                    </span>
                                    <input
                                        type="range"
                                        min="1"
                                        max="10"
                                        value={strokeWidth}
                                        onChange={(e) =>
                                            setStrokeWidth(
                                                Number(e.target.value),
                                            )
                                        }
                                        className="w-16 sm:w-20 h-1.5 bg-white/20 rounded-lg appearance-none cursor-pointer accent-violet-500"
                                    />
                                    <span className="text-white text-xs min-w-[1.5rem]">
                                        {strokeWidth}
                                    </span>
                                </div>

                                <div className="w-px h-6 bg-white/20" />

                                <button
                                    onClick={undoLastDrawing}
                                    disabled={drawingPaths.length === 0}
                                    className="px-2 sm:px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-white text-xs sm:text-sm"
                                >
                                    Undo
                                </button>
                                <button
                                    onClick={clearDrawings}
                                    disabled={drawingPaths.length === 0}
                                    className="px-2 sm:px-3 py-1.5 rounded-lg bg-white/10 hover:bg-rose-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-white text-xs sm:text-sm"
                                >
                                    Clear
                                </button>

                                <div className="w-px h-6 bg-white/20" />

                                <button
                                    onClick={downloadImage}
                                    className="px-2 sm:px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 transition-colors text-white text-xs sm:text-sm flex items-center gap-1"
                                >
                                    <Icons.ArrowDown className="w-3 h-3 sm:w-4 sm:h-4" />
                                    Download
                                </button>

                                <button
                                    onClick={saveToServer}
                                    disabled={
                                        drawingPaths.length === 0 || isSaving
                                    }
                                    className="px-2 sm:px-3 py-1.5 rounded-lg bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-white text-xs sm:text-sm flex items-center gap-1"
                                >
                                    <Icons.Save className="w-3 h-3 sm:w-4 sm:h-4" />
                                    {isSaving ? "Saving..." : "Save"}
                                </button>
                            </motion.div>
                        )}
                    </AnimatePresence>

                    {/* Crop Tools (shown when crop mode is active) */}
                    <AnimatePresence>
                        {isCropping && (
                            <motion.div
                                initial={{ opacity: 0, y: -10 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, y: -10 }}
                                className="flex items-center justify-center gap-2 sm:gap-3 p-2 bg-black/50 backdrop-blur-sm"
                            >
                                <span className="text-white/70 text-xs sm:text-sm">
                                    {cropStart && cropEnd
                                        ? "Drag to adjust selection"
                                        : "Click and drag to select area"}
                                </span>

                                {cropStart && cropEnd && (
                                    <>
                                        <div className="w-px h-6 bg-white/20" />
                                        <button
                                            onClick={applyCrop}
                                            disabled={isSaving}
                                            className="px-2 sm:px-3 py-1.5 rounded-lg bg-green-600 hover:bg-green-700 disabled:opacity-50 transition-colors text-white text-xs sm:text-sm"
                                        >
                                            {isSaving
                                                ? "Cropping..."
                                                : "Apply Crop"}
                                        </button>
                                        <button
                                            onClick={cancelCrop}
                                            className="px-2 sm:px-3 py-1.5 rounded-lg bg-white/10 hover:bg-rose-500 transition-colors text-white text-xs sm:text-sm"
                                        >
                                            Cancel
                                        </button>
                                    </>
                                )}
                            </motion.div>
                        )}
                    </AnimatePresence>

                    {/* Image Container */}
                    <div
                        className={cn(
                            "flex-1 flex items-center justify-center overflow-hidden",
                            isCropping
                                ? "cursor-crosshair"
                                : isDrawing
                                  ? "cursor-crosshair"
                                  : zoom > 1
                                    ? "cursor-grab"
                                    : "cursor-default",
                            isDragging && "cursor-grabbing",
                        )}
                        onWheel={handleWheel}
                        onMouseDown={handleMouseDown}
                        onMouseMove={handleMouseMove}
                        onMouseUp={handleMouseUp}
                        onMouseLeave={handleMouseUp}
                        onTouchStart={handleTouchStart}
                        onTouchMove={handleTouchMove}
                        onTouchEnd={handleTouchEnd}
                    >
                        <div
                            className="relative max-w-full max-h-full"
                            style={{
                                transform: `translate(${position.x}px, ${position.y}px) scale(${zoom}) rotate(${rotation}deg)`,
                                transition: isDragging
                                    ? "none"
                                    : "transform 0.2s ease-out",
                            }}
                        >
                            <img
                                ref={imageRef}
                                src={src}
                                alt={alt}
                                crossOrigin="anonymous"
                                className="max-w-[90vw] max-h-[80vh] object-contain select-none"
                                draggable={false}
                            />

                            {/* Drawing SVG Overlay */}
                            {(drawingPaths.length > 0 || currentPath) && (
                                <svg
                                    ref={canvasRef}
                                    className="absolute inset-0 w-full h-full pointer-events-none"
                                    viewBox="0 0 100 100"
                                    preserveAspectRatio="none"
                                >
                                    {drawingPaths.map((pathData, index) => {
                                        const { path, color, width } =
                                            JSON.parse(pathData);
                                        return (
                                            <path
                                                key={index}
                                                d={path}
                                                fill="none"
                                                stroke={color}
                                                strokeWidth={width || 3}
                                                strokeLinecap="round"
                                                strokeLinejoin="round"
                                                vectorEffect="non-scaling-stroke"
                                            />
                                        );
                                    })}
                                    {currentPath &&
                                        currentPath.includes(" L ") && (
                                            <path
                                                d={currentPath}
                                                fill="none"
                                                stroke={drawColor}
                                                strokeWidth={strokeWidth}
                                                strokeLinecap="round"
                                                strokeLinejoin="round"
                                                vectorEffect="non-scaling-stroke"
                                            />
                                        )}
                                </svg>
                            )}

                            {/* Crop Selection Overlay */}
                            {isCropping && cropStart && cropEnd && (
                                <div
                                    className="absolute pointer-events-none"
                                    style={{
                                        left: `${Math.min(cropStart.x, cropEnd.x)}%`,
                                        top: `${Math.min(cropStart.y, cropEnd.y)}%`,
                                        width: `${Math.abs(cropEnd.x - cropStart.x)}%`,
                                        height: `${Math.abs(cropEnd.y - cropStart.y)}%`,
                                        border: "2px dashed #fff",
                                        boxShadow:
                                            "0 0 0 9999px rgba(0, 0, 0, 0.5)",
                                    }}
                                />
                            )}
                        </div>
                    </div>

                    {/* Image Info */}
                    <div className="p-2 sm:p-3 bg-black/50 backdrop-blur-sm text-center">
                        <p className="text-white/70 text-xs sm:text-sm truncate px-4">
                            {alt}
                        </p>
                    </div>
                </motion.div>
            )}
        </AnimatePresence>
    );
};

export default ImageViewer;
