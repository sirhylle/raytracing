import argparse
import scenes
import loader
from modes import renderer
from modes import viewer_pygames as viewer
import gc

def main():
    parser = argparse.ArgumentParser(description='Python Path Tracer (C++ Core)')
    
    # --- Arguments Généraux ---
    group_general = parser.add_argument_group("General")
    group_general.add_argument('--scene', type=str, default=None, choices=scenes.AVAILABLE_SCENES.keys(), help="Choice of the scene to render (default: cornell, or defined in scenes.py)")
    group_general.add_argument('--preview', action='store_true', help="Enable real-time preview mode")
    
    # --- Arguments de Rendu (Config) ---
    group_render = parser.add_argument_group("Rendering Configuration")
    group_render.add_argument('--width', type=int, help="Output image width in pixels")
    group_render.add_argument('--height', type=int, help="Output image height in pixels")
    group_render.add_argument('--spp', type=int, help="Samples per pixel (default: 100, higher = better quality and slower)")
    group_render.add_argument('--depth', type=int, help="Maximum recursion depth for light bounces (default: 50)")
    
    # --- Environment ---
    group_env = parser.add_argument_group("Environment")
    group_env.add_argument('--env', type=str, dest='env_map', help="Path to HDR environment map file")
    group_env.add_argument('--env-background-level', type=float, help="Background light intensity multiplier")
    group_env.add_argument('--env-direct-level', type=float, help="Direct lighting intensity from environment")
    group_env.add_argument('--env-indirect-level', type=float, help="Indirect lighting intensity from environment")
    
    # --- Camera ---
    group_cam = parser.add_argument_group("Camera")
    group_cam.add_argument('--lookfrom', nargs=3, type=float, help="Camera position (x y z)")
    group_cam.add_argument('--lookat', nargs=3, type=float, help="Camera target point (x y z)")
    group_cam.add_argument('--vup', nargs=3, type=float, help="Camera up vector (x y z)")
    group_cam.add_argument('--vfov', type=float, help="Vertical Field of View in degrees (default: 40)")
    group_cam.add_argument('--aperture', type=float, help="Camera aperture radius (default: 0.0, for pinhole)")
    group_cam.add_argument('--focus_dist', type=float, help="Distance to focus plane (default: 10)")
    
    # --- Auto-Sun ---
    group_sun = parser.add_argument_group("Auto-Sun")
    group_sun.add_argument('--auto-sun', nargs='?', const=True, default=None, help='Enable physical sun. Optional config string: "I50.0 R50 D1000 E0.2"')
    group_sun.add_argument('--auto-sun-intensity', type=float, help="Intensity of the physical sun (default: 50)")
    group_sun.add_argument('--auto-sun-radius', type=float, help="Radius of the physical sun (default: 50, affects soft shadows)")
    group_sun.add_argument('--auto-sun-dist', type=float, help="Distance of the sun from origin (default: 1000)")
    group_sun.add_argument('--auto-sun-env_level', type=float, help="Environment map multiplier when sun is active (default: 0.2)")
    
    # --- Animation ---
    group_anim = parser.add_argument_group("Animation")
    group_anim.add_argument('--animate', action='store_true', help="Enable animation mode (turntable)")
    group_anim.add_argument('--frames', type=int, help="Number of frames for animation")
    group_anim.add_argument('--fps', type=int, help="Frames per second for video output")
    group_anim.add_argument('--radius', type=float, help="Turntable radius for camera orbit")
    
    # --- System ---
    group_sys = parser.add_argument_group("System")
    group_sys.add_argument('--threads', type=int, default=0, help="Number of threads to use (0 = auto)")
    group_sys.add_argument('--leave-cores', type=int, default=2, help="Number of cores to leave free when using auto-threads (default: 2)")
    group_sys.add_argument('--param-stamp', action='store_true', help="Writes parameters inside the image, adds a timestamp to the filename")
    group_sys.add_argument('--save-raw', action='store_true', help="Save intermediate images (raw, albedo, normal)")

    args = parser.parse_args()

    # 1. Init Moteur & Scène (Loader)
    # C'est ici que toute la magie d'initialisation opère
    engine, config = loader.initialize_scene_and_engine(args)
    
    # 2. Dispatch selon le mode
    if args.preview:
        final_cam = viewer.run(engine, config)
        if final_cam:
            print("\n" + "="*60)
            print("CAMERA STATE CAPTURED")
            print("="*60)
            
            # Formatage des vecteurs avec 2 décimales pour être propre
            def fmt_vec(v): return f"{v[0]:.2f} {v[1]:.2f} {v[2]:.2f}"
            
            # Construction de la ligne de commande
            cmd = "uv run main.py"
            if args.scene: cmd += f" --scene {args.scene}"
            
            # On ajoute les params de rendu (non modifiés par le viewer mais utiles pour le replay)
            cmd += f" --width {config.width} --height {config.height} --spp {config.spp}"
            
            # Paramètres Caméra (Modifiés)
            cmd += f" --lookfrom {fmt_vec(final_cam['lookfrom'])}"
            cmd += f" --lookat {fmt_vec(final_cam['lookat'])}"
            cmd += f" --vfov {final_cam['vfov']:.2f}"
            cmd += f" --focus_dist {final_cam['focus_dist']:.2f}"
            
            # Si auto-sun était présent
            if args.auto_sun:
               # On remet l'argument auto-sun tel quel (s'il était présent)
               # Note: Si l'utilisateur a modifié le soleil dynamiquement dans le viewer (pas encore implémenté), 
               # il faudrait aussi le dumper ici. Pour l'instant on garde l'original.
               if isinstance(args.auto_sun, str):
                   cmd += f" --auto-sun \"{args.auto_sun}\""
               else:
                   cmd += " --auto-sun"

            print("To render this exact view, use:\n")
            print(cmd)
            print("\n" + "="*60)

    else:
        renderer.run(engine, config)

    # 3. Cleanup Explicit (Fix Nanobind Leaks at exit)
    # On supprime l'objet moteur pour que le destructeur C++ soit appelé
    # avant l'arrêt de l'interpréteur Python.
    del engine
    gc.collect()



if __name__ == "__main__":
    main()