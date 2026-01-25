import os
import sys
import shutil
import urllib.request
import zipfile
import subprocess
import platform
from pathlib import Path

# --- CONFIGURATION ---
# --- CONFIGURATION ---
OIDN_REPO_API = "https://api.github.com/repos/RenderKit/oidn/releases/latest"
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

# --- 1. GESTION OIDN (AUTO-UPDATE) ---
def get_platform_oidn_asset_filter():
    sys_name = platform.system()
    machine = platform.machine().lower()
    
    if sys_name == "Windows":
        return ".x64.windows.zip"
    elif sys_name == "Linux":
        return ".x86_64.linux.tar.gz"
    elif sys_name == "Darwin": # macOS
        if "arm" in machine or "aarch" in machine:
            return ".arm64.macos.tar.gz"
        else:
            return ".x86_64.macos.tar.gz"
    return None

def install_oidn():
    # Check si déjà installé (approximatif, on regarde si le binaire existe)
    # Sur Windows c'est bin/oidnDenoise.exe, sur Linux/Mac c'est bin/oidnDenoise
    bin_name = "oidnDenoise.exe" if os.name == 'nt' else "oidnDenoise"
    expected_bin = os.path.join(OIDN_DIR, "bin", bin_name)
    
    if os.path.exists(OIDN_DIR) and os.path.exists(expected_bin):
        print(f"   ✔ Dossier '{OIDN_DIR}' prêt.")
        return

    step("Recherche de la dernière version de OIDN (GitHub API)...")
    
    import json
    import platform
    import tarfile

    asset_filter = get_platform_oidn_asset_filter()
    if not asset_filter:
        print(f"   ❌ Plateforme non supportée automatiquement: {platform.system()} {platform.machine()}")
        return

    try:
        # 1. Fetch JSON Release
        with urllib.request.urlopen(OIDN_REPO_API) as response:
            data = json.loads(response.read().decode())
        
        tag_name = data.get("tag_name", "Unknown")
        print(f"   ℹ Version trouvée : {tag_name}")
        
        # 2. Find matching asset
        download_url = None
        asset_name = None
        
        for asset in data.get("assets", []):
            name = asset["name"]
            if name.endswith(asset_filter):
                download_url = asset["browser_download_url"]
                asset_name = name
                break
        
        if not download_url:
            print(f"   ❌ Aucun asset correspondant à '{asset_filter}' trouvé dans la release.")
            return

        # 3. Download
        step(f"Téléchargement de {asset_name}...")
        
        def reporthook(blocknum, blocksize, totalsize):
            readsofar = blocknum * blocksize
            if totalsize > 0:
                percent = readsofar * 100 / totalsize
                sys.stdout.write(f"\r   Progress: {percent:.1f}%")
                sys.stdout.flush()
        
        urllib.request.urlretrieve(download_url, asset_name, reporthook)
        print("\n   ✔ Téléchargement terminé.")

        # 4. Extract
        print("   Extraction...")
        
        extracted_folder_name = None
        
        if asset_name.endswith(".zip"):
            with zipfile.ZipFile(asset_name, 'r') as zip_ref:
                # On devine le nom du dossier extrait (souvent oidn-2.x.x...)
                root_name = zip_ref.namelist()[0].split('/')[0]
                extracted_folder_name = root_name
                zip_ref.extractall(".")
        elif asset_name.endswith(".tar.gz") or asset_name.endswith(".tgz"):
            with tarfile.open(asset_name, "r:gz") as tar:
                # On devine le nom du dossier extrait
                root_name = tar.getnames()[0].split('/')[0]
                extracted_folder_name = root_name
                tar.extractall(".")
        
        # 5. Move & Cleanup
        if extracted_folder_name and os.path.exists(extracted_folder_name):
            # Sur Windows l'archive contient souvent le dossier 'bin' directement dans le dossier racine
            # On veut déplacer le contenu de extracted_folder_name vers OIDN_DIR
            
            if os.path.exists(OIDN_DIR): shutil.rmtree(OIDN_DIR)
            shutil.move(extracted_folder_name, OIDN_DIR)
            print(f"   ✔ Installé dans ./{OIDN_DIR}")

            # Sur Unix/Mac, il faut rendre le binaire exécutable
            if os.name != 'nt':
                bin_path = os.path.join(OIDN_DIR, "bin", "oidnDenoise")
                if os.path.exists(bin_path):
                    import stat
                    st = os.stat(bin_path)
                    os.chmod(bin_path, st.st_mode | stat.S_IEXEC)
                    print(f"   ✔ Permissions +x appliquées sur {bin_path}")
        else:
            print(f"   ❌ Erreur d'extraction : dossier '{extracted_folder_name}' introuvable.")

        if os.path.exists(asset_name): os.remove(asset_name)

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
def check_build_tools():
    step("Vérification des outils de compilation...")
    
    # 1. Check CMake (Géré par uv, mais on vérifie quand même)
    try:
        subprocess.run(["uv", "run", "cmake", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        print("   ✔ CMake est présent (via uv).")
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("   ❌ ERREUR CRITIQUE: 'cmake' introuvable dans le PATH.")
        print("   -> Assurez-vous d'avoir fait 'uv sync' (qui installe le package cmake pypi).")
        sys.exit(1)

    # 2. Check Compiler (Le vrai point dur)
    # On essaie de détecter un compilateur C++ commun
    compilers = []
    if os.name == 'nt':
        compilers = ["cl", "g++", "clang++"]
    else:
        compilers = ["c++", "g++", "clang++"]
        
    found_compiler = False
    
    # 2a. Check dans le PATH
    for comp in compilers:
        if shutil.which(comp):
            found_compiler = True
            print(f"   ✔ Compilateur détecté (PATH) : {comp}")
            break
    
    # 2b. Check spécial Windows (vswhere ou Ninja/CMake capability)
    if not found_compiler and os.name == 'nt':
        # CMake est malin, il sait trouver VS même sans PATH.
        # On va faire confiance à la présence de "vswhere" ou d'une install standard VS.
        vswhere = os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe")
        if os.path.exists(vswhere):
             found_compiler = True
             print(f"   ✔ Visual Studio détecté (via vswhere).")

    if not found_compiler:
        print("   ⚠️  ATTENTION: Aucun compilateur C++ standard (cl, g++, clang++) n'a été trouvé dans le PATH.")
        print("   Cependant, si Visual Studio est installé, CMake le trouvera peut-être tout seul.")
        print("   La compilation risque d'échouer si rien n'est trouvé.")
        if os.name == 'nt':
             print("   Conseil : Lancez ce script depuis le 'x64 Native Tools Command Prompt for VS 20xx' si ça échoue.")
        
        # On ne quitte pas forcément, car cmake peut trouver un compilo non standard,
        # mais on prévient l'utilisateur.
        print("\n   Appuyez sur Entrée pour tenter quand même, ou Ctrl+C pour annuler.")
        try: input()
        except: sys.exit(1)

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
        check_build_tools()
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