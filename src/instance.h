#pragma once

#include "common.h"
#include "hittable.h"
#include "materials.h"

// ===============================================================================================
// INSTANCE (L'Objet placé dans le monde)
// ===============================================================================================
// C'est le lien entre une géométrie (Mesh/Sphère) et une position (Matrice).
// C'est la seule chose qu'on manipule dans l'éditeur.

class Instance : public Hittable {
public:
  std::shared_ptr<Hittable> object; // L'objet original (ex: le lapin)

  // Matériau de remplacement (ex: Lapin Rouge au lieu de Blanc)
  std::shared_ptr<Material> override_material = nullptr;

  // Identifiant unique pour le "Picking" (Sélection à la souris)
  int id;

  // Matrices de transformation
  Matrix4 transform;     // Local -> Monde (Pour positionner le point d'impact)
  Matrix4 inv_transform; // Monde -> Local (Pour transformer le rayon entrant)
  Matrix4 normal_matrix; // Inverse Transpose (Pour orienter les normales
                         // correctement)

  // Constructeur
  // On demande à l'appelant de fournir l'inverse, car c'est pénible à calculer
  // en C++ pur (Python/Numpy le fera très bien pour nous).
  Instance(std::shared_ptr<Hittable> obj, const Matrix4 &m,
           const Matrix4 &inv_m, int _id = -1)
      : object(obj), transform(m), inv_transform(inv_m), id(_id) {
    update_normal_matrix();
  }

  // Méthode pour déplacer l'objet en temps réel
  void set_transform(const Matrix4 &m, const Matrix4 &inv_m) {
    transform = m;
    inv_transform = inv_m;
    update_normal_matrix();
  }

  // Méthode pour remplacer le matériau de l'objet
  void set_material(std::shared_ptr<Material> mat) { override_material = mat; }

  void update_normal_matrix() { normal_matrix = inv_transform.transpose(); }

  // --- INTERSECTION (Le cœur du système) ---
  virtual bool hit(const Ray &r, Real t_min, Real t_max,
                   HitRecord &rec) const override {
    // 1. Transformer le rayon du Monde vers l'Espace Local de l'objet
    Vec3 o_local = inv_transform.point(r.orig);
    Vec3 d_local = inv_transform.vector(r.dir);

    // Note : Si on a un scale, la longueur de d_local change.
    // Cela affecte 't', mais pour un hit booléen c'est acceptable.
    // Pour être rigoureux, il faudrait normaliser d_local et ajuster t_max,
    // mais cela complique le code pour un gain marginal ici.
    Ray r_local(o_local, d_local, r.tm);

    // 2. Intersecter l'objet original (qui est souvent à l'origine 0,0,0)
    if (!object->hit(r_local, t_min, t_max, rec))
      return false;

    // 3. Retransformer le résultat vers le Monde
    // Le point d'impact :
    Vec3 p_world = transform.point(rec.p);

    // La normale :
    // On utilise la matrice normale (Inverse Transpose) pour gérer les scales
    // non-uniformes
    Vec3 n_world = normal_matrix.vector(rec.normal);
    n_world = unit_vector(n_world);

    // On met à jour l'enregistrement
    rec.p = p_world;
    rec.set_face_normal(r, n_world); // Oriente la normale face à la caméra
    rec.instance_id = this->id; // Stocke l'identifiant de l'instance frappée

    // Si l'instance possède un matériau propre, on remplace celui de la
    // géométrie.
    if (override_material) {
      rec.mat_ptr = override_material.get();
    }

    return true;
  }

  virtual bool bounding_box(AABB &output_box) const override {
    // 1. On récupère la boite de l'objet original (non transformé)
    AABB obj_box;
    if (!object->bounding_box(obj_box))
      return false;

    // 2. On transforme les 8 coins de la boite par la matrice
    Vec3 min(INFINITY_REAL, INFINITY_REAL, INFINITY_REAL);
    Vec3 max = -min;

    Vec3 corners[8];
    corners[0] = Vec3(obj_box.min.x(), obj_box.min.y(), obj_box.min.z());
    corners[1] = Vec3(obj_box.max.x(), obj_box.min.y(), obj_box.min.z());
    corners[2] = Vec3(obj_box.min.x(), obj_box.max.y(), obj_box.min.z());
    corners[3] = Vec3(obj_box.max.x(), obj_box.max.y(), obj_box.min.z());
    corners[4] = Vec3(obj_box.min.x(), obj_box.min.y(), obj_box.max.z());
    corners[5] = Vec3(obj_box.max.x(), obj_box.min.y(), obj_box.max.z());
    corners[6] = Vec3(obj_box.min.x(), obj_box.max.y(), obj_box.max.z());
    corners[7] = Vec3(obj_box.max.x(), obj_box.max.y(), obj_box.max.z());

    for (int i = 0; i < 8; i++) {
      Vec3 p_new = transform.point(corners[i]);
      min.e[0] = std::fmin(min.e[0], p_new.x());
      min.e[1] = std::fmin(min.e[1], p_new.y());
      min.e[2] = std::fmin(min.e[2], p_new.z());

      max.e[0] = std::fmax(max.e[0], p_new.x());
      max.e[1] = std::fmax(max.e[1], p_new.y());
      max.e[2] = std::fmax(max.e[2], p_new.z());
    }

    output_box = AABB(min, max);
    return true;
  }

  // --- GESTION DES LUMIÈRES (NEE) ---
  // Ces méthodes sont appelées quand le moteur cherche une lumière.
  // L'instance doit déléguer à l'objet interne en transformant les points.

  virtual Real pdf_value(const Vec3 &o, const Vec3 &v) const override {
    // On transforme le point d'origine et la direction vers l'espace local
    Vec3 o_loc = inv_transform.point(o);
    Vec3 v_loc = inv_transform.vector(v);

    // Attention : la PDF change avec le scale (densité de probabilité par
    // aire). C'est complexe mathématiquement d'être exact pour un scale
    // non-uniforme. Pour l'instant, on délègue, ce qui est une approximation
    // acceptable pour le NEE.
    return object->pdf_value(o_loc, v_loc);
  }

  virtual Vec3 random(const Vec3 &o) const override {
    // 1. On se place dans l'espace local
    Vec3 o_loc = inv_transform.point(o);

    // 2. On demande un point cible sur la géométrie unitaire
    Vec3 v_loc = object->random(o_loc);

    // 3. On remet ce vecteur dans le monde (c'est une direction, donc vector())
    // Note: random() renvoie souvent un vecteur direction (point_obj - o).
    // Il faut être prudent ici selon l'implémentation de geometry.h
    // Dans geometry.h, random() renvoie (point_sur_surface - o).

    // Version robuste : recalculer le point monde cible
    // Si v_loc est une direction locale, transform.vector(v_loc) donne la
    // direction monde.
    return unit_vector(transform.vector(v_loc));
  }
};