#pragma once

// ===============================================================================================
// MODULE: PATH TRACING CORE
// ===============================================================================================
//
// DESCRIPTION:
//   This is the heart of the rendering engine. It implements a Unidirectional
//   Path Tracer with Next Event Estimation (NEE).
//
//   It solves the Rendering Equation (Kajiya 1986) by integrating light
//   arriving at the camera through recursive Monte Carlo sampling.
//
// ALGORITHM OVERVIEW:
//   1. ray_color(): Recursive function that traces the path of a photon
//   backwards from the eye.
//      L_o = L_e + Integral( f_r * L_i * cos(theta) )
//
//   2. Next Event Estimation (sample_direct_light):
//      Instead of waiting for a random bounce to hit a light source (which is
//      rare), we explicitly sample light sources at every bounce (except for
//      specular surfaces). This significantly reduces noise (variance).
//
// ===============================================================================================

#include "common.h"
#include "environment.h" // Pour EnvironmentMap
#include "geometry.h"    // Pour HittableList
#include "hittable.h"
#include "materials.h" // Pour ScatterRecord

// ===============================================================================================
// MOTEUR DE RENDU (Path Tracing Core)
// ===============================================================================================

// -----------------------------------------------------------------------------------------------
// ALGORITHM: DIRECT LIGHT SAMPLING (Next Event Estimation)
// -----------------------------------------------------------------------------------------------
// Calculates the direct illumination contribution at a point 'rec.p' from all
// light sources.
// - It samples either the Environment Map or Geometric Lights (Area Lights).
// - It casts a Shadow Ray to check visibility.
// - It applies Multiple Importance Sampling (MIS) heuristics (simplified here
// as PDF balancing).
// -----------------------------------------------------------------------------------------------
inline Vec3 sample_direct_light(const Ray &r, const HitRecord &rec,
                                const ScatterRecord &srec,
                                const Hittable &world,
                                const HittableList &lights,
                                const EnvironmentMap *env_map) {
  // =========================================================
  // NEE (Next Event Estimation) - Éclairage Direct
  // =========================================================
  Vec3 direct_light(0, 0, 0);

  // Stratégie de choix : EnvMap OU Lumières géométriques ?
  bool sample_env = false;

  // On vérifie si l'env map contribue vraiment
  bool env_is_active = env_map && (env_map->env_direct_scale > 0.001f);
  bool lights_are_active = !lights.raw_objects.empty();

  // On gère les différents cas entre envMap et lumières géométriques
  if (env_is_active && lights_are_active) {
    // 50/50
    sample_env = random_real() < 0.5f;
  } else if (env_is_active) {
    // EnvMap seule
    sample_env = true;
  } else if (lights_are_active) {
    // Lumières géométriques seule
    sample_env = false;
  } else {
    // Aucune source de lumière directe !
    return Vec3(0, 0, 0);
    // return emitted + srec.attenuation * ray_color(srec.specular_ray, world,
    //                                               lights, env_map, depth - 1,
    //                                               false);
  }

  // Préparation des variables pour le sampling
  Ray light_ray;
  Real light_pdf_val = 0.0f;
  bool is_env_sample = false;
  Vec3 potential_light_emission(0, 0, 0);

  // --- A. Génération du rayon vers la lumière ---
  if (sample_env && env_map) {
    // Importance Sampling de l'HDRI
    Real pdf = 0;
    Vec3 dir = env_map->sample_direction(
        pdf); // Direction vers un point brillant du ciel
    light_ray = Ray(rec.p, dir, r.tm, true);
    light_pdf_val = pdf;

    if (lights_are_active)
      light_pdf_val *= 0.5f; // Compensation du choix 50/50

    potential_light_emission = env_map->sample(dir, 1);
    if (potential_light_emission.length_squared() <= 0)
      light_pdf_val = 0; // Optim

    is_env_sample = true;

  } else if (!lights.raw_objects.empty()) {
    // Sampling d'une lumière géométrique (Sphère, Quad)
    auto light_ray_dir = lights.random(rec.p);
    light_ray = Ray(rec.p, light_ray_dir, r.tm, true);
    light_pdf_val = lights.pdf_value(rec.p, light_ray.dir);

    if (env_is_active)
      light_pdf_val *= 0.5f; // Compensation du choix 50/50

    is_env_sample = false;
  }

  // --- B. Validation et Calcul (Shadow Ray) ---
  if (light_pdf_val > 0) {
    // Le BSDF de notre matériau pour cette direction de lumière
    auto scattering_pdf = rec.mat_ptr->scattering_pdf(r, rec, light_ray);

    if (scattering_pdf > 0) {
      // Rayon d'ombre : Est-ce qu'on voit la lumière ?
      Vec3 transmission(1.0f, 1.0f, 1.0f);
      Ray shadow_ray = light_ray;

      bool light_visible = false;

      // Boucle pour traverser les objets transparents (ex: fenêtres)
      for (int i = 0; i < 5; ++i) {
        HitRecord hit_obstacle;
        // On utilise le BVH ici via 'world'
        if (world.hit(shadow_ray, EPSILON, INFINITY_REAL, hit_obstacle)) {

          if (hit_obstacle.mat_ptr->is_transparent()) {
            // Si on ne visait PAS le ciel, on vérifie si l'objet transparent
            // n'est pas notre lampe invisible (Lightbulb dans une sphere de
            // verre)
            if (!is_env_sample) {
              Vec3 emission_found = hit_obstacle.mat_ptr->emit(
                  shadow_ray, hit_obstacle, hit_obstacle.u, hit_obstacle.v,
                  hit_obstacle.p);
              if (emission_found.length_squared() > 0) {
                potential_light_emission = emission_found;
                light_visible = true;
                break;
              }
            }

            // C'est du verre (ou pas la bonne lumière), on atténue et on
            // continue
            ScatterRecord srec_shadow;
            if (hit_obstacle.mat_ptr->scatter(shadow_ray, hit_obstacle,
                                              srec_shadow)) {
              transmission = transmission * srec_shadow.attenuation;

              // Hack pour les objets purement diélectriques (sans émission)
              // pour garder du volume
              Vec3 check_emit = hit_obstacle.mat_ptr->emit(
                  shadow_ray, hit_obstacle, hit_obstacle.u, hit_obstacle.v,
                  hit_obstacle.p);
              if (check_emit.length_squared() == 0) {
                transmission = transmission * DIELECTRIC_SHADOW_TRANSMISSION;
              }
            }
            // On avance le rayon
            shadow_ray = Ray(hit_obstacle.p + EPSILON * shadow_ray.dir,
                             shadow_ray.dir, shadow_ray.tm, true);
          } else {
            // Obstacle Opaque ou Lumière
            if (is_env_sample) {
              light_visible = false; // Le ciel est caché
            } else {
              // Est-ce la lampe qu'on visait ?
              auto li_emit = hit_obstacle.mat_ptr->emit(
                  shadow_ray, hit_obstacle, hit_obstacle.u, hit_obstacle.v,
                  hit_obstacle.p);
              if (li_emit.length_squared() > 0) {
                potential_light_emission = li_emit;
                light_visible = true;
              }
            }
            break;
          }
        } else {
          // Rien touché -> Ciel visible
          if (is_env_sample)
            light_visible = true;
          break;
        }
      }

      // --- C. Contribution finale ---
      if (light_visible) {
        direct_light = potential_light_emission * srec.attenuation *
                       scattering_pdf * transmission / light_pdf_val;
      }
    }
  }

  return direct_light;
}

// -----------------------------------------------------------------------------------------------
// ALGORITHM: PATH TRACING RECURSION
// -----------------------------------------------------------------------------------------------
// Calculates the radiance along a ray.
//
// Steps:
// 1. Intersection: Find the closest object hit.
// 2. Emission: If the object emits light (and we are allowed to see it), add
// it.
// 3. Scattering: Use the Material BSDF to generate a new ray direction.
// 4. Direct Light: Compute NEE contribution (shadow rays).
// 5. Indirect Light: Recurse (shoot the scattered ray).
// -----------------------------------------------------------------------------------------------
inline Vec3 ray_color(const Ray &r, const Hittable &world,
                      const HittableList &lights, const EnvironmentMap *env_map,
                      int depth, bool allow_emission = true) {

  // 1. Bounce Limit (Recursion Depth)
  if (depth <= 0)
    return Vec3(0, 0, 0);

  // 2. Scene Intersection
  HitRecord rec;
  // Note : Epsilon à 0.001f ou 0.01f pour éviter l'acné, INFINITY_REAL pour le
  // max
  if (!world.hit(r, EPSILON, INFINITY_REAL, rec)) {
    // Si on rate tout, on touche le fond (Environment Map)
    if (env_map && allow_emission) {
      // Si primaire (caméra) -> Mode 0 (Visible)
      // Sinon (rebond) -> Mode 2 (Indirect)
      int mode = r.is_primary ? 0 : 2;
      return env_map->sample(r.dir, mode);
    }
    return Vec3(0, 0, 0);
  }

  // 3. Emission
  Vec3 emitted = rec.mat_ptr->emit(r, rec, rec.u, rec.v, rec.p);
  if (!allow_emission)
    emitted = Vec3(0, 0, 0); // Empêche le double comptage pour le NEE

  // 4. Scattering & BSDF Sampling
  ScatterRecord srec;
  if (!rec.mat_ptr->scatter(r, rec, srec))
    return emitted; // C'est une lumière ou un objet noir, on s'arrête.

  // 5. Special Case: Specular Surfaces (Mirror/Glass)
  // We cannot use NEE (Direct Light Sampling) on perfect specular surfaces
  // because the probability of hitting a light source from a delta distribution
  // is zero. We just follow the ray.
  if (srec.is_specular) {
    return emitted +
           srec.attenuation *
               ray_color(
                   srec.specular_ray, world, lights, env_map, depth - 1,
                   true); // true car on veut voir les lumières dans le miroir
  }

  // 6. Direct Light (Next Event Estimation)
  Vec3 direct_light = sample_direct_light(r, rec, srec, world, lights, env_map);

  // 7. Indirect Light (Recursive Step)
  Vec3 indirect = srec.attenuation * ray_color(srec.specular_ray, world, lights,
                                               env_map, depth - 1, false);

  // 8. Firefly Clamping (Reduces outliers)
  indirect.e[0] = soft_clamp(indirect.x(), FIREFLY_CLAMP_LIMIT);
  indirect.e[1] = soft_clamp(indirect.y(), FIREFLY_CLAMP_LIMIT);
  indirect.e[2] = soft_clamp(indirect.z(), FIREFLY_CLAMP_LIMIT);

  return emitted + direct_light + indirect;
}