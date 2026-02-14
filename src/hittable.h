#pragma once

#include "common.h"
#include "sampler.h"

// ===============================================================================================
// FORWARD DECLARATION
// ===============================================================================================
// Forward declaration to allow 'Material*' usage in HitRecord
// without checking circular includes.
class Material;

// ===============================================================================================
// HIT RECORD (Structure containing intersection details)
// ===============================================================================================

struct HitRecord {
  Vec3 p;            // Point d'impact précis (x,y,z)
  Vec3 normal;       // La normale de la surface à ce point
  Material *mat_ptr; // Pointeur vers le matériau de l'objet touché
  Real t;            // La distance depuis l'origine du rayon (ray.at(t))
  Real u;            // Coordonnée de texture U (horizontale)
  Real v;            // Coordonnée de texture V (verticale)
  bool front_face;   // True si le rayon tape l'extérieur, False si l'intérieur
  int instance_id = -1; // -1 signifie "pas d'identifiant" ou "décor"

  // Cette fonction garantit que la normale pointe toujours CONTRE le rayon
  // (vers l'extérieur pour la caméra). Essentiel pour le verre.
  inline void set_face_normal(const Ray &r, const Vec3 &outward_normal) {
    front_face = dot(r.dir, outward_normal) < 0;
    normal = front_face ? outward_normal : -outward_normal;
  }
};

// ===============================================================================================
// CLASSE ABSTRAITE HITTABLE
// ===============================================================================================

class Hittable {
public:
  // Est-ce que le rayon touche l'objet entre t_min et t_max ?
  virtual bool hit(const Ray &r, Real t_min, Real t_max,
                   HitRecord &rec) const = 0;

  // Calcule la boite englobante (AABB) pour le BVH
  virtual bool bounding_box(AABB &output_box) const = 0;

  // --- Pour l'Importance Sampling (PDF) ---
  // Quelle est la probabilité que le rayon touche cet objet ?
  virtual Real pdf_value(const Vec3 &o, const Vec3 &v) const { return 0.0f; }

  // Génère une direction aléatoire vers cet objet (pour viser les lumières)
  virtual Vec3 random(const Vec3 &o, Sampler &sampler) const {
    return Vec3(1, 0, 0);
  }

  virtual ~Hittable() = default;
};