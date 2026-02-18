import React from "react";
import { Icons, Spinner } from "../Icons";
import { cn } from "../../lib/utils";
import type { GalleryImage } from "../../hooks/useApi";

interface GalleryTabProps {
    galleryImages: GalleryImage[];
    isUploadingImage: boolean;
    isDraggingOver: boolean;
    onDragOver: (e: React.DragEvent<HTMLDivElement>) => void;
    onDragLeave: (e: React.DragEvent<HTMLDivElement>) => void;
    onDrop: (e: React.DragEvent<HTMLDivElement>) => void;
    onImageUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
    onDeleteImage: (filename: string) => void;
    onSelectImage: (image: GalleryImage) => void;
}

const GalleryTab: React.FC<GalleryTabProps> = ({
    galleryImages,
    isUploadingImage,
    isDraggingOver,
    onDragOver,
    onDragLeave,
    onDrop,
    onImageUpload,
    onDeleteImage,
    onSelectImage,
}) => {
    return (
        <div className="space-y-6">
            {/* Upload */}
            <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">
                    Upload
                </h3>
                <div
                    onDragOver={onDragOver}
                    onDragLeave={onDragLeave}
                    onDrop={onDrop}
                    className={cn(
                        "text-center py-8 border-2 border-dashed rounded-xl cursor-pointer transition-all duration-200",
                        isDraggingOver
                            ? "border-violet-500 bg-violet-50 dark:bg-violet-900/20 scale-[1.02]"
                            : "border-slate-200 dark:border-dark-600 hover:border-slate-300 dark:hover:border-dark-500",
                    )}
                    onClick={() =>
                        document
                            .getElementById("gallery-file-input")
                            ?.click()
                    }
                >
                    {isUploadingImage ? (
                        <>
                            <Spinner size="md" className="mx-auto mb-2" />
                            <p className="text-sm text-slate-500 dark:text-slate-400">
                                Uploading...
                            </p>
                        </>
                    ) : isDraggingOver ? (
                        <>
                            <Icons.Upload className="w-8 h-8 mx-auto text-violet-500 mb-2 animate-bounce" />
                            <p className="text-sm font-medium text-violet-600 dark:text-violet-400">
                                Drop images here
                            </p>
                        </>
                    ) : (
                        <>
                            <Icons.Upload className="w-8 h-8 mx-auto text-slate-300 dark:text-dark-500 mb-2" />
                            <p className="text-sm text-slate-500 dark:text-slate-400">
                                {galleryImages.length === 0
                                    ? "No images uploaded yet"
                                    : "Drag & drop images here, or click to browse"}
                            </p>
                            {galleryImages.length === 0 && (
                                <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                                    Drag & drop images here, or click to browse
                                </p>
                            )}
                            <p className="text-xs text-slate-400 dark:text-slate-500 mt-2">
                                Accepted: JPEG, PNG, GIF, BMP, WebP (max 50MB)
                            </p>
                        </>
                    )}
                    <input
                        id="gallery-file-input"
                        type="file"
                        accept="image/jpeg,image/png,image/gif,image/bmp,image/webp"
                        multiple
                        onChange={onImageUpload}
                        className="hidden"
                        disabled={isUploadingImage}
                    />
                </div>
            </div>

            {/* Images Grid */}
            {galleryImages.length > 0 && (
                <div className="border-t border-slate-200 dark:border-slate-700 pt-6">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">
                        Images
                    </h3>
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2 sm:gap-3">
                        {galleryImages.map((image) => (
                            <div
                                key={image.name}
                                className="relative group aspect-square rounded-lg overflow-hidden bg-slate-100 dark:bg-dark-700 cursor-pointer"
                                onClick={() => onSelectImage(image)}
                            >
                                <img
                                    src={image.path}
                                    alt={image.name}
                                    className="w-full h-full object-cover transition-transform duration-200 group-hover:scale-105"
                                />
                                <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors" />
                                <button
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        onDeleteImage(image.name);
                                    }}
                                    className="absolute top-1 right-1 p-1.5 rounded-lg bg-black/50 text-white opacity-0 group-hover:opacity-100 transition-opacity hover:bg-rose-500"
                                >
                                    <Icons.X className="w-3 h-3" />
                                </button>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};

export default GalleryTab;
