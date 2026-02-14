"""
================================================================================================
MODULE: SCENE LOADER & BUILDER
================================================================================================

DESCRIPTION:
  High-level Python wrapper around the C++ Engine.
  - SceneBuilder: Facade that simplifies object creation (Sphere, Quad, Mesh).
  - Environment Loading: Handles background images (HDR).
  - Auto-Sun: Intelligent feature that analyzes an HDR map to detect the brightest spot
    and places a physical directional light source there.
  
  The 'SceneBuilder' also maintains a 'Registry' (Dictionary) of all objects with their
  editable properties (Pos, Rot, Scale, Material). This registry is the Single Source of Truth
  for the Editor UI.

================================================================================================
"""
import cpp_engine
import os
import numpy as np
import imageio.v3 as iio
import scenes
import transforms as tf
from config import RenderConfig

# ==================================================================================
# SCENE BUILDER (Wrapper & State Manager)
# ==================================================================================

class SceneBuilder:
    """
    Sert d'intermédiaire entre la définition de la scène (Python) et le moteur (C++).
    Son rôle est double :
    1. Créer les objets dans le moteur via les bindings C++.
    2. Stocker l'état initial (Position, Rotation, Scale) pour l'éditeur (Gizmo).
    """
    def __init__(self, engine):
        self.engine = engine
        # Le Registre : ID -> {type, pos, rot, scale, ...}
        self.registry = {}
        self.asset_library = {}

    # --- Primitives PBR ---

    def add_sphere(self, center, radius, mat_type, color, roughness=0.5, metallic=0.0, ir=1.5, transmission=0.0, fuzz=None):
        # Compatibility handling
        if fuzz is not None: roughness = fuzz

        c_list = list(center) if isinstance(center, (list, tuple, np.ndarray)) else [center.x(), center.y(), center.z()]
        v_center = cpp_engine.Vec3(float(c_list[0]), float(c_list[1]), float(c_list[2]))
        
        # New C++ Signature
        obj_id = self.engine.add_sphere(v_center, float(radius), mat_type, 
                                        cpp_engine.Vec3(float(color[0]), float(color[1]), float(color[2])), 
                                        float(roughness), float(metallic), float(ir), float(transmission))
        
        self.registry[obj_id] = {
            'type': 'sphere',
            'pos': c_list,
            'rot': [0.0, 0.0, 0.0],
            'scale': [radius, radius, radius],
            'mat_type': mat_type,
            'color': color,
            'roughness': float(roughness),
            'metallic': float(metallic),
            'ir': float(ir),
            'transmission': float(transmission)
        }
        return obj_id

    def add_checker_sphere(self, center, radius, c1, c2, scale):
        # Checker remains simple for now
        def to_v3(v):
            l = list(v) if isinstance(v, (list, tuple, np.ndarray)) else [v.x(), v.y(), v.z()]
            return cpp_engine.Vec3(float(l[0]), float(l[1]), float(l[2])), l

        v_center, c_list = to_v3(center)
        v_c1, c1_list = to_v3(c1)
        v_c2, c2_list = to_v3(c2)

        obj_id = self.engine.add_checker_sphere(v_center, float(radius), v_c1, v_c2, float(scale))
        
        self.registry[obj_id] = {
            'type': 'checker_sphere',
            'pos': c_list,
            'rot': [0.0, 0.0, 0.0],
            'scale': [radius, radius, radius],
            'mat_type': 'lambertian',
            'color': c1_list,
            'color2': c2_list,
            'texture_scale': float(scale),
            'roughness': 1.0,
            'metallic': 0.0,
            'ir': 1.5,
            'transmission': 0.0
        }
        return obj_id

    def add_cylinder(self, center, radius, height, mat_type, color, roughness=0.5, metallic=0.0, ir=1.5, transmission=0.0, fuzz=None):
        if fuzz is not None: roughness = fuzz
        c_list = list(center) if isinstance(center, (list, tuple, np.ndarray)) else [center.x(), center.y(), center.z()]
        v_center = cpp_engine.Vec3(float(c_list[0]), float(c_list[1]), float(c_list[2]))
        
        obj_id = self.engine.add_cylinder(v_center, float(radius), float(height), mat_type, 
                                          cpp_engine.Vec3(float(color[0]), float(color[1]), float(color[2])), 
                                          float(roughness), float(metallic), float(ir), float(transmission))
        
        self.registry[obj_id] = {
            'type': 'cylinder',
            'pos': c_list,
            'rot': [0.0, 0.0, 0.0],
            'scale': [radius, height, radius], # Scale Y is height
            'mat_type': mat_type,
            'color': color,
            'roughness': float(roughness),
            'metallic': float(metallic),
            'ir': float(ir),
            'transmission': float(transmission)
        }
        return obj_id
        
    def add_cone(self, center, radius, height, mat_type, color, roughness=0.5, metallic=0.0, ir=1.5, transmission=0.0, fuzz=None):
        if fuzz is not None: roughness = fuzz
        c_list = list(center) if isinstance(center, (list, tuple, np.ndarray)) else [center.x(), center.y(), center.z()]
        v_center = cpp_engine.Vec3(float(c_list[0]), float(c_list[1]), float(c_list[2]))
        
        obj_id = self.engine.add_cone(v_center, float(radius), float(height), mat_type, 
                                      cpp_engine.Vec3(float(color[0]), float(color[1]), float(color[2])), 
                                      float(roughness), float(metallic), float(ir), float(transmission))
        
        self.registry[obj_id] = {
            'type': 'cone',
            'pos': c_list,
            'rot': [0.0, 0.0, 0.0],
            'scale': [radius, height, radius], 
            'mat_type': mat_type,
            'color': color,
            'roughness': float(roughness),
            'metallic': float(metallic),
            'ir': float(ir),
            'transmission': float(transmission)
        }
        return obj_id

    def add_quad(self, Q, u, v, mat_type, color, roughness=0.5, metallic=0.0, ir=1.5, transmission=0.0, fuzz=None):
        if fuzz is not None: roughness = fuzz

        def to_v3(val):
            l = list(val) if isinstance(val, (list, tuple, np.ndarray)) else [val.x(), val.y(), val.z()]
            return cpp_engine.Vec3(float(l[0]), float(l[1]), float(l[2])), l

        v_Q, q_list = to_v3(Q)
        v_u, u_list = to_v3(u)
        v_v, v_list = to_v3(v)
        v_color, col_list = to_v3(color)

        origin = cpp_engine.Vec3(0.0, 0.0, 0.0)
        obj_id = self.engine.add_quad(origin, v_u, v_v, mat_type, v_color, float(roughness), float(metallic), float(ir), float(transmission))
        
        self.registry[obj_id] = {
            'type': 'quad',
            'pos': q_list,
            'u': u_list,
            'v': v_list,
            'rot': [0.0, 0.0, 0.0],
            'scale': [1.0, 1.0, 1.0],
            'mat_type': mat_type,
            'color': col_list,
            'roughness': float(roughness),
            'metallic': float(metallic),
            'ir': float(ir),
            'transmission': float(transmission)
        }
        
        M = tf.translate(q_list[0], q_list[1], q_list[2])
        InvM = np.linalg.inv(M)
        self.engine.update_instance_transform(
            obj_id, 
            np.ascontiguousarray(M, dtype=np.float32), 
            np.ascontiguousarray(InvM, dtype=np.float32)
        )
        return obj_id

    def add_invisible_sphere_light(self, center, radius, color, raw_color):
        c_list = list(center) if isinstance(center, (list, tuple, np.ndarray)) else [center.x(), center.y(), center.z()]
        v_center = cpp_engine.Vec3(float(c_list[0]), float(c_list[1]), float(c_list[2]))
        
        r, g, b = 0, 0, 0
        if hasattr(color, 'x'): r, g, b = color.x(), color.y(), color.z()
        else: r, g, b = color[0], color[1], color[2]

        obj_id = self.engine.add_invisible_sphere_light(v_center, float(radius), cpp_engine.Vec3(r,g,b))
        
        self.registry[obj_id] = {
            'type': 'light_sun',
            'pos': c_list,
            'rot': [0.0, 0.0, 0.0],
            'scale': [radius, radius, radius],
            'mat_type': 'invisible_light',
            'color': [r, g, b],
            'raw_color': raw_color,
            'roughness': 1.0,
            'metallic': 0.0,
            'ir': 1.0
        }
        return obj_id

    # --- Instances (Meshes) ---

    def add_mesh_instance(self, mesh_name, pos=[0.0,0.0,0.0], rot=[0.0,0.0,0.0], scale=[1.0,1.0,1.0], registry_type="mesh"):
        M = tf.translate(pos[0], pos[1], pos[2]) @ \
            tf.rotate_y(rot[1]) @ \
            tf.rotate_x(rot[0]) @ \
            tf.rotate_z(rot[2]) @ \
            tf.scale(scale[0], scale[1], scale[2])
            
        InvM = np.linalg.inv(M)
        c_M = np.ascontiguousarray(M, dtype=np.float32)
        c_InvM = np.ascontiguousarray(InvM, dtype=np.float32)
        
        obj_id = self.engine.add_instance(mesh_name, c_M, c_InvM)

        def_type = 'standard'
        def_col = [0.8, 0.8, 0.8]
        def_rough = 0.5
        def_metal = 0.0
        def_ir = 1.5
        def_trans = 0.0

        if mesh_name in self.asset_library:
            info = self.asset_library[mesh_name]
            def_type = info.mat_type
            def_col = info.color
            # PBR Mapping
            def_rough = info.roughness
            def_metal = info.metallic
            def_ir = info.ior
            def_trans = info.transmission

        self.registry[obj_id] = {
            'type': registry_type,
            'asset_name': mesh_name, # Vital for persistence
            'name': mesh_name,
            'pos': list(pos),
            'rot': list(rot),
            'scale': list(scale),
            'mat_type': def_type, 
            'color': def_col,
            'roughness': def_rough,
            'metallic': def_metal,
            'ir': def_ir,
            'transmission': def_trans
        }
        return obj_id

    # --- Passthrough ---
    def load_asset(self, *args, **kwargs):
        # meshloader utilise directement l'engine pour charger les données brutes
        # Ce n'est pas un objet affichable, donc pas d'ID de scène.
        import meshloader
        info = meshloader.load_asset(self.engine, *args, **kwargs)
        if info:
            self.asset_library[info.name] = info
        return info

    def set_environment(self, data, clipping_threshold=float('inf')):
        self.engine.set_environment(data, clipping_threshold)
    
    def set_env_levels(self, exposure, bg, diffuse, specular):
        self.engine.set_env_levels(float(exposure), float(bg), float(diffuse), float(specular))

    def get_env_sun_info(self):
        return self.engine.get_env_sun_info()


# ==================================================================================
# LOGIQUE DE CHARGEMENT
# ==================================================================================

def create_auto_sun(builder, intensity, radius, distance):
    """
    ALGORITHM: AUTO-SUN GENERATION
    ------------------------------
    Analyzes the loaded environment map to find the "Point of Maximum Radiance" (Hotspot).
    Creates an invisible spherical light source at that direction to simulate the sun physically.
    
    1. Query the C++ engine for the brightest direction (Max pixel value in EnvMap).
    2. Place a light at 'distance' units in that direction.
    3. Scale the color intensity to match the user's requested 'intensity'.
    """
    # 1. Analyse du moteur
    # Renvoie des Vec3 C++
    sun_dir, sun_color = builder.get_env_sun_info()
    
    # 2. Conversion en tableaux Python/Numpy pour usage ultérieur
    dir_arr = np.array([sun_dir.x(), sun_dir.y(), sun_dir.z()])
    raw_col_arr = np.array([sun_color.x(), sun_color.y(), sun_color.z()])
    
    # 3. Calculs mathématiques
    # Position
    pos = dir_arr * distance
    
    # Couleur (Scaling par intensité)
    raw_intensity = max(raw_col_arr[0], max(raw_col_arr[1], raw_col_arr[2]))
    if raw_intensity <= 0: raw_intensity = 1.0
    
    # On calcule le facteur d'échelle pour atteindre l'intensité cible
    scale = intensity / raw_intensity
    final_col = raw_col_arr * scale
    
    # 4. Création via le Builder
    oid = builder.add_invisible_sphere_light(
        pos, 
        radius,
        final_col,   # Couleur active
        raw_col_arr  # Couleur brute (Single Source of Truth)
    )
    
    return oid, dir_arr, raw_col_arr

def load_environment(builder, environment, 
    env_exposure=1.0, env_background=1.0, env_diffuse=1.0, env_specular=1.0, 
    auto_sun=False, auto_sun_intensity=None, auto_sun_radius=None,
    auto_sun_dist=None, clipping_multiplier=None):
    """Charge la HDRI ou une couleur unie et configure le soleil physique automatique via le Builder."""

    # 1. Cas : Rien défini
    if environment is None:
        return 1.0

    env_img = None
    median_val = 1.0

    try:
        # 2. Cas : Couleur unie (List/Tuple/Array)
        if isinstance(environment, (list, tuple, np.ndarray)):
             print(f"[Loader] Loading uniform environment color: {environment}")
             # Conversion en Numpy (1x1x3)
             arr = np.array(environment, dtype=np.float32)
             # Si c'est juste [R, G, B], on reshape
             if arr.ndim == 1 and arr.shape[0] >= 3:
                 env_img = arr[:3].reshape((1, 1, 3))
             else:
                 env_img = arr # Supposons que l'user sait ce qu'il fait (ou array déjà formaté)
             
             # Pas de calcul de médiane nécessaire pour une couleur unie
             median_val = np.mean(env_img) # Simple moyenne

        # 3. Cas : Fichier (String)
        elif isinstance(environment, str):
            if not os.path.exists(environment):
                print(f"[Loader] No environment map found or path invalid: {environment}")
                return 1.0
            
            print(f"[Loader] Loading environment map: {environment}")
            img = iio.imread(environment)
            
            if img.ndim == 2: img = np.stack((img,)*3, axis=-1)
            if img.ndim == 3 and img.shape[2] > 3: img = img[:, :, :3]
            
            env_data = img.astype(np.float32)
            if img.dtype == np.uint8: env_data /= 255.0
            if img.dtype != np.float32:
                img = img.astype(np.float32)
            
            env_img = img

            # Calcul du seuil de clipping (MIS) pour les Maps seulement
            # On calcule la médiane de la luminance pour identifier le "fond" du ciel
            if auto_sun or (clipping_multiplier is not None and clipping_multiplier > 0):
                lum = 0.2126 * env_data[:,:,0] + 0.7152 * env_data[:,:,1] + 0.0722 * env_data[:,:,2]
                median_val = np.median(lum)

        # 4. Envoi au moteur (Commun)
        if env_img is not None:
             clipping_threshold = float('inf')
             
             # Le clipping dynamique n'a de sens que pour les HDRIs (hautes dynamiques)
             # Pour une couleur unie (LDR ou HDR basse), le clipping est inutile voire contre-productif.
             if isinstance(environment, str) and (auto_sun or (clipping_multiplier and clipping_multiplier > 0)):
                 if clipping_multiplier is not None and clipping_multiplier > 0:
                     clipping_threshold = median_val * clipping_multiplier
                 else:
                     clipping_threshold = median_val * 20.0

             builder.set_environment(env_img, clipping_threshold)

        # Environment Levels (Pro Split)
        # Passed directly to engine
        builder.set_env_levels(env_exposure, env_background, env_diffuse, env_specular)

        if auto_sun:
            print("[Loader] Auto-Sun: Analyzing Environment...")

            # Appel de la logique partagée
            create_auto_sun(
                builder, 
                auto_sun_intensity, 
                auto_sun_radius, 
                auto_sun_dist
            )
            print(f"[Loader] Auto-Sun added via Builder. Registry Updated.")
            
        return median_val if 'median_val' in locals() else 1.0

    except Exception as e:
        print(f"[Loader] Failed to load environment map: {e}")
        return 1.0

def initialize_scene_and_engine(args, scene_name=None):
    """
    Initialise le moteur, charge la scène.
    Retourne (engine, config, builder).
    """
    print("[Loader] Initializing Engine...")
    engine = cpp_engine.Engine()
    
    # Instanciation du Builder qui wrapper l'engine
    builder = SceneBuilder(engine)
    
    selected_scene = scene_name if scene_name else 'cornell'
    if hasattr(args, 'scene') and args.scene:
        selected_scene = args.scene

    print(f"[Loader] Loading Scene: {selected_scene}")
    scene_obj = scenes.AVAILABLE_SCENES[selected_scene]
    
    # Setup de la scène (geometry, materials) VIA LE BUILDER
    partial_config = scene_obj.setup(builder)
    
    # Config Complète
    from config import build_configuration
    config = build_configuration(args, partial_config)
    
    # Camera Init
    def v3(l): return cpp_engine.Vec3(float(l[0]), float(l[1]), float(l[2]))
    aspect = config.width / config.height
    engine.set_camera(v3(config.lookfrom), v3(config.lookat), v3(config.vup),
                      float(config.vfov), float(aspect), float(config.aperture), float(config.focus_dist))

    # Environment (Passe le builder)
    load_environment(builder, config.environment, 
                     env_exposure=config.env_exposure,
                     env_background=config.env_background, 
                     env_diffuse=config.env_diffuse, 
                     env_specular=config.env_specular,
                     auto_sun=config.auto_sun,
                     auto_sun_intensity=config.auto_sun_intensity,
                     auto_sun_radius=config.auto_sun_radius,
                     auto_sun_dist=config.auto_sun_dist,
                     clipping_multiplier=config.clipping_multiplier)

    # 4. Blue Noise Dithering (Optional Asset)
    bn_path = "blue_noise.png"
    if os.path.exists(bn_path):
        try:
            print(f"[Loader] Loading Blue Noise Dither Tile: {bn_path}")
            bn_img = iio.imread(bn_path)
            # Ensure grayscale / single channel
            if bn_img.ndim == 3:
                bn_img = bn_img[:, :, 0]
            bn_data = bn_img.astype(np.float32)
            if bn_img.dtype == np.uint8:
                bn_data /= 255.0
            
            engine.set_blue_noise_texture(np.ascontiguousarray(bn_data))
        except Exception as e:
            print(f"[Loader] Warning: Failed to load blue noise texture: {e}")
                     
    return engine, config, builder
