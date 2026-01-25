# Audit de Code - Raytracing Project

Ce document rassemble les résultats de l'audit complet du code.

## Légende
- **Non-optimalité** : Ce qui pose problème.
- **Raison probable** : Pourquoi c'est comme ça (historique, quick win, limite technique).
- **Quick Fix** : Solution rapide, faible impact.
- **Perfect Fix** : Solution idéale, refactoring potentiel.

---

## Phase 1 : Analyse Bottom-Up (Fichier par Fichier)

*(Cette section sera remplie au fur et à mesure de l'analyse)*

| Fichier | Localisation / Élément | Problème (Non-optimalité) | Raison Probable | Quick Fix | Perfect Fix |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `main.py` | `del engine; gc.collect()` en fin de script | **Fragile** : Si une exception survient avant, le destructeur C++ peut ne pas être appelé proprement (pyglet/pygame ont parfois du mal à fermer). | Contournement Nanobind | **Quick**: `try...finally` block. **Perfect**: Context Manager pour l'engine. |
| `main.py` | Parsing CLI très long dans `main()` | **Lisibilité** : Pollue le point d'entrée. | Évolution organique | **Quick**: Extraire dans `cli.py`. |
| `config.py` | Parsing manuel de la string `auto_sun` ("I50 R10...") | **Robustesse** : String parsing manuel sujet à erreur. | Besoin de config compacte | **Quick**: Validation Regex. **Perfect**: Utiliser des subparsers ou args CLI séparés (déjà le cas partiellement). |
| `scenes.py` | `def v3(x,y,z)` redéfini dans chaque classe | **DRY (Don't Repeat Yourself)**. | Copier-coller rapide | **Quick**: Mettre dans `common.py` ou `cpp_engine.vec3` alias. |
| `scenes.py` | Valeurs en dur (Magic Numbers) partout | **Maintenabilité** : Difficile de tuner une scène sans éditer le code. | Prototypage | **Quick**: Constantes en haut de fichier. **Perfect**: Fichiers JSON/YAML de définition de scène (Data Driven). |
| `loader.py` | `SceneBuilder` : Double Source de Vérité (C++ & `self.registry`) | **Complexité** : Risque de désynchronisation entre l'objet C++ et les métadonnées Python. | Nécessaire pour l'UI Editor | **Perfect**: Le C++ devrait stocker des métadonnées (User Pointer/Data) et Python les récupérer, ou architecture Entity-Component pure. |
| `loader.py` | `load_environment` fait trop de choses (IO, Image Proc, Logic, Engine Calls) | **Responsabilité Unique** : Fonction monolithique. | - | **Quick**: Extraire `calculate_clipping_threshold` et `setup_auto_sun`. |
| `meshloader.py` | Duplication logique `load_mesh_to_engine` vs `load_asset` | **Maintenance** : Si on change la logique de conversion matériau, il faut le faire 2 fois. | - | **Quick**: Factoriser le parsing Trimesh -> MeshInfo. |
| `modes/editor/state.py` | `EditorState` est un "God Object" | **Cohésion** : Gère Caméra, Rendu, UI, Sélection, IO. Difficile à tester/maintenir. | Centralisation facile | **Perfect**: Découper en `CameraState`, `SelectionState`, `RenderSettings`. |
| `modes/editor/state.py` | `update_transform` recalcule la matrice en Python | **Duplication** : Logique de matrice aussi présente dans le loader. | - | **Quick**: Utiliser une lib de math unifiée ou déléguer au C++. |
| `modes/editor/state.py` | Sauvegarde JSON manuelle (`save_scene`/`load_scene`) | **Fragilité** : Si on ajoute une propriété, il faut modifier 5 endroits (Registry, Save, Load, Loader, UI). | - | **Perfect**: Système de sérialisation automatique (ex: marshmallow) ou introspection. |
| `modes/editor/ui_core.py` | Layout Absolu (X, Y hardcodés) | **Rigidité** : Difficile d'ajouter un bouton sans tout décaler manuellement. | Simplicité initiale | **Perfect**: StackLayout / VBox / HBox automatique. |
| `modes/editor/main.py` | Boucle `run()` géante | **Lisibilité** : Mélange Events, Rendu, UI Draw. | - | **Quick**: Extraire `handle_input()` et `draw_viewport()`. |
| `modes/editor/panels/*` | Duplication de code de layout (`VIEW_W + 100`) | **DRY** : Beaucoup de "Magic Numbers" pour le positionnement. | Pas de layout auto | **Quick**: Helper `row(label, widget)`. |
| `tab_object.py` | `draw_section_header` dupliqué (aussi dans `tab_scene`, `tab_render`) | **DRY** : Copier-coller évident. | - | **Quick**: Déplacer dans `ui_core.py` ou `panels/common.py`. |
| `modes/renderer.py` | Calcul vectoriel caméra (Animation) refait en Numpy manuel | **Duplication** : Réimplémente la logique de `lookat` déjà présente ailleurs. | - | **Quick**: Utiliser une lib vectorielle partagée. |
| `modes/renderer.py` | Tone Mapping & Gamma en Python (Numpy) | **Performance** : Peut être lent pour des résolutions 4K+. | Facilité d'écriture | **Perfect**: Déplacer le Post-Process en C++ (Kernel SIMD). |
| `modes/renderer.py` | Threading : `tqdm` boucle en attendant `engine.render` | **Performance** : Si le C++ ne relâche pas le GIL (Global Interpreter Lock), l'UI `tqdm` gèlera quand même. | - | **Check**: Vérifier `gil_scoped_release` dans `src/main.cpp`. |
| `denoise.py` | Gestion PFM manuelle (open/write bytes) | **Verbosité** : Code assez bas niveau pour juste IO une image. | Pas de dépendance lourde (OpenCV/ImageIO limité) | **Quick**: Utiliser `imageio` s'il supporte PFM (possible). |
| `src/main.cpp` | `add_sphere` et al. créent une géométrie + instance unitaire | **Double Source de Vérité** : Python stocke "radius=10", C++ stocke "UnitSphere + Scale=10". | Simplification du moteur (ne gère que des instances) | **Perfect**: Stocker les params primitifs dans un `UserPtr` ou `Metadata` côté C++. |
| `src/main.cpp` | `render_preview` reconstruit le BVH à la volée | **Performance** : Si beaucoup d'objets, le rebuild à chaque frame (si modif) est coûteux. | Simplicité (pas de refit) | **Perfect**: Implémenter `BVH::refit` pour les mouvements simples. |
| `src/bvh.h` | Construction par "Longest Axis Split" (Médiane spatiale) | **Performance Rendu** : Moins efficace que SAH (Surface Area Heuristic). | Facile à coder | **Perfect**: Implémenter SAH Binning. |
| `src/renderer.h` | `ray_color` est récursif | **Stabilité** : Risque de Stack Overflow si depth > 1000 (peu probable en PT, mais possible). | Clarté algorithmique | **Perfect**: Transformer en boucle itérative. |
| `src/common.h` | `aces_filmic` présent en C++ ET en Python | **Duplication** : Deux implémentations du même algo. | - | **Quick**: Choisir un côté (C++ idéalement pour perf). |
| `src/common.h` | Paramètres globaux (`DIELECTRIC_SHADOW`, `VISIBLE_IN_REFLECTIONS`) | **Rigidité** : Impossible de configurer ça par objet ou scène. | Facilité | **Perfect**: Déplacer dans `RenderConfig` ou `Material`. |
| `src/materials.h` (Plastic) | `srec.is_specular = true` pour la branche diffuse | **Physique/Sampling** : Désactive le Next Event Estimation (NEE) sur la couche diffuse. Convergence très lente. | Éviter d'écrire une PDF mixte (diffuse+speculaire) complexe. | **Perfect**: Implémenter une PDF pondérée par Fresnel pour permettre le NEE sur la base diffuse. |

---

## Phase 1.5 : Audit Physique & Algorithmique (Deep Dive PBR)

Voici les résultats de l'analyse "Physicien" demandée spécifiquement sur la justesse (Correctness) des calculs.

| Fichier | Élément | Problème (Biais / Bias) | Impact | Solution |
| :--- | :--- | :--- | :--- | :--- |
| `src/materials.h` | `Metal` | Modèle "Miroir + Random Fuzz" (Shirley-style). | **Qualité/Sampling** : Rendu visuel simpliste. "Fuzz" est un hack qui empêche le NEE (car traité comme spéculaire pur). | **Perfect**: Modèle Microfacettes (GGX/Cook-Torrance). Ouvre la voie au NEE sur les surfaces rugueuses. |
| `src/materials.h` | `Lambertian` | Modèle Diffus Idéal (Loi de Lambert). | **Réalisme** : Les matériaux mats réels (tissu, terre) ont de la rétro-réflexion aux angles rasants. Aspect "plat". | **Perfect**: Modèle Oren-Nayar pour les surfaces rugueuses. |
| `src/geometry.h` | `Triangle::hit` | Pas d'implémentation de `pdf_value` ni `random`. | **Sampling** : Impossible de sampler explicitement un maillage (Mesh Light). Seules les Sphères et Quads sont supportés en NEE. | **Perfect**: Implémenter le sampling de triangle (Uniform Surface). |
| `src/environment.h` | `sample_direction` | La rotation (`set_rotation`) est ignorée lors de la génération de rayon (`sample_direction`). | **Convergence** : L'Importance Sampling vise les "anciens" points chauds. Si on tourne le ciel, on envoie les rayons au mauvais endroit ! | **Critical Fix**: Appliquer la rotation inverse au vecteur de sortie ou recalculer les CDF. |
| `src/renderer.h` | `sample_direct_light` | Heuristique MIS manquante (Balance Heuristic). Division par `light_pdf` simple. | **Fireflies** : Si `light_pdf` est faible mais que le materiau est très brillant (Spike BSDF), la variance explose. "Simple Estimator" vs "MIS". | **Perfect**: Implémenter la vraie formule MIS : $w = \frac{p_{light}}{p_{light} + p_{bsdf}}$. |
| `src/renderer.h` | `sample_direct_light` | NEE activé pour les surfaces rugueuses mais pas de pondération BSDF. | **Justesse** : Le code fait `scattering_pdf * ... / light_pdf`. Pour un miroir parfait c'est géré à part, mais pour un `Metal` rugueux, on risque des valeurs aberrantes. | **Perfect**: Utiliser MIS pour pondérer correctement les choix (BSDF Sampling vs Light Sampling). |
| `src/main.cpp` | `render_accumulate` | `Ray(..., depth=6)` hardcodé. | **Flexibilité** : Impossible de changer la profondeur de rebond en temps réel pour optimiser la preview. | **Quick**: Passer `depth` en paramètre de `render_accumulate`. |
| `src/main.cpp` | `render_preview` | Mode "Clay" est un simple Shader Lambertien local (N dot L). | **Visibilité** : C'est utile, mais ce n'est pas du path tracing. (Pas un bug, mais à noter). | - |

---

## Phase 2 : Analyse Top-Down (Structurelle & Philosophique)

L'audit révèle une dualité dans le code : une architecture logicielle "Pythonic/Glue" qui a grandi organiquement, et un moteur C++ "Weekend Raytracer" qui atteint ses limites physiques.

### 1. Le Plafond de Verre "Ray Tracing in One Weekend" (Algorithmique)
Le moteur repose sur des abstractions simplistes (Metal = Miroir Flou, Lambertian = Diffus Idéal).
*   **Problème** : Cette approche ("Shirley-style") est excellente pour l'éducation, mais bloque l'évolution vers le photoréalisme. Le "Fuzz" du métal est un hack qui empêche mathématiquement le *Next Event Estimation* (car la PDF est une Dirac ou inconnue).
*   **Conséquence** : On ne peut pas avoir de métaux rugueux éclairés par une HDR sans bruit excessif, ni de matériaux complexes (Clearcoat, Subsurface).
*   **Insight** : Il faut passer d'un modèle "Hackés" à un modèle **Microfacettes (GGX)** unifié.

### 2. La "Double Source de Vérité" (Engineering)
*   **Problème** : Python stocke "radius=10", C++ stocke "Scale Matrix".
*   **Conséquence** : Synchronisation constante et bug-prone. Si on ajoute la physique (RigidBody), ça deviendra ingérable.
*   **Insight** : C++ doit devenir l'unique propriétaire de l'état (Entity-Component System simplifié).

### 3. Le Pipeline de Données "Lourd" (Performance)
*   **Problème** : Transfert de buffers Float32 4K complets à chaque frame vers Python pour le ToneMapping.
*   **Insight** : Python ne doit gérer que les commandes (inputs, scénario), le C++ doit gérer tout le pixel flow jusqu'à l'affichage ou la sauvegarde.

---

## Phase 3 : Synthèse & Roadmap Stratégique

La roadmap se divise désormais en deux axes parallèles : **Consolidation Logicielle** (pour la stabilité/maintenabilité) et **Évolution PBR** (pour la qualité visuelle).

### Axe A : Consolidation Logicielle (Priority: Stability)
1.  **Critical Fix (Bug)** : Corriger l'Importance Sampling de l'HDRI (Rotation ignorée `src/environment.h`).
2.  **Architecture** : Remplacer `del engine` par un Context Manager.
3.  **Refactoring UI** : Nettoyer `EditorState` (God Object) et utiliser un layout automatique.
4.  **Single Source of Truth** : Faire en sorte que Python interroge le C++ pour l'état des objets (Getters/Setters via Nanobind).

### Axe B : Évolution PBR (Priority: Quality)
1.  **Microfacets Core** : Remplacer `Metal` et `Plastic` par une implémentation **GGX / Cook-Torrance**.
    *   *Gain* : Réalisme physique, cohérence énergétique.
    *   *Enable* : Permet d'échantillonner correctement les surfaces brillantes (Glossy).
2.  **MIS (Multiple Importance Sampling)** : Implémenter le "Balance Heuristic".
    *   *Gain* : Réduction drastique du bruit ("Fireflies") pour les matériaux mixtes (ni parfaitement diffus, ni parfaitement miroirs).
3.  **Advanced Diffuse** : Remplacer `Lambertian` par **Oren-Nayar**.
    *   *Gain* : Aspect plus naturel pour la pierre, le tissu, la peau.

### Recommandation Immédiate
Je suggère de traiter le **Bug Critique de Rotation HDRI** immédiatement, car il fausse tous les tests d'éclairage actuels. Ensuite, lancer le chantier **MIS + Microfacettes** qui transformera visuellement le moteur.
