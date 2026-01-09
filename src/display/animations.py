import asyncio
import math
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional, Tuple

from .base import Color, Colors


class Easing(Enum):
    LINEAR = "linear"
    EASE_IN = "ease_in"
    EASE_OUT = "ease_out"
    EASE_IN_OUT = "ease_in_out"
    BOUNCE = "bounce"
    ELASTIC = "elastic"


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    size: float
    color: Color


class AnimationController:
    @staticmethod
    def ease(t: float, easing: Easing = Easing.LINEAR) -> float:
        t = max(0.0, min(1.0, t))

        if easing == Easing.LINEAR:
            return t
        elif easing == Easing.EASE_IN:
            return t * t * t
        elif easing == Easing.EASE_OUT:
            return 1 - (1 - t) ** 3
        elif easing == Easing.EASE_IN_OUT:
            if t < 0.5:
                return 4 * t * t * t
            return 1 - ((-2 * t + 2) ** 3) / 2
        elif easing == Easing.BOUNCE:
            if t < 1 / 2.75:
                return 7.5625 * t * t
            elif t < 2 / 2.75:
                t -= 1.5 / 2.75
                return 7.5625 * t * t + 0.75
            elif t < 2.5 / 2.75:
                t -= 2.25 / 2.75
                return 7.5625 * t * t + 0.9375
            else:
                t -= 2.625 / 2.75
                return 7.5625 * t * t + 0.984375
        elif easing == Easing.ELASTIC:
            if t == 0 or t == 1:
                return t
            return -(2 ** (10 * t - 10)) * math.sin(
                (t * 10 - 10.75) * (2 * math.pi) / 3
            )
        return t

    @staticmethod
    def interpolate(
        start: float, end: float, t: float, easing: Easing = Easing.EASE_OUT
    ) -> float:
        return start + (end - start) * AnimationController.ease(t, easing)

    @staticmethod
    def interpolate_color(
        start: Color, end: Color, t: float, easing: Easing = Easing.EASE_OUT
    ) -> Color:
        t = AnimationController.ease(t, easing)
        return Color(
            r=int(start.r + (end.r - start.r) * t),
            g=int(start.g + (end.g - start.g) * t),
            b=int(start.b + (end.b - start.b) * t),
        )


class ParticleSystem:
    def __init__(self, max_particles: int = 100):
        self.particles: List[Particle] = []
        self.max_particles = max_particles

    def emit(
        self,
        x: float,
        y: float,
        count: int = 1,
        velocity_range: Tuple[float, float] = (-2, 2),
        life_range: Tuple[float, float] = (0.5, 2.0),
        size_range: Tuple[float, float] = (2, 6),
        color: Color = Colors.WHITE,
        direction: Optional[float] = None,
        spread: float = math.pi * 2,
    ) -> None:
        for _ in range(count):
            if len(self.particles) >= self.max_particles:
                break

            if direction is not None:
                angle = direction + random.uniform(-spread / 2, spread / 2)
            else:
                angle = random.uniform(0, math.pi * 2)

            speed = random.uniform(velocity_range[0], velocity_range[1])
            life = random.uniform(life_range[0], life_range[1])
            size = random.uniform(size_range[0], size_range[1])

            self.particles.append(
                Particle(
                    x=x,
                    y=y,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed,
                    life=life,
                    max_life=life,
                    size=size,
                    color=color,
                )
            )

    def update(self, dt: float, gravity: float = 0) -> None:
        alive = []
        for p in self.particles:
            p.x += p.vx * dt * 60
            p.y += p.vy * dt * 60
            p.vy += gravity * dt
            p.life -= dt
            if p.life > 0:
                alive.append(p)
        self.particles = alive

    def clear(self) -> None:
        self.particles = []


class WeatherEffects:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.raindrops: List[dict] = []
        self.snowflakes: List[dict] = []
        self.clouds: List[dict] = []
        self.sun_rays: List[dict] = []
        self.lightning_flash = 0.0
        self._init_clouds()

    def _init_clouds(self) -> None:
        for i in range(3):
            self.clouds.append(
                {
                    "x": random.uniform(0, self.width),
                    "y": random.uniform(self.height * 0.1, self.height * 0.3),
                    "width": random.uniform(80, 150),
                    "speed": random.uniform(0.2, 0.5),
                }
            )

    def update_rain(self, dt: float, intensity: float = 1.0) -> None:
        spawn_count = int(intensity * 3)
        for _ in range(spawn_count):
            if len(self.raindrops) < 100:
                self.raindrops.append(
                    {
                        "x": random.uniform(0, self.width),
                        "y": -10,
                        "speed": random.uniform(8, 15),
                        "length": random.uniform(10, 25),
                    }
                )

        alive = []
        for drop in self.raindrops:
            drop["y"] += drop["speed"] * dt * 60
            drop["x"] += 1 * dt * 60
            if drop["y"] < self.height + 30:
                alive.append(drop)
        self.raindrops = alive

    def update_snow(self, dt: float, intensity: float = 1.0) -> None:
        spawn_count = int(intensity * 2)
        for _ in range(spawn_count):
            if len(self.snowflakes) < 80:
                self.snowflakes.append(
                    {
                        "x": random.uniform(0, self.width),
                        "y": -10,
                        "speed": random.uniform(1, 3),
                        "size": random.uniform(2, 5),
                        "wobble": random.uniform(0, math.pi * 2),
                        "wobble_speed": random.uniform(1, 3),
                    }
                )

        alive = []
        for flake in self.snowflakes:
            flake["y"] += flake["speed"] * dt * 60
            flake["wobble"] += flake["wobble_speed"] * dt
            flake["x"] += math.sin(flake["wobble"]) * 0.5
            if flake["y"] < self.height + 10:
                alive.append(flake)
        self.snowflakes = alive

    def update_clouds(self, dt: float) -> None:
        for cloud in self.clouds:
            cloud["x"] += cloud["speed"] * dt * 60
            if cloud["x"] > self.width + cloud["width"]:
                cloud["x"] = -cloud["width"]

    def update_sun_rays(self, dt: float) -> None:
        if len(self.sun_rays) < 8:
            for i in range(8):
                angle = (i / 8) * math.pi * 2
                self.sun_rays.append(
                    {
                        "angle": angle,
                        "length": random.uniform(40, 80),
                        "pulse": random.uniform(0, math.pi * 2),
                    }
                )

        for ray in self.sun_rays:
            ray["pulse"] += dt * 2
            ray["length"] = 50 + math.sin(ray["pulse"]) * 20

    def trigger_lightning(self) -> None:
        self.lightning_flash = 1.0

    def update_lightning(self, dt: float) -> None:
        if self.lightning_flash > 0:
            self.lightning_flash -= dt * 5
            if self.lightning_flash < 0:
                self.lightning_flash = 0


class WaveformVisualizer:
    def __init__(self, width: int, height: int, bar_count: int = 32):
        self.width = width
        self.height = height
        self.bar_count = bar_count
        self.values = [0.0] * bar_count
        self.target_values = [0.0] * bar_count
        self.peaks = [0.0] * bar_count
        self.peak_decay = 0.02

    def update(self, amplitude: float, dt: float) -> None:
        self.target_values.pop(0)
        self.target_values.append(amplitude)

        for i in range(self.bar_count):
            diff = self.target_values[i] - self.values[i]
            self.values[i] += diff * min(1.0, dt * 15)

            if self.values[i] > self.peaks[i]:
                self.peaks[i] = self.values[i]
            else:
                self.peaks[i] -= self.peak_decay * dt * 60
                self.peaks[i] = max(self.peaks[i], 0)

    def set_values(self, values: List[float]) -> None:
        for i, v in enumerate(values[: self.bar_count]):
            self.target_values[i] = v


class PulseAnimation:
    def __init__(self):
        self.phase = 0.0
        self.speed = 2.0

    def update(self, dt: float) -> None:
        self.phase += dt * self.speed
        if self.phase > math.pi * 2:
            self.phase -= math.pi * 2

    def get_scale(self, base: float = 1.0, amplitude: float = 0.1) -> float:
        return base + math.sin(self.phase) * amplitude

    def get_alpha(self, base: float = 1.0, amplitude: float = 0.3) -> float:
        return max(0, min(1, base + math.sin(self.phase) * amplitude))


class TransitionManager:
    def __init__(self):
        self.active = False
        self.progress = 0.0
        self.duration = 0.5
        self.type = "fade"
        self._start_time = 0.0

    def start(self, transition_type: str = "fade", duration: float = 0.5) -> None:
        self.active = True
        self.progress = 0.0
        self.duration = duration
        self.type = transition_type
        self._start_time = time.time()

    def update(self, dt: float) -> bool:
        if not self.active:
            return False

        elapsed = time.time() - self._start_time
        self.progress = min(1.0, elapsed / self.duration)

        if self.progress >= 1.0:
            self.active = False
            return False
        return True

    def get_fade_alpha(self, phase: str = "out") -> float:
        if phase == "out":
            return 1.0 - AnimationController.ease(self.progress, Easing.EASE_IN_OUT)
        return AnimationController.ease(self.progress, Easing.EASE_IN_OUT)

    def get_slide_offset(self, distance: int, direction: str = "left") -> int:
        eased = AnimationController.ease(self.progress, Easing.EASE_OUT)
        offset = int(distance * (1 - eased))
        if direction in ("left", "up"):
            return -offset
        return offset
