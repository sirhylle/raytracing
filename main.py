import argparse
import sys
import os
import gc
import json
import shutil
from pathlib import Path

# Local imports
import loader
import scenes
from modes import renderer
from modes import editor as viewer
from config import RenderConfig

def cmd_render(args):
    """Handler for the 'render' command."""
    # 1. Initialize Engine & Config
    # scene_source is the positional argument 'scene'
    scene_source = args.scene
    
    # We pass 'args' as overrides. loader.initialize_scene_and_engine will merge them.
    engine, config, builder = loader.initialize_scene_and_engine(scene_source, args)
    
    # 2. Run Renderer
    try:
        renderer.run(engine, config)
    except KeyboardInterrupt:
        print("\n[System] Render interrupted by user.")
    
    # 3. Cleanup
    del engine
    gc.collect()

def cmd_editor(args):
    """Handler for the 'editor' command."""
    scene_source = args.scene # Can be None
    
    # 1. Initialize
    engine, config, builder = loader.initialize_scene_and_engine(scene_source, args)
    
    # 2. Run Editor
    # Legacy flags dispatch
    if args.v2:
        from modes import viewer_legacyV2 as viewer_legacyV2
        viewer_legacyV2.run(engine, config, builder)
    elif args.v1:
        from modes import viewer_legacyV1 as viewer_legacyV1
        viewer_legacyV1.run(engine, config)
    else:
        # Default V3
        viewer.run(engine, config, builder)

    # 4. Cleanup
    del engine
    gc.collect()

def cmd_init(args):
    """Handler for the 'init' command."""
    filename = args.filename
    if not filename.endswith('.json'):
        filename += '.json'
    
    # Logic: If no directory is specified, default to 'scenes/'
    if os.path.dirname(filename) == '':
        scenes_dir = 'scenes'
        if not os.path.exists(scenes_dir):
            try:
                os.makedirs(scenes_dir)
                print(f"[Info] Created directory: {scenes_dir}")
            except OSError as e:
                print(f"[Error] Could not create directory {scenes_dir}: {e}")
                return
        filename = os.path.join(scenes_dir, filename)
        
    if os.path.exists(filename) and not args.force:
        print(f"[Error] File '{filename}' already exists. Use --force to overwrite.")
        return

    template_name = args.template
    
    # Basic Template Data
    data = {
        "version": "1.0",
        "render_settings": {
            "width": 800,
            "height": 600,
            "spp": 100,
            "depth": 10
        },
        "camera": {
            "lookfrom": [0, 1, 3],
            "lookat": [0, 0, 0],
            "vfov": 40.0,
            "aperture": 0.0,
            "focus_dist": 10.0
        },
        "environment": {
            "background_level": 1.0,
            "diffuse_level": 1.0,
            "specular_level": 1.0,
            "auto_sun": False
        },
        "objects": []
    }

    # Template Customization
    if template_name == 'cornell':
        # Juste une référence, on ne va pas dumper toute la cornell box procédurale ici
        # Mais on pourrait pré-remplir les murs. 
        # Pour l'instant on fait simple.
        print("[Info] Cornell template not fully implemented in JSON init yet. Creating basic scene.")
    elif template_name == 'outdoor':
        data["environment"]["auto_sun"] = True
        data["environment"]["sun_intensity"] = 50.0
        data["environment"]["sun_radius"] = 10.0
        data["environment"]["sun_dist"] = 1000.0
        # Add a floor
        data["objects"].append({
            "type": "checker_sphere",
            "pos": [0, -1000.5, 0],
            "scale": [1000.0, 1000.0, 1000.0],
            "color": [0.2, 0.3, 0.1],
            "color2": [0.9, 0.9, 0.9], 
            "texture_scale": 10.0
        })

    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)
        print(f"[Success] Created new scene file: {filename}")
    except Exception as e:
        print(f"[Error] Failed to write file: {e}")

def main():
    parser = argparse.ArgumentParser(description="Python Path Tracer CLI (Data-Driven)")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # --- COMMON ARGUMENTS (reused across mixins) ---
    # Pour éviter la duplication, on peut utiliser des parents parsers, 
    # mais le plus simple ici est de définir des helpers ou de répéter un peu (c'est plus explicite).

    # 1. RENDER COMMAND
    parser_render = subparsers.add_parser('render', help='Render a scene (Headless)')
    parser_render.add_argument('scene', type=str, help='Path to JSON scene file or procedural scene name (e.g., cornell)')
    
    # Overrides
    grp_res = parser_render.add_argument_group("Resolution Override")
    grp_res.add_argument('--width', type=int, help='Override width')
    grp_res.add_argument('--height', type=int, help='Override height')
    
    grp_qual = parser_render.add_argument_group("Quality Override")
    grp_qual.add_argument('--spp', type=int, help='Override Samples Per Pixel')
    grp_qual.add_argument('--depth', type=int, help='Override Bounce Depth')
    grp_qual.add_argument('--sampler', type=int, choices=[0, 1], help='0=Random, 1=Sobol')
    
    grp_sys = parser_render.add_argument_group("System")
    grp_sys.add_argument('--threads', type=int, default=0, help='Number of threads (0=auto)')
    grp_sys.add_argument('--leave-cores', type=int, default=2, help='Cores to leave free (default: 2)')
    grp_sys.add_argument('--param-stamp', action='store_true', help='Burn params into image')
    
    grp_out = parser_render.add_argument_group("Output Control")
    grp_out.add_argument('--keep-raw', action='store_true', help='Save raw (noisy) render')
    grp_out.add_argument('--keep-denoised', action='store_true', help='Save denoised render (default if no flags)')
    grp_out.add_argument('--keep-albedo', action='store_true', help='Save albedo pass')
    grp_out.add_argument('--keep-normal', action='store_true', help='Save normal pass')
    
    grp_anim = parser_render.add_argument_group("Animation Override")
    grp_anim.add_argument('--animate', action='store_true', help='Enable animation')
    grp_anim.add_argument('--frames', type=int, help='Total frames')
    grp_anim.add_argument('--fps', type=int, help='Framerate')
    grp_anim.add_argument('--radius', type=float, help='Turntable radius')
    
    parser_render.set_defaults(func=cmd_render)

    # 2. EDITOR COMMAND
    parser_editor = subparsers.add_parser('editor', aliases=['gui'], help='Launch Interactive Editor')
    parser_editor.add_argument('scene', type=str, nargs='?', default=None, help='(Optional) Scene to open')
    
    parser_editor.add_argument('--width', type=int, help='Initial Window Width')
    parser_editor.add_argument('--height', type=int, help='Initial Window Height')
    parser_editor.add_argument('--threads', type=int, default=0)
    parser_editor.add_argument('--leave-cores', type=int, default=2)
    
    grp_legacy = parser_editor.add_argument_group("Legacy Versions")
    grp_legacy.add_argument('--v2', action='store_true', help='Use legacy PyGame editor')
    grp_legacy.add_argument('--v1', action='store_true', help='Use legacy Matplotlib editor')

    parser_editor.set_defaults(func=cmd_editor)

    # 3. INIT COMMAND
    parser_init = subparsers.add_parser('init', help='Initialize a new scene file')
    parser_init.add_argument('filename', type=str, help='Filename (e.g. my_scene.json)')
    parser_init.add_argument('--template', type=str, choices=['empty', 'cornell', 'outdoor'], default='empty', help='Starting template')
    parser_init.add_argument('--force', action='store_true', help='Overwrite existing file')
    
    parser_init.set_defaults(func=cmd_init)

    # Dispatch
    args = parser.parse_args()
    
    if hasattr(args, 'func'):
        args.func(args)
    else:
        # No subcommand provided
        parser.print_help()
        sys.exit(0)

if __name__ == "__main__":
    main()