import cpp_engine
import numpy as np
from PIL import Image
import os
import time
import argparse
import threading
import multiprocessing
import math
from tqdm import tqdm
import glob
import scenes
from config import RenderConfig
from dataclasses import asdict

# ===============================================================================================
# 1. UTILS & POST-PROCESSING (C'est ici qu'on centralise la logique "Image")
# ===============================================================================================

def aces_filmic(x):
    """Narkowicz 2015 / ACES approximation"""
    a = 2.51
    b = 0.03
    c = 2.43
    d = 0.59
    e = 0.14
    return (x * (a * x + b)) / (x * (c * x + d) + e)

def apply_tone_mapping(linear_pixels):
    """Convertit des pixels linéaires (Physique) en sRGB affichable (ACES + Gamma 2.2)."""
    # 1. ACES Tonemapping
    data = aces_filmic(linear_pixels)
    
    # 2. Gamma Correction (Linear -> sRGB)
    data = np.clip(data, 0.0, 1.0)
    data = np.power(data, 1.0/2.2) 
    
    return data

def convert_to_uint8(data):
    """Convertit un tableau float (0..1) en uint8 (0..255)."""
    return (np.clip(data, 0.0, 1.0) * 255).astype(np.uint8)

def save_image(linear_pixels, filename):
    """Pipeline complet : ToneMap -> Uint8 -> Sauvegarde Disque."""
    toned = apply_tone_mapping(linear_pixels)
    img_uint8 = convert_to_uint8(toned)
    Image.fromarray(img_uint8, 'RGB').save(filename)
    print(f"Saved: {filename}")

def try_denoise(pixels):
    """Tente de débruiter l'image. Retourne None si échec ou module absent."""
    try:
        # Import local pour éviter de planter si le module n'est pas là au démarrage
        from denoise import denoise_image
        # print("Denoising...") 
        return denoise_image(pixels)
    except ImportError:
        return None
    except Exception as e:
        print(f"[Warn] Denoising failed: {e}")
        return None

# ===============================================================================================
# 2. CONFIGURATION & ENVIRONMENT
# ===============================================================================================

def build_configuration(args, scene_config):
    final_conf = RenderConfig()

    # 1. Appliquer la config de la scène
    if scene_config:
        scene_data = {k: v for k, v in asdict(scene_config).items() if v is not None}
        for k, v in scene_data.items():
            if hasattr(final_conf, k):
                setattr(final_conf, k, v)

    # 2. Appliquer les arguments CLI (Override)
    args_data = vars(args)
    for k, v in args_data.items():
        if v is not None and hasattr(final_conf, k):
            current_val = getattr(final_conf, k)
            if current_val != v:
                print(f"[Override] CLI '{k}': {current_val} -> {v}")
            setattr(final_conf, k, v)
            
    return final_conf

def load_environment(engine, env_path, background_level=None, direct_level=None, indirect_level=None, add_sun_light=False):
    """Charge la HDRI et configure le soleil physique automatique."""
    if not env_path or not os.path.exists(env_path):
        return

    try:
        import imageio.v3 as iio
        print(f"Loading environment map: {env_path}")
        
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
        if add_sun_light:
            print("Auto-Sun: Analyzing Environment...")
            sun_dir, sun_color = engine.get_env_sun_info()
            
            # On coupe le direct de l'envmap pour remplacer par le soleil physique
            engine.set_env_levels(bg_lvl, 0.1, indir_lvl)

            dist = 500.0
            pos = [sun_dir.x() * dist, sun_dir.y() * dist, sun_dir.z() * dist]
            
            # Normalisation et Boost
            raw_intensity = max(sun_color.x(), max(sun_color.y(), sun_color.z()))
            if raw_intensity <= 0: raw_intensity = 1.0
            
            target_intensity = 100.0 # Curseur d'intensité artistique
            scale = target_intensity / raw_intensity
            
            sun_col = [sun_color.x()*scale, sun_color.y()*scale, sun_color.z()*scale]
            
            engine.add_invisible_sphere_light(
                cpp_engine.Vec3(*pos), 
                15.0, # Rayon 
                cpp_engine.Vec3(*sun_col)
            )
            print(f"Auto-Sun added. Intensity scaled {raw_intensity:.0f} -> {target_intensity}")

    except Exception as e:
        print(f"Failed to load environment map: {e}")

# ===============================================================================================
# 3. RENDERING MODES
# ===============================================================================================

def run_single_frame(engine, conf, pool_threads):
    """Gère le rendu d'une image unique avec barre de progression."""
    print(f"Rendering Single Frame {conf.width}x{conf.height} ({conf.spp} spp)...")
    
    # 1. Lancement du thread de rendu
    result_container = {}
    def render_thread():
        try:
            result_container['pixels'] = engine.render(conf.width, conf.height, conf.spp, conf.depth, pool_threads)
        except Exception as e:
            result_container['error'] = e

    t = threading.Thread(target=render_thread)
    t.start()
    
    # 2. Gestion de la barre de progression
    t0 = time.time()
    pbar = tqdm(total=100, unit="%", bar_format="{l_bar}{bar}| {n:.1f}% [{elapsed}<{remaining}]")
    last_progress = 0
    
    while t.is_alive():
        progress = engine.get_progress() * 100
        if progress > last_progress:
            pbar.update(progress - last_progress)
            last_progress = progress
        time.sleep(0.1)
    
    pbar.update(100 - last_progress)
    pbar.close()
    t.join()
    
    if 'error' in result_container:
        print(f"Render failed: {result_container['error']}")
        return

    pixels = result_container['pixels']
    print(f"Render complete in {time.time()-t0:.2f}s")
    
    # 3. Pipeline de sauvegarde (Raw -> Denoised)
    print("Processing outputs...")
    save_image(pixels, 'output_raw.png')
    
    denoised_pixels = try_denoise(pixels)
    if denoised_pixels is not None:
        print("Denoising success.")
        save_image(denoised_pixels, 'output_denoised.png')
    else:
        print("Skipping denoise output (module missing or failed).")


def run_animation(engine, conf, pool_threads):
    """Gère le rendu d'une séquence d'animation et la compilation vidéo."""
    import imageio
    
    output_dir = "animation_frames"
    os.makedirs(output_dir, exist_ok=True)
    
    frames_data = [] # Stockera les arrays uint8 pour la vidéo finale
    start_frame = 0

    # 1. Vérification des frames existantes
    existing_files = sorted(glob.glob(os.path.join(output_dir, "frame_*.png")))
    num_existing = len(existing_files)

    if num_existing > 0:
        print(f"\n[Info] Found {num_existing} existing frames (Target: {conf.frames}).")
        
        # Logique interactive
        if num_existing < conf.frames:
            while True:
                choice = input("Resume render [r] or Delete all and restart [d]? ").strip().lower()
                
                if choice in ['r', 'resume']:
                    print(f"Resuming from frame {num_existing}...")
                    start_frame = num_existing
                    
                    # On doit recharger les images existantes pour la compilation vidéo finale
                    print("Reloading existing frames for video compilation...")
                    for fpath in tqdm(existing_files, desc="Loading frames"):
                        try:
                            # On charge et on s'assure que c'est du uint8 RGB
                            img = np.array(Image.open(fpath).convert('RGB'))
                            frames_data.append(img)
                        except Exception as e:
                            print(f"[Error] Failed to load {fpath}: {e}")
                    break
                    
                elif choice in ['d', 'delete', 'restart']:
                    print("Deleting existing frames...")
                    for fpath in existing_files:
                        try: os.remove(fpath)
                        except: pass
                    frames_data = [] # On repart à vide
                    start_frame = 0
                    break
        else:
            # On a déjà toutes les frames (ou plus)
            print("Target frame count reached.")
            choice = input("Recompile video only [c] or Delete and restart [d]? ").strip().lower()
            if choice in ['c', 'compile']:
                print("Reloading frames for compilation...")
                for fpath in existing_files[:conf.frames]:
                    frames_data.append(np.array(Image.open(fpath).convert('RGB')))
                start_frame = conf.frames # On saute le rendu
            else:
                print("Deleting and restarting...")
                for fpath in existing_files:
                    os.remove(fpath)
                start_frame = 0

    print(f"\nStarting Animation Loop: Frames {start_frame} to {conf.frames}")

    # Calcul de la base caméra (Tangente)
    center_pos = np.array(conf.lookfrom)
    target_pos = np.array(conf.lookat)
    forward = target_pos - center_pos
    forward /= np.linalg.norm(forward)
    world_up = np.array([0, 1, 0])
    right = np.cross(forward, world_up)
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)

    def v3(v): return cpp_engine.Vec3(float(v[0]), float(v[1]), float(v[2]))

    # Boucle de rendu
    for i in range(start_frame, conf.frames):
        print(f"--- Frame {i+1}/{conf.frames} ---")
        
        # A. Mise à jour Caméra (Wobble)
        t = (i / conf.frames) * 2 * math.pi
        offset = conf.radius * (math.cos(t) * right + math.sin(t) * up)
        new_lookfrom = center_pos + offset
        
        aspect = conf.width / conf.height
        engine.set_camera(
            v3(new_lookfrom), v3(target_pos), v3(conf.vup), 
            float(conf.vfov), float(aspect), 
            float(conf.aperture), float(conf.focus_dist)
        )
        
        # B. Rendu
        try:
            raw_pixels = engine.render(conf.width, conf.height, conf.spp, conf.depth, pool_threads)
            
            # C. Denoising
            clean_pixels = try_denoise(raw_pixels)
            if clean_pixels is None:
                clean_pixels = raw_pixels
            
            # D. Post-Process & Save
            # Note : on utilise les fonctions utilitaires définies plus haut dans le script
            final_pixels = apply_tone_mapping(clean_pixels)
            img_uint8 = convert_to_uint8(final_pixels)
            
            frame_path = os.path.join(output_dir, f"frame_{i:04d}.png")
            Image.fromarray(img_uint8, 'RGB').save(frame_path)
            
            frames_data.append(img_uint8)
            
        except Exception as e:
            print(f"Frame {i} failed: {e}")
            continue

    # 3. Compilation Vidéo
    if frames_data:
        print("Compiling MP4...")
        try:
            imageio.mimsave('animation.mp4', frames_data, fps=conf.fps, ffmpeg_params=['-crf', '18'])
            print("Animation saved: animation.mp4")
        except Exception as e:
            print(f"Video compilation failed: {e}")
            print("But frames are saved in 'animation_frames/' folder.")

# ===============================================================================================
# 4. MAIN ENTRY POINT
# ===============================================================================================

def main():
    parser = argparse.ArgumentParser(description='Python Path Tracer (C++ Core)')
    # ... (Définition des arguments identiques à avant) ...
    parser.add_argument('--scene', type=str, default=None, choices=scenes.AVAILABLE_SCENES.keys())
    parser.add_argument('--width', type=int)
    parser.add_argument('--height', type=int)
    parser.add_argument('--spp', type=int)
    parser.add_argument('--depth', type=int)
    parser.add_argument('--env', type=str)
    parser.add_argument('--env-background-level', type=float)
    parser.add_argument('--env-direct-level', type=float)
    parser.add_argument('--env-indirect-level', type=float)
    parser.add_argument('--aperture', type=float)
    parser.add_argument('--focus_dist', type=float)
    parser.add_argument('--auto-sun', action='store_true')
    parser.add_argument('--animate', action='store_true')
    parser.add_argument('--frames', type=int)
    parser.add_argument('--fps', type=int)
    parser.add_argument('--radius', type=float)
    parser.add_argument('--threads', type=int, default=0)
    parser.add_argument('--leave-cores', type=int, default=2)

    args = parser.parse_args()

    # 1. Init Moteur & Scène
    print("Initializing Engine...")
    engine = cpp_engine.Engine()
    
    scene_name = args.scene if args.scene else 'cornell'
    print(f"Loading Scene: {scene_name}")
    scene_obj = scenes.AVAILABLE_SCENES[scene_name]
    partial_config = scene_obj.setup(engine)
    
    # 2. Config finale
    conf = build_configuration(args, partial_config)
    
    # 3. Setup Camera Initial
    def v3(l): return cpp_engine.Vec3(float(l[0]), float(l[1]), float(l[2]))
    aspect = conf.width / conf.height
    engine.set_camera(v3(conf.lookfrom), v3(conf.lookat), v3(conf.vup),
                      float(conf.vfov), float(aspect), float(conf.aperture), float(conf.focus_dist))

    # 4. Setup Environment
    load_environment(engine, conf.env_map, 
                     conf.env_background_level, 
                     conf.env_direct_level, 
                     conf.env_indirect_level,
                     conf.auto_sun)

    # 5. Calcul Threads
    pool_threads = conf.threads
    if pool_threads == 0 and conf.leave_cores > 0:
        pool_threads = max(1, multiprocessing.cpu_count() - conf.leave_cores)
    print(f"Using {pool_threads} threads.")

    # 6. Dispatch
    if conf.animate:
        run_animation(engine, conf, pool_threads)
    else:
        run_single_frame(engine, conf, pool_threads)

if __name__ == "__main__":
    main()