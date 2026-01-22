#pragma once

// ===============================================================================================
// MODULE: ACCELERATION STRUCTURE (BVH)
// ===============================================================================================
//
// DESCRIPTION:
//   Implements volume hierarchy (BVH) to accelerate ray-scene intersections.
//   Instead of testing a ray against every object (O(N)), we test against a
//   tree of bounding boxes. If a ray misses a node's box, we can skip all its
//   children (O(log N)).
//
// ALGORITHM:
//   - Construction (Top-Down):
//     1. Compute the bounding box of the current set of objects.
//     2. Choose a splitting axis (e.g., the longest dimension of the box).
//     3. Sort objects along this axis.
//     4. Split into two halves (Left/Right) and recurse.
//
//   - Traversal:
//     1. Check intersection with the node's AABB. If miss, return false.
//     2. If hit, recurse into Left child.
//     3. Then recurse into Right child, but OPTIMIZED: pass the hit distance
//     't' from the left
//        child as the new 't_max' for the right child. This culls objects that
//        are further away.
//
// ===============================================================================================

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

    // -------------------------------------------------------------------------------------------
    // ALGORITHM: BVH CONSTRUCTION (Splitting Strategy)
    // -------------------------------------------------------------------------------------------
    // We determine the best axis to split the objects (X, Y, or Z).
    // A simple heuristic is used here: pick the axis where the bounding box is
    // the largest.
    // -------------------------------------------------------------------------------------------

    // 1. Compute total bounding box of the span
    AABB total_box;
    bool first = true;
    for (size_t i = start; i < end; ++i) {
      AABB temp_box;
      if (objects[i]->bounding_box(temp_box)) {
        total_box = first ? temp_box : surrounding_box(total_box, temp_box);
        first = false;
      }
    }

    // 2. Choose splitting axis (Longest Extent)
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

  // ---------------------------------------------------------------------------------------------
  // ALGORITHM: TRAVERSAL
  // ---------------------------------------------------------------------------------------------
  virtual bool hit(const Ray &r, Real t_min, Real t_max,
                   HitRecord &rec) const override {
    // 1. Box Test: If the ray misses the bounding box, we can skip the entire
    // subtree.
    if (!box.hit(r, t_min, t_max))
      return false;

    // 2. Check Children
    // We recursively check the Left child.
    bool hit_left = left->hit(r, t_min, t_max, rec);

    // Then check Right child.
    // OPTIMIZATION: If we hit the left child at distance 'rec.t', we clamp
    // 't_max' for the right child search. We only care about objects CLOSER
    // than the one we just found.
    bool hit_right = right->hit(r, t_min, hit_left ? rec.t : t_max, rec);

    return hit_left || hit_right;
  }

  virtual bool bounding_box(AABB &output_box) const override {
    output_box = box;
    return true;
  }
};