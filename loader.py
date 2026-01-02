import cpp_engine
import os
import numpy as np
import imageio.v3 as iio
import scenes
from config import RenderConfig

def load_environment(engine, env_path, 
    background_level=None, direct_level=None, indirect_level=None, 
    auto_sun=False, auto_sun_intensity=None, auto_sun_radius=None,
    auto_sun_dist=None, auto_sun_env_level=None):
    """Charge la HDRI et configure le soleil physique automatique."""

    if not env_path or not os.path.exists(env_path):
        print(f"[Loader] No environment map found or path invalid: {env_path}")
        return

    try:
        print(f"[Loader] Loading environment map: {env_path}")
        
        # Chargement intelligent (support EXR/HDR)
        img = iio.imread(env_path)
        
        # Nettoyage des dimensions (H, W, C)
        if img.ndim == 2: img = np.stack((img,)*3, axis=-1)
        if img.ndim == 3 and img.shape[2] > 3: img = img[:, :, :3]
        
        # Conversion Float32 & Contiguous
        env_data = img.astype(np.float32)
        if img.dtype == np.uint8: env_data /= 255.0
        env_data = np.ascontiguousarray(env_data)

        engine.set_environment(env_data)
        
        # Gestion des niveaux
        bg_lvl = background_level if background_level is not None else 1.0
        dir_lvl = direct_level if direct_level is not None else 0.5
        indir_lvl = indirect_level if indirect_level is not None else 0.5
        
        engine.set_env_levels(bg_lvl, dir_lvl, indir_lvl)

        # Logique Auto-Sun
        if auto_sun:
            print("[Loader] Auto-Sun: Analyzing Environment...")
            sun_dir, sun_color = engine.get_env_sun_info()
            
            # On coupe le direct de l'envmap pour remplacer par le soleil physique
            engine.set_env_levels(bg_lvl, auto_sun_env_level, indir_lvl)

            dist = auto_sun_dist
            pos = [sun_dir.x() * dist, sun_dir.y() * dist, sun_dir.z() * dist]
            
            # Normalisation et Boost
            raw_intensity = max(sun_color.x(), max(sun_color.y(), sun_color.z()))
            if raw_intensity <= 0: raw_intensity = 1.0
            
            target_intensity = auto_sun_intensity # Curseur d'intensité artistique
            scale = target_intensity / raw_intensity
            
            sun_col = [sun_color.x()*scale, sun_color.y()*scale, sun_color.z()*scale]
            
            engine.add_invisible_sphere_light(
                cpp_engine.Vec3(*pos), 
                auto_sun_radius, # Rayon 
                cpp_engine.Vec3(*sun_col)
            )
            print(f"[Loader] Auto-Sun added. Intensity scaled {raw_intensity:.0f} -> {target_intensity}")

    except Exception as e:
        print(f"[Loader] Failed to load environment map: {e}")

def initialize_scene_and_engine(args, scene_name=None):
    """
    Initialise le moteur, charge la scène et l'environnement.
    Retourne (engine, config).
    """
    print("[Loader] Initializing Engine...")
    engine = cpp_engine.Engine()
    
    selected_scene = scene_name if scene_name else 'cornell'
    if hasattr(args, 'scene') and args.scene:
        selected_scene = args.scene

    print(f"[Loader] Loading Scene: {selected_scene}")
    scene_obj = scenes.AVAILABLE_SCENES[selected_scene]
    
    # Setup de la scène (geometry, materials)
    partial_config = scene_obj.setup(engine)
    
    # Construction de la config complète (Scene + CLI Args)
    from config import build_configuration
    config = build_configuration(args, partial_config)
    
    # Setup Camera Initiale (pour que le viewer ait un point de départ correct)
    def v3(l): return cpp_engine.Vec3(float(l[0]), float(l[1]), float(l[2]))
    aspect = config.width / config.height
    engine.set_camera(v3(config.lookfrom), v3(config.lookat), v3(config.vup),
                      float(config.vfov), float(aspect), float(config.aperture), float(config.focus_dist))

    # Chargement Environment & Soleil
    load_environment(engine, config.env_map, 
                     config.env_background_level, 
                     config.env_direct_level, 
                     config.env_indirect_level,
                     config.auto_sun,
                     config.auto_sun_intensity,
                     config.auto_sun_radius,
                     config.auto_sun_dist,
                     config.auto_sun_env_level)
                     
    return engine, config
