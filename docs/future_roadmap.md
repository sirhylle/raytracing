# Future Roadmap (Strategic)

La roadmap se divise en deux axes parallèles : **Consolidation Logicielle** (pour la stabilité/maintenabilité) et **Évolution PBR** (pour la qualité visuelle).

## Axe A : Consolidation Logicielle (Priority: Stability)

1.  **Critical Fix (Bug)** : Corriger l'Importance Sampling de l'HDRI (Rotation ignorée `src/environment.h`).
    *   **Status**: *Pending*
2.  **Architecture** : Remplacer `del engine` par un Context Manager (`with Engine() as e:`).
    *   **Status**: *Draft*
3.  **Refactoring UI** : Nettoyer `EditorState` (God Object) et utiliser un layout automatique.
    *   **Status**: *Draft*
4.  **Single Source of Truth** : Faire en sorte que Python interroge le C++ pour l'état des objets (Getters/Setters via Nanobind).
    *   **Status**: *Planned*

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
