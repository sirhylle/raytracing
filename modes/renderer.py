import cpp_engine
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import os
import time
import datetime
import threading
import multiprocessing
import math
from tqdm import tqdm
import glob

SAVE_INTERMEDIATE_IMAGES = False

# ===============================================================================================
# UTILS & POST-PROCESSING
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
    try:
        font = ImageFont.truetype("arial.ttf", 14) 
    except IOError:
        font = ImageFont.load_default()

    if hasattr(draw, "textbbox"):
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        # unused text_h
    else:
        text_w, _ = draw.textsize(text, font=font)

    margin = 10
    x = pil_image.width - text_w - margin
    y = margin

    draw.text((x+1, y+1), text, font=font, fill=(0, 0, 0))
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
    if is_normal:
        img_data = (img_data + 1.0) * 0.5
        
    img_data = np.clip(img_data, 0.0, 1.0)
    img_data = np.power(img_data, 1.0/2.2) 
    
    img_uint8 = (img_data * 255).astype(np.uint8)
    Image.fromarray(img_uint8, 'RGB').save(filename)
    print(f"Saved Debug: {filename}")

def try_denoise(pixels, **kwargs):
    """Tente de débruiter l'image."""
    try:
        from denoise import denoise_image
        return denoise_image(pixels, **kwargs)
    except ImportError:
        return None
    except Exception as e:
        print(f"[Warn] Denoising failed: {e}")
        return None

# ===============================================================================================
# RENDER LOOPS
# ===============================================================================================

def run_single_frame(engine, conf, pool_threads):
    print(f"[Renderer] Rendering Single Frame {conf.width}x{conf.height} ({conf.spp} spp)...")
    
    result_container = {}
    def render_thread():
        try:
            result_container['output'] = engine.render(conf.width, conf.height, conf.spp, conf.depth, pool_threads)
        except Exception as e:
            result_container['error'] = e

    t = threading.Thread(target=render_thread)
    t.start()
    
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

    outputs = result_container['output']
    pixels = outputs['color']
    albedo = outputs['albedo']
    normal = outputs['normal']
    
    duration = time.time() - t0
    print(f"Render complete in {duration:.2f}s")

    timestamp = ""
    overlay_txt = None

    if conf.param_stamp:
        timestamp = datetime.datetime.now().strftime("_%Y%m%d_%H%M%S")
        ren_txt = f"Size: {conf.width}x{conf.height} | SPP: {conf.spp} | Depth: {conf.depth} | Time: {duration:.2f}s"
        sun_txt = f"Sun-Int: {conf.auto_sun_intensity:.2f} | Sun-Rad: {conf.auto_sun_radius:.2f} | Sun-Dist: {conf.auto_sun_dist:.2f} | Sun-Env: {conf.auto_sun_env_level:.2f}" if conf.auto_sun else "Sun: Off"
        env_txt = f"Env-Dir: {conf.env_direct_level:.2f} |  Env-Ind: {conf.env_indirect_level:.2f} | Env-Bg: {conf.env_background_level:.2f}"
        cam_txt = f"Camera: {conf.lookfrom} -> {conf.lookat} | Aperture: {conf.aperture:.2f} | Focus: {conf.focus_dist:.2f} | VFOV: {conf.vfov:.2f}"
        
        overlay_txt = f"{ren_txt}\n{sun_txt}\n{env_txt}\n{cam_txt}"
    
    print("Processing outputs...")
    if SAVE_INTERMEDIATE_IMAGES: 
        save_image(pixels, f'output_raw{timestamp}.png', overlay_txt)

    if albedo is not None and SAVE_INTERMEDIATE_IMAGES:
        save_debug_layer(albedo, f'output_albedo{timestamp}.png', is_normal=False)
    
    if normal is not None and SAVE_INTERMEDIATE_IMAGES:
        save_debug_layer(normal, f'output_normal{timestamp}.png', is_normal=True)
    
    # Denoise
    denoised_pixels = try_denoise(pixels, albedo=albedo, normal=normal)
    
    if denoised_pixels is not None:
        print("Denoising success (with Feature Buffers).")
        save_image(denoised_pixels, f'output_denoised{timestamp}.png', overlay_txt)
    else:
        print("Skipping denoise output (failed or module missing). 保存 l'image raw.")
        save_image(pixels, f'output_denoised{timestamp}.png', overlay_txt)

def run_animation(engine, conf, pool_threads):
    import imageio
    
    output_dir = "animation_frames"
    os.makedirs(output_dir, exist_ok=True)
    
    frames_data = [] 
    start_frame = 0

    existing_files = sorted(glob.glob(os.path.join(output_dir, "frame_*.png")))
    num_existing = len(existing_files)

    if num_existing > 0:
        print(f"\n[Info] Found {num_existing} existing frames.")
        if num_existing < conf.frames:
            # Pour l'instant on assume resume, on ne demande pas d'input interactif ici pour simplifier
            # Ou on force la recompilation si nécessaire. 
            # Dans le doute, on reprend.
            print(f"Resuming from frame {num_existing}...")
            start_frame = num_existing
            for fpath in tqdm(existing_files, desc="Loading existing"):
                    frames_data.append(np.array(Image.open(fpath).convert('RGB')))
        else:
            print("All frames exist. Compiling only.")
            for fpath in existing_files[:conf.frames]:
                    frames_data.append(np.array(Image.open(fpath).convert('RGB')))
            start_frame = conf.frames

    print(f"Animation loop: {start_frame} -> {conf.frames}")

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
            outputs = engine.render(conf.width, conf.height, conf.spp, conf.depth, pool_threads)
            raw = outputs['color']
            
            clean = try_denoise(raw, albedo=outputs['albedo'], normal=outputs['normal'])
            if clean is None: clean = raw
            
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

def run(engine, config):
    # Calcul Threads
    pool_threads = config.threads
    if pool_threads == 0 and config.leave_cores > 0:
        pool_threads = max(1, multiprocessing.cpu_count() - config.leave_cores)
    print(f"[Renderer] Using {pool_threads} threads.")

    if config.animate:
        run_animation(engine, config, pool_threads)
    else:
        run_single_frame(engine, config, pool_threads)
