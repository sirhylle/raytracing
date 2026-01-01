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

def build_configuration(args, scene_config):
    # 1. Commencer avec les valeurs par défaut globales
    final_conf = RenderConfig()

    # 2. Appliquer la config de la scène (si elle existe)
    if scene_config:
        # On ne prend que les valeurs non-None définies par la scène
        scene_data = {k: v for k, v in asdict(scene_config).items() if v is not None}
        # On met à jour l'objet final
        for k, v in scene_data.items():
            if hasattr(final_conf, k):
                setattr(final_conf, k, v)

    # 3. Appliquer les arguments CLI (Priorité absolue)
    # L'astuce : argparse doit avoir des defaults=None pour savoir si l'user a tapé qqchose
    args_data = vars(args)
    for k, v in args_data.items():
        # Si l'argument existe dans la config et n'est pas None (donc fourni par l'user)
        if v is not None and hasattr(final_conf, k):
            current_val = getattr(final_conf, k)
            if current_val != v:
                print(f"[Override] CLI '{k}': {current_val} -> {v}")
            setattr(final_conf, k, v)
            
    return final_conf

def load_environment(engine, env_path, background_level_override=None, direct_level_override=None, indirect_level_override=None, add_sun_light=False):
    if not env_path or not os.path.exists(env_path):
        if env_path != DEFAULT_ENV: # Only warn if user specified something else or if default is missing
             print(f"Environment map '{env_path}' not found, using black background.")
        return

    try:
        import imageio.v3 as iio
        import imageio.v2 as iio2
        import imageio
        
        print(f"Loading environment map: {env_path}")
        
        # Determine format based on extension
        ext = os.path.splitext(env_path)[1].lower()
        is_exr = (ext == '.exr')
        
        env_data = None
        
        # Strategy 1: Default v3 load
        try:
             img = iio.imread(env_path)
             # Check if it loaded as uint8 when it should be HDR (exr/hdr)
             if is_exr and img.dtype == np.uint8:
                 print("Warning: EXR loaded as uint8 (LDR) by default backend. Attempting EXR-FI...")
                 raise ValueError("Low definition load for EXR")
             env_data = img
        except Exception as e_default:
             if is_exr:
                 print(f"Default load failed or low-quality: {e_default}. Trying FreeImage (EXR-FI)...")
                 # Strategy 2: FreeImage (v2 API)
                 try:
                     env_data = iio2.imread(env_path, format="EXR-FI")
                 except Exception as e_fi:
                     print(f"EXR-FI failed: {e_fi}. Attempting dependency download...")
                     try:
                         imageio.plugins.freeimage.download()
                         env_data = iio2.imread(env_path, format="EXR-FI")
                     except Exception as e_download:
                         print(f"Critical: Failed to load EXR even after download attempt: {e_download}")
                         raise e_download
             else:
                 raise e_default

        if env_data is None: raise RuntimeError("Failed to load image data.")
        
        img = env_data
        
        # Squeeze potential 4D (1, H, W, C)
        if img.ndim == 4 and img.shape[0] == 1:
            img = np.squeeze(img, axis=0)

        # Ensure RGB
        if img.ndim == 3 and img.shape[2] > 3:
            img = img[:, :, :3]
        elif img.ndim == 2:
            img = np.stack((img,)*3, axis=-1)
            
        # Float32 and Contiguous
        if img.dtype == np.uint8:
            env_data = img.astype(np.float32) / 255.0
        else:
            env_data = img.astype(np.float32)
        
        # Let's load RAW.
        # env_data *= 1.0 
             
        # Ensure C-Contiguous
        env_data = np.ascontiguousarray(env_data, dtype=np.float32)

        engine.set_environment(env_data)
        
        # Calculate Final Levels
        if background_level_override is not None: final_env_background_level = background_level_override
        else: final_env_background_level = DEFAULT_ENV_BACKGROUND_LEVEL
        if direct_level_override is not None: final_env_direct_level = direct_level_override
        else: final_env_direct_level = DEFAULT_ENV_DIRECT_LEVEL
        if indirect_level_override is not None: final_env_indirect_level = indirect_level_override
        else: final_env_indirect_level = DEFAULT_ENV_INDIRECT_LEVEL
        
        engine.set_env_levels(
            env_background_level=final_env_background_level,
            env_direct_level=final_env_direct_level,
            env_indirect_level=final_env_indirect_level
        )

        # --- AUTO-SUN LOGIC ---
        if add_sun_light:
            print("Analyzing Environment for Sun position...")
            sun_dir, sun_color = engine.get_env_sun_info()
            
            # IMPORTANT : On coupe la lumière directe de l'Env Map 
            # pour éviter d'avoir deux soleils (celui de l'image + la sphère)
            # On garde juste le background (visuel) et l'indirect (ciel bleu)
            engine.set_env_levels(
                env_background_level=final_env_background_level,
                env_direct_level=0.1,  # <--- ON REDUIT ICI
                env_indirect_level=final_env_indirect_level
            )

            # Position (Loin)
            dist = 500.0
            pos_x = sun_dir.x() * dist
            pos_y = sun_dir.y() * dist
            pos_z = sun_dir.z() * dist

            # NORMALISATION
            r = sun_color.x()
            g = sun_color.y()
            b = sun_color.z()
            current_max = max(r, max(g, b))

            # Sécurité anti-bug
            if current_max <= 0: current_max = 1.0

            # RÉGLAGE DE LA PUISSANCE
            # 50.0 = Soleil doux / Matin
            # 100.0 = Plein soleil (Zénith) -> Recommandé
            # 200.0 = Désert / Très brillant
            target_intensity = 100.0

            scale_factor = target_intensity / current_max

            final_sun_r = r * scale_factor
            final_sun_g = g * scale_factor
            final_sun_b = b * scale_factor

            print(f"Adding Physical Sun. Raw={current_max:.0f} -> Scaled={target_intensity}")

            sun_pos = cpp_engine.Vec3(pos_x, pos_y, pos_z)
            sun_col = cpp_engine.Vec3(final_sun_r, final_sun_g, final_sun_b)

            # Taille du soleil
            # Le soleil réel fait environ 0.5 degrés de diamètre.
            # tan(0.25 deg) * 1000 ~= 4.5 rayon
            sun_radius = 15.0 # Un peu plus gros pour des ombres douces (soft shadows)
            
            engine.add_invisible_sphere_light(sun_pos, sun_radius, sun_col)
        
        print(f"Environment map loaded. Image={env_path}, Background_level={final_env_background_level}, Direct_level={final_env_direct_level}, Indirect_level={final_env_indirect_level}")
    except Exception as e:
        print(f"Failed to load environment map: {e}")
        print("Fallback to PIL...")
        try:
             img_pil = Image.open(env_path).convert('RGB')
             env_data = np.array(img_pil).astype(np.float32) / 255.0 * strength
             env_data = np.ascontiguousarray(env_data, dtype=np.float32)
             engine.set_environment(env_data)
             print("Loaded via PIL fallback.")
        except Exception as e2:
             print(f"PIL fallback failed: {e2}")

def aces_filmic(x):
    # Narkowicz 2015 / ACES approximation
    a = 2.51
    b = 0.03
    c = 2.43
    d = 0.59
    e = 0.14
    return (x * (a * x + b)) / (x * (c * x + d) + e)

def resolve_param(cli_val, scene_val, name, default):
    """
    Resolve parameter: CLI (if set) > Scene (if set) > Default.
    Logs warning if CLI overrides Scene default.
    """
    if cli_val is not None:
        if scene_val is not None and cli_val != scene_val:
            print(f"[Info] CLI '{name}' ({cli_val}) overrides scene default ({scene_val}).")
        else:
            print(f"[Info] Using CLI '{name}' ({cli_val}).")
        return cli_val
        
    if scene_val is not None:
        return scene_val
        
    return default

def main():
    parser = argparse.ArgumentParser(description='Python Path Tracer (C++ Core)')
    
    # Renderer params
    parser.add_argument('--scene', type=str, default=None, choices=scenes.AVAILABLE_SCENES.keys(), help='Scene to render')
    parser.add_argument('--width', type=int, default=None, help='Image width')
    parser.add_argument('--height', type=int, default=None, help='Image height (default square/aspect ratio)')
    parser.add_argument('--spp', type=int, default=None, help='Samples per pixel')
    parser.add_argument('--depth', type=int, default=None, help='Max recursion depth')
    
    # Scene params
    parser.add_argument('--env', type=str, default=None, help='Path to environment map')
    parser.add_argument('--env-background-level', type=float, default=None, help='Environment brightness')
    parser.add_argument('--env-direct-level', type=float, default=None, help='Environment direct light level')
    parser.add_argument('--env-indirect-level', type=float, default=None, help='Environment indirect light level')
    parser.add_argument('--aperture', type=float, default=None, help='Camera aperture')
    parser.add_argument('--focus_dist', type=float, default=None, help='Focus distance')
    parser.add_argument('--auto-sun', action='store_true', default=None, help='Add a physical sun sphere based on environment hotspot')

    # Animation params
    parser.add_argument('--animate', action='store_true', default=None, help='Render an animation sequence')
    parser.add_argument('--frames', type=int, default=None, help='Number of frames')
    parser.add_argument('--fps', type=int, default=None, help='Frames per second')
    parser.add_argument('--radius', type=float, default=None, help='Radius of camera wobble')

    # Performance
    parser.add_argument('--threads', type=int, default=None, help='Explicit number of threads (0 = max avail)')
    parser.add_argument('--leave-cores', type=int, default=None, help='Number of CPU cores to leave free')

    args = parser.parse_args()

    # 1. Initialiser moteur
    print(f"Initializing C++ Engine...")
    engine = cpp_engine.Engine()
        
    # 2. Setup Scene
    scene_name = args.scene if args.scene else 'cornell'
    print(f"Setting up Scene: {scene_name}")
    scene_obj = scenes.AVAILABLE_SCENES[scene_name]
    partial_scene_config = scene_obj.setup(engine)
    
    # 3. Fusion des paramètres CLI et Scene
    conf = build_configuration(args, partial_scene_config)
    final_config = build_configuration(args, partial_scene_config)
    
    # 4. Camera
    def v3(l): return cpp_engine.Vec3(float(l[0]), float(l[1]), float(l[2]))
    # Aspect Ratio Logic (si width/height pas fournis, les defaults de RenderConfig s'appliquent)
    aspect = conf.width / conf.height
    print(f"Setting up Camera: {conf.lookfrom} -> {conf.lookat}, Aspect: {aspect}, Aperture: {conf.aperture}, Focus: {conf.focus_dist}")
    engine.set_camera(
        v3(conf.lookfrom), v3(conf.lookat), v3(conf.vup),
        float(conf.vfov), float(aspect), 
        float(conf.aperture), float(conf.focus_dist)
    )

    # 5. Environment
    load_environment(engine, conf.env_map, 
                     conf.env_background_level, 
                     conf.env_direct_level, 
                     conf.env_indirect_level,
                     conf.auto_sun)

    # 6. Threads
    pool_threads = conf.threads
    if pool_threads == 0 and conf.leave_cores > 0:
        pool_threads = max(1, multiprocessing.cpu_count() - conf.leave_cores)
    print(f"Setting up Threads: {pool_threads}")

    # Render Logic
    if conf.animate:
        import imageio
        output_dir = "animation_frames"
        os.makedirs(output_dir, exist_ok=True)
        
        # Check for existing frames
        existing_files = sorted(glob.glob(os.path.join(output_dir, "frame_*.png")))
        num_existing = len(existing_files)
        start_frame = 0
        frames = []
        
        if num_existing > 0:
            if num_existing < conf.frames:
                print(f"Found {num_existing} existing frames (Target: {conf.frames}).")
                while True:
                    choice = input("Resume from last frame [r] or Delete all and restart [d]? ").strip().lower()
                    if choice == 'r' or choice == 'resume':
                        # Resume
                        print(f"Resuming from frame {num_existing}...")
                        start_frame = num_existing
                        # Load existing frames to ensure video compilation is complete
                        print("Loading existing frames...")
                        for fpath in existing_files:
                            try:
                                img = Image.open(fpath).convert('RGB')
                                frames.append(np.array(img))
                            except Exception as e:
                                print(f"Warning: Failed to load {fpath}: {e}")
                        break
                    elif choice == 'delete' or choice == 'd' or choice == 'restart':
                        # Reset
                        print("Deleting existing frames...")
                        for fpath in existing_files:
                            os.remove(fpath)
                        frames = []
                        break
            else:
                # num_existing >= conf.frames
                print(f"Found {num_existing} existing frames (Target: {conf.frames}).")
                while True:
                     choice = input("Delete and restart? [y/n] ").strip().lower()
                     if choice == 'y':
                         print("Deleting existing frames...")
                         for fpath in existing_files:
                             os.remove(fpath)
                         frames = []
                         break
                     else:
                         print("Aborting render. Proceeding to compilation if available.")
                         # If we don't restart, we might want to just compile what we have or exit.
                         # Let's try to load them and compile video.
                         start_frame = conf.frames # Skip loop
                         
                         # Check if we should load frames for compilation
                         frames = []
                         print("Loading existing frames for compilation...")
                         for fpath in existing_files: # Load all, even if > conf.frames? Or just up to conf.frames?
                              # Only load up to conf.frames usually, or all if we want full video
                              if len(frames) < conf.frames: # Or match all
                                  try:
                                      img = Image.open(fpath).convert('RGB')
                                      frames.append(np.array(img))
                                  except: pass
                         break

        
        print(f"Starting Animation Render ({conf.frames} frames)...")
        
        if start_frame < conf.frames:
             pass # frames list is already populated if resuming

        
        # Calculate Basis for Tangent Circle
        # Center = lookfrom
        # Forward = lookat - lookfrom
        
        center_pos = np.array(config.lookfrom)
        target_pos = np.array(config.lookat)
        forward = target_pos - center_pos
        forward = forward / np.linalg.norm(forward)
        
        # Arbitrary Up for Basis construction (not necessarily scene Up)
        world_up = np.array([0, 1, 0])
        # If looking straight up/down, handle singularity? Assuming not.
        right = np.cross(forward, world_up)
        right = right / np.linalg.norm(right)
        up = np.cross(right, forward) # Orthogonal up
        
        for frame_idx in range(start_frame, conf.frames):
            t = (frame_idx / conf.frames) * 2 * math.pi
            
            # Wobble in the Right/Up plane
            offset = conf.radius * (math.cos(t) * right + math.sin(t) * up)
            new_lookfrom = center_pos + offset
            
            # Update Camera
            engine.set_camera(v3(new_lookfrom), v3(target_pos), v3(config.vup), 
                              float(config.vfov), float(aspect_ratio), float(aperture), float(focus_dist))
            
            # Render Frame
            print(f"Rendering Frame {frame_idx+1}/{conf.frames}...")
            # We can't reuse the threaded logic easily without refactoring 'render_thread' to be callable.
            # Let's simplify and run synchronous for animation to avoid complex thread restarts, 
            # OR wrap the thread logic in a loop. Synchronous is safer for now.
            
            try:
                raw_pixels = engine.render(conf.width, conf.height, conf.spp, conf.depth, pool_threads)
                
                # Post Process
                # Denoise (Optional inside loop)
                frame_pixels = raw_pixels
                try:
                    from denoise import denoise_image
                    # Only denoise if imported successfully
                    frame_pixels = denoise_image(raw_pixels)
                except ImportError:
                    pass
                except Exception:
                    pass # Denoise failed, fallback to raw

                # Tone Map
                frame_pixels = aces_filmic(frame_pixels)
                frame_pixels = np.clip(frame_pixels, 0.0, 1.0)
                frame_pixels = np.power(frame_pixels, 1.0/2.2)
                
                # Convert to uint8
                img_uint8 = (frame_pixels * 255).astype(np.uint8)
                
                # Save Frame
                frame_path = os.path.join(output_dir, f"frame_{frame_idx:04d}.png")
                Image.fromarray(img_uint8, 'RGB').save(frame_path)
                frames.append(img_uint8)
                
            except Exception as e:
                print(f"Frame {frame_idx} failed: {e}")
                
        # Compile Video
        print("Compiling video...")
        imageio.mimsave('animation.mp4', frames, fps=conf.fps)
        print("Saved animation.mp4")
        return

    # Standard Single Frame Render
    print(f"Rendering {conf.width}x{conf.height} with {conf.spp} spp...")
    print(f"Config: Aperture={conf.aperture}, Focus={conf.focus_dist}, Env='{conf.env_map}'")
    print(f"Lighting: EnvBackgroundLevel={conf.env_background_level}, EnvDirectLevel={conf.env_direct_level}, EnvIndirectLevel={conf.env_indirect_level}")
    if pool_threads > 0:
        print(f"Threads: {pool_threads} (Limit applied)")
    else:
        print(f"Threads: Max Available")
    
    # Threaded Rendering
    result_container = {}
    def render_thread():
        try:
            result_container['pixels'] = engine.render(conf.width, conf.height, conf.spp, conf.depth, pool_threads)
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
    t1 = time.time()
    
    if 'error' in result_container:
        print(f"\nRender failed: {result_container['error']}")
        return

    pixels = result_container['pixels']
    print(f"\nRender complete in {t1-t0:.2f}s")
    
    # Denoise
    denoised_pixels = None
    try:
        from denoise import denoise_image
        print("Denoising...")
        denoised_pixels = denoise_image(pixels)
    except:
        pass



    def process_and_save(data, name):
        # Tone Map
        # 1. Exposure (Optional, maybe engine output is already exposed well?)
        # Let's assume engine output is linear physical units. 
        # For simplicity, we skip exposure gain unless scene is dark.
        
        # 2. ACES
        data = aces_filmic(data)
        
        # 3. Gamma 2.2
        data = np.clip(data, 0.0, 1.0)
        data = np.power(data, 1.0/2.2) 
        
        img = Image.fromarray((data * 255).astype(np.uint8), 'RGB')
        img.save(name)
        print(f"Saved {name} (ACES + Gamma)")

    print("Saving images...")
    process_and_save(pixels, 'output_raw.png')
    if denoised_pixels is not None:
        process_and_save(denoised_pixels, 'output_denoised.png')

if __name__ == "__main__":
    main()
