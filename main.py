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
import cpp_engine
from config import RenderConfig

def cmd_render(args):
    """Handler for the 'render' command."""
    # 1. Initialize Engine & Config
    scene_source = args.scene
    
    with loader.EngineManager() as engine:
        # We pass 'engine' to initialize_scene_and_engine to use within context
        engine, config, builder = loader.initialize_scene_and_engine(scene_source, args, engine=engine)
        
        # 2. Run Renderer
        try:
            renderer.run(engine, config)
        except KeyboardInterrupt:
            print("\n[System] Render interrupted by user.")

def cmd_editor(args):
    """Handler for the 'editor' command."""
    scene_source = args.scene # Can be None
    
    with loader.EngineManager() as engine:
        # 1. Initialize
        engine, config, builder = loader.initialize_scene_and_engine(scene_source, args, engine=engine)
        
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

import serializer # NEW
from dataclasses import asdict # NEW

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
    
    # Generate Scene using Builder & Serializer
    print(f"[Info] Generating scene '{filename}' from template '{template_name}'...")
    
    # 1. Init Virtual Engine (No Window needed)
    # We use a dummy builder to accumulate objects
    with loader.EngineManager() as engine:
        builder = loader.SceneBuilder(engine)
        config = RenderConfig()
        
        # 2. Load Template
        # We use the existing scenes.py module which defines templates
        scene_cls = scenes.AVAILABLE_SCENES.get(template_name)
        if not scene_cls:
            print(f"[Warning] Template '{template_name}' not found. Using 'empty'.")
            scene_cls = scenes.Empty()
            
        # 3. Setup Scene (Populate Builder & Config)
        try:
            scene_config = scene_cls.setup(builder)
            if scene_config:
                # Update RenderConfig from SceneConfig (dataclass)
                # We use asdict to convert it to a dictionary
                config.update_from_dict(asdict(scene_config))
                
                # Special case: Map scene_config.environment to config.environment (path or color)
                # update_from_dict handles keys matching RenderConfig.
                # SceneConfig has 'environment' field which matches RenderConfig 'environment'.
                pass
                
        except Exception as e:
            print(f"[Error] Failed to generate template: {e}")
            return

        # 4. Serialize to JSON
        try:
            serializer.serialize_scene(config, builder, filename)
            print(f"[Success] Created new scene file: {filename}")
        except Exception as e:
            print(f"[Error] Failed to save file: {e}")

def main():
    parser = argparse.ArgumentParser(description="Python Path Tracer CLI (Data-Driven)")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # --- COMMON ARGUMENTS (reused across mixins) ---
    # To avoid duplication, we could use parent parsers,
    # but simplest is defining helpers or repeating slightly (more explicit).

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