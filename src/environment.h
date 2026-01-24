#pragma once

#include "common.h"
#include <algorithm>
#include <cmath>
#include <utility> // pour std::pair
#include <vector>

struct EnvironmentMap {
  std::vector<Real> data;
  int width;
  int height;
  Real env_visible_scale = 1.0f;
  Real env_direct_scale = 1.0f;
  Real env_indirect_scale = 1.0f;
  Real rotation = 0.0f;
  Real clipping_threshold; // Seuil de clipping pour le MIS et le sampling

  // Pour l'Importance Sampling
  std::vector<Real> marginal_CDF; // Probabilité de choisir une ligne Y
  std::vector<std::vector<Real>>
      conditional_CDFs; // Probabilité de choisir X sachant Y

  EnvironmentMap(const std::vector<Real> &d, int w, int h,
                 Real threshold = INFINITY_REAL)
      : data(d), width(w), height(h), clipping_threshold(threshold) {
    build_cdf();
  }

  void set_scales(Real vis, Real direct, Real indirect) {
    env_visible_scale = vis;
    env_direct_scale = direct;
    env_indirect_scale = indirect;
  }

  // Setter pour la rotation (reçoit des degrés)
  void set_rotation(Real degrees) {
    // Conversion Degrés -> Radians
    // On inverse le signe si besoin selon le sens de rotation voulu,
    // mais standard = positif tourne vers la gauche
    rotation = degrees * (PI / 180.0f);
  }

  // Setter pour le clipping (Reconstruit les CDFs pour ignorer le soleil
  // clippé)
  void set_clipping_threshold(Real t) {
    clipping_threshold = t;
    build_cdf();
  }

  // Trouve la direction du pixel le plus lumineux (Pour le soleil auto)
  std::pair<Vec3, Vec3> find_sun_hotspot() const {
    Real max_lum = -1.0f;
    int best_x = 0;
    int best_y = 0;
    Vec3 best_color(0, 0, 0);

    for (int y = 0; y < height; ++y) {
      for (int x = 0; x < width; ++x) {
        int idx = (y * width + x) * 3;
        Real r = data[idx];
        Real g = data[idx + 1];
        Real b = data[idx + 2];
        Real lum = 0.2126f * r + 0.7152f * g + 0.0722f * b;

        if (lum > max_lum) {
          max_lum = lum;
          best_x = x;
          best_y = y;
          best_color = Vec3(r, g, b);
        }
      }
    }

    // Conversion (x,y) -> Direction
    Real u = (best_x + 0.5f) / width;
    Real v = (best_y + 0.5f) / height;
    Real theta = v * PI;
    // Calcul de l'angle Phi dans l'espace texture
    Real phi_texture = (u * 2 * PI) - PI;

    // Si l'environnement est tourné de +R, le pixel (u,v) correspond
    // à une direction monde tournée de -R.
    // sample() fait : phi_texture = phi_monde + rotation
    // Donc : phi_monde = phi_texture - rotation
    Real phi_world = phi_texture - rotation;

    Real sin_theta = std::sin(theta);
    Real cos_theta = std::cos(theta);
    Real sin_phi = std::sin(phi_world);
    Real cos_phi = std::cos(phi_world);

    // Y-up convention
    Vec3 dir(sin_theta * cos_phi, cos_theta, -sin_theta * sin_phi);
    return {unit_vector(dir), best_color};
  }

  Real get_luminance(int x, int y) const {
    int idx = (y * width + x) * 3;
    Real r = data[idx];
    Real g = data[idx + 1];
    Real b = data[idx + 2];
    return 0.2126f * r + 0.7152f * g + 0.0722f * b;
  }

  void build_cdf() {
    marginal_CDF.resize(height + 1);
    conditional_CDFs.resize(height, std::vector<Real>(width + 1));

    Real total_integral = 0.0f;

    for (int y = 0; y < height; ++y) {
      Real v = (y + 0.5f) / height;
      Real theta = v * PI;
      Real sin_theta = std::sin(theta);

      Real row_integral = 0.0f;
      conditional_CDFs[y][0] = 0.0f;

      for (int x = 0; x < width; ++x) {
        Real raw_lum = get_luminance(x, y);
        Real clipped_lum = std::min(raw_lum, clipping_threshold);
        Real importance = clipped_lum * sin_theta;
        row_integral += importance;
        conditional_CDFs[y][x + 1] = row_integral;
      }

      if (row_integral > 0) {
        for (int x = 1; x <= width; ++x)
          conditional_CDFs[y][x] /= row_integral;
      } else {
        for (int x = 1; x <= width; ++x)
          conditional_CDFs[y][x] = (Real)x / width;
      }

      total_integral += row_integral;
      marginal_CDF[y + 1] = total_integral;
    }

    if (total_integral > 0) {
      for (int y = 1; y <= height; ++y)
        marginal_CDF[y] /= total_integral;
    } else {
      for (int y = 1; y <= height; ++y)
        marginal_CDF[y] = (Real)y / height;
    }
  }

  // Importance Sampling : Choisit une direction brillante
  Vec3 sample_direction(Real &pdf) const {
    // L'Importance Sampling ne change pas vraiment avec la rotation
    // car on sample la texture (u,v) puis on convertit en direction.
    // Si on veut être puriste, il faudrait tourner le vecteur résultant.
    // MAIS pour l'instant, sample_direction est utilisé par le Renderer pour
    // choisir où envoyer les rayons. Si on le laisse tel quel, il va sampler
    // selon les points chauds de la texture. Le Renderer convertira ce U,V en
    // vecteur. Il faudra juste s'assurer que le renderer applique la rotation à
    // ce vecteur s'il l'utilise directement.

    // Pour l'instant on laisse tel quel, c'est une approximation acceptable
    // car sample_direction retourne une direction en fonction de la texture
    // brute. Idéalement il faudrait tourner le vecteur résultat :
    Real r1 = random_real();
    auto it_y = std::lower_bound(marginal_CDF.begin(), marginal_CDF.end(), r1);
    int y = std::max(0, (int)(it_y - marginal_CDF.begin()) - 1);

    Real r2 = random_real();
    auto it_x = std::lower_bound(conditional_CDFs[y].begin(),
                                 conditional_CDFs[y].end(), r2);
    int x = std::max(0, (int)(it_x - conditional_CDFs[y].begin()) - 1);

    Real u = (x + random_real()) / width;
    Real v = (y + random_real()) / height;

    Real theta = v * PI;
    Real phi_texture = (u * 2 * PI) - PI;

    // Conversion Texture Space -> World Space
    Real phi_world = phi_texture - rotation;

    Real sin_theta = std::sin(theta);
    Real cos_theta = std::cos(theta);
    Real sin_phi = std::sin(phi_world);
    Real cos_phi = std::cos(phi_world);

    Vec3 dir(sin_theta * cos_phi, cos_theta, -sin_theta * sin_phi);

    // Estimation PDF simple
    Real pixel_lum = get_luminance(x, y);
    Real pdf_uv = (pixel_lum * sin_theta);

    // Approximatif mais suffisant pour le NEE
    if (sin_theta == 0)
      pdf = 0;
    else {
      Real safe_sin = std::max(sin_theta, 1e-5f);
      // Note: La formule exacte est complexe sans l'intégrale totale stockée,
      // mais l'idée est que la PDF est proportionnelle à la brillance.
      Real prob_y = marginal_CDF[y + 1] - marginal_CDF[y];
      Real prob_x_given_y = conditional_CDFs[y][x + 1] - conditional_CDFs[y][x];
      Real prob_pixel = prob_y * prob_x_given_y;

      pdf = prob_pixel * (width * height) / (2 * PI * PI * safe_sin);
    }

    return unit_vector(dir);
  }

  Vec3 sample(const Vec3 &dir, int mode) const {
    if (dir.length_squared() < 1e-6f)
      return Vec3(0, 0, 0);

    Real strength = 1.0f;
    if (mode == 0)
      strength = env_visible_scale;
    else if (mode == 1)
      strength = env_direct_scale;
    else if (mode == 2)
      strength = env_indirect_scale;

    if (strength <= 0)
      return Vec3(0, 0, 0);

    auto unit_dir = unit_vector(dir);
    auto theta = std::acos(unit_dir.y());
    auto phi_world = std::atan2(-unit_dir.z(), unit_dir.x()) + PI;

    // Application de la rotation
    // On décale l'angle de lecture pour simuler la rotation de la sphère
    Real phi_texture = phi_world + rotation;

    Real u = phi_texture / (2 * PI);
    Real v = theta / PI;

    Real px = u * width - 0.5f;
    Real py = v * height - 0.5f;
    int x0 = static_cast<int>(std::floor(px));
    int y0 = static_cast<int>(std::floor(py));
    Real fx = px - x0;
    Real fy = py - y0;

    auto get_pixel = [&](int x, int y) {
      x = (x % width + width) % width;
      y = std::max(0, std::min(y, height - 1));
      int idx = (y * width + x) * 3;
      if (idx < 0 || idx + 2 >= data.size())
        return Vec3(0, 0, 0);
      return Vec3(data[idx], data[idx + 1], data[idx + 2]);
    };

    Vec3 c00 = get_pixel(x0, y0);
    Vec3 c10 = get_pixel(x0 + 1, y0);
    Vec3 c01 = get_pixel(x0, y0 + 1);
    Vec3 c11 = get_pixel(x0 + 1, y0 + 1);

    Vec3 c0 = c00 * (1.0f - fx) + c10 * fx;
    Vec3 c1 = c01 * (1.0f - fx) + c11 * fx;

    Vec3 raw_radiance = (c0 * (1.0f - fy) + c1 * fy) * strength;

    // Application du clipping
    // [MODIFICATION] Le clipping ne s'applique PAS au fond visible (Mode 0)
    // pour que l'aspect visuel du ciel reste fidèle.
    // Il s'applique uniquement à l'éclairage (Direct/Indirect) pour réduire le
    // bruit (fireflies).
    if (mode != 0 && clipping_threshold < INFINITY_REAL) {
      Real max_val = clipping_threshold * strength;
      return Vec3(std::min(raw_radiance.x(), max_val),
                  std::min(raw_radiance.y(), max_val),
                  std::min(raw_radiance.z(), max_val));
    }

    return raw_radiance;
  }
};