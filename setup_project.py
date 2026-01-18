import os
import sys
import shutil
import urllib.request
import zipfile
import subprocess
import platform
from pathlib import Path

# --- CONFIGURATION ---
OIDN_URL = "https://github.com/RenderKit/oidn/releases/download/v2.3.0/oidn-2.3.0.x64.windows.zip"
OIDN_DIR = "oidn"
ASSETS_DIR = "assets"
ASSETS = {
    "bmw": "https://casual-effects.com/g3d/data10/research/model/bmw/bmw.zip",
    "bunny": "https://casual-effects.com/g3d/data10/research/model/bunny/bunny.zip",
    "dragon": "https://casual-effects.com/g3d/data10/research/model/dragon/dragon.zip",
    "erato": "https://casual-effects.com/g3d/data10/research/model/erato/erato.zip"
}
ENV_DIR = "env-maps"
ENV_MAPS = [
    "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/4k/san_giuseppe_bridge_4k.hdr",
    "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/4k/docklands_01_4k.hdr",
    "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/4k/venice_sunrise_4k.hdr",
    "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/4k/venice_sunset_4k.hdr",
    "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/4k/university_workshop_4k.hdr",
    "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/4k/brown_photostudio_02_4k.hdr",
    "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/4k/dikhololo_night_4k.hdr",
    "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/4k/meadow_4k.hdr",
    "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/4k/studio_garden_4k.hdr"
]
ENV_MAP_DEFAULT = {'name': 'env-dock-sun.hdr', 'url': 'https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/4k/docklands_02_4k.hdr'}
BUILD_DIR = Path("build")
MODULE_NAME = "cpp_engine"

def step(msg):
    print(f"\n[SETUP] ➤ {msg}")

# --- 1. GESTION OIDN ---
def install_oidn():
    if os.path.exists(OIDN_DIR) and os.path.exists(os.path.join(OIDN_DIR, "oidnDenoise.exe")):
        print(f"   ✔ Dossier '{OIDN_DIR}' prêt.")
        return

    step(f"Téléchargement de OIDN...")
    zip_name = "oidn.zip"
    
    try:
        def reporthook(blocknum, blocksize, totalsize):
            readsofar = blocknum * blocksize
            if totalsize > 0:
                percent = readsofar * 100 / totalsize
                sys.stdout.write(f"\r   Progress: {percent:.1f}%")
                sys.stdout.flush()
        
        urllib.request.urlretrieve(OIDN_URL, zip_name, reporthook)
        print("\n   ✔ Téléchargement terminé.")

        print("   Extraction...")
        with zipfile.ZipFile(zip_name, 'r') as zip_ref:
            zip_ref.extractall(".")

        # Nettoyage et déplacement
        extracted_name = "oidn-2.3.0.x64.windows" # À adapter si la version change
        bin_folder = os.path.join(extracted_name, "bin")
        
        if os.path.exists(OIDN_DIR): shutil.rmtree(OIDN_DIR)
        
        if os.path.exists(bin_folder):
            shutil.move(bin_folder, OIDN_DIR)
            print(f"   ✔ Installé dans ./{OIDN_DIR}")
        else:
            print("   ❌ Erreur : Dossier bin introuvable dans l'archive.")

        if os.path.exists(zip_name): os.remove(zip_name)
        if os.path.exists(extracted_name): shutil.rmtree(extracted_name)

    except Exception as e:
        print(f"   ❌ Erreur OIDN : {e}")

# --- 1b. GESTION ASSETS ---
def install_assets():
    if not os.path.exists(ASSETS_DIR):
        os.makedirs(ASSETS_DIR)
        print(f"   ✔ Création du dossier '{ASSETS_DIR}'")

    def reporthook(blocknum, blocksize, totalsize):
        readsofar = blocknum * blocksize
        if totalsize > 0:
            percent = readsofar * 100 / totalsize
            sys.stdout.write(f"\r   Progress: {percent:.1f}%")
            sys.stdout.flush()

    # Configure opener with User-Agent to avoid 406
    opener = urllib.request.build_opener()
    opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36')]
    urllib.request.install_opener(opener)

    for name, url in ASSETS.items():
        target_dir = os.path.join(ASSETS_DIR, name)
        # On vérifie si le dossier existe et n'est pas vide
        if os.path.exists(target_dir) and os.listdir(target_dir):
            print(f"   ✔ Asset '{name}' déjà présent.")
            continue
            
        step(f"Téléchargement de l'asset '{name}'...")
        zip_name = f"{name}.zip"
        
        try:
            print(f"   Source: {url}")
            urllib.request.urlretrieve(url, zip_name, reporthook)
            print(f"\n   ✔ Téléchargement terminé.")

            print("   Extraction...")
            # On crée le dossier cible
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)

            with zipfile.ZipFile(zip_name, 'r') as zip_ref:
                # On extrait tout dans le dossier cible
                zip_ref.extractall(target_dir)
            
            print(f"   ✔ Extrait dans {target_dir}")
            
            if os.path.exists(zip_name): os.remove(zip_name)
            
        except Exception as e:
            print(f"   ❌ Erreur Asset {name}: {e}")

# --- 1c. GESTION ENV MAPS ---
def install_env_maps():
    if not os.path.exists(ENV_DIR):
        os.makedirs(ENV_DIR)
        print(f"   ✔ Création du dossier '{ENV_DIR}'")

    def reporthook(blocknum, blocksize, totalsize):
        readsofar = blocknum * blocksize
        if totalsize > 0:
            percent = readsofar * 100 / totalsize
            sys.stdout.write(f"\r   Progress: {percent:.1f}%")
            sys.stdout.flush()

    # Configure opener with User-Agent to avoid 406
    opener = urllib.request.build_opener()
    opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36')]
    urllib.request.install_opener(opener)

    for url in ENV_MAPS:
        # On extrait le nom du fichier
        name = os.path.basename(url)
        target_file = os.path.join(ENV_DIR, name)
        # On vérifie si le fichier existe et n'est pas vide
        if os.path.exists(target_file):
            print(f"   ✔ Env Map '{name}' déjà présent.")
            continue
            
        step(f"Téléchargement de l'env map '{name}'...")
        
        try:
            print(f"   Source: {url}")
            urllib.request.urlretrieve(url, target_file, reporthook)
            print(f"\n   ✔ Téléchargement terminé.\n")
            
        except Exception as e:
            print(f"   ❌ Erreur Env Map {name}: {e}")

    if os.path.exists(os.path.join("./", ENV_MAP_DEFAULT['name'])):
        print(f"   ✔ Env Map '{ENV_MAP_DEFAULT['name']}' déjà présente.")
    else:
        step(f"Téléchargement de l'env map '{ENV_MAP_DEFAULT['name']}'...")
        
        try:
            print(f"   Source: {ENV_MAP_DEFAULT['url']}")
            urllib.request.urlretrieve(ENV_MAP_DEFAULT['url'], os.path.join("./", ENV_MAP_DEFAULT['name']), reporthook)
            print(f"\n   ✔ Téléchargement terminé.\n")
            
        except Exception as e:
            print(f"   ❌ Erreur Env Map {ENV_MAP_DEFAULT['name']}: {e}")



# --- 2. BUILD SYSTEM (Nanobind + CMake) ---
def check_uv():
    step("Vérification dépendances (uv sync)...")
    subprocess.run(["uv", "sync"], check=True)

def run_cmake_build():
    step("Configuration CMake (Nanobind)...")
    
    # On force Ninja s'il est dispo (plus rapide), sinon VS
    cmd_config = ["uv", "run", "cmake", "-S", ".", "-B", str(BUILD_DIR)]
    
    # Spécifique Windows : On sécurise l'architecture 64 bits
    if os.name == 'nt':
        # Cette option dit au générateur Visual Studio de cibler x64.
        # Note : Si jamais vous forciez l'usage de "Ninja", il faudrait retirer cette ligne,
        # mais par défaut CMake sur Windows préfère Visual Studio, donc c'est safe.
        cmd_config.extend(["-A", "x64"])

    subprocess.run(cmd_config, check=True)
    
    step("Compilation...")
    cmd_build = ["uv", "run", "cmake", "--build", str(BUILD_DIR), "--config", "Release"]
    subprocess.run(cmd_build, check=True)

def copy_artifact():
    step("Copie du module (.pyd)...")
    ext = ".pyd" if os.name == 'nt' else ".so"
    # Nanobind + CMake génèrent souvent le fichier directement dans build/
    # ou build/Release. On cherche partout.
    found = list(BUILD_DIR.rglob(f"{MODULE_NAME}*{ext}"))
    
    if not found:
        print(f"   ❌ Erreur: {MODULE_NAME}*{ext} introuvable.")
        sys.exit(1)
        
    src = found[0]
    dst = Path.cwd() / src.name
    
    if dst.exists():
        try: os.remove(dst)
        except: pass
        
    shutil.copy2(src, dst)
    print(f"   ✔ Succès : {src.name} -> Racine")

def main():
    print("=== AUTO-SETUP RAYTRACER (NANOBIND) ===")
    try:
        check_uv()
        install_oidn()
        install_assets()
        install_env_maps()
        run_cmake_build()
        copy_artifact()
        print("\n✅ PRÊT. Lance: uv run main.py")
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()