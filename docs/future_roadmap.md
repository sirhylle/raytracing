# Future Roadmap (Strategic)

La roadmap se divise en plusieurs axes parallèles : **Consolidation Logicielle**, **Évolution PBR** (pour la qualité visuelle), et les nouvelles extensions créatives et de post-traitement.

## Axe A : Consolidation Logicielle (Priority: Stability)

1.  **Critical Fix (Bug)** : Corriger l'Importance Sampling de l'HDRI (Rotation ignorée `src/environment.h`).
    *   **Status**: *Pending*
2.  **Architecture** : Remplacer `del engine` par un Context Manager (`with Engine() as e:`).
    *   **Status**: *Draft*
3.  **Refactoring UI** : Nettoyer `EditorState` (God Object) et utiliser un layout automatique.
    *   **Status**: *Draft*
4.  **Single Source of Truth** : Faire en sorte que Python interroge le C++ pour l'état des objets (Getters/Setters via Nanobind).
    *   **Status**: *Planned*
5.  **UX: Decouple Preview from UI State** (Priority: High)
    *   **Differentiation**: Distinguer "Scene Data Change" (qui requiert un restart rendu) de "UI State Change" (Tabs, Accordions).
    *   **Objective**: Empêcher le redémarrage du rendu lors de la navigation dans l'interface si la scène n'a pas changé.
6.  **Shadow Rays "Any Hit"** (Priority: High)
    *   *Diff*: Medium | *Value*: High (Perf)
    *   *Desc*: Add `hit_any()` to BVH for shadow rays. Stop traversal at the *first* intersection found instead of searching for the closest one. Expected gain: 20-30% on complex scenes.

## Axe B : Évolution PBR (Priority: Quality)

1.  **Microfacets Core** : Remplacer `Metal` et `Plastic` par une implémentation **GGX / Cook-Torrance**.
    *   *Gain* : Réalisme physique, cohérence énergétique.
    *   *Enable* : Permet d'échantillonner correctement les surfaces brillantes (Glossy).
2.  **MIS (Multiple Importance Sampling)** : Implémenter le "Balance Heuristic".
    *   *Gain* : Réduction drastique du bruit ("Fireflies") pour les matériaux mixtes (ni parfaitement diffus, ni parfaitement miroirs).
3.  **Advanced Diffuse** : Remplacer `Lambertian` par **Oren-Nayar**.
    *   *Gain* : Aspect plus naturel pour la pierre, le tissu, la peau.

4.  **Caustics & Transparency (Visualisation & Rendu)**
    *   **Solution : Targeted Photon Mapping**.
        *   Lancer de photons uniquement vers la Bounding Box des objets transparents (Geometry Cone).
        *   **Visualisation** : Afficher les points d'impact des photons dans l'Éditeur 3D pour donner un feedback immédiat.
        *   **Rendu** : Utiliser cette carte pour éclairer les zones d'ombre (Caustiques).
    *   **Intérêt** : Permet de voir la lumière traverser le verre sans attendre la convergence du Path Tracing.

## Axe C : Extension PBR & Material (Creative)

*   **Textures Support** (Priority: High)
    *   *Diff*: Medium | *Value*: High (Essential)
    *   *Desc*: Support for UV mapping and Image Textures (Albedo, Roughness, Normal). Basic feature missing in current engine.
*   **Procedural Noise (Perlin/Simplex)** (Priority: Medium)
    *   *Diff*: Low/Medium | *Value*: High (Versatility)
    *   *Desc*: Native C++ Perlin/Simplex noise generation.
    *   *Use Cases*: Marble, Clouds, Heterogeneous materials.
*   **Normal Alteration (Bump/Displacement)** (Priority: Medium)
    *   *Diff*: Medium | *Value*: High (Detail)
    *   *Desc*: Using Noise or Textures to perturb normals for high-frequency detail without adding geometry complexity.
*   **Semi-Random Meshes** (Priority: Low)
    *   *Diff*: High | *Value*: Fun/Niche
    *   *Desc*: Procedural mesh generation or modification (e.g. deformed spheres, random blobs) directly in C++.

## Axe D : Visual Polish & Camera (Filmic)

*   **Chromatic Aberration & Grain** (Priority: Medium)
    *   *Diff*: Medium (Constraint: Post-Denoiser) | *Value*: High (Realism)
    *   *Desc*: Post-processing effects to simulate real lenses (fringing, film grain).
    *   **Constraint**: Must be implemented **AFTER** the OIDN Denoiser, otherwise the denoiser will clean up the grain.
*   **Global Homogeneous Atmosphere (Fog/Aerial Perspective)** (Priority: Medium)
    *   *Diff*: High | *Value*: HIgh (Depth)
    *   *Desc*: Uniform participating media (fog). Adds "God Rays" and depth to large scenes. Easier to sample than clouds.
*   **Volumetrics (Heterogeneous / Clouds)** (Priority: Low - Long Term)
    *   *Diff*: Very High | *Value*: High (Specific)
    *   *Desc*: Cloudscape, Smoke, Fire. Requires advanced Delta Tracking. Very noise-prone.
*   **Subsurface Scattering (SSS)** (Priority: Low)
    *   *Diff*: High | *Value*: Specific Quality
    *   *Desc*: For wax/skin/jade. Can be approximated (Random Walk). To be done usually *after* volumetric logic is understood.

### New Ideas (Proposed)

*   **Procedural Sky (Hosek-Wilkie)** (Priority: High)
    *   *Diff*: Medium | *Value*: High (Atmosphere)
    *   *Desc*: Parametric Sky based on Sun position and turbidity. Replaces static HDRIs with dynamic day/night cycles. Perfect synergy with Volumetric Fog.
*   **Scatter System (Instancing Tool)** (Priority: Medium)
    *   *Diff*: Low (Python UI) | *Value*: High (Creative)
    *   *Desc*: "Paint" or procedural generation of instances (grass, pebbles) on surfaces. Purely a UI/Python layer over the existing Instance engine.
*   **Adaptive Sampling** (Priority: High)
    *   *Diff*: High | *Value*: High (Perf)
    *   *Desc*: Stop sampling pixels that have converged (low variance). Accelerates simple areas (sky, walls) by 2-4x.
*   **Advanced Tone Mapping (AgX / Configurable)** (Priority: Medium)
    *   *Diff*: Low | *Value*: High (Realism)
    *   *Status*: *Implemented (Fixed ACES)*. The current `renderer.py` hardcodes ACES + Gamma.
    *   *Goal*: Allow selecting different operators (AgX, Filmic, Linear) via CLI/UI. AgX handles saturated bright colors better than ACES.
*   **Imperfect Glass (Schlieren / Stress)** (Priority: Medium)
    *   *Diff*: Medium | *Value*: High (Realism)
    *   *Desc*: Perturbing IOR or Normal based on 3D World Position Noise to simulate internal stress/density variations. Removes the "perfectly digital" look of glass spheres. Synergies with Procedural Noise.
*   **Toon/Cel Shading Preview** (Priority: Low)
    *   *Diff*: Low | *Value*: High (Fun/Preview)
    *   *Desc*: Non-photorealistic rendering mode for the editor. Quantized lighting bands + Edge detection (Sobel). Makes the editor feel like a stylized game.


## Axe E : Debug & Quality of Life

*   **Blue Noise Samplers** (Priority: Low)
    *   *Diff*: Medium | *Value*: Medium (Visual)
    *   *Desc*: Better error distribution than White Noise/Sobol for low SPP/dithering patterns.
*   **Debug Views (Heatmaps)** (Priority: Low)
    *   *Diff*: Low | *Value*: Medium (Debug)
    *   *Desc*: Visualize technical metrics: Bounce Count (Heatmap), BVH Depth costs. (Note: Normals preview already exists).

---

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
