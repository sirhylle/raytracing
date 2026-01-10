#pragma once

#include "common.h"
#include "geometry.h" // Nécessaire car BVHNode prend une HittableList en entrée
#include "hittable.h"

#include <algorithm>
#include <iostream>
#include <memory>
#include <vector>

class BVHNode : public Hittable {
public:
  std::shared_ptr<Hittable> left;
  std::shared_ptr<Hittable> right;
  AABB box;

  // 1. Constructeur Public (Point d'entrée facile)
  // On passe une HittableList. Le constructeur va copier le vecteur d'objets
  // pour pouvoir le trier.
  BVHNode(const HittableList &list) {
    // On fait LA copie ici, une seule fois
    auto objects = list.owned_objects;
    // On appelle une méthode privée qui travaille sur cette copie
    build(objects, 0, objects.size());
  }

  // 2. Constructeur privé pour la récursion (ou méthode 'build')
  // Note : J'utilise ici une surcharge de constructeur ou une méthode init
  BVHNode(std::vector<std::shared_ptr<Hittable>> &objects, size_t start,
          size_t end) {
    build(objects, start, end);
  }

private:
  // Constructeur Récursif (Le moteur de construction)
  // Il prend une référence vers un vecteur de pointeurs, et deux indices
  // (début, fin).
  void build(std::vector<std::shared_ptr<Hittable>> &objects, size_t start,
             size_t end) {

    // -- Choix de l'axe de découpe --
    // On calcule la boite englobante de TOUS les objets de cette section
    // pour voir quel axe est le plus étiré (X, Y ou Z).
    // C'est une heuristique simple mais efficace (SAH serait mieux mais plus
    // complexe).

    AABB total_box;
    bool first = true;
    for (size_t i = start; i < end; ++i) {
      AABB temp_box;
      if (objects[i]->bounding_box(temp_box)) {
        total_box = first ? temp_box : surrounding_box(total_box, temp_box);
        first = false;
      }
    }

    Vec3 extent = total_box.max - total_box.min;
    int axis = 0; // Par défaut X
    if (extent.y() > extent.x() && extent.y() > extent.z())
      axis = 1; // Y est le plus long
    else if (extent.z() > extent.x() && extent.z() > extent.y())
      axis = 2; // Z est le plus long

    // Comparateur : Trie les objets selon leur position min sur l'axe choisi
    auto comparator = [axis](const std::shared_ptr<Hittable> &a,
                             const std::shared_ptr<Hittable> &b) {
      AABB box_a, box_b;
      if (!a->bounding_box(box_a) || !b->bounding_box(box_b))
        return false;
      return box_a.min[axis] < box_b.min[axis];
    };

    size_t object_span = end - start;

    if (object_span == 1) {
      // Fin de la récursion : un seul objet -> gauche et droite pointent dessus
      left = right = objects[start];
    } else if (object_span == 2) {
      // Deux objets : on les trie et on assigne
      if (comparator(objects[start], objects[start + 1])) {
        left = objects[start];
        right = objects[start + 1];
      } else {
        left = objects[start + 1];
        right = objects[start];
      }
    } else {
      // Cas général : On trie et on coupe au milieu
      std::sort(objects.begin() + start, objects.begin() + end, comparator);

      size_t mid = start + object_span / 2;

      // Appels récursifs
      left = std::make_shared<BVHNode>(objects, start, mid);
      right = std::make_shared<BVHNode>(objects, mid, end);
    }

    // On calcule la boite englobante finale de ce nœud (union des enfants)
    AABB box_left, box_right;
    if (!left->bounding_box(box_left) || !right->bounding_box(box_right))
      std::cerr << "Erreur: Création BVH avec un objet sans BBox.\n";

    box = surrounding_box(box_left, box_right);
  }

  // TRAVERSÉE (L'étape critique pour la performance)
  virtual bool hit(const Ray &r, Real t_min, Real t_max,
                   HitRecord &rec) const override {
    // 1. Test rapide AABB : Si on rate la boite, on rate tout ce qu'il y a
    // dedans.
    if (!box.hit(r, t_min, t_max))
      return false;

    // 2. Si on touche la boite, on doit vérifier les enfants.
    // On teste le gauche.
    bool hit_left = left->hit(r, t_min, t_max, rec);

    // On teste le droit.
    // Optimisation : Si on a touché à gauche à une distance T, on ne cherche à
    // droite QUE ce qui est plus proche que T (hit_left ? rec.t : t_max).
    bool hit_right = right->hit(r, t_min, hit_left ? rec.t : t_max, rec);

    return hit_left || hit_right;
  }

  virtual bool bounding_box(AABB &output_box) const override {
    output_box = box;
    return true;
  }
};