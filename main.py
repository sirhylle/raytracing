import argparse
import scenes
import loader
from modes import renderer
from modes import viewer_pygames as viewer
import gc

def main():
    parser = argparse.ArgumentParser(description='Python Path Tracer (C++ Core)')
    
    # --- Arguments Généraux ---
    parser.add_argument('--scene', type=str, default=None, choices=scenes.AVAILABLE_SCENES.keys())
    parser.add_argument('--preview', action='store_true', help="Lance le mode prévisualisation temps réel")
    
    # --- Arguments de Rendu (Config) ---
    parser.add_argument('--width', type=int)
    parser.add_argument('--height', type=int)
    parser.add_argument('--spp', type=int)
    parser.add_argument('--depth', type=int)
    
    # --- Environment ---
    parser.add_argument('--env', type=str, dest='env_map')
    parser.add_argument('--env-background-level', type=float)
    parser.add_argument('--env-direct-level', type=float)
    parser.add_argument('--env-indirect-level', type=float)
    
    # --- Camera ---
    parser.add_argument('--lookfrom', nargs=3, type=float, help="Position caméra (ex: 0 1 5)")
    parser.add_argument('--lookat', nargs=3, type=float, help="Cible caméra (ex: 0 1 0)")
    parser.add_argument('--vup', nargs=3, type=float, help="Vecteur haut (ex: 0 1 0)")
    parser.add_argument('--vfov', type=float, help="FOV vertical en degrés")
    parser.add_argument('--aperture', type=float)
    parser.add_argument('--focus_dist', type=float)
    
    # --- Auto-Sun ---
    parser.add_argument('--auto-sun', nargs='?', const=True, default=None, help='Active le soleil. Optionnel: string compacte "I50.0 R50 D1000 E0.2"')
    parser.add_argument('--auto-sun-intensity', type=float)
    parser.add_argument('--auto-sun-radius', type=float)
    parser.add_argument('--auto-sun-dist', type=float)
    parser.add_argument('--auto-sun-env_level', type=float)
    
    # --- Animation ---
    parser.add_argument('--animate', action='store_true')
    parser.add_argument('--frames', type=int)
    parser.add_argument('--fps', type=int)
    parser.add_argument('--radius', type=float)
    
    # --- System ---
    parser.add_argument('--threads', type=int, default=0)
    parser.add_argument('--leave-cores', type=int, default=2)
    parser.add_argument('--param-stamp', action='store_true', help="Incruste les params sur l'image et un timestamp")
    parser.add_argument('--save-raw', action='store_true', help="Sauvegarde les images intermédiaires (raw, albedo, normal)")

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