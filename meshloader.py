import trimesh
import numpy as np
import os

def load_mesh_to_engine(engine, file_path, scale=1.0, translation=[0,0,0], auto_center=False):
    """
    Charge un fichier 3D (.obj, .glb, .stl) et l'envoie au moteur C++.
    Gère la conversion automatique des matériaux (.mtl -> PBR).
    """
    if not os.path.exists(file_path):
        print(f"[Error] Mesh file not found: {file_path}")
        return

    print(f"[Loader] Processing mesh: {file_path}...")
    
    # 1. Chargement avec Trimesh
    # force='mesh' permet de s'assurer qu'on ne récupère pas une 'Scene' vide
    try:
        scene_or_mesh = trimesh.load(file_path, force=None)
    except Exception as e:
        print(f"[Error] Failed to load mesh: {e}")
        return

    # Si c'est une Scène (plusieurs objets), on itère sur toutes les géométries
    geometries = []
    if isinstance(scene_or_mesh, trimesh.Scene):
        # On peut fusionner tout en un seul mesh si on veut, 
        # mais garder les matériaux séparés est mieux.
        # dump(concatenate=False) retourne une liste de meshes
        geometries = list(scene_or_mesh.geometry.values())
    else:
        geometries = [scene_or_mesh]

    # Calcul du centre global pour l'auto-centrage (optionnel)
    if auto_center:
        # On calcule le bounds global
        all_verts = []
        for g in geometries: 
            all_verts.append(g.vertices)
        if all_verts:
            all_verts = np.vstack(all_verts)
            center_mass = all_verts.mean(axis=0)
        else:
            center_mass = np.array([0,0,0])

    print(f"[Loader] Found {len(geometries)} sub-meshes.")

    # 2. Traitement de chaque sous-objet
    for geom in geometries:
        # --- A. Conversion Matériau (.mtl -> PBR) ---
        mat_type = "lambertian"
        color = [0.8, 0.8, 0.8] # Gris par défaut
        fuzz = 0.0
        ior = 1.5
        
        # Trimesh parse le .mtl et le met dans 'visual.material'
        if hasattr(geom.visual, 'material'):
            mat = geom.visual.material
            
            # 1. Couleur (Diffuse / Albedo)
            if hasattr(mat, 'diffuse'):
                # diffuse est souvent en RGBA uint8 (0-255)
                # On convertit en float (0.0-1.0) et on enlève Alpha
                rgba = mat.diffuse
                if rgba.dtype == np.uint8:
                    color = rgba[:3] / 255.0
                else:
                    color = rgba[:3] # Déjà float

            # 2. Transparence (Verre)
            # 'opacity' dans trimesh vient souvent du 'd' du mtl
            opacity = getattr(mat, 'opacity', 1.0) # Par défaut 1.0 (Opaque)
            
            # Parfois l'alpha est dans la couleur diffuse[3]
            if len(getattr(mat, 'diffuse', [])) == 4:
                alpha = mat.diffuse[3] / 255.0 if mat.diffuse.dtype == np.uint8 else mat.diffuse[3]
                if alpha < opacity: opacity = alpha

            if opacity < 0.99:
                mat_type = "dielectric"
                # On essaie de trouver l'IOR (Ni), sinon 1.5 standard
                ior = getattr(mat, 'refraction_index', 1.5)
                # Petit hack : Si la couleur est très sombre (noir), le verre sera invisible.
                # On force un peu de blanc pour le "teinter"
                if np.mean(color) < 0.1: color = [0.9, 0.9, 0.9]

            # 3. Métaux (Spéculaire)
            # Heuristique : Si le speculaire est brillant, c'est du métal ou du plastique brillant
            elif hasattr(mat, 'specular'):
                spec = mat.specular
                if spec.dtype == np.uint8: spec = spec / 255.0
                
                # Si la composante spéculaire moyenne est forte (> 0.2)
                if np.mean(spec[:3]) > 0.2:
                    mat_type = "metal"
                    # Conversion Shininess (Phong) -> Roughness (PBR)
                    # Ns (Shininess) va souvent de 0 à 1000
                    shininess = getattr(mat, 'shininess', 50.0)
                    fuzz = max(0.0, min(1.0, 1.0 - (shininess / 1000.0)))

        # --- B. Nettoyage Géométrie ---
        
        # Important : Appliquer les transformations locales (si on vient d'une Scene)
        # (Certains loaders trimesh appliquent déjà, d'autres non, check rapide)
        # Ici on simplifie en assumant que geom.vertices est déjà en World Space
        # ou Local Space.
        
        # 1. Triangulation (S'assurer qu'on n'a pas de Quads)
        # trimesh le fait souvent au chargement, mais on force pour être sûr
        # (Note: trimesh stocke toujours en triangles, les quads sont divisés)
        
        # 2. Transformations manuelles (Scale / Translation / Centrage)
        verts = geom.vertices.copy()
        
        if auto_center:
            verts -= center_mass
        
        verts *= scale
        verts += np.array(translation)
        
        # 3. Préparation pour C++ (Contiguous Array + Float32/Int32)
        c_verts = np.ascontiguousarray(verts, dtype=np.float32)
        c_faces = np.ascontiguousarray(geom.faces, dtype=np.int32)

        # --- C. Envoi au Moteur ---
        # On utilise la méthode add_mesh
        # Note : on passe des listes Python pour la couleur si c'est un array numpy
        if isinstance(color, np.ndarray): color = color.tolist()
        
        engine.add_mesh(c_verts, c_faces, mat_type, color, float(fuzz), float(ior))
        
    print(f"[Loader] Finished. Loaded {len(geometries)} parts.")