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
BUILD_DIR = Path("build")
MODULE_NAME = "cpp_engine"

def step(msg):
    print(f"\n[SETUP] ➤ {msg}")

# --- 1. GESTION OIDN (Ta version améliorée) ---
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
        run_cmake_build()
        copy_artifact()
        print("\n✅ PRÊT. Lance: uv run main.py")
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()