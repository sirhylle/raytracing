import numpy as np
import subprocess
import os
import tempfile
import uuid

# --- CONFIGURATION ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
OIDN_EXE_NAME = "oidnDenoise.exe" if os.name == 'nt' else "oidnDenoise"
# On cherche dans un dossier 'oidn' au même niveau que le script
OIDN_PATH = os.path.join(CURRENT_DIR, "oidn", "bin", OIDN_EXE_NAME)

def _save_pfm(file_path, image):
    """
    Sauvegarde une image float32 en format PFM (Portable Float Map).
    Format requis par OIDN : Little Endian, Float32, Bottom-Left origin.
    """
    image = np.ascontiguousarray(image, dtype=np.float32)
    height, width, channels = image.shape
    
    # Le format PFM utilise un scale négatif pour indiquer Little Endian
    scale = -1.0
    
    with open(file_path, 'wb') as f:
        # Header: PF = couleur (3 canaux), Pf = gris (1 canal)
        header = f"PF\n{width} {height}\n{scale}\n".encode('ascii')
        f.write(header)
        
        # PFM stocke l'image de bas en haut (Bottom-Left), numpy est Top-Left.
        # On inverse l'axe Y.
        f.write(image[::-1, :, :].tobytes())

def _load_pfm(file_path):
    """Charge une image PFM et la remet dans le sens numpy (Top-Left)."""
    with open(file_path, 'rb') as f:
        header = b""
        while True:
            line = f.readline()
            if not line.startswith(b'#'): header += line
            if header.count(b'\n') >= 3: break
            
        lines = header.split(b'\n')
        if b'PF' not in lines[0]: 
            raise ValueError("Format PFM invalide ou non supporté (doit être PF)")
            
        dims = lines[1].split()
        width, height = int(dims[0]), int(dims[1])
        
        data = np.fromfile(f, dtype=np.float32)
        return data.reshape((height, width, 3))[::-1, :, :]

def _run_oidn_command(cmd_args, description):
    """Exécute la commande OIDN et gère l'affichage console."""
    # Sous Windows, on évite l'apparition de fenêtres noires intempestives
    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    print(f"[OIDN] Tentative sur {description}...")
    try:
        # On capture stdout/stderr pour diagnostiquer sans polluer sauf si erreur
        result = subprocess.run(
            cmd_args, 
            check=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            startupinfo=startupinfo
        )
        # Si succès, on peut afficher un petit log si besoin, ou juste retourner True
        return True
    except subprocess.CalledProcessError as e:
        print(f"[OIDN] Échec sur {description}.")
        print(f"Log Erreur : {e.stderr.decode().strip()}")
        return False

def denoise_image(noisy_img, albedo=None, normal=None):
    """
    Débruite l'image en utilisant l'exécutable Intel OIDN externe.
    Stratégie : Tente CUDA (GPU) -> Fallback CPU.
    """
    if not os.path.exists(OIDN_PATH):
        print(f"[ERREUR] OIDN introuvable : {OIDN_PATH}")
        return noisy_img

    # ID unique pour éviter les conflits de fichiers si plusieurs rendus lancés
    run_id = str(uuid.uuid4())[:8]
    temp_dir = tempfile.gettempdir()
    
    # Fichiers temporaires
    f_in = os.path.join(temp_dir, f"oidn_in_{run_id}.pfm")
    f_out = os.path.join(temp_dir, f"oidn_out_{run_id}.pfm")
    f_alb = os.path.join(temp_dir, f"oidn_alb_{run_id}.pfm")
    f_nrm = os.path.join(temp_dir, f"oidn_nrm_{run_id}.pfm")
    
    files_to_clean = [f_in, f_out]

    try:
        # 1. Écriture des inputs
        _save_pfm(f_in, noisy_img)
        
        # Construction des arguments communs
        # --hdr : indique que l'entrée principale est HDR (float)
        # --quality high : force la meilleure qualité (peut être plus lent)
        base_cmd = [OIDN_PATH, "--hdr", f_in, "-o", f_out, "--quality", "high"]
        
        if albedo is not None:
            _save_pfm(f_alb, albedo)
            base_cmd.extend(["--alb", f_alb])
            files_to_clean.append(f_alb)
            
        if normal is not None:
            _save_pfm(f_nrm, normal)
            base_cmd.extend(["--nrm", f_nrm])
            files_to_clean.append(f_nrm)

        # 2. Tentative 1 : GPU / Default
        cmd_gpu = []
        desc_gpu = ""
        
        if os.name == 'nt':
            # Windows : on tente CUDA explicitement (optim pour RTX)
            cmd_gpu = base_cmd + ["--device", "cuda"]
            desc_gpu = "GPU (Nvidia RTX)"
        else:
            # Mac/Linux : on laisse OIDN choisir (Metal pour Mac, ou CPU/SyCL sur Linux)
            cmd_gpu = base_cmd + ["--device", "default"]
            desc_gpu = "Device par défaut (Metal/CPU)"

        success = _run_oidn_command(cmd_gpu, desc_gpu)

        # 3. Tentative 2 : CPU (Fallback) si le GPU a échoué
        if not success:
            print("[OIDN] Bascule sur le CPU (Fallback)...")
            cmd_cpu = base_cmd + ["--device", "cpu"]
            success = _run_oidn_command(cmd_cpu, "CPU")

        # 4. Chargement du résultat
        if success and os.path.exists(f_out):
            return _load_pfm(f_out)
        else:
            print("[WARN] Impossible de débruiter l'image (GPU et CPU ont échoué).")
            return noisy_img

    except Exception as e:
        print(f"[EXCEPTION] Erreur critique dans le script de débruitage : {e}")
        return noisy_img
        
    finally:
        # Nettoyage
        for f in files_to_clean:
            if os.path.exists(f):
                try: os.remove(f)
                except: pass