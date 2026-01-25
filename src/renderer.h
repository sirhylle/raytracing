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
// Helper: Power Heuristic
inline Real power_heuristic(Real pdf_f, Real pdf_g) {
  Real f2 = pdf_f * pdf_f;
  Real g2 = pdf_g * pdf_g;
  Real den = f2 + g2;
  if (den < 1e-10f)
    return 0.0f; // Prevent NaN
  return f2 / den;
}

// -----------------------------------------------------------------------------------------------
// ALGORITHM: DIRECT LIGHT SAMPLING (Next Event Estimation)
// -----------------------------------------------------------------------------------------------
inline Vec3 sample_direct_light(const Ray &r, const HitRecord &rec,
                                const ScatterRecord &srec,
                                const Hittable &world,
                                const HittableList &lights,
                                const EnvironmentMap *env_map) {
  Vec3 direct_light(0, 0, 0);

  // Strategy: 50/50 EnvMap vs Geometric Lights
  bool sample_env = false;
  bool env_is_active = env_map && (env_map->env_direct_scale > 0.001f);
  bool lights_are_active = !lights.raw_objects.empty();

  if (env_is_active && lights_are_active) {
    sample_env = random_real() < 0.5f;
  } else if (env_is_active) {
    sample_env = true;
  } else if (lights_are_active) {
    sample_env = false;
  } else {
    return Vec3(0, 0, 0);
  }

  // --- A. Generate Light Sample ---
  Ray light_ray;
  Real light_pdf_val = 0.0f;
  bool is_env_sample = false;
  Vec3 potential_light_emission(0, 0, 0);

  if (sample_env && env_map) {
    // Importance Sampling HDRI
    Vec3 dir = env_map->sample_direction(light_pdf_val);
    light_ray = Ray(rec.p, dir, r.tm, true);

    if (lights_are_active)
      light_pdf_val *= 0.5f;

    potential_light_emission = env_map->sample(dir, 1);
    if (potential_light_emission.length_squared() <= 0)
      light_pdf_val = 0;
    is_env_sample = true;

  } else if (!lights.raw_objects.empty()) {
    // Sampling Geometric Light
    auto light_ray_dir = lights.random(rec.p);
    light_ray = Ray(rec.p, light_ray_dir, r.tm, true);
    light_pdf_val = lights.pdf_value(rec.p, light_ray.dir);

    if (env_is_active)
      light_pdf_val *= 0.5f;
    is_env_sample = false;
  }

  // --- B. Validation & MIS Calculation ---
  if (light_pdf_val > 0) {
    // 1. Evaluate BSDF for this light direction
    Vec3 bsdf_val = rec.mat_ptr->eval_bsdf(r, rec, light_ray.dir);

    if (bsdf_val.x() > 0 || bsdf_val.y() > 0 || bsdf_val.z() > 0) {

      // 2. Calculate Scattering PDF (p_bsdf) for MIS
      Real bsdf_pdf = rec.mat_ptr->scattering_pdf(r, rec, light_ray);

      // 3. Shadow Ray
      Vec3 transmission(1.0f, 1.0f, 1.0f);
      Ray shadow_ray = light_ray;
      bool light_visible = false;

      // Traversal Logic (Handles transparent shadows)
      for (int i = 0; i < 5; ++i) {
        HitRecord hit_obstacle;
        if (world.hit(shadow_ray, EPSILON, INFINITY_REAL, hit_obstacle)) {
          if (hit_obstacle.mat_ptr->is_transparent()) {

            // CRITICAL FIX: If we are targeting a Geometric Light, and we hit a
            // transparent object... Check if THIS object IS the light we are
            // looking for!
            if (!is_env_sample) {
              Vec3 emission_found = hit_obstacle.mat_ptr->emit(
                  shadow_ray, hit_obstacle, 0, 0, hit_obstacle.p);
              if (emission_found.length_squared() > 0) {
                potential_light_emission = emission_found;
                light_visible = true;
                // We found our light! Stop traversing.
                // Note: We multiply by accumulated transmission so far.
                // direct_light calculation later uses 'transmission' *
                // 'potential_light_emission'.
                break;
              }
            }

            ScatterRecord srec_shadow;
            if (hit_obstacle.mat_ptr->scatter(shadow_ray, hit_obstacle,
                                              srec_shadow)) {
              transmission = transmission * srec_shadow.attenuation;
              Vec3 check_emit = hit_obstacle.mat_ptr->emit(
                  shadow_ray, hit_obstacle, 0, 0, hit_obstacle.p);
              if (check_emit.length_squared() == 0)
                transmission = transmission * DIELECTRIC_SHADOW_TRANSMISSION;
            }
            shadow_ray = Ray(hit_obstacle.p + EPSILON * shadow_ray.dir,
                             shadow_ray.dir, shadow_ray.tm, true);
          } else {
            // Opaque Obstacle
            if (is_env_sample) {
              light_visible = false;
            } else {
              // Sampled Geom Light?
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
          // Hit Nothing -> Sky
          if (is_env_sample)
            light_visible = true;
          break;
        }
      }

      // 4. Final Contribution with MIS Weight
      if (light_visible) {
        // Power Heuristic: W_nee = p_light^2 / (p_light^2 + p_bsdf^2)
        // Note: For delta lights (point), p_light is infinite?
        // Our lights are Area Lights, so p_light is finite.

        Real w_mis = power_heuristic(light_pdf_val, bsdf_pdf);

        // For Delta Material (Mirror), bsdf_pdf is 0/undefined, but we
        // shouldn't be here (srec.is_specular handles delta). Actually, for
        // Mirror, srec.is_specular=true, so we skip NEE entirely in ray_color.
        // So here we are guaranteed non-delta BSDF.

        direct_light = potential_light_emission * bsdf_val * transmission *
                       (w_mis / light_pdf_val);
      }
    }
  }

  return direct_light;
}

// -----------------------------------------------------------------------------------------------
// ALGORITHM: PATH TRACING RECURSION (MIS Aware)
// -----------------------------------------------------------------------------------------------
// -----------------------------------------------------------------------------------------------
// ALGORITHM: PATH TRACING RECURSION (MIS Aware)
// -----------------------------------------------------------------------------------------------
// -----------------------------------------------------------------------------------------------
// ALGORITHM: PATH TRACING RECURSION (MIS Aware)
// -----------------------------------------------------------------------------------------------
inline Vec3
ray_color(const Ray &r, const Hittable &world, const HittableList &lights,
          const EnvironmentMap *env_map, int depth,
          Real prev_bsdf_pdf = 1.0f, // PDF of the ray generation
          Real prev_roughness =
              1.0f // New: Roughness of previous bounce (0=Mirror, 1=Matte)
) {

  // 1. Bounce Limit
  if (depth <= 0)
    return Vec3(0, 0, 0);

  // 2. Scene Intersection
  HitRecord rec;
  if (!world.hit(r, EPSILON, INFINITY_REAL, rec)) {
    // --- BACKGROUND / ENV MAP HIT ---
    if (env_map) {
      // Logic for Environment Scale (Visual Split)
      // Mode 0 (Visible) : Primary Rays.
      // Mode 1 (Direct)  : Sky lighting Diffuse/Rough surfaces (Illumination).
      // Mode 2 (Reflect) : Sky appearing in Mirrors/Glossy reflections.

      int mode = 0;
      if (r.is_primary) {
        mode = 0; // Visible Background
      } else if (prev_roughness < 0.2f) {
        // Treating Glossy/Specular bounces as "Reflections"
        // This allows the "Indirect/Reflections" slider to control Metal/Glass
        // appearance.
        mode = 2;
      } else {
        // Treating Rough/Matte bounces as "Illumination"
        // This allows the "Direct/Global Light" slider to control Scene
        // Brightness.
        mode = 1;
      }

      Vec3 L_e = env_map->sample(r.dir, mode);

      // If purely specular (delta), MIS weight is 1.0.
      // Checking roughness < epsilon is a proxy for delta.
      if (prev_roughness < 0.001f)
        return L_e;

      // Calculate what the Light PDF would have been for this direction
      Real light_pdf = 0.0f;
      bool env_is_active = env_map->env_direct_scale > 0.001f;
      bool lights_are_active = !lights.raw_objects.empty();

      if (env_is_active) {
        light_pdf = env_map->pdf_value(r.dir);
        if (lights_are_active)
          light_pdf *= 0.5f; // 50/50 chance
      }

      Real w_mis = power_heuristic(prev_bsdf_pdf, light_pdf);
      return L_e * w_mis;
    }
    return Vec3(0, 0, 0);
  }

  // 3. Emission Hit
  Vec3 emitted = rec.mat_ptr->emit(r, rec, rec.u, rec.v, rec.p);
  if (emitted.length_squared() > 0) {
    if (prev_roughness < 0.001f)
      return emitted;

    // Calculate Light PDF for this point
    bool env_is_active = env_map && (env_map->env_direct_scale > 0.001f);
    bool lights_are_active = !lights.raw_objects.empty();

    if (lights_are_active) {
      Real p_light = lights.pdf_value(r.orig, r.dir);
      if (env_is_active)
        p_light *= 0.5f;

      Real w_mis = power_heuristic(prev_bsdf_pdf, p_light);
      return emitted * w_mis;
    }
    return emitted;
  }

  // 4. Scattering & BSDF Sampling
  ScatterRecord srec;
  if (!rec.mat_ptr->scatter(r, rec, srec))
    return Vec3(0, 0, 0);

  // 5. Specular Optimization
  if (srec.is_specular) {
    return srec.attenuation * ray_color(srec.specular_ray, world, lights,
                                        env_map, depth - 1, 1.0f,
                                        srec.roughness);
  }

  // 6. Direct Light (Next Event Estimation)
  Vec3 direct_light = sample_direct_light(r, rec, srec, world, lights, env_map);

  // 7. Indirect Light (Recursive Step)
  Real bsdf_pdf = rec.mat_ptr->scattering_pdf(r, rec, srec.specular_ray);

  Vec3 indirect =
      srec.attenuation * ray_color(srec.specular_ray, world, lights, env_map,
                                   depth - 1, bsdf_pdf, srec.roughness);

  // 8. Output
  Vec3 total = direct_light + indirect;

  // Firefly Clamp
  total.e[0] = soft_clamp(total.x(), FIREFLY_CLAMP_LIMIT);
  total.e[1] = soft_clamp(total.y(), FIREFLY_CLAMP_LIMIT);
  total.e[2] = soft_clamp(total.z(), FIREFLY_CLAMP_LIMIT);

  return total;
}