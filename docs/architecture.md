# Architecture du Projet Raytracing

Ce document décrit la structure globale, le flux de données et l'organisation des modules de l'application.

## 1. Point d'Entrée & Modes

Le fichier **`main.py`** est le chef d'orchestre. Il ne contient pas de logique métier lourde mais gère :
1.  Le parsing des arguments (CLI).
2.  L'initialisation du moteur et le chargement de la scène via `loader.py`.
3.  Le choix du mode d'exécution :
    *   **Mode Éditeur (Défaut si `--editor`)** : Lance l'interface graphique interactive via `modes/editor/main.py`.
    *   **Mode Rendu (Défaut sinon)** : Lance le rendu offline (CLI) via `modes/renderer.py`.

## 2. Structure des Dossiers

### Racine
| Fichier | Rôle |
| :--- | :--- |
| `main.py` | Point d'entrée unique. |
| `config.py` | Classes et constantes pour la configuration (Config, RenderConfig). |
| `scenes.py` | Définition déclarative de scènes (objets, positions, matériaux) pouvant être chargées. |
| `loader.py` | Orchestre la création des objets C++ à partir des définitions Python (Scènes -> Moteur). |
| `meshloader.py` | Gestion spécifique du chargement des fichiers 3D (OBJ/GLB) via Trimesh. |

### `src/` (Moteur C++)
Contient le code natif (C++20) pour le Raytracing haute performance.
*   **Compilation** : CMake + Nanobind, orchestré par `uv run setup_project.py` qui compile et copie le module, et télécharge les assets (OIDN, Modèles, HDRIs).
*   **Responsabilité** : BVH, Intersection Rayon/Triangle, Shading, Sampling.

### `modes/` (Logique Applicative)
Contient les deux "cerveaux" de l'application selon le mode choisi. Pour voir toutes les options :
```bash
uv run main.py --help
```

#### A. `modes/renderer.py` (Mode Rendu Offline)
Gère le pipeline de production d'images finales.
*   **Pipeline** : Rendu par tranches (tiles) ou progressif -> Post-Process (Tone Mapping, Denoising OIDN) -> Sauvegarde Disque.
*   **Multithreading** : Utilise `threading` pour ne pas bloquer l'UI (tqdm) pendant le calcul intensif C++.

#### B. `modes/editor/` (Mode Interactif V3)
Interface graphique basée sur **PyGame**.

**Les Modes de Rendu (Visualisation)** :
Le moteur C++ expose plusieurs pipelines de visualisation utilisés par l'éditeur :
1.  **Preview (Mode 0: Normals)** : Affiche les vecteurs normaux de la géométrie. Très rapide, utile pour debugger l'orientation ou voir la géométrie nue.
2.  **Preview (Mode 1: Clay)** : Affiche un shading blanc "Argile" (N dot L). Utile pour voir les volumes et l'éclairage de base sans textures.
3.  **Ray Accumulate** : Rendu Path Tracing progressif. L'image s'affine frame après frame (suppression du bruit) tant que la caméra ne bouge pas.
4.  **Final Render** : Le rendu "de production" (identique au CLI). Bloquant (ou threadé), avec une qualité maximale (bounces élevés, résolution pleine).

*   **`main.py`** : La "Game Loop". Gère les événements (souris/clavier), appelle le rendu (preview ou raytracing) et dessine l'UI.

*   **`state.py`** : **Source de Vérité**. Contient tout l'état de l'application (Caméra, Sélection, Onglet actif, Paramètres). C'est lui qui fait le pont avec le moteur C++ (`update_transform`, etc.) et gère la Sauvegarde/Chargement (JSON).
*   **`ui_core.py`** : Framework UI maison. Définit les widgets (Bouton, Slider, Input) et le style (Couleurs, Dimensions).
*   **`panels/`** : Contient la définition des panneaux de l'interface (Scene, Object, Create, Global Layout).

## 3. Flux de Données (Data Flow)

### Initialisation
1.  `main.py` crée l'objet `Config`.
2.  `loader.py` lit la scène demandée dans `scenes.py`.
3.  Pour chaque objet, `loader.py` appelle l'API C++ (`cpp_engine.add_sphere`, etc.) et stocke les métadonnées dans un **Registre Python** (`builder.registry`).
    *   *Note : Le registre Python est crucial car le C++ ne stocke pas les métadonnées de haut niveau (noms, types originaux).*

### Boucle Éditeur
1.  **Input** : `editor/main.py` capture les inputs.
2.  **Update** : Si une action modifie la scène (ex: Gizmo déplace un objet), `state.py` met à jour les données Python ET appelle le moteur C++ (`engine.update_instance_transform`).
3.  **Flag Dirty** : `state.dirty = True` est levé pour signaler qu'il faut relancer le rendu.
4.  **Render** :
    *   Si `dirty` ou accumulation incomplète : Appel à `engine.render_preview` (rapide) ou `engine.render_accumulate` (progressif).
    *   Le résultat (buffer float) est converti en surface PyGame et affiché.
    *   L'UI est dessinée par-dessus (Overlay).

## 4. Concepts Clés

*   **Hybridation Nanobind** : Python pilote, C++ exécute. Les objets lourds (Meshes) sont passés par buffers pour éviter la copie.
*   **Ui Rebuild** : L'interface est "Retained" mais reconstruite dynamiquement. Si l'état UI change (changement d'onglet), `state.needs_ui_rebuild` force la régénération de la liste des widgets.
*   **Hot-Reloading (Partiel)** : Le code Python des scènes peut être rechargé en relançant l'app, sans recompiler le C++.
