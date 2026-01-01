import os
import urllib.request
import zipfile
import shutil
import sys

# URL officielle Intel OIDN 2.3.0 (Windows)
OIDN_URL = "https://github.com/RenderKit/oidn/releases/download/v2.3.3/oidn-2.3.3.x64.windows.zip"
OIDN_DIR = "oidn"

def install_oidn():
    if os.path.exists(OIDN_DIR):
        print(f"Le dossier '{OIDN_DIR}' existe déjà. Installation ignorée.")
        return

    print(f"Téléchargement de OIDN depuis {OIDN_URL}...")
    zip_name = "oidn.zip"
    
    try:
        # 1. Télécharger avec barre de progression simple
        def reporthook(blocknum, blocksize, totalsize):
            readsofar = blocknum * blocksize
            if totalsize > 0:
                percent = readsofar * 1e2 / totalsize
                sys.stdout.write(f"\r{percent:.1f}%")
                sys.stdout.flush()
        
        urllib.request.urlretrieve(OIDN_URL, zip_name, reporthook)
        print("\nTéléchargement terminé.")

        # 2. Extraire
        print("Extraction...")
        with zipfile.ZipFile(zip_name, 'r') as zip_ref:
            zip_ref.extractall(".")

        # 3. Renommer/Déplacer
        # Le zip contient un dossier 'oidn-2.3.3.x64.windows', on veut juste le contenu de 'bin' ou le dossier racine
        extracted_folder = "oidn-2.3.3.x64.windows"
        
        # On ne garde que le dossier 'bin' qui contient l'exe et les dlls, c'est plus propre
        bin_folder = os.path.join(extracted_folder, "bin")
        
        if os.path.exists(bin_folder):
            shutil.move(bin_folder, OIDN_DIR)
            print(f"Installé dans ./{OIDN_DIR}")
        else:
            print("Erreur: structure du zip inattendue.")

        # 4. Nettoyage
        os.remove(zip_name)
        shutil.rmtree(extracted_folder)
        print("Nettoyage terminé. OIDN est prêt !")

    except Exception as e:
        print(f"Erreur lors de l'installation : {e}")

if __name__ == "__main__":
    install_oidn()