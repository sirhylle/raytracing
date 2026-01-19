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
        self.asset_library = {}

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
            'scale': [radius, radius, radius],
            'mat_type': mat_type,
            'color': color,
            'fuzz': float(fuzz),
            'ir': float(ir)
        }
        return obj_id

    def add_checker_sphere(self, center, radius, c1, c2, scale):
        # Conversion robuste Inputs (List/Tuple/Numpy -> Vec3)
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
            'fuzz': 0.0,
            'ir': 1.5
        }
        return obj_id

    def add_quad(self, Q, u, v, mat_type, color, fuzz=0.0, ir=1.5):
        # 1. Conversion des inputs (List -> Vec3)
        def to_v3(val):
            l = list(val) if isinstance(val, (list, tuple, np.ndarray)) else [val.x(), val.y(), val.z()]
            return cpp_engine.Vec3(float(l[0]), float(l[1]), float(l[2])), l

        v_Q, q_list = to_v3(Q)
        v_u, u_list = to_v3(u)
        v_v, v_list = to_v3(v)
        v_color, col_list = to_v3(color)

        # [CORRECTION] On crée le Quad à l'origine (0,0,0) dans le moteur C++
        # Ainsi, sa position ne dépendra QUE de la matrice de transformation.
        origin = cpp_engine.Vec3(0.0, 0.0, 0.0)
        
        # On passe 'origin' au lieu de 'v_Q'
        obj_id = self.engine.add_quad(origin, v_u, v_v, mat_type, v_color, float(fuzz), float(ir))
        
        # 2. On garde la VRAIE position dans le registre (pour le Gizmo)
        self.registry[obj_id] = {
            'type': 'quad',
            'pos': q_list, # Le Gizmo affichera cette position
            'u': u_list,
            'v': v_list,
            'rot': [0.0, 0.0, 0.0],
            'scale': [1.0, 1.0, 1.0],
            'mat_type': mat_type,
            'color': col_list,
            'fuzz': float(fuzz),
            'ir': float(ir)
        }
        
        # 3. [CRITIQUE] On applique immédiatement la transformation initiale
        # On déplace le Quad de (0,0,0) vers sa position Q
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
        
        # Gestion couleur (parfois Vec3 C++, parfois liste Python)
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
            'fuzz': 0.0,
            'ir': 1.0
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

        # Récupération des données par défaut depuis la bibliothèque
        def_type = 'lambertian'
        def_col = [0.8, 0.8, 0.8]
        def_fuzz = 0.0
        def_ir = 1.5
        if mesh_name in self.asset_library:
            info = self.asset_library[mesh_name]
            def_type = info.mat_type
            def_col = info.color
            def_fuzz = info.fuzz
            def_ir = info.ior
        
        # 2. Enregistrement
        self.registry[obj_id] = {
            'type': 'mesh',
            'name': mesh_name,
            'pos': list(pos),
            'rot': list(rot), # Stocké en degrés pour l'éditeur
            'scale': list(scale),
            'mat_type': def_type, 
            'color': def_col,
            'fuzz': def_fuzz,
            'ir': def_ir
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

    def set_environment(self, data):
        self.engine.set_environment(data)
    
    def set_env_levels(self, bg, dir, indir):
        self.engine.set_env_levels(bg, dir, indir)

    def get_env_sun_info(self):
        return self.engine.get_env_sun_info()


# ==================================================================================
# LOGIQUE DE CHARGEMENT
# ==================================================================================

def create_auto_sun(builder, intensity, radius, distance):
    """
    Analyse l'env map actuelle du moteur, trouve le point chaud,
    et crée un soleil physique correspondant via le builder.
    Retourne (sun_id, sun_dir_array, sun_raw_color_array).
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

def load_environment(builder, env_path, 
    env_light_level=None, env_direct_level=None, env_indirect_level=None, 
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
        
        # direct_lvl = Visibilité Caméra (Arg 1)
        cam_vis = env_direct_level if env_direct_level is not None else 1.0
        # light_lvl = Éclairage de la scène (Arg 2)
        lighting = env_light_level if env_light_level is not None else 1.0
        # indirect_lvl = Reflets (Arg 3)
        refl = env_indirect_level if env_indirect_level is not None else 1.0
        
        #builder.set_env_levels(bg_lvl, dir_lvl, indir_lvl)
        builder.set_env_levels(cam_vis, lighting, refl)

        if auto_sun:
            print("[Loader] Auto-Sun: Analyzing Environment...")
            
            # On applique le niveau d'environnement réduit pour l'Auto-Sun
            builder.set_env_levels(cam_vis, auto_sun_env_level, refl)

            # Appel de la logique partagée
            create_auto_sun(
                builder, 
                auto_sun_intensity, 
                auto_sun_radius, 
                auto_sun_dist
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
                     env_light_level=config.env_light_level, 
                     env_direct_level=config.env_direct_level, 
                     env_indirect_level=config.env_indirect_level,
                     auto_sun=config.auto_sun,
                     auto_sun_intensity=config.auto_sun_intensity,
                     auto_sun_radius=config.auto_sun_radius,
                     auto_sun_dist=config.auto_sun_dist,
                     auto_sun_env_level=config.auto_sun_env_level)
                     
    return engine, config, builder