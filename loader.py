import cpp_engine
import os
import numpy as np
import imageio.v3 as iio
import scenes
import transforms as tf
import math
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

    # --- Primitives Simples ---

    def add_sphere(self, center, radius, mat_type, color, fuzz=0.0, ir=1.5):
        # 1. Appel Moteur
        # Note: center peut être liste ou vec3, on assure le format liste pour le registre
        c_list = list(center) if isinstance(center, (list, tuple, np.ndarray)) else [center.x(), center.y(), center.z()]
        
        # Le binding C++ attend un Vec3
        v_center = cpp_engine.Vec3(float(c_list[0]), float(c_list[1]), float(c_list[2]))
        
        obj_id = self.engine.add_sphere(v_center, float(radius), mat_type, 
                                        cpp_engine.Vec3(float(color[0]), float(color[1]), float(color[2])), 
                                        float(fuzz), float(ir))
        
        # 2. Enregistrement État
        # Une sphère définie par rayon est vue comme un scale uniforme
        self.registry[obj_id] = {
            'type': 'sphere',
            'pos': c_list,
            'rot': [0.0, 0.0, 0.0],
            'scale': [radius, radius, radius]
        }
        return obj_id

    def add_checker_sphere(self, center, radius, c1, c2, scale):
        c_list = list(center) if isinstance(center, (list, tuple, np.ndarray)) else [center.x(), center.y(), center.z()]
        v_center = cpp_engine.Vec3(float(c_list[0]), float(c_list[1]), float(c_list[2]))
        v_c1 = cpp_engine.Vec3(float(c1[0]), float(c1[1]), float(c1[2]))
        v_c2 = cpp_engine.Vec3(float(c2[0]), float(c2[1]), float(c2[2]))

        obj_id = self.engine.add_checker_sphere(v_center, float(radius), v_c1, v_c2, float(scale))
        
        self.registry[obj_id] = {
            'type': 'checker_sphere',
            'pos': c_list,
            'rot': [0.0, 0.0, 0.0],
            'scale': [radius, radius, radius]
        }
        return obj_id

    def add_quad(self, Q, u, v, mat_type, color, fuzz=0.0, ir=1.5):
        # Les Quads sont gérés "bruts" pour l'instant (pas de matrice TRS simple)
        # On les passe tels quels, mais on pourrait imaginer une transformation plus tard.
        obj_id = self.engine.add_quad(Q, u, v, mat_type, 
                                      cpp_engine.Vec3(float(color[0]), float(color[1]), float(color[2])),
                                      float(fuzz), float(ir))
        # On enregistre un placeholder pour éviter les erreurs si on clique dessus
        self.registry[obj_id] = {
            'type': 'quad',
            'pos': [Q.x(), Q.y(), Q.z()],
            'rot': [0,0,0], 'scale': [1,1,1]
        }
        return obj_id

    def add_invisible_sphere_light(self, center, radius, color):
        c_list = list(center) if isinstance(center, (list, tuple, np.ndarray)) else [center.x(), center.y(), center.z()]
        v_center = cpp_engine.Vec3(float(c_list[0]), float(c_list[1]), float(c_list[2]))
        
        # Gestion couleur (parfois Vec3 C++, parfois liste Python)
        r, g, b = 0, 0, 0
        if hasattr(color, 'x'): r, g, b = color.x(), color.y(), color.z()
        else: r, g, b = color[0], color[1], color[2]

        obj_id = self.engine.add_invisible_sphere_light(v_center, float(radius), cpp_engine.Vec3(r,g,b))
        
        self.registry[obj_id] = {
            'type': 'light_sun',
            'pos': c_list,
            'rot': [0.0, 0.0, 0.0],
            'scale': [radius, radius, radius]
        }
        return obj_id

    # --- Instances (Meshes) ---

    def add_mesh_instance(self, mesh_name, pos=[0.0,0.0,0.0], rot=[0.0,0.0,0.0], scale=[1.0,1.0,1.0]):
        """
        Ajoute une instance de mesh avec une transformation complète.
        :param rot: Rotation en DEGRÉS [x, y, z]
        """
        # 1. Calcul de la Matrice (Ordre: Scale -> Rotate X/Y/Z -> Translate)
        # Note: transforms.py gère les degrés
        M = tf.translate(pos[0], pos[1], pos[2]) @ \
            tf.rotate_y(rot[1]) @ \
            tf.rotate_x(rot[0]) @ \
            tf.rotate_z(rot[2]) @ \
            tf.scale(scale[0], scale[1], scale[2])
            
        InvM = np.linalg.inv(M)
        
        c_M = np.ascontiguousarray(M, dtype=np.float32)
        c_InvM = np.ascontiguousarray(InvM, dtype=np.float32)
        
        obj_id = self.engine.add_instance(mesh_name, c_M, c_InvM)
        
        # 2. Enregistrement
        self.registry[obj_id] = {
            'type': 'mesh',
            'name': mesh_name,
            'pos': list(pos),
            'rot': list(rot), # Stocké en degrés pour l'éditeur
            'scale': list(scale)
        }
        return obj_id

    # --- Passthrough ---
    def load_asset(self, *args, **kwargs):
        # meshloader utilise directement l'engine pour charger les données brutes
        # Ce n'est pas un objet affichable, donc pas d'ID de scène.
        import meshloader
        return meshloader.load_asset(self.engine, *args, **kwargs)

    def set_environment(self, data):
        self.engine.set_environment(data)
    
    def set_env_levels(self, bg, dir, indir):
        self.engine.set_env_levels(bg, dir, indir)

    def get_env_sun_info(self):
        return self.engine.get_env_sun_info()


# ==================================================================================
# LOGIQUE DE CHARGEMENT
# ==================================================================================

def load_environment(builder, env_path, 
    background_level=None, direct_level=None, indirect_level=None, 
    auto_sun=False, auto_sun_intensity=None, auto_sun_radius=None,
    auto_sun_dist=None, auto_sun_env_level=None):
    """Charge la HDRI et configure le soleil physique automatique via le Builder."""

    if not env_path or not os.path.exists(env_path):
        print(f"[Loader] No environment map found or path invalid: {env_path}")
        return

    try:
        print(f"[Loader] Loading environment map: {env_path}")
        img = iio.imread(env_path)
        
        if img.ndim == 2: img = np.stack((img,)*3, axis=-1)
        if img.ndim == 3 and img.shape[2] > 3: img = img[:, :, :3]
        
        env_data = img.astype(np.float32)
        if img.dtype == np.uint8: env_data /= 255.0
        env_data = np.ascontiguousarray(env_data)

        builder.set_environment(env_data)
        
        bg_lvl = background_level if background_level is not None else 1.0
        dir_lvl = direct_level if direct_level is not None else 0.5
        indir_lvl = indirect_level if indirect_level is not None else 0.5
        
        builder.set_env_levels(bg_lvl, dir_lvl, indir_lvl)

        if auto_sun:
            print("[Loader] Auto-Sun: Analyzing Environment...")
            sun_dir, sun_color = builder.get_env_sun_info()
            
            builder.set_env_levels(bg_lvl, auto_sun_env_level, indir_lvl)

            dist = auto_sun_dist
            pos = [sun_dir.x() * dist, sun_dir.y() * dist, sun_dir.z() * dist]
            
            raw_intensity = max(sun_color.x(), max(sun_color.y(), sun_color.z()))
            if raw_intensity <= 0: raw_intensity = 1.0
            
            target_intensity = auto_sun_intensity 
            scale = target_intensity / raw_intensity
            
            sun_col = [sun_color.x()*scale, sun_color.y()*scale, sun_color.z()*scale]
            
            # On utilise le builder pour que le soleil soit éditable
            builder.add_invisible_sphere_light(
                pos, 
                auto_sun_radius,
                sun_col
            )
            print(f"[Loader] Auto-Sun added via Builder. Registry Updated.")

    except Exception as e:
        print(f"[Loader] Failed to load environment map: {e}")

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
    load_environment(builder, config.env_map, 
                     config.env_background_level, 
                     config.env_direct_level, 
                     config.env_indirect_level,
                     config.auto_sun,
                     config.auto_sun_intensity,
                     config.auto_sun_radius,
                     config.auto_sun_dist,
                     config.auto_sun_env_level)
                     
    return engine, config, builder