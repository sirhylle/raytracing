from dataclasses import dataclass, field, asdict
from typing import Optional, List

@dataclass
class RenderConfig:
    # --- Canvas ---
    width: int = 800
    height: int = 600
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
    env_exposure: float = 1.0     # Master scale
    env_background: float = 1.0   # Camera visibility
    env_diffuse: float = 1.0      # GI/Lighting
    env_specular: float = 1.0     # Reflections
    clipping_multiplier: float = 20.0
    auto_sun: bool = False
    auto_sun_intensity: float = 50.0
    auto_sun_radius: float = 50.0
    auto_sun_dist: float = 1000.0
    # auto_sun_env_level Removed (Legacy)
    
    # --- Animation ---
    animate: bool = False
    frames: int = 48
    fps: int = 24
    radius: float = 0.5
    
    
    # --- System ---
    threads: int = 0
    leave_cores: int = 2
    param_stamp: bool = False
    save_raw: bool = False

def build_configuration(args, scene_config):
    final_conf = RenderConfig()

    # 1. Appliquer la config de la scène
    if scene_config:
        scene_data = {k: v for k, v in asdict(scene_config).items() if v is not None}
        for k, v in scene_data.items():
            if hasattr(final_conf, k):
                setattr(final_conf, k, v)

    # 2. Gestion de la string compacte Auto-Sun
    if hasattr(args, 'auto_sun') and args.auto_sun is not None:
        # On active le flag principal quoi qu'il arrive
        if not final_conf.auto_sun:
            print(f"[Override] CLI 'auto_sun': {final_conf.auto_sun} -> True")
            final_conf.auto_sun = True
        
        # Si c'est une string de config (pas juste le flag par défaut 'ON')
        if type(args.auto_sun) == str and args.auto_sun != '':
            try:
                # On découpe par espace : "I10 R30 D1000" -> ["I10", "R30", "D1000"]
                parts = args.auto_sun.split()
                for p in parts:
                    code = p[0].upper()      # La lettre (I, R, D, C)
                    val = float(p[1:])       # Le nombre
                    
                    if code == 'I': 
                        print(f"[Override] CLI 'auto_sun_intensity': {final_conf.auto_sun_intensity} -> {val}")
                        final_conf.auto_sun_intensity = val
                    elif code == 'R': 
                        print(f"[Override] CLI 'auto_sun_radius': {final_conf.auto_sun_radius} -> {val}")
                        final_conf.auto_sun_radius = val
                    elif code == 'D': 
                        print(f"[Override] CLI 'auto_sun_dist': {final_conf.auto_sun_dist} -> {val}")
                        final_conf.auto_sun_dist = val
                    # 'E' code removed (Legacy auto_sun_env_level)
                    elif code == 'C':
                        print(f"[Override] CLI 'clipping_multiplier': {final_conf.clipping_multiplier} -> {val}")
                        final_conf.clipping_multiplier = val
                    else: print(f"[Warn] Code auto-sun inconnu: {code}")
            except Exception as e:
                print(f"[Error] Failed to parse auto-sun string: {e}")

    # 3. Appliquer les arguments CLI (Override)
    args_data = vars(args)
    for k, v in args_data.items():
        if v is not None and hasattr(final_conf, k) and k != 'auto_sun':
            # Gestion spéciale pour les vecteurs (listes)
            if k in ['lookfrom', 'lookat', 'vup']:
                # args.lookfrom est [1, 2, 3] (list de float si nargs=3)
                print(f"[Override] CLI '{k}': {getattr(final_conf, k)} -> {v}")
                setattr(final_conf, k, v)
            else:
                current_val = getattr(final_conf, k)
                if current_val != v:
                    print(f"[Override] CLI '{k}': {current_val} -> {v}")
                setattr(final_conf, k, v)
            
    return final_conf