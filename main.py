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

# Global Defaults
DEFAULT_WIDTH = 800
DEFAULT_HEIGHT = 800 # or relative to aspect ratio
DEFAULT_SPP = 100
DEFAULT_DEPTH = 50
DEFAULT_ENV = "env-map.png"
DEFAULT_APERTURE = 0.0
DEFAULT_FOCUS_DIST = 10.0
DEFAULT_ENV_STRENGTH = 1.0

def load_environment(engine, env_path, strength=1.0, vis_override=None, light_override=None):
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
            
        # Apply base intensity multiplier (legacy strength)
        # If overrides are present, we handle split.
        # Ideally, we load raw data and use set_env_strength.
        
        # NOTE: We do NOT multiply data if we use set_env_strength properly?
        # Actually existing set_environment takes data.
        # Let's keep data as-is (multiply by 1.0 or strength if no overrides?)
        # Better: Multiply data by 1.0 (Raw). Apply multipliers via set_env_strength.
        
        # But wait, if we change behaviour, existing scenes might look different if they relied on data modification?
        # Actually previous code did `env_data *= strength`.
        # Now we want `vis = strength`, `light = strength`.
        
        # Let's load RAW.
        # env_data *= 1.0 
             
        # Ensure C-Contiguous
        env_data = np.ascontiguousarray(env_data, dtype=np.float32)

        engine.set_environment(env_data)
        
        # Calculate Final Strengths
        final_vis = strength
        final_light = strength
        
        if vis_override is not None: final_vis = vis_override
        if light_override is not None: final_light = light_override
        
        engine.set_env_strength(float(final_vis), float(final_light))
        
        print(f"Environment map loaded. Base={strength}, Vis={final_vis}, Light={final_light}")
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
    parser.add_argument('--scene', type=str, default='cornell', choices=scenes.AVAILABLE_SCENES.keys(), help='Scene to render')
    parser.add_argument('--width', type=int, default=DEFAULT_WIDTH, help='Image width')
    parser.add_argument('--height', type=int, help='Image height (default square/aspect ratio)')
    parser.add_argument('--spp', type=int, default=DEFAULT_SPP, help='Samples per pixel')
    parser.add_argument('--depth', type=int, default=DEFAULT_DEPTH, help='Max recursion depth')
    
    # Overrideable params (default=None to detect user input)
    parser.add_argument('--env', type=str, default=None, help='Path to environment map')
    # Removed --strength in favor of --ambient
    parser.add_argument('--aperture', type=float, default=None, help='Camera aperture')
    parser.add_argument('--focus_dist', type=float, default=None, help='Focus distance')
    
    # Lighting Debug
    parser.add_argument('--sun-intensity', type=float, default=None, help='Intensity of the Sun (Default: Scene specific)')
    parser.add_argument('--show-sun', action='store_true', help='Force sun to be visible (white ball)')
    parser.add_argument('--ambient', type=float, default=None, help='Ambient/Sky lighting multiplier (Default: Scene specific)')
    parser.add_argument('--sky-gain', type=float, default=None, help='Sky visibility multiplier (Default: 1.0)')

    # Animation
    parser.add_argument('--animate', action='store_true', help='Render an animation sequence')
    parser.add_argument('--frames', type=int, default=48, help='Number of frames')
    parser.add_argument('--fps', type=int, default=24, help='Frames per second')
    parser.add_argument('--radius', type=float, default=0.5, help='Radius of camera wobble')

    # Performance
    parser.add_argument('--threads', type=int, default=0, help='Explicit number of threads (0 = max avail)')
    parser.add_argument('--leave-cores', type=int, default=0, help='Number of CPU cores to leave free')
    
    # Removed --force-override as CLI now naturally overrides
    
    args = parser.parse_args()

    # Image Dimensions
    image_width = args.width
    # Aspect ratio logic: depends on scene? usually determined by W/H.
    # We'll set height first.
    if args.height:
        image_height = args.height
        aspect_ratio = image_width / image_height
    else:
        # Default square for now unless scene implies otherwise?
        # Usually aspect ratio is derived from image size, not vice versa in this engine.
        image_height = int(image_width / 1.0)
        aspect_ratio = 1.0

    print(f"Initializing C++ Engine...")
    engine = cpp_engine.Engine()
    
    # Create override dict
    overrides = {}
    if args.sun_intensity is not None:
        overrides['sun_intensity'] = args.sun_intensity
    if args.show_sun:
        overrides['sun_visible'] = True
        
    # Setup Scene
    print(f"Setting up scene: {args.scene}")
    scene_obj = scenes.AVAILABLE_SCENES[args.scene]
    
    # Try passing overrides (legacy scenes might fail)
    try:
        config = scene_obj.setup(engine, overrides)
    except TypeError:
         config = scene_obj.setup(engine)
    
    # Resolve Parameters (CLI > Scene > Default)
    aperture = resolve_param(args.aperture, config.aperture, "aperture", DEFAULT_APERTURE)
    focus_dist = resolve_param(args.focus_dist, config.focus_dist, "focus_dist", DEFAULT_FOCUS_DIST)
    env_map = resolve_param(args.env, config.env_map, "env", DEFAULT_ENV)
    
    # Lighting Resolution
    ambient = resolve_param(args.ambient, config.ambient, "ambient", DEFAULT_ENV_STRENGTH)
    sky_gain = resolve_param(args.sky_gain, config.sky_gain, "sky_gain", 1.0)
    
    # Camera
    if config.lookfrom is None: config.lookfrom = [278, 278, -800]
    if config.lookat is None: config.lookat = [278, 278, 0]
    if config.vup is None: config.vup = [0, 1, 0]
    if config.vfov is None: config.vfov = 40.0
    
    def v3(l): return cpp_engine.Vec3(float(l[0]), float(l[1]), float(l[2]))
    
    engine.set_camera(v3(config.lookfrom), v3(config.lookat), v3(config.vup), 
                      float(config.vfov), float(aspect_ratio), float(aperture), float(focus_dist))

    # Environment
    load_environment(engine, env_map, strength=1.0, 
                     vis_override=sky_gain, 
                     light_override=ambient)

    # Determine Threads
    pool_threads = 0
    if args.threads > 0:
        pool_threads = args.threads
    elif args.leave_cores > 0:
        total = multiprocessing.cpu_count()
        pool_threads = max(1, total - args.leave_cores)
    # else 0 invokes C++ default (max)

    # Render Logic
    if args.animate:
        import imageio
        output_dir = "animation_frames"
        os.makedirs(output_dir, exist_ok=True)
        
        # Check for existing frames
        existing_files = sorted(glob.glob(os.path.join(output_dir, "frame_*.png")))
        num_existing = len(existing_files)
        start_frame = 0
        frames = []
        
        if num_existing > 0:
            if num_existing < args.frames:
                print(f"Found {num_existing} existing frames (Target: {args.frames}).")
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
                # num_existing >= args.frames
                print(f"Found {num_existing} existing frames (Target: {args.frames}).")
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
                         start_frame = args.frames # Skip loop
                         
                         # Check if we should load frames for compilation
                         frames = []
                         print("Loading existing frames for compilation...")
                         for fpath in existing_files: # Load all, even if > args.frames? Or just up to args.frames?
                              # Only load up to args.frames usually, or all if we want full video
                              if len(frames) < args.frames: # Or match all
                                  try:
                                      img = Image.open(fpath).convert('RGB')
                                      frames.append(np.array(img))
                                  except: pass
                         break

        
        print(f"Starting Animation Render ({args.frames} frames)...")
        
        if start_frame < args.frames:
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
        
        for frame_idx in range(start_frame, args.frames):
            t = (frame_idx / args.frames) * 2 * math.pi
            
            # Wobble in the Right/Up plane
            offset = args.radius * (math.cos(t) * right + math.sin(t) * up)
            new_lookfrom = center_pos + offset
            
            # Update Camera
            engine.set_camera(v3(new_lookfrom), v3(target_pos), v3(config.vup), 
                              float(config.vfov), float(aspect_ratio), float(aperture), float(focus_dist))
            
            # Render Frame
            print(f"Rendering Frame {frame_idx+1}/{args.frames}...")
            # We can't reuse the threaded logic easily without refactoring 'render_thread' to be callable.
            # Let's simplify and run synchronous for animation to avoid complex thread restarts, 
            # OR wrap the thread logic in a loop. Synchronous is safer for now.
            
            try:
                raw_pixels = engine.render(image_width, image_height, args.spp, args.depth, pool_threads)
                
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
        imageio.mimsave('animation.mp4', frames, fps=args.fps)
        print("Saved animation.mp4")
        return

    # Standard Single Frame Render
    print(f"Rendering {image_width}x{image_height} with {args.spp} spp...")
    print(f"Config: Aperture={aperture}, Focus={focus_dist}, Env='{env_map}'")
    print(f"Lighting: Ambient={ambient}, SkyGain={sky_gain}")
    if pool_threads > 0:
        print(f"Threads: {pool_threads} (Limit applied)")
    else:
        print(f"Threads: Max Available")
    
    # Threaded Rendering
    result_container = {}
    def render_thread():
        try:
            result_container['pixels'] = engine.render(image_width, image_height, args.spp, args.depth, pool_threads)
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
