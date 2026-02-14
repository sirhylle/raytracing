"""
================================================================================================
MODULE: CLI RENDERER (OFFLINE)
================================================================================================

DESCRIPTION:
  Handles the "offline" rendering process (command line interface).
  It orchestrates:
  1. Multithreading setup.
  2. Progress Bar tracking (tqdm).
  3. Image Post-Processing (Tone Mapping, Gamma Correction, Denoising).
  4. Video Compilation (if animation).

  This is where the raw linear floating point data from C++ is converted into 
  viewable PNG/MP4 files.

================================================================================================
"""
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
from denoise import denoise_image



# --- OUTPUT DIRECTORIES ---
OUTPUT_ROOT = "outputs"
IMG_DIR = os.path.join(OUTPUT_ROOT, "images")
FRAME_DIR = os.path.join(OUTPUT_ROOT, "frames")
VIDEO_DIR = os.path.join(OUTPUT_ROOT, "videos")

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

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
    """
    POST-PROCESSING PIPELINE
    ------------------------
    Raw render output is "Linear HDR" (values > 1.0, linear light).
    Monitors expect "Gamma Encoded SDR" (0.0 - 1.0, non-linear).
    
    1. Tone Mapping (ACES Filmic): Compresses High Dynamic Range (values > 1) 
       into the 0-1 range with a film-like curve (crushed blacks, desaturated highlights).
       
    2. Gamma Correction (sRGB): Applies the characteristic 2.2 gamma curve so the image
       looks correct on standard displays.
    """
    # 1. ACES Tonemapping
    data = aces_filmic(linear_pixels)
    
    # 2. Gamma Correction (Linear -> sRGB)
    data = np.clip(data, 0.0, 1.0)
    data = np.power(data, 1.0/2.2) 
    
    return data

def convert_to_uint8(data):
    """Converts a float array (0..1) to uint8 (0..255)."""
    return (np.clip(data, 0.0, 1.0) * 255).astype(np.uint8)

def overlay_params(pil_image, text):
    """Draws discrete text at the top right."""
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
    """Full pipeline: ToneMap -> Uint8 -> Disk Save."""
    toned = apply_tone_mapping(linear_pixels)
    img_uint8 = convert_to_uint8(toned)
    img = Image.fromarray(img_uint8, 'RGB')
    if overlay_text:
        img = overlay_params(img, overlay_text)
    img.save(filename)
    print(f"Saved: {filename}")

def save_debug_layer(data, filename, is_normal=False):
    """Saves a raw pass (Albedo or Normal) for inspection."""
    img_data = data.copy()
    if is_normal:
        # img_data = (img_data + 1.0) * 0.5
        # C++ already sends 0..1 => Do NOT touch.
        # Especially no Gamma which washes out vectors.
        pass
    else:
        # Albedo (Color) => Needs Gamma to be displayed correctly
        img_data = np.clip(img_data, 0.0, 1.0)
        img_data = np.power(img_data, 1.0/2.2)
    
    img_uint8 = (img_data * 255).astype(np.uint8)
    Image.fromarray(img_uint8, 'RGB').save(filename)
    print(f"Saved Debug: {filename}")

def try_denoise(pixels, **kwargs):
    """Attempts to denoise the image."""
    try:
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
    """
    Orchestrates the rendering of a still image.
    - Launches C++ Render in a background thread to keep Python responsive (for tqdm).
    - Polls progress periodically.
    - Saves Raw (Linear) and Processed (PNG) outputs.
    """
    width = conf.render.width
    height = conf.render.height
    spp = conf.render.spp
    depth = conf.render.depth
    sampler = conf.render.sampler
    
    print(f"[Renderer] Rendering Single Frame {width}x{height} ({spp} spp)...")
    
    result_container = {}
    def render_thread():
        try:
            result_container['output'] = engine.render(width, height, spp, depth, pool_threads, sampler)
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

    timestamp = datetime.datetime.now().strftime("_%Y%m%d_%H%M%S")
    overlay_txt = None

    if conf.system.param_stamp:
        ren_txt = f"Size: {width}x{height} | SPP: {spp} | Depth: {depth} | Time: {duration:.2f}s"
        sun_txt = f"Sun-Int: {conf.environment.sun_intensity:.2f} | Sun-Rad: {conf.environment.sun_radius:.2f} | Sun-Dist: {conf.environment.sun_dist:.2f} | Clipping: {conf.environment.clipping_multiplier:.2f}" if conf.environment.auto_sun else "Sun: Off"
        env_txt = f"Env-Exp: {conf.environment.exposure:.2f} |  Env-Bck: {conf.environment.background:.2f} | Env-Diff: {conf.environment.diffuse:.2f} | Env-Spec: {conf.environment.specular:.2f}"
        cam_txt = f"Camera: {[f'{x:.2f}' for x in conf.camera.lookfrom]} -> {[f'{x:.2f}' for x in conf.camera.lookat]} | Aperture: {conf.camera.aperture:.2f} | Focus: {conf.camera.focus_dist:.2f} | VFOV: {conf.camera.vfov:.2f}"
        
        overlay_txt = f"{ren_txt}\n{sun_txt}\n{env_txt}\n{cam_txt}"
    
    print("Processing outputs...")
    ensure_dir(IMG_DIR)
    
    # Determine what to save based on flags
    do_save_denoised = conf.system.keep_denoised
    do_save_raw = conf.system.keep_raw
    do_save_albedo = conf.system.keep_albedo
    do_save_normal = conf.system.keep_normal

    # Default behavior: If no flags are provided, save denoised only
    if not (do_save_denoised or do_save_raw or do_save_albedo or do_save_normal):
        do_save_denoised = True

    if do_save_raw: 
        save_image(pixels, os.path.join(IMG_DIR, f'output_raw{timestamp}.png'), overlay_txt)

    if albedo is not None and do_save_albedo:
        save_debug_layer(albedo, os.path.join(IMG_DIR, f'output_albedo{timestamp}.png'), is_normal=False)
    
    if normal is not None and do_save_normal:
        save_debug_layer(normal, os.path.join(IMG_DIR, f'output_normal{timestamp}.png'), is_normal=True)
    
    # Denoise
    # Optimization: Only run OIDN if we WANT to save the Denoised version
    denoised_pixels = None
    if do_save_denoised:
        denoised_pixels = try_denoise(pixels, albedo=albedo, normal=normal)
    
    if denoised_pixels is not None:
        print("Denoising success (with Feature Buffers).")
        save_image(denoised_pixels, os.path.join(IMG_DIR, f'output_denoised{timestamp}.png'), overlay_txt)
    elif do_save_denoised:
        print("Skipping denoise output (failed or module missing).")
        # Fallback: if user wanted denoised but it failed, we might want to warn or save raw as backup?
        # For now, if explicit denoised was requested and failed, we effectively save nothing for that channel.
        # But if it was the DEFAULT (no flags), we should probably save the raw one as 'output.png' or similar.
        print("Fallback: Saving RAW as main output due to denoise failure.")
        save_image(pixels, os.path.join(IMG_DIR, f'output_fallback{timestamp}.png'), overlay_txt)

def run_animation(engine, conf, pool_threads):
    import imageio
    
    ensure_dir(FRAME_DIR)
    ensure_dir(VIDEO_DIR)
    
    output_dir = FRAME_DIR
    
    frames_data = [] 
    start_frame = 0
    total_frames = conf.system.frames
    fps = conf.system.fps

    existing_files = sorted(glob.glob(os.path.join(output_dir, "frame_*.png")))
    num_existing = len(existing_files)

    if num_existing > 0:
        print(f"\n[Info] Found {num_existing} existing frames.")
        if num_existing < total_frames:
            # Assuming resume for now, not asking for interactive input to simplify.
            # Or force recompile if necessary.
            # In doubt, resume.
            print(f"Resuming from frame {num_existing}...")
            start_frame = num_existing
            for fpath in tqdm(existing_files, desc="Loading existing"):
                    frames_data.append(np.array(Image.open(fpath).convert('RGB')))
        else:
            print("All frames exist. Compiling only.")
            for fpath in existing_files[:total_frames]:
                    frames_data.append(np.array(Image.open(fpath).convert('RGB')))
            start_frame = total_frames

    print(f"Animation loop: {start_frame} -> {total_frames}")

    center_pos = np.array(conf.camera.lookfrom)
    target_pos = np.array(conf.camera.lookat)
    forward = target_pos - center_pos
    forward /= np.linalg.norm(forward)
    world_up = np.array([0, 1, 0])
    right = np.cross(forward, world_up)
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    def v3(v): return cpp_engine.Vec3(float(v[0]), float(v[1]), float(v[2]))
    
    turntable_radius = conf.system.turntable_radius

    for i in range(start_frame, total_frames):
        print(f"--- Frame {i+1}/{total_frames} ---")
        
        t = (i / total_frames) * 2 * math.pi
        offset = turntable_radius * (math.cos(t) * right + math.sin(t) * up)
        engine.set_camera(v3(center_pos + offset), v3(target_pos), v3(conf.camera.vup), 
                          float(conf.camera.vfov), float(conf.render.width/conf.render.height), 
                          float(conf.camera.aperture), float(conf.camera.focus_dist))
        
        try:
            # Determine saving preference
            do_save_denoised = conf.system.keep_denoised
            do_save_raw = conf.system.keep_raw
            if not (do_save_denoised or do_save_raw):
                do_save_denoised = True

            outputs = engine.render(conf.render.width, conf.render.height, conf.render.spp, conf.render.depth, pool_threads, conf.render.sampler)
            raw = outputs['color']
            
            clean = None
            if do_save_denoised:
                clean = try_denoise(raw, albedo=outputs['albedo'], normal=outputs['normal'])
            
            # 1. Save Raw if requested
            if do_save_raw:
                 raw_uint8 = convert_to_uint8(apply_tone_mapping(raw))
                 Image.fromarray(raw_uint8, 'RGB').save(os.path.join(output_dir, f"frame_raw_{i:04d}.png"))

            # 2. Prepare Final (Denoised or Raw fallback)
            final_pixels = raw
            if clean is not None:
                final_pixels = clean
            
            final_mapped = apply_tone_mapping(final_pixels)
            img_uint8 = convert_to_uint8(final_mapped)

            # 3. Save Final/Denoised if requested (or default)
            if do_save_denoised:
                frame_path = os.path.join(output_dir, f"frame_{i:04d}.png")
                Image.fromarray(img_uint8, 'RGB').save(frame_path)
            
            # Video compilation always uses the best available version
            frames_data.append(img_uint8)
            
        except Exception as e:
            print(f"Frame {i} failed: {e}")
            continue

    if frames_data:
        print("Compiling video...")
        timestamp = datetime.datetime.now().strftime("_%Y%m%d_%H%M%S")
        vid_path = os.path.join(VIDEO_DIR, f'animation{timestamp}.mp4')
        imageio.mimsave(vid_path, frames_data, fps=fps, ffmpeg_params=['-crf', '18'])
        print(f"Done: {vid_path}")

def run(engine, config):
    # Setup Threads
    pool_threads = config.system.threads
    if pool_threads == 0 and config.system.leave_cores > 0:
        pool_threads = max(1, multiprocessing.cpu_count() - config.system.leave_cores)
    print(f"[Renderer] Using {pool_threads} threads.")

    if config.system.animate:
        run_animation(engine, config, pool_threads)
    else:
        run_single_frame(engine, config, pool_threads)
