from dataclasses import dataclass, field, asdict
from typing import Optional, List

@dataclass
class RenderSettings:
    width: int = 800
    height: int = 600
    spp: int = 100
    depth: int = 50
    sampler: int = 1 # 0=Random, 1=Sobol

@dataclass
class CameraSettings:
    lookfrom: List[float] = field(default_factory=lambda: [0, 0, 0])
    lookat: List[float]   = field(default_factory=lambda: [0, 0, -1])
    vup: List[float]      = field(default_factory=lambda: [0, 1, 0])
    vfov: float = 40.0
    aperture: float = 0.0
    focus_dist: float = 10.0

@dataclass
class EnvironmentSettings:
    # Source (Path string or RGB list)
    source: Optional[object] = None 
    
    # Lighting params
    exposure: float = 1.0
    background: float = 1.0
    diffuse: float = 1.0
    specular: float = 1.0
    rotation: float = 0.0
    clipping_multiplier: float = 20.0
    
    # Auto Sun
    auto_sun: bool = False
    sun_intensity: float = 50.0
    sun_radius: float = 50.0
    sun_dist: float = 1000.0

@dataclass
class SystemSettings:
    threads: int = 0
    leave_cores: int = 2
    param_stamp: bool = False
    
    # Engine Globals
    epsilon: float = 0.001
    firefly_clamp: float = 100.0
    
    # Output
    keep_denoised: bool = False
    keep_raw: bool = False
    keep_albedo: bool = False
    keep_normal: bool = False
    
    # Animation
    animate: bool = False
    frames: int = 48
    fps: int = 24
    turntable_radius: float = 0.5 # Renamed from 'radius' to match JSON better

    # Flexible dict for experimental params (epsilon etc)
    # merged into system in JSON usually
    extra: dict = field(default_factory=dict) 

@dataclass
class RenderConfig:
    render: RenderSettings = field(default_factory=RenderSettings)
    camera: CameraSettings = field(default_factory=CameraSettings)
    environment: EnvironmentSettings = field(default_factory=EnvironmentSettings)
    system: SystemSettings = field(default_factory=SystemSettings)

    def update_from_dict(self, data: dict):
        """
        Recursive update that tolerates unknown keys and differences in structure.
        """
        # 1. Update sub-objects
        if "render_settings" in data:
            _update_dataclass(self.render, data["render_settings"])
        if "camera" in data:
            _update_dataclass(self.camera, data["camera"])
        if "environment" in data:
            env_data = data["environment"]
            
            # Case 1: env_data is a dict (Classic config)
            if isinstance(env_data, dict):
                # Handle legacy 'background_level' vs 'background'
                if "background_level" in env_data: env_data["background"] = env_data["background_level"]
                if "diffuse_level" in env_data: env_data["diffuse"] = env_data["diffuse_level"]
                if "specular_level" in env_data: env_data["specular"] = env_data["specular_level"]
                
                # Handle map_path/background_color -> source
                if "map_path" in env_data and env_data["map_path"]:
                    env_data["source"] = env_data["map_path"]
                elif "background_color" in env_data and env_data["background_color"]:
                    env_data["source"] = env_data["background_color"]
                    
                _update_dataclass(self.environment, env_data)
            
            # Case 2: env_data is value (String path or Color list) - coming from SceneConfig
            elif env_data is not None:
                self.environment.source = env_data
        if "system" in data:
            _update_dataclass(self.system, data["system"])
            
        # 2. Handle flat overrides (CLI args often come flattened)
        # Strategy: Iterate over CLI args and try to find matching field in sub-objects
        apply_cli_args_to_config(self, data)

def _update_dataclass(instance, data: dict):
    from dataclasses import fields
    valid_keys = {f.name for f in fields(instance)}
    for k, v in data.items():
        if k in valid_keys and v is not None: # Skip None values to let defaults take over
            setattr(instance, k, v)
        elif k == "extra" and hasattr(instance, "extra"):
            # Special case for SystemSettings.extra
            instance.extra.update(v)

def apply_cli_args_to_config(config: RenderConfig, data: dict):
    """
    Attempts to update deep fields from a flat dictionary (e.g. argparse output).
    Example: data={'width': 1920} -> config.render.width = 1920
    """
    # Map field name to (instance, attr_name)
    # If there are collisions (e.g. multiple 'width'), last one wins or we define priority.
    # Typically field names are unique enough (width, height, spp, lookfrom...).
    
    lookup = {}
    
    # 1. Render
    for f in ["width", "height", "spp", "depth", "sampler"]: 
        lookup[f] = (config.render, f)
        
    # 2. Camera
    for f in ["lookfrom", "lookat", "vup", "vfov", "aperture", "focus_dist"]:
        lookup[f] = (config.camera, f)
        
    # 3. Environment
    # Note: CLI args mapping. 'env_exposure' -> environment.exposure
    lookup["env_exposure"] = (config.environment, "exposure")
    lookup["env_background"] = (config.environment, "background")
    lookup["env_diffuse"] = (config.environment, "diffuse")
    lookup["env_specular"] = (config.environment, "specular")
    lookup["env_rotation"] = (config.environment, "rotation")
    lookup["auto_sun"] = (config.environment, "auto_sun")
    # ... handle manual mapping for CLI args that have prefixes
    
    # 4. System
    for f in ["threads", "leave_cores", "param_stamp", "keep_denoised", "keep_raw"]:
        lookup[f] = (config.system, f)
    for f in ["animate", "frames", "fps"]:
        lookup[f] = (config.system, f)
    lookup["radius"] = (config.system, "turntable_radius")
    
    for k, v in data.items():
        if k in lookup:
            obj, attr = lookup[k]
            setattr(obj, attr, v)


def build_configuration(args, scene_config):
    final_conf = RenderConfig()

    # 1. Apply Scene Config
    if scene_config:
        # Use asdict to get a clean dict, but wait, scene_config is likely a dataclass too
        # or just an object. 
        # Safety check: if it has asdict
        if hasattr(scene_config, '__dataclass_fields__'):
             scene_data = asdict(scene_config)
        else:
             scene_data = vars(scene_config)
             
        # Use our smart update, filtering out None to respect RenderConfig defaults
        scene_data = {k: v for k, v in scene_data.items() if v is not None}
        final_conf.update_from_dict(scene_data)

    # 2. Gestion de la string compacte Auto-Sun
    if hasattr(args, 'auto_sun') and args.auto_sun is not None:
        # Enable main flag in any case
        if not final_conf.environment.auto_sun:
            print(f"[Override] CLI 'auto_sun': {final_conf.environment.auto_sun} -> True")
            final_conf.environment.auto_sun = True
        
        # Si c'est une string de config (pas juste le flag par défaut 'ON')
        if type(args.auto_sun) == str and args.auto_sun != '':
            try:
                # Split by space: "I10 R30 D1000" -> ["I10", "R30", "D1000"]
                parts = args.auto_sun.split()
                for p in parts:
                    code = p[0].upper()      # La lettre (I, R, D, C)
                    val = float(p[1:])       # Le nombre
                    
                    if code == 'I': 
                        print(f"[Override] CLI 'auto_sun_intensity': {final_conf.environment.sun_intensity} -> {val}")
                        final_conf.environment.sun_intensity = val
                    elif code == 'R': 
                        print(f"[Override] CLI 'auto_sun_radius': {final_conf.environment.sun_radius} -> {val}")
                        final_conf.environment.sun_radius = val
                    elif code == 'D': 
                        print(f"[Override] CLI 'auto_sun_dist': {final_conf.environment.sun_dist} -> {val}")
                        final_conf.environment.sun_dist = val
                    elif code == 'C':
                        print(f"[Override] CLI 'clipping_multiplier': {final_conf.environment.clipping_multiplier} -> {val}")
                        final_conf.environment.clipping_multiplier = val
                    else: print(f"[Warn] Code auto-sun inconnu: {code}")
            except Exception as e:
                print(f"[Error] Failed to parse auto-sun string: {e}")

    # 3. Appliquer les arguments CLI (Override)
    # Filter out None values to prevent overwriting defaults with None
    args_data = {k: v for k, v in vars(args).items() if v is not None}
    final_conf.update_from_dict(args_data)
            
    return final_conf