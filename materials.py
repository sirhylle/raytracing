from dataclasses import dataclass
from typing import Optional, Tuple

@dataclass
class MaterialPreset:
    name: str # Human readable name
    metallic: float
    roughness: float
    ior: float
    transmission: float
    albedo: Optional[Tuple[float, float, float]] = None # Optional override
    description: str = ""

# PBR Presets (Roughness, Metallic, IOR, Transmission)
PRESETS = {
    # Metals (Metallic=1.0)
    "CHROME": MaterialPreset("Chrome", 1.0, 0.02, 1.5, 0.0, (0.9, 0.9, 0.9), "Perfect mirror"),
    "GOLD":   MaterialPreset("Gold",   1.0, 0.15, 1.5, 0.0, (1.0, 0.76, 0.33), "Colored metal"),
    
    # Dielectrics (Metallic=0.0) -> IOR matters
    "GLASS":        MaterialPreset("Glass",         0.0, 0.0,  1.5,  1.0, (1.0, 1.0, 1.0), "Clear glass"),
    "FROSTED_GLASS":MaterialPreset("Frosted Glass", 0.0, 0.3,  1.5,  1.0, (1.0, 1.0, 1.0), "Blurred glass"),
    "WATER":        MaterialPreset("Water",         0.0, 0.02, 1.33, 1.0, (0.95, 0.95, 1.0), "Low IOR liquid"),
    "DIAMOND":      MaterialPreset("Diamond",       0.0, 0.0,  2.4,  1.0, (1.0, 1.0, 1.0), "High IOR"),

    # Opaque Dielectrics (Plastics, etc.)
    "CLAY":         MaterialPreset("Clay",          0.0, 1.0,  1.5,  0.0, None, "Matte diffuse"), # IOR doesn't matter much if rough=1 (pure diffuse)
    "HARD_PLASTIC": MaterialPreset("Hard Plastic",  0.0, 0.05, 1.55, 0.0, None, "Shiny plastic"),
    "CERAMIC":      MaterialPreset("Ceramic",       0.0, 0.15, 1.5,  0.0, None, "Shiny tiles"),
    "RUBBER":       MaterialPreset("Rubber",        0.0, 0.95, 1.5,  0.0, None, "Soft matte"),
    
    # Organics
    "WOOD_VARNISH": MaterialPreset("Varnished Wood",0.0, 0.1,  1.52, 0.0, None, "Shiny coating"),
    "WOOD_ROUGH":   MaterialPreset("Rough Wood",    0.0, 0.8,  1.5,  0.0, None, "Dry wood"),
}

def get_preset_params(key: str) -> dict:
    p = PRESETS.get(key)
    if not p: return {}
    return {
        "roughness": p.roughness,
        "metallic": p.metallic,
        "ir": p.ior,
        "transmission": p.transmission
    }
