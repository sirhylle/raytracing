# Future Roadmap (Strategic)

La roadmap se divise en plusieurs axes parallèles : **Consolidation Logicielle**, **Évolution PBR** (pour la qualité visuelle), et les nouvelles extensions créatives et de post-traitement.

## Axe A : Consolidation Logicielle & Refactoring

1.  **Critical Fix (Bug)**: Corriger l'Importance Sampling de l'HDRI (Rotation ignorée `src/environment.h`).
    *   **Status**: ✅ **Completed**. (Rotation is correctly applied to phi_world in `environment.h`).
    *   *Desc*: La rotation de l'environnement n'était pas prise en compte lors du sampling.

2.  **Architecture**: Context Manager pour le Moteur (`with Engine() as ...`).
    *   **Status**: ✅ **Implemented** (via `loader.py` Wrapper).
    *   *Desc*: `EngineManager` class in `loader.py` handles `__enter__`/`__exit__` and calls `engine.clear()`.

3.  **Refactoring UI**: Nettoyer `EditorState` qui est devenu un God Object.
    *   **Status**: ⚠️ **Partial**. (File is still large ~950 lines, handles UI/Render/Logic).
    *   *Desc*: Séparer `CameraControl`, `SceneManager`, `RenderState`.

4.  **Single Source of Truth**: Ne plus dupliquer l'état dans Python (`EditorState`) et C++.
    *   **Status**: ❌ **Not Implemented**. (Python iterates `builder.registry` instead of querying Engine).
    *   *Desc*: Python doit interroger le moteur pour la position des objets, et non maintenir une copie.

5.  **UX**: Découpler le "Preview" de l'état UI.
    *   **Status**: ❌ **Not Implemented**. (UI updates trigger full accumulation reset).
    *   *Desc*: Pouvoir bouger la caméra sans reset l'accumulation si on est en pause ?

6.  **~~Partial Accumulation (Timeslicing) for UI Responsiveness~~**.
    *   **Status**: ⛔ **Tested & Rejected / Solved Differently**.
    *   *Desc*: L'idée initiale était de rendre l'accumulation fractionnée par blocs ou budget temps.
    *   *Lesson*: Rejeté car le rendu par blocs (ou scanline) créait des artefacts de déchirement ("tearing") très disgracieux lors du déplacement de la caméra en temps réel.
    *   *Alternative choisie*: Mesure des FPS en temps réel et réduction dynamique de la résolution de rendu si les FPS chutent trop bas. Cela garantit une navigation fluide sans artefacts visuels.

7.  **~~Shadow Rays "Any Hit"~~** (Optimisation).
    *   **Status**: ⛔ **Tested & Rejected** (Feb 2025). Shadow early-exit (`all_opaque` flag + first-hit return) benchmarked: no measurable improvement. Shadow rays are not the bottleneck — primary/indirect rays dominate. Infrastructure (`is_opaque()`, `all_opaque` flag) kept for future use.
    *   *Lesson*: In path tracing with NEE, shadow rays are ~50% of rays but most either miss (AABB pruning handles this) or are quickly blocked. The expensive closest-hit traversal is dominated by indirect bounces, not shadows.

## Axe B : Évolution PBR (Physically Based Rendering)

1.  **Microfacets Core (GGX)**.
    *   **Status**: ✅ **Completed**. (`src/materials.h` implements GGX/Trowbridge-Reitz and Smith Geometry).
    *   *Desc*: Remplacer les matériaux Legacy par une BRDF unifiée (Disney-like).

2.  **MIS (Multiple Importance Sampling)**.
    *   **Status**: ✅ **Completed**. (`src/renderer.h` uses Power Heuristic for NEE and BSDF sampling).
    *   *Desc*: Combiner BSDF sampling et Light sampling pour réduire le bruit (Matériaux brillants vs Sources larges).

3.  **Advanced Diffuse (Oren-Nayar)**.
    *   **Status**: ✅ **Completed**. (`eval_oren_nayar` implemented in `src/materials.h`).
    *   *Desc*: Modèle pour les surfaces rugueuses (Argile, Tissu) plus réaliste que Lambert.

4.  **Caustics & Transparency**.
    *   **Status**: ⚠️ **Partial** (Fake "Transparent Shadows").
    *   *Desc*: Les ombres des objets en verre sont colorées (Beer's Law), mais pas de vraies caustiques (Photon Mapping absent).

5.  **Dispersion Chromatique (Rendu Spectral ou RGB-Shift)** (Priority: Research/Low)
    *   **Status**: ✅ **Completed**.
    *   *Diff*: Very High | *Value*: Specific Realism (Gemstones, Prisms)
    *   *Desc*: Simulation de la variation de l'IOR selon la longueur d'onde. Implémentée via échantillonnage d'un spectre RGB continu (`color_filter`) dans `materials.h`, exposée dans `loader.py` et paramétrable via l'UI (`tab_object.py`).
    *   **WARNING (Historique)** : Tentatives passées non concluantes ("Dispersive Caustics").
        *   Le passage au "Full Spectral" a causé des régressions de performance massives et du bruit de couleur difficile à converger.
        *   La séparation simple R/G/B donnait un effet "Ghosting" irréaliste.
        *   *Stratégie Actuelle*: L'approche actuelle utilise des spectres d'absorption triangulaires continus sur [0,1] pour garantir la conservation d'énergie tout en générant un arc-en-ciel fluide.

## Axe C : Extension PBR & Material (Creative)

1.  **Textures Support** (Priority: High).
    *   **Status**: ✅ **Implemented** (Primitives) / ⚠️ **Partial** (Meshes).
    *   *Desc*: L'échantillonnage PBR complet (Albedo, Roughness, Metallic, Normal) est implémenté en C++, exposé à Python (`update_instance_textures`), et intégré dans l'interface utilisateur. L'UV mapping est opérationnel sur les primitives de base.
    *   *Reste à faire*: Gérer l'extraction et l'interpolation des coordonnées UV lors du chargement de fichiers `.obj` complexes (Meshes).

2.  **Procedural Noise** (Perlin, Voronoi).
    *   **Status**: ❌ **Not Implemented**.
    *   *Desc*: Pour varier la roughness/couleur sans texture.

3.  **Normal Alteration** (Bump/Displacement).
    *   **Status**: ❌ **Not Implemented**.
    *   *Desc*: Perturber la normale avant le shading (nécessite Textures ou Noise).

4.  **Semi-Random Meshes** (e.g. Rocks).
    *   **Status**: ❌ **Not Implemented**.
    *   *Desc*: Génération procédurale de cailloux/débris.

## Axe D : Visual Polish & Camera

1.  **Chromatic Aberration & Grain** (Post-process).
    *   **Status**: ❌ **Not Implemented**.
    *   *Desc*: Effets caméra "fin de chaîne".

2.  **Global Homogeneous Atmosphere (Fog)**.
    *   **Status**: ❌ **Not Implemented**.
    *   *Desc*: Absorption volumétrique constante (profondeur).

3.  **Volumetrics (Clouds/Heterogeneous)**.
    *   **Status**: ❌ **Not Implemented**.
    *   *Desc*: Ray Marching dans le volume (très coûteux).

4.  **Subsurface Scattering (SSS)**.
    *   **Status**: ❌ **Not Implemented** (Beer's Law used for glass is a simplification).
    *   *Desc*: Pour la peau, la cire, le marbre (Random Walk).

## New Ideas (Brainstorming)

1.  **Procedural Sky (Hosek-Wilkie)**.
    *   **Status**: ❌ **Not Implemented** (Uses HDRI or constant color).
    *   *Desc*: Ciel physique dynamique (Heure de la journée, Turbidity).

2.  **Scatter System**.
    *   **Status**: ❌ **Not Implemented**.
    *   *Desc*: Remplir une surface avec des instances (Herbe, Cailloux).

3.  **Adaptive Sampling**.
    *   **Status**: ❌ **Not Implemented**.
    *   *Desc*: Concentrer les samples sur les zones bruitées (Variance estimation).

4.  **Advanced Tone Mapping (AgX / Khronos PBR)**.
    *   **Status**: ❌ **Not Implemented** (Uses ACES Filmic).
    *   *Desc*: Mieux gérer la saturation dans les hautes lumières (le "Notorious Six" problem de ACES).

5.  **Imperfect Glass**.
    *   **Status**: ❌ **Not Implemented**.
    *   *Desc*: Surface roughness variable + Smudges (Texture dependent).

6.  **Toon/Cel Shading Preview**.
    *   **Status**: ❌ **Not Implemented**.
    *   *Desc*: Mode de rendu non-photoréaliste pour le debug ou le style.

7.  **Blue Noise Samplers**.
    *   **Status**: ✅ **Completed**. (`src/sampler.h` uses Blue Noise for Sobol scrambling).
    *   *Desc*: Améliorer la distribution des samples pour réduire les artefacts visuels à bas SPP.

8.  **Debug Views (Heatmaps)**.
    *   **Status**: ❌ **Not Implemented**.
    *   *Desc*: Visualiser le coût de rendu par pixel (Heatmap de nombre de rebonds ou temps calcul).

## Axe F : Interactivity & Animation (New)

1.  **Camera Bookmarks System** (Priority: Medium).
    *   **Status**: ❌ **Not Implemented**.
    *   *Desc*: Sauvegarder des "instantanés" de l'état de la caméra (position, direction, focus, champ de vision). Utile pour basculer rapidement entre une vue d'édition et une vue de rendu final.
    *   **Features**:
        *   UI pour capturer/supprimer des points.
        *   Support dans le fichier JSON de scène.

2.  **Animation Timeline (Interpolation)**.
    *   **Status**: ❌ **Not Implemented**.
    *   *Desc*: Enchaîner les bookmarks de caméra pour créer une séquence vidéo.
    *   **Challenge**: Interpolation fluide (Slerp pour la rotation, Splines pour la position) avec contrôle de vitesse (Ease-in/out).

3.  **General Keyframing System**.
    *   **Status**: ❌ **Not Implemented**.
    *   *Desc*: Étendre le principe des bookmarks à d'autres paramètres (intensité lumineuse, position des objets, couleurs des matériaux).
    *   **Architecture**: Nécessite un système d'échantillonnage temporel pour que le moteur C++ sache quel état utiliser à la frame *T*.

## Axe G : C++ Modernization & Vectorization (Performance)

> Objectif : exploiter C++23 et améliorer le code pour aider le compilateur à vectoriser,
> sans bouleverser l'architecture ni sacrifier la lisibilité.

1.  **~~Branchless AABB Slab Test~~** (Priority: ~~High~~ → Rejected).
    *   **Status**: ⛔ **Tested \u0026 Rejected** (Feb 2025). Two variants benchmarked: `initializer_list` (+60% slower) and scalar `min/max` (+8% slower). The original loop+early-exit wins because most rays miss most boxes, making the branch predictor + short-circuit more valuable than branchless vectorization.
    *   *Lesson*: Early-exit saves 2 axes of computation on misses. Branch prediction is nearly perfect here (regular hit/miss patterns). Don't fix what ain't broke.

2.  **`constexpr` / `if consteval` pour les maths PBR**.
    *   **Status**: ❌ **Not Implemented**. (Les fonctions math comme `firefly_clamp`, `aces_filmic`, `ndf_ggx` sont `inline` mais pas `constexpr`).
    *   *Diff*: Low | *Value*: Medium
    *   *Desc*: Marquer les fonctions pures (`firefly_clamp`, `schlick_fresnel_color`, `ndf_ggx`, `geometry_smith`, `aces_filmic`) comme `constexpr`. Cela permet au compilateur d'évaluer les appels à arguments constants au compile-time (ex: `firefly_clamp` avec `USE_HARD_CLAMP = false` connue). Utiliser `if consteval` pour choisir entre un chemin compile-time exact et un chemin runtime rapide (ex: fast inverse sqrt vs `1/sqrt`).

3.  **~~`alignas(16)` sur `Vec3`~~** (SIMD-Friendly Layout).
    *   **Status**: ⛔ **Tested & Rejected** (Feb 2025). Vec3 changed from `e[3]` (12 bytes) to `alignas(16) e[4]` (16 bytes). Uniform regression of +2-4% across all scenes. The 33% size increase hurts cache locality (AABB 24→32, BVH nodes larger, more cache misses) more than SIMD alignment helps.
    *   *Lesson*: Same as E.1 — cache performance dominates. Modern CPUs handle unaligned loads (`movups`) efficiently; the extra padding bytes waste precious cache lines.

4.  **BVH Itératif + Adaptive Traversal** (Stack-Based, Auto Simple/Ordered).
    *   **Status**: ✅ **Implemented** (Feb 2025). Iterative stack-based traversal with adaptive dispatch: simple (left/right) for BVHs with ≤500 primitives, ordered (front-to-back via `split_axis`) for deeper BVHs (meshes). One branch per `hit()` call, not per node.
    *   *Benchmark vs original recursive (960×720, SAH)*:

        | Scene | Before | After | Gain |
        |---|---|---|---|
        | random (486 sph, 128 SPP) | 7.416s | 6.360s | **-14.2%** |
        | cornell (8 obj, 128 SPP) | 9.965s | 9.215s | **-7.5%** |
        | showcase (85 obj, 128 SPP) | 8.981s | 8.527s | **-5.1%** |
        | mesh2 (9 dragons, 64 SPP) | ~55s | 35.7s | **~-35%** |

5.  **Hybrid Flat BVH** (Cache-Optimized Linear BVH for Meshes).
    *   **Status**: ✅ **Implemented** (Feb 2025). New `flat_bvh.h` — 32-byte `FlatNode` in a contiguous `std::vector` (vs ~80+ byte heap-scattered `BVHNode`). Used for mesh-internal BVHs only (deep, 100K+ nodes). World BVH stays as `BVHNode` (shallow, <100 objects).
    *   *Benchmark (960×720, SAH, hybrid vs BVHNode-only)*:

        | Scene | BVHNode | Hybrid FlatBVH | Gain |
        |---|---|---|---|
        | random (486 sph, 128 SPP) | 6.339s | 6.412s | ~0% |
        | cornell (8 obj, 128 SPP) | 9.394s | 9.483s | ~0% |
        | showcase (85 obj, 128 SPP) | 8.635s | 8.919s | ~0% |
        | mesh1 (bunny 78K tri, 128 SPP) | 12.935s | 12.358s | **-4.5%** |
        | mesh2 (9 dragons 1M tri, 64 SPP) | 36.202s | 29.649s | **-18.1%** |

    *   *Lesson*: Pure FlatBVH regressed on simple scenes (+6-12%) due to array indexing overhead vs direct pointer dispatch. Hybrid approach isolates the gain to deep BVHs where cache locality matters most.

6.  **~~Unification PBR & Approximation de Schlick (Diélectriques)~~**.
    *   **Status**: ⛔ **Tested & Rejected** (Avril 2026). Tentative d'unifier l'évaluation de tous les matériaux sous l'approximation de Fresnel de Schlick (en convertissant l'IOR en `F0` mis en cache) pour éviter les calculs coûteux par rayon.
    *   *Lesson*: Le gain de performance mesuré sur la version C++ était imperceptible dans la pratique. L'approximation de Schlick, bien qu'étant le standard dans l'industrie temps-réel, induit une légère déviation de la probabilité de réflexion aux angles intermédiaires, créant des différences stochastiques dans les chemins de rayons (~1,18% de pixels différents). Nous avons décidé de privilégier la lisibilité du code et la pureté mathématique (utilisation de l'équation de Fresnel exacte pour les diélectriques) plutôt qu'une micro-optimisation contre-intuitive.

# Appendix: Lessons Learned & Specific Fixes (Legacy Notes)

**Context**: Attempted to implement "Configurable NEE" (Stochastic vs Exhaustive) + MIS. The NEE branching added complexity for little visual gain on simple scenes. The user decided to revert the NEE configuration but keep the knowledge for MIS and Material fixes.

## 1. Golden Fixes (To Re-Apply Immediately)
These are independent bugs found during the session that significantly improve quality.

### A. Plastic Material Fix
**The Bug**: The `Plastic` material was flagging its Diffuse component as `is_specular = true`.
**Consequence**: NEE was incorrectly disabled on red plastic spheres, causing noise.
**The Fix**:
In `Plastic::scatter`:
```cpp
// Diffuse Branch
srec.is_specular = false; // ENABLE NEE!
srec.attenuation = albedo;
```

### B. MIS Implementation (Verified)
The MIS logic itself (Power Heuristic) was correct and useful.
**Key Formula**:
```cpp
inline Real power_heuristic(Real pdf_a, Real pdf_b) {
  auto a2 = pdf_a * pdf_a;
  auto b2 = pdf_b * pdf_b;
  return a2 / (a2 + b2);
}
```
**Integration** requires updating `renderer.h` to weigh `direct_light` (NEE) and `indirect_light` (BSDF) using their respective PDFs.

## 2. The Trap: Material Models vs NEE
**Lesson Learned**: *Don't force NEE on ad-hoc models.*

We tried to force NEE on "Fuzzy Metal".
- **Current Model**: `reflected + fuzz * random_sphere()`.
- **Problem**: This model has no mathematical PDF (`scattering_pdf`) we can evaluate easily.
- **Fail**: When NEE was forced, the PDF was estimated wrong (Lambertian fallback), resulting in a **dark image** (Energy Loss).
- **Correct Approach**: Keep "Fuzzy Metal" as `is_specular = true` (Path Tracing only, no NEE) until we have GGX.

## 3. The Holy Grail: GGX / Microfacet
To properly render rough metals/plastics with noise-free NEE, we need a standard PBR model.

**Implementation Checklist**:
1.  **NDF (Normal Distribution Function)**: GGX Trowbridge-Reitz.
    *   Determines probability of microfacet alignment.
2.  **Fresnel (Schlick)**:
    *   Already have this, but needs to use the *Half Vector* (H) instead of Normal.
3.  **Geometry (Smith)**:
    *   Masking/Shadowing factor.
4.  **Sampling**:
    *   Implement `sample_ggx(roughness)` to generate rays according to the NDF peak.
    *   Implement `pdf_ggx()` to return the exact probability density.

**Impact**: This unlocks "Glossy NEE" (clean studio renders of metals).

## 4. Architecture Pitfalls (To Avoid)
*   **Binding Forgetting**: When adding parameters to `render()`, remember to add them to:
    1.  The Class Member variables.
    2.  The `render()` arguments.
    3.  The `ray_color()` recursive call arguments.
    4.  **AND** the Python Binding `.def(...)`. (We lost time debugging `Main::render` ignoring settings).
*   **Offline vs Preview**: Always verify that `render()` (Offline) receives the same parameter updates as `render_accumulate()` (Preview).

# Architecture Refactoring: Asset & Scene Graph (Long Term)

The current architecture suffers from fragmentation (Shotgun surgery required for new primitives) and mixing of Assets vs Instances.

## 1. Unified Asset Manager
Instead of `loader.py` maintaining ad-hoc lists and regeneration logic:
*   Implement a robust **AssetLibrary** class.
*   **Responsibility**: Ensure resources exist (Load from disk OR Generate procedurally).
*   **Key Change**: Scene Loader only asks `AssetLibrary.get_or_create(id, recipe)`. It does NOT contain regeneration code itself.

## 2. Generic GameObjects (Entity-Component)
Les objets de la scène ne seraient pas typés "Sphere" ou "Cube" dans le code de sérialisation. Ce seraient des **GameObjects** avec des **Composants**.

*   **Structure** : `GameObject { transform: Matrix, component: GeometryComponent }`.
*   `GeometryComponent` pointe vers un Asset (ID) ou définit une Primitive Analytique.
    ```json
    {
      "id": 1,
      "transform": [...],
      "component": {
        "type": "geometry",
        "data": { "shape": "cylinder", "radius": 1.0, "height": 2.0 }
      },
      // ...
    }
    ```
*   **Gain** : La sauvegarde devient une boucle générique `for obj in objects: json.dump(obj.properties)`. Plus de `if type == 'cylinder' ... elif type == 'cone'`.

## 3. Separation of Concerns
*   **Registry**: Should be Data-Driven.
*   **UI**: Should ideally generate itself based on exposed C++ properties, rather than manually coding `btn("Cylinder", ...)` and corresponding `add_cylinder` handlers.
