from dataclasses import dataclass, field, asdict
from typing import Optional, List

@dataclass
class RenderConfig:
    # --- Canvas ---
    width: int = 800
    height: int = 800
    spp: int = 100
    depth: int = 50
    
    # --- Camera ---
    lookfrom: List[float] = field(default_factory=lambda: [0, 0, 0])
    lookat: List[float]   = field(default_factory=lambda: [0, 0, -1])
    vup: List[float]      = field(default_factory=lambda: [0, 1, 0])
    vfov: float = 40.0
    aperture: float = 0.0
    focus_dist: float = 10.0
    
    # --- Environment ---
    env_map: Optional[str] = "env-dock-sun.hdr"
    env_background_level: float = 1.0
    env_direct_level: float = 0.5
    env_indirect_level: float = 0.5
    auto_sun: bool = False
    
    # --- Animation ---
    animate: bool = False
    frames: int = 48
    fps: int = 24
    radius: float = 0.5
    
    # --- System ---
    threads: int = 0
    leave_cores: int = 2