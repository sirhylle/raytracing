# Documentation d'Architecture : Brouillard Volumétrique & Effets Atmosphériques (Non Retenu)

> [!WARNING]
> **Statut de la fonctionnalité : REJETÉE / ROLLED BACK**
> Cette documentation sert à archiver une évolution technique qui a été entièrement implémentée et validée, mais **qui n'a finalement pas été retenue** et fait l'objet d'un rollback.
>
> **Motif du rejet :** L'intention initiale était de créer des faisceaux de lumière volumétrique saisissants ("rays of god" ou rayons crépusculaires). Malheureusement, l'implémentation du brouillard n'a jamais permis de faire ressortir cette lumière volumétrique de manière satisfaisante (l'effet "rays of god" n'a pas pu être produit de manière nette). Le rendu restait trop diffus et homogène ou souffrait d'une variance stochastique extrême (bruit de type "neige" ou "fireflies") inhérente au path tracing unidirectionnel avec Next Event Estimation (NEE) dans les milieux participants à faible nombre de samples (SPP). Ce document est conservé à titre de spécification technique de référence pour de futures expérimentations.


---

## 1. Vue d'ensemble Technique

L'objectif de cette évolution était d'intégrer un **milieu participant hétérogène (brouillard volumétrique)** capable de diffuser, d'absorber et de transmettre la lumière. Le système devait interagir dynamiquement avec les sources lumineuses du moteur (HDRI, Auto Sun, lumières géométriques) pour créer des effets atmosphériques réalistes et des faisceaux lumineux ("God rays") derrière des objets occultants (comme une sphère réfléchissante placée devant le soleil).

### Objectifs Techniques Visés :
*   **Hétérogénéité spatiale** : Densité variable selon l'altitude (décroissance exponentielle) et perturbation par un bruit procédural 3D (Perlin fBm : utilisation de l'implémentation stb_perlin.h by Sean Barrett) pour simuler des poches de brouillard ou des nuages.
*   **Diffusion anisotrope** : Modélisation de la diffusion vers l'avant ou l'arrière via la fonction de phase de **Henyey-Greenstein**.
*   **Direct Lighting Volumétrique (NEE)** : Échantillonnage direct des sources lumineuses depuis l'intérieur du volume avec calcul de transmittance.
*   **Transmittance Stable** : Calcul de l'atténuation lumineuse sans introduire la variance extrême propre aux méthodes purement stochastiques.

---

## 2. Galerie de Rendu (Visual Feedback Archive)

5 captures d'écran documentent les résultats visuels obtenus durant les différentes phases de raffinement du brouillard volumétrique :

````carousel
![Fog 1 - Premier jet du brouillard homogène avec bruit de neige important](file:///D:/Python/raytracing/docs/illustrations/fog1.png)
<!-- slide -->
![Fog 2 - Brouillard hétérogène avec perturbation par le bruit de Perlin 3D](file:///D:/Python/raytracing/docs/illustrations/fog2.png)
<!-- slide -->
![Fog 3 - Tentative de God Rays avec forte densité et éclairage direct du soleil](file:///D:/Python/raytracing/docs/illustrations/fog3.png)
<!-- slide -->
![Fog 4 - Test de visibilité des rayons lumineux avec la sphère réfléchissante en face caméra](file:///D:/Python/raytracing/docs/illustrations/fog4.png)
<!-- slide -->
![Fog 5 - Rendu stabilisé après application de la transmittance par intégration déterministe](file:///D:/Python/raytracing/docs/illustrations/fog5.png)
````

*Les illustrations ci-dessus montrent la transition d'un bruit de "neige" stochastique à un brouillard volumétrique plus stable, mais qui manque de la netteté et du contraste nécessaires pour dessiner des rayons de lumière précis.*

---

## 3. Choix Algorithmiques & Spécifications Mathématiques

### A. Échantillonnage de Distance : Woodcock (Delta) Tracking
Dans un milieu homogène, la distance de collision d'un rayon se calcule facilement via la loi de Beer-Lambert : $t = -\ln(1-u) / \sigma_t$. 
Dans un milieu hétérogène (comme notre brouillard perturbé par Perlin), la densité change à chaque point du rayon, rendant l'intégration analytique impossible. Nous avons choisi l'algorithme de **Woodcock Tracking** (ou Delta Tracking), qui est une méthode de type rejet :
1.  Calculer une densité maximale globale (majorant $\bar{\sigma}$) sur le segment de rayon.
2.  Avancer de manière stochastique en supposant un milieu homogène de densité $\bar{\sigma}$ : $t \leftarrow t - \ln(1-u_1) / \bar{\sigma}$.
3.  Si la limite de distance est dépassée, le rayon traverse sans collision.
4.  Sinon, évaluer la vraie densité locale $\sigma(p)$. Accepter la collision avec une probabilité $\sigma(p) / \bar{\sigma}$ (évaluée via un second nombre aléatoire $u_2$). Sinon, répéter à partir du point actuel.

### B. Estimation de la Transmittance : Ray Marching Déterministe
La transmittance détermine l'atténuation de la lumière le long d'un rayon (ex: ombres volumétriques ou atténuation de l'arrière-plan).
*   **L'approche stochastique (Ratio Tracking)** : Évalue la transmittance en multipliant les poids de non-collision de Woodcock. Bien qu'impartiale, cette méthode introduit une variance extrême à faible SPP (Samples Per Pixel), créant un effet de "neige" blanche (pixels saturés de lumière ayant échappé aux collisions face à des pixels sombres les ayant subies).
*   **L'approche déterministe (Ray Marching)** : Pour stabiliser l'image, nous avons implémenté un estimateur par **Ray Marching à pas fixe (16 pas)** :
    $$T(t) = \exp \left( - \sum_{i=1}^{N} \sigma(p_i) \Delta t \right)$$
    Cette méthode déterministe a éliminé instantanément le bruit de neige sur le fond et dans les ombres de volume, au prix d'un calcul d'échantillonnage de densité régulier.

### C. Fonction de Phase de Henyey-Greenstein
Pour modéliser la diffusion de la lumière par les particules de brouillard, nous utilisons la fonction de phase HG :
$$p(\cos\theta) = \frac{1 - g^2}{4\pi (1 + g^2 - 2g\cos\theta)^{3/2}}$$
*   $g \in [-1, 1]$ représente l'anisotropie.
*   $g > 0$ modélise une forte diffusion vers l'avant (caractéristique du brouillard d'eau, produisant des halos lumineux intenses autour des sources de lumière).
*   $g = 0$ donne une diffusion isotrope uniforme (type Lambertien).

### D. Multiple Importance Sampling (MIS) dans le Volume
Lors d'une collision volumétrique, pour calculer la lumière reçue par le point, nous combinons :
1.  **Le sampling de la fonction de phase** : Générer une direction selon la distribution HG et évaluer le rayon indirect.
2.  **Le sampling direct des lumières (NEE)** : Choisir une direction pointant vers une source de lumière (HDRI ou Auto Sun) et évaluer sa contribution pondérée par la transmittance volumétrique.
Les deux stratégies sont combinées via l'heuristique de puissance (Power Heuristic) pour minimiser la variance.

---

## 4. Spécification de l'Architecture Logicielle (Fichiers & Code)

Si cette fonctionnalité doit être ré-implémentée à l'avenir, voici l'inventaire des composants et les détails de leur code :

### A. Structure C++ de l'Atmosphère (`src/volumes.h`)
Elle encapsule les paramètres physiques et gère le bruit procédural ainsi que l'échantillonnage :

```cpp
struct Atmosphere {
    bool active = false;
    Real density = 0.0f;
    Real anisotropy = 0.0f;
    Vec3 color = Vec3(1.0f, 1.0f, 1.0f);
    
    bool use_noise = false;
    Real noise_scale = 1.0f;

    // Décroissance exponentielle de la hauteur + Bruit de Perlin 3D
    Real get_density(const Vec3& p) const {
        if (!active || density <= 0.0f) return 0.0f;
        
        // Chute d'altitude : division par 2 environ tous les 35 unités de hauteur
        Real height_factor = std::exp(-std::max(0.0f, p.y()) * 0.02f);
        Real current_density = density * height_factor;

        if (!use_noise) return current_density;
        
        Real scale = noise_scale > 0.0f ? noise_scale : 1.0f;
        Vec3 np = p * scale;
        
        // fBm de Perlin 3D (4 octaves) via stb_perlin.h
        Real n = stb_perlin_fbm_noise3(np.x(), np.y(), np.z(), 2.0f, 0.5f, 4);
        
        // Remappage et augmentation du contraste pour accentuer les structures de faisceaux
        Real mapped = (n + 1.2f) / 2.4f;
        mapped = std::pow(std::max(0.0f, std::min(mapped, 1.0f)), 2.0f);
        
        return current_density * mapped;
    }

    // Woodcock Tracking pour échantillonner la distance de collision libre
    bool sample_distance(const Ray& r, Real max_dist, Sampler& sampler, Real& t_hit, Real& transmittance) const {
        if (!active || density <= 0.0f) {
            transmittance = 1.0f;
            return false;
        }

        Real capped_max_dist = std::min(max_dist, 500.0f); // Évite les distances infinies
        Real majorant = density * 1.1f; // Marge de sécurité de 10%
        Real t = 0.0f;
        
        while (t < capped_max_dist) {
            t += -std::log(1.0f - sampler.get_1d()) / majorant;
            if (t >= capped_max_dist) break;
            
            Real current_density = get_density(r.orig + r.dir * t);
            if (sampler.get_1d() < current_density / majorant) {
                t_hit = t;
                transmittance = 1.0f;
                return true;
            }
        }
        
        transmittance = 1.0f;
        return false;
    }

    // Calcul stable de la transmittance via Ray Marching à 16 pas
    Real evaluate_transmittance_stable(const Ray& r, Real max_dist) const {
        if (!active || density <= 0.0f) return 1.0f;
        
        Real capped_max_dist = std::min(max_dist, 500.0f);
        const int steps = 16;
        Real step_size = capped_max_dist / (Real)steps;
        Real optical_depth = 0.0f;
        
        for (int i = 0; i < steps; ++i) {
            Real t = (i + 0.5f) * step_size;
            optical_depth += get_density(r.orig + r.dir * t);
        }
        
        return std::exp(-optical_depth * step_size);
    }
};
```

### B. Intégration dans le Tracé de Rayon (`src/renderer.h`)
Les modifications majeures résident dans l'interception des collisions dans `ray_color` et la fonction dédiée d'éclairage direct pour les points du volume :

1.  **Interception Volumétrique** :
    ```cpp
    Real t_vol;
    Real transmittance;
    bool scattered_in_volume = false;
    
    if (atmosphere && atmosphere->active) {
        scattered_in_volume = atmosphere->sample_distance(r, max_dist, sampler, t_vol, transmittance);
    } else {
        transmittance = 1.0f;
    }

    if (scattered_in_volume) {
        Vec3 p_vol = r.orig + r.dir * t_vol;
        Vec3 direct_light_vol = sample_direct_light_volume(r, p_vol, world, lights, env_map, atmosphere, sampler);
        
        // Phase function scattering (Henyey-Greenstein)
        Vec3 new_dir = sample_hg(r.dir, atmosphere->anisotropy, sampler);
        Ray scattered_ray(p_vol, new_dir, r.tm, false);
        
        Real phase_pdf = hg_phase(dot(r.dir, new_dir), atmosphere->anisotropy);
        Vec3 indirect_vol = ray_color(scattered_ray, world, lights, env_map, atmosphere, depth - 1, sampler, phase_pdf, 1.0f);
        
        Vec3 total = direct_light_vol + atmosphere->color * indirect_vol;
        
        // Clamping strict des fireflies volumétriques
        total.e[0] = firefly_clamp(total.x(), FIREFLY_CLAMP_LIMIT);
        total.e[1] = firefly_clamp(total.y(), FIREFLY_CLAMP_LIMIT);
        total.e[2] = firefly_clamp(total.z(), FIREFLY_CLAMP_LIMIT);
        return total;
    }
    ```

2.  **Bridage des Fireflies** dans `sample_direct_light_volume` :
    Pour éviter que la fonction de phase extrêmement piquée vers l'avant ($g \approx 0.9$) ne génère des pics d'intensité aberrants lorsqu'un rayon frôle l'axe du soleil, le terme de phase a été bridé à `10.0f` et le résultat final de l'éclairage direct volumétrique a été tronqué à `10.0f` maximum par canal de couleur.

### C. Bindings Python (`src/main.cpp`)
Les bindings Nanobind exposaient l'objet d'ambiance globale de la scène :
```cpp
nb::class_<Atmosphere>(m, "Atmosphere")
    .def_rw("active", &Atmosphere::active)
    .def_rw("density", &Atmosphere::density)
    .def_rw("anisotropy", &Atmosphere::anisotropy)
    .def_rw("use_noise", &Atmosphere::use_noise)
    .def_rw("noise_scale", &Atmosphere::noise_scale)
    .def_rw("color", &Atmosphere::color);
```

### D. Gestion d'État & Crash de Cast (`modes/editor/state.py`)
Un problème critique de typage a été résolu lors de l'envoi des couleurs de l'atmosphère à C++. L'attribut `state.atmos_color` (stocké sous forme de liste Python de floats) était parfois interprété par NumPy comme un type `numpy.float64` ou posait des problèmes de conversion nanobind. Le correctif a consisté à forcer le cast en types natifs Python `float` avant l'envoi à C++ :
```python
atmos.color = (float(self.atmos_color[0]), float(self.atmos_color[1]), float(self.atmos_color[2]))
```
De plus, la densité de l'interface utilisateur a été atténuée par un facteur d'échelle constant de `0.1` (`atmos.density = self.atmos_density * 0.1`) afin de conserver des curseurs d'UI agréables à manipuler pour des atmosphères subtiles.

### E. Intégration de l'Interface Utilisateur (`tab_scene.py`)
L'interface disposait d'un panneau accordéon dédié dans l'onglet `SCENE` :
*   **Active Toggle** : Bouton ON/OFF pour activer/désactiver l'atmosphère globalement.
*   **Density Slider** : Plage de `0.0` à `1.0` avec une courbe de sensibilité cubique (`power=3.0`) pour un contrôle ultra-fin dans les très faibles densités.
*   **Anisotropy Slider** : Plage de `-0.99` à `0.99` pour ajuster la directionnalité de la lumière (HG).
*   **Color Pickers** : 3 sliders pour les canaux Rouge, Vert, Bleu.
*   **Perlin Noise Toggle** : Bouton ON/OFF pour basculer sur un brouillard hétérogène.
*   **Noise Scale Slider** : Plage de `0.01` à `10.0` avec une courbe quadratique (`power=2.0`) pour modifier l'échelle spatiale des formations de brouillard.

---

## 5. Pourquoi les "God Rays" n'ont pas fonctionné (Leçons Apprises)

L'absence d'un effet "faisceau de lumière" saisissant, malgré un code mathématiquement correct, s'explique par des contraintes fondamentales liées à la nature du path tracing unidirectionnel :

1.  **Le problème du Path Tracing Unidirectionnel** :
    Dans un moteur unidirectionnel, les rayons partent de la caméra. Pour capturer un faisceau lumineux, un rayon de caméra doit entrer en collision stochastique avec le volume exactement à un endroit éclairé par une source lumineuse et diffuser vers la caméra. Avec un soleil lointain (Auto Sun) ou une HDRI, la probabilité d'échantillonner le bon point de volume qui connecte efficacement la lumière et la caméra sans bruit est faible.
2.  **Variance Extrême à Anisotropie Élevée** :
    Pour obtenir des rayons de lumière nets, il faut une forte diffusion vers l'avant ($g \ge 0.85$). Cependant, plus $g$ est proche de $1.0$, plus la fonction de phase ressemble à une fonction Dirac (un pic extrêmement étroit). La probabilité qu'un rayon aléatoire de caméra frappe exactement ce cône minuscule est minuscule, ce qui cause :
    *   Un bruit de "fireflies" constant (des pixels blancs isolés extrêmement brillants lorsque le cône est frappé par hasard).
    *   Un rendu terne et homogène la majorité du temps (quand le cône n'est pas frappé).
3.  **Absence d'un Denoiseur Volumétrique Dédié** :
    Le denoiseur Intel OIDN utilisé par le moteur est entraîné sur des surfaces solides (avec des buffers d'Albedo et de Normales géométriques très marqués). Dans un volume, les normales géométriques n'existent pas et l'albedo est diffus, ce qui empêche OIDN de distinguer le bruit stochastique du brouillard hétérogène. OIDN a tendance à lisser complètement le volume ou à créer des bavures disgracieuses qui effacent la structure des faisceaux de lumière.
4.  **Alternatives futures suggérées** :
    Pour obtenir de vrais "God Rays" nets et performants, il faudrait plutôt :
    *   Un **chemin de rendu dédié par Ray Marching analytique de lumière** uniquement pour le soleil (en projetant les ombres de la shadow map ou de la géométrie de la scène dans le volume).
    *   Une méthode de **Light Transport bidirectionnel (BDPT)** ou de **Volumetric Path Guiding**.
    *   Un effet de post-traitement en espace écran (Screen-Space Volumetric Rays), bien plus rapide et parfait pour le temps réel.
