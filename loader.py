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
import sys
import cpp_engine
import os
import numpy as np
import imageio.v3 as iio
import scenes
import transforms as tf
from config import RenderConfig
from dataclasses import asdict

# ==================================================================================
# SCENE BUILDER (Wrapper & State Manager)
# ==================================================================================

class SceneBuilder:
    """
    Intermediary between Python scene definition and the C++ engine.
    Its role is two-fold:
    1. Create objects in the engine via C++ bindings.
    2. Store the initial state (Position, Rotation, Scale) for the editor (Gizmo).
    """
    def __init__(self, engine):
        self.engine = engine
        # Le Registre : ID -> {type, pos, rot, scale, ...}
        self.registry = {}
        self.asset_library = {}
        self.texture_cache = {}  # path -> cpp_engine.ImageTexture

    def load_texture(self, filepath):
        """Loads an image file and returns a cpp_engine.ImageTexture. Uses cache."""
        if filepath in self.texture_cache:
            return self.texture_cache[filepath]
        
        if not os.path.exists(filepath):
            print(f"[Loader] Texture not found: {filepath}")
            return None
        
        try:
            img = iio.imread(filepath)
            if img.ndim == 2:
                img = np.stack((img,)*3, axis=-1)
            if img.ndim == 3 and img.shape[2] > 3:
                img = img[:,:,:3]
            
            img_f = img.astype(np.float32)
            if img.dtype == np.uint8:
                img_f /= 255.0
            
            h, w = img_f.shape[:2]
            flat = np.ascontiguousarray(img_f.reshape(-1), dtype=np.float32)
            tex = cpp_engine.ImageTexture(flat, w, h)
            self.texture_cache[filepath] = tex
            print(f"[Loader] Loaded texture: {filepath} ({w}x{h})")
            return tex
        except Exception as e:
            print(f"[Loader] Failed to load texture {filepath}: {e}")
            return None

    # --- Primitives PBR ---

    def add_sphere(self, center, radius, mat_type, color, roughness=0.5, metallic=0.0, ir=1.5, transmission=0.0, dispersion=0.0, fuzz=None):
        # Compatibility handling
        if fuzz is not None: roughness = fuzz

        c_list = list(center) if isinstance(center, (list, tuple, np.ndarray)) else [center.x(), center.y(), center.z()]
        v_center = cpp_engine.Vec3(float(c_list[0]), float(c_list[1]), float(c_list[2]))
        
        # New C++ Signature
        obj_id = self.engine.add_sphere(v_center, float(radius), mat_type, 
                                        cpp_engine.Vec3(float(color[0]), float(color[1]), float(color[2])), 
                                        float(roughness), float(metallic), float(ir), float(transmission))
        
        # Apply dispersion if needed (since add_sphere might not take it yet)
        if dispersion > 0.0:
             self.engine.update_instance_material(obj_id, mat_type, cpp_engine.Vec3(float(color[0]), float(color[1]), float(color[2])),
                                                  float(roughness), float(metallic), float(ir), float(transmission), float(dispersion))

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
            'transmission': float(transmission),
            'dispersion': float(dispersion)
        }
        # For light materials, decompose emission into normalized color + intensity
        if mat_type in ('light', 'invisible_light'):
            intensity = max(color[0], color[1], color[2])
            if intensity <= 0: intensity = 1.0
            self.registry[obj_id]['color'] = [color[0]/intensity, color[1]/intensity, color[2]/intensity]
            self.registry[obj_id]['intensity'] = float(intensity)
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

    def add_quad(self, Q, u, v, mat_type, color, roughness=0.5, metallic=0.0, ir=1.5, transmission=0.0, dispersion=0.0, fuzz=None):
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
        
        if dispersion > 0.0:
             self.engine.update_instance_material(obj_id, mat_type, v_color,
                                                  float(roughness), float(metallic), float(ir), float(transmission), float(dispersion))

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
            'transmission': float(transmission),
            'dispersion': float(dispersion)
        }
        # For light materials, decompose emission into normalized color + intensity
        if mat_type in ('light', 'invisible_light'):
            intensity = max(col_list[0], col_list[1], col_list[2])
            if intensity <= 0: intensity = 1.0
            self.registry[obj_id]['color'] = [col_list[0]/intensity, col_list[1]/intensity, col_list[2]/intensity]
            self.registry[obj_id]['intensity'] = float(intensity)
        
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
        
        # Decompose emission into normalized color + intensity
        intensity = max(r, g, b)
        if intensity <= 0: intensity = 1.0
        self.registry[obj_id] = {
            'type': 'light_sun',
            'pos': c_list,
            'rot': [0.0, 0.0, 0.0],
            'scale': [radius, radius, radius],
            'mat_type': 'invisible_light',
            'color': [r/intensity, g/intensity, b/intensity],
            'intensity': float(intensity),
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
    # 1. Engine Analysis
    # Returns C++ Vec3
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

def load_environment(builder, env_settings):
    """Charge HDRI or solid color and configure auto-sun via Builder."""
    from config import EnvironmentSettings
    if env_settings is None:
        return 1.0
        
    # Duck typing or type check
    # If passed as string/list directly (legacy internal calls?), wrap it?
    # No, we updated call site to pass EnvironmentSettings.
    
    environment = env_settings.source

    # 1. Cas : Rien défini
    if environment is None:
        # Default white? Or keep previous?
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
            if env_settings.auto_sun or (env_settings.clipping_multiplier is not None and env_settings.clipping_multiplier > 0):
                lum = 0.2126 * env_data[:,:,0] + 0.7152 * env_data[:,:,1] + 0.0722 * env_data[:,:,2]
                median_val = np.median(lum)

        # 4. Envoi au moteur (Commun)
        if env_img is not None:
             clipping_threshold = float('inf')
             
             # Dynamic clipping only makes sense for HDRIs (high dynamic range)
             # For a solid color (LDR or low HDR), clipping is useless or even detrimental.
             if isinstance(environment, str) and (env_settings.auto_sun or (env_settings.clipping_multiplier and env_settings.clipping_multiplier > 0)):
                 if env_settings.clipping_multiplier is not None and env_settings.clipping_multiplier > 0:
                     clipping_threshold = median_val * env_settings.clipping_multiplier
                 else:
                     clipping_threshold = median_val * 20.0

             builder.set_environment(env_img, clipping_threshold)

        # Environment Levels (Pro Split)
        # Passed directly to engine
        builder.set_env_levels(
            env_settings.exposure, 
            env_settings.background, 
            env_settings.diffuse, 
            env_settings.specular
        )
        
        # Rotation
        builder.engine.set_env_rotation(env_settings.rotation)

        if env_settings.auto_sun:
            print("[Loader] Auto-Sun: Analyzing Environment...")

            # Appel de la logique partagée
            create_auto_sun(
                builder, 
                env_settings.sun_intensity, 
                env_settings.sun_radius, 
                env_settings.sun_dist
            )
            print("[Loader] Auto-Sun added via Builder. Registry Updated.")
            
        return median_val if 'median_val' in locals() else 1.0

    except Exception as e:
        print(f"[Loader] Failed to load environment map: {e}")
        import traceback
        traceback.print_exc()
        return 1.0

def load_scene_from_json(builder, filepath, config):
    """
    Charge une scène JSON dans le moteur via le Builder et met à jour la Config.
    """
    import json
    if not os.path.exists(filepath):
        print(f"[Loader] Error: File not found {filepath}")
        return False

    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[Loader] JSON Load Failed: {e}")
        return False

    print(f"[Loader] Parsing scene: {filepath}...")

    # 1. CONFIGURATION
    # The config class now handles the robust nested update.
    config.update_from_dict(data)

    # 1b. ENGINE GLOBALS (System Extras)
    # Some params are not in RenderConfig structure but engine globals
    if "system" in data:
         sys_conf = data["system"]
         if "epsilon" in sys_conf: cpp_engine.set_epsilon(float(sys_conf["epsilon"]))
         if "firefly_clamp" in sys_conf: cpp_engine.set_firefly_clamp(float(sys_conf["firefly_clamp"]))

    # 1c. ENVIRONMENT ROTATION (Engine-side)
    # Config has it, but we need to push it to engine? 
    # initialize_scene_and_engine calls load_environment later which uses config.environment.rotation.
    # So we don't need to do it here if load_scene_from_json is followed by setup.
    # However, load_scene_from_json modifies the config object in place.
    
    # 2. OBJECTS
    if "objects" in data:
        for obj in data["objects"]:
            otype = obj.get("type", "unknown")
            pos = obj.get("pos", [0,0,0])
            rot = obj.get("rot", [0,0,0])
            scale = obj.get("scale", [1,1,1])
            
            # PBR
            mat = obj.get("mat_type", "lambertian")
            col = obj.get("color", [0.8, 0.8, 0.8])
            rough = obj.get("roughness", 0.5)
            metal = obj.get("metallic", 0.0)
            trans = obj.get("transmission", 0.0)
            ior = obj.get("ir", 1.5)
            
            # Re-construction
            if otype == 'sphere':
                builder.add_sphere(pos, scale[0], mat, col, roughness=rough, metallic=metal, ir=ior, transmission=trans)
            
            elif otype == 'mesh':
                name = obj.get("asset_name", "Unknown")
                # Handle relative asset paths
                if not os.path.exists(name):
                     # Try relative to scene file
                     scene_dir = os.path.dirname(filepath)
                     alt_path = os.path.join(scene_dir, name)
                     if os.path.exists(alt_path):
                         name = alt_path
                     elif os.path.exists(os.path.join("assets", os.path.basename(name))):
                         name = os.path.join("assets", os.path.basename(name))

                # Load asset if needed
                if name not in builder.asset_library:
                    builder.load_asset(os.path.basename(name), name)
                
                oid = builder.add_mesh_instance(os.path.basename(name), pos, rot, scale)
                # Apply overrides
                if oid in builder.registry:
                    builder.registry[oid]['color'] = col
                    builder.registry[oid]['mat_type'] = mat
                    builder.registry[oid]['roughness'] = rough
                    builder.registry[oid]['metallic'] = metal
                    builder.registry[oid]['ir'] = ior
                    builder.registry[oid]['transmission'] = trans
                    # Push material to engine
                    v_col = cpp_engine.Vec3(float(col[0]), float(col[1]), float(col[2]))
                    builder.engine.update_instance_material(oid, mat, v_col, float(rough), float(metal), float(ior), float(trans))

            elif otype == 'checker_sphere':
                c2 = obj.get("color2", [0,0,0])
                tscale = obj.get("texture_scale", 4.0)
                builder.add_checker_sphere(pos, scale[0], col, c2, tscale)
            
            elif otype == 'quad':
                u = obj.get("u", [1,0,0])
                v = obj.get("v", [0,1,0])
                builder.add_quad(pos, u, v, mat, col, roughness=rough, metallic=metal, ir=ior, transmission=trans)
                
            elif otype == 'light_sun':
                # Skip, handled by environment auto-sun
                continue

    return True


def initialize_scene_and_engine(scene_source=None, args_overrides=None, engine=None):
    """
    Initialise le moteur.
    - scene_source: Chemin fichier (.json) OU Nom de scène procédurale (ex: 'cornell').
    - args_overrides: Arguments CLI pour surcharger config.py (ex: --spp).
    - engine: (Optional) Existing engine instance to use.
    """
    print("[Loader] Initializing Engine...")
    if engine is None:
        engine = cpp_engine.Engine()
    builder = SceneBuilder(engine)
    
    # 1. Base Configuration (Defaults)
    from config import build_configuration, RenderConfig
    # On commence avec une config vide/par défaut
    base_config = RenderConfig()
    
    # 2. Loading Logic
    is_json = False
    
    # Détection de la source
    is_json = False
    if scene_source:
        # 1. Search for File Match (CWD or scenes/)
        candidates = [scene_source]
        
        # If relative path, try appending .json and checking scenes/
        if not os.path.isabs(scene_source):
            if not scene_source.endswith('.json'):
                candidates.append(scene_source + ".json")
            
            # Check scenes/ subdirectory
            candidates.append(os.path.join("scenes", scene_source))
            if not scene_source.endswith('.json'):
                candidates.append(os.path.join("scenes", scene_source + ".json"))
        
        found_file = None
        for c in candidates:
            if os.path.isfile(c):
                found_file = c
                break
        
        if found_file:
             print(f"[Loader] Resolved scene file: {found_file}")
             scene_source = found_file
             is_json = True
        
        # 2. Check Procedural Match
        elif scene_source in scenes.AVAILABLE_SCENES:
             is_json = False
        
        # 3. Fallback
        else:
             print(f"[Loader] Warning: Unknown scene '{scene_source}'. Falling back to default 'cornell'.")
             scene_source = 'cornell'
    else:
        # Default
        scene_source = 'cornell'

    if is_json:
        print(f"[Loader] Loading JSON Scene: {scene_source}")
        # On charge le JSON dans base_config et le builder
        success = load_scene_from_json(builder, scene_source, base_config)
        if not success:
            print("[Loader] Failed to load JSON. Exiting.")
            sys.exit(1)
    else:
        print(f"[Loader] Loading Procedural Scene: {scene_source}")
        scene_obj = scenes.AVAILABLE_SCENES[scene_source]
        # Setup procédural
        partial = scene_obj.setup(builder)
        # Apply partial to base
        # SceneConfig is flat, but flat_update in config.update_from_dict handles it!
        if partial:
            base_config.update_from_dict(asdict(partial))

    # 3. Apply CLI Overrides (Last interaction)
    # On utilise build_configuration pour merger args_overrides sur base_config
    if args_overrides:
        config = build_configuration(args_overrides, base_config)
    else:
        config = base_config

    # 4. Engine Camera Setup
    def v3(l): return cpp_engine.Vec3(float(l[0]), float(l[1]), float(l[2]))
    
    # Access nested camera settings
    cam = config.camera
    rend = config.render
    
    # Use safer defaults if scene forgot them
    aspect = rend.width / rend.height
    engine.set_camera(v3(cam.lookfrom), v3(cam.lookat), v3(cam.vup),
                      float(cam.vfov), float(aspect), float(cam.aperture), float(cam.focus_dist))

    # 5. Environment Load
    # Pass the EnvironmentSettings object to load_environment (which needs update)
    # OR pass fields. 
    # Let's update load_environment to take the object.
    load_environment(builder, config.environment)

    # 6. Blue Noise
    bn_path = "blue_noise.png"
    if os.path.exists(bn_path):
        try:
            print(f"[Loader] Loading Blue Noise Dither Tile: {bn_path}")
            bn_img = iio.imread(bn_path)
            if bn_img.ndim == 3: bn_img = bn_img[:, :, 0]
            bn_data = bn_img.astype(np.float32)
            if bn_img.dtype == np.uint8: bn_data /= 255.0
            engine.set_blue_noise_texture(np.ascontiguousarray(bn_data))
        except Exception as e:
            print(f"[Loader] Warning: Failed to load blue noise texture: {e}")
            
    # Apply global render settings that might affect engine state?
    # e.g. Sampler type
    
    return engine, config, builder

class EngineManager:
    """
    Context manager for the Engine to ensure resource cleanup.
    """
    def __init__(self, engine=None):
        self.engine = engine if engine is not None else cpp_engine.Engine()
    
    def __enter__(self):
        return self.engine
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.engine.clear()
        except:
            pass
        # Engine will be garbage collected eventually, but clear() releases heavy memory immediately.

