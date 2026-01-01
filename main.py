import cpp_engine
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import os
import time
import datetime
import argparse
import threading
import multiprocessing
import math
from tqdm import tqdm
import glob
import scenes
from config import RenderConfig
from dataclasses import asdict

SAVE_INTERMEDIATE_IMAGES = False

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

def overlay_params(pil_image, text):
    """Dessine un texte discret en haut à droite."""
    draw = ImageDraw.Draw(pil_image)
    
    # Essai de chargement d'une police propre (Arial sur Windows, ou défaut)
    try:
        # Taille 12 pour être discret mais lisible
        font = ImageFont.truetype("arial.ttf", 14) 
    except IOError:
        # Fallback si arial n'est pas trouvé (Linux/Mac parfois)
        font = ImageFont.load_default()

    # Calcul de la taille du texte pour le caler à droite
    # (textbbox est la méthode moderne de Pillow, textsize est déprécié)
    if hasattr(draw, "textbbox"):
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    else:
        # Fallback pour vieilles versions de Pillow
        text_w, text_h = draw.textsize(text, font=font)

    margin = 10
    x = pil_image.width - text_w - margin
    y = margin

    # 1. Ombre noire (pour lisibilité sur fond clair)
    draw.text((x+1, y+1), text, font=font, fill=(0, 0, 0))
    # 2. Texte blanc
    draw.text((x, y), text, font=font, fill=(255, 255, 255))
    
    return pil_image

def save_image(linear_pixels, filename, overlay_text=None):
    """Pipeline complet : ToneMap -> Uint8 -> Sauvegarde Disque."""
    toned = apply_tone_mapping(linear_pixels)
    img_uint8 = convert_to_uint8(toned)
    img = Image.fromarray(img_uint8, 'RGB')
    if overlay_text:
        img = overlay_params(img, overlay_text)
    img.save(filename)
    print(f"Saved: {filename}")

def save_debug_layer(data, filename, is_normal=False):
    """Sauvegarde une passe brute (Albedo ou Normal) pour inspection."""
    img_data = data.copy()
    
    # Si c'est une carte de normales, on transforme [-1, 1] vers [0, 1]
    if is_normal:
        img_data = (img_data + 1.0) * 0.5
        
    # On applique juste une correction Gamma simple pour que ce soit visible
    # (On n'utilise pas le Tonemapping ACES ici car on veut voir la donnée brute)
    img_data = np.clip(img_data, 0.0, 1.0)
    img_data = np.power(img_data, 1.0/2.2) 
    
    img_uint8 = (img_data * 255).astype(np.uint8)
    Image.fromarray(img_uint8, 'RGB').save(filename)
    print(f"Saved Debug: {filename}")

def try_denoise(pixels, **kwargs):
    """Tente de débruiter l'image. kwargs peut contenir albedo=... et normal=..."""
    try:
        from denoise import denoise_image
        return denoise_image(pixels, **kwargs)
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

    # 2. Gestion de la string compacte Auto-Sun
    if args.auto_sun is not None:
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
                    code = p[0].upper()      # La lettre (I, R, D, E)
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
                    elif code == 'E': 
                        print(f"[Override] CLI 'auto_sun_env_level': {final_conf.auto_sun_env_level} -> {val}")
                        final_conf.auto_sun_env_level = val
                    else: print(f"[Warn] Code auto-sun inconnu: {code}")
            except Exception as e:
                print(f"[Error] Failed to parse auto-sun string: {e}")

    # 3. Appliquer les arguments CLI (Override)
    args_data = vars(args)
    for k, v in args_data.items():
        if v is not None and hasattr(final_conf, k) and k != 'auto_sun':
            current_val = getattr(final_conf, k)
            if current_val != v:
                print(f"[Override] CLI '{k}': {current_val} -> {v}")
            setattr(final_conf, k, v)
            
    return final_conf

def load_environment(engine, env_path, 
    background_level=None, direct_level=None, indirect_level=None, 
    auto_sun=False, auto_sun_intensity=None, auto_sun_radius=None,
    auto_sun_dist=None, auto_sun_env_level=None):
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
        if auto_sun:
            print("Auto-Sun: Analyzing Environment...")
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
            print(f"Auto-Sun added. Intensity scaled {raw_intensity:.0f} -> {target_intensity}")

    except Exception as e:
        print(f"Failed to load environment map: {e}")

# ===============================================================================================
# 3. RENDERING MODES
# ===============================================================================================

def run_single_frame(engine, conf, pool_threads):
    print(f"Rendering Single Frame {conf.width}x{conf.height} ({conf.spp} spp)...")
    
    result_container = {}
    def render_thread():
        try:
            # engine.render renvoie maintenant un dict
            result_container['output'] = engine.render(conf.width, conf.height, conf.spp, conf.depth, pool_threads)
        except Exception as e:
            result_container['error'] = e

    t = threading.Thread(target=render_thread)
    t.start()
    
    # ... (Barre de progression identique) ...
    # ... (Copiez le bloc while t.is_alive() de votre ancien code ou du précédent) ...
    # (Pour abréger ici je remets juste la logique post-thread)
    
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

    # Extraction des buffers
    outputs = result_container['output']
    pixels = outputs['color']
    albedo = outputs['albedo']
    normal = outputs['normal']
    
    duration = time.time() - t0
    print(f"Render complete in {duration:.2f}s")

    timestamp = ""
    overlay_txt = None

    if conf.param_stamp:
        # 1. Création du Timestamp (ex: _20231025_143005)
        timestamp = datetime.datetime.now().strftime("_%Y%m%d_%H%M%S")
        
        # 2. Création du texte des paramètres
        ren_txt = f"Size: {conf.width}x{conf.height} | SPP: {conf.spp} | Depth: {conf.depth} | Time: {duration:.2f}s"
        sun_txt = f"Sun-Int: {conf.auto_sun_intensity:.2f} | Sun-Rad: {conf.auto_sun_radius:.2f} | Sun-Dist: {conf.auto_sun_dist:.2f} | Sun-Env: {conf.auto_sun_env_level:.2f}" if conf.auto_sun else "Sun: Off"
        env_txt = f"Env-Dir: {conf.env_direct_level:.2f} |  Env-Ind: {conf.env_indirect_level:.2f} | Env-Bg: {conf.env_background_level:.2f}"
        cam_txt = f"Camera: {conf.lookfrom} -> {conf.lookat} | Aperture: {conf.aperture:.2f} | Focus: {conf.focus_dist:.2f} | VFOV: {conf.vfov:.2f}"
        
        overlay_txt = (
            f"{ren_txt}\n"
            f"{sun_txt}\n"
            f"{env_txt}\n"
            f"{cam_txt}"
        )
    
    print("Processing outputs...")
    if SAVE_INTERMEDIATE_IMAGES: 
        save_image(pixels, f'output_raw{timestamp}.png', overlay_txt)

    if albedo is not None and SAVE_INTERMEDIATE_IMAGES:
        save_debug_layer(albedo, f'output_albedo{timestamp}.png', is_normal=False)
    
    if normal is not None and SAVE_INTERMEDIATE_IMAGES:
        save_debug_layer(normal, f'output_normal{timestamp}.png', is_normal=True)
    
    # Appel avec Albedo et Normal
    denoised_pixels = try_denoise(pixels, albedo=albedo, normal=normal)
    
    if denoised_pixels is not None:
        print("Denoising success (with Feature Buffers).")
        save_image(denoised_pixels, f'output_denoised{timestamp}.png', overlay_txt)
    else:
        print("Skipping denoise output.")

def run_animation(engine, conf, pool_threads):
    import imageio
    
    output_dir = "animation_frames"
    os.makedirs(output_dir, exist_ok=True)
    
    frames_data = [] 
    start_frame = 0

    # --- LOGIQUE DE REPRISE (RESUME) ---
    existing_files = sorted(glob.glob(os.path.join(output_dir, "frame_*.png")))
    num_existing = len(existing_files)

    if num_existing > 0:
        print(f"\n[Info] Found {num_existing} existing frames.")
        if num_existing < conf.frames:
            # Choix interactif
            choice = input("Resume [r] or Delete [d]? ").strip().lower()
            if choice in ['r', 'resume']:
                print(f"Resuming from frame {num_existing}...")
                start_frame = num_existing
                for fpath in tqdm(existing_files, desc="Loading existing"):
                     frames_data.append(np.array(Image.open(fpath).convert('RGB')))
            else:
                print("Deleting...")
                for f in existing_files: os.remove(f)
                frames_data = []
        else:
            # Tout est déjà là
            choice = input("Compile only [c] or Restart [d]? ").strip().lower()
            if choice in ['c']:
                print("Compiling...")
                for fpath in existing_files[:conf.frames]:
                     frames_data.append(np.array(Image.open(fpath).convert('RGB')))
                start_frame = conf.frames
            else:
                for f in existing_files: os.remove(f)
                start_frame = 0

    print(f"Animation loop: {start_frame} -> {conf.frames}")

    # (Calcul vecteurs caméra identique...)
    center_pos = np.array(conf.lookfrom)
    target_pos = np.array(conf.lookat)
    forward = target_pos - center_pos
    forward /= np.linalg.norm(forward)
    world_up = np.array([0, 1, 0])
    right = np.cross(forward, world_up)
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    def v3(v): return cpp_engine.Vec3(float(v[0]), float(v[1]), float(v[2]))

    for i in range(start_frame, conf.frames):
        print(f"--- Frame {i+1}/{conf.frames} ---")
        
        t = (i / conf.frames) * 2 * math.pi
        offset = conf.radius * (math.cos(t) * right + math.sin(t) * up)
        engine.set_camera(v3(center_pos + offset), v3(target_pos), v3(conf.vup), 
                          float(conf.vfov), float(conf.width/conf.height), 
                          float(conf.aperture), float(conf.focus_dist))
        
        try:
            # Rendu et unpack
            outputs = engine.render(conf.width, conf.height, conf.spp, conf.depth, pool_threads)
            raw = outputs['color']
            
            # Denoise avec features
            clean = try_denoise(raw, albedo=outputs['albedo'], normal=outputs['normal'])
            if clean is None: clean = raw
            
            # Save
            final = apply_tone_mapping(clean)
            img_uint8 = convert_to_uint8(final)
            
            frame_path = os.path.join(output_dir, f"frame_{i:04d}.png")
            Image.fromarray(img_uint8, 'RGB').save(frame_path)
            frames_data.append(img_uint8)
            
        except Exception as e:
            print(f"Frame {i} failed: {e}")
            continue

    if frames_data:
        print("Compiling video...")
        imageio.mimsave('animation.mp4', frames_data, fps=conf.fps, ffmpeg_params=['-crf', '18'])
        print("Done: animation.mp4")

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
    parser.add_argument('--auto-sun', nargs='?', const=True, default=None, help='Active le soleil. Optionnel: string compacte "I50.0 R50 D1000 E0.2"')
    parser.add_argument('--auto-sun-intensity', type=float)
    parser.add_argument('--auto-sun-radius', type=float)
    parser.add_argument('--auto-sun-dist', type=float)
    parser.add_argument('--auto-sun-env-level', type=float)
    parser.add_argument('--animate', action='store_true')
    parser.add_argument('--frames', type=int)
    parser.add_argument('--fps', type=int)
    parser.add_argument('--radius', type=float)
    parser.add_argument('--threads', type=int, default=0)
    parser.add_argument('--leave-cores', type=int, default=2)
    parser.add_argument('--param-stamp', action='store_true', help="Incruste les params sur l'image et un timestamp")

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
                     conf.auto_sun,
                     conf.auto_sun_intensity,
                     conf.auto_sun_radius,
                     conf.auto_sun_dist,
                     conf.auto_sun_env_level)

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