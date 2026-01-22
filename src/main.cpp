#include <nanobind/nanobind.h>

// ===============================================================================================
// MODULE: PYTHON BINDINGS (NANOBIND)
// ===============================================================================================
//
// DESCRIPTION:
//   This file acts as the bridge between the high-performance C++ Core and the
//   Python logic. It exposes the C++ classes and functions to Python as a
//   module named 'cpp_engine'.
//
// KEY ROLES:
//   1. Scene Management (PyScene):
//      - Stores the state of the world (Objects, Lights, Camera).
//      - Manages Assets (Meshes loaded in memory).
//      - Manages Instances (Scene Graph nodes pointing to assets/primitives).
//
//   2. Rendering Entry Points:
//      - render()             : Offline rendering (full quality).
//      - render_preview()     : Fast, low-quality preview (Clay / Normals).
//      - render_accumulate()  : Progressive rendering for interactive viewport.
//
//   3. Data Conversion:
//      - Converts Numpy arrays to C++ pointers and back.
//      - Exposes C++ Vec3 to Python.
//
// ===============================================================================================

#include <nanobind/ndarray.h>
#include <nanobind/stl/map.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/shared_ptr.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/tuple.h>
#include <nanobind/stl/vector.h>

#include <atomic>
#include <iostream>
#include <map>
#include <omp.h>
#include <string>

// --- NOS MODULES ---
#include "bvh.h"
#include "camera.h"
#include "common.h"
#include "environment.h"
#include "geometry.h"
#include "hittable.h"
#include "instance.h"
#include "materials.h"
#include "renderer.h"

namespace nb = nanobind;
using namespace nb::literals;

// ===============================================================================================
// SCENE MANAGER
// ===============================================================================================

class PyScene {
public:
  // Les conteneurs d'objets
  HittableList world;
  HittableList lights;

  // Le BVH (reconstruit dynamiquement)
  std::shared_ptr<Hittable> world_bvh;
  std::shared_ptr<Camera> camera;
  std::shared_ptr<EnvironmentMap> background;

  // Bibliothèque d'Assets (Meshes chargés en mémoire)
  // Nom -> BVH du Mesh
  std::map<std::string, std::shared_ptr<Hittable>> mesh_assets;

  // Gestionnaire d'instances (ID -> Objet)
  std::map<int, std::shared_ptr<Instance>> instances_map;
  int next_instance_id = 0;

  // Progression & Rendu
  std::atomic<int> completed_scanlines{0};
  std::atomic<int> total_scanlines{1};
  std::vector<float> accumulation_buffer;
  int accumulated_spp = 0;
  int acc_width = 0;
  int acc_height = 0;

  PyScene() {
    // Environnement par défaut (Noir)
    std::vector<Real> d = {0, 0, 0};
    background = std::make_shared<EnvironmentMap>(d, 1, 1);
  }

  // ---------------------------------------------------------------------------------------------
  // HELPER: INSTANCE REGISTRATION
  // ---------------------------------------------------------------------------------------------
  // Wraps a geometric object (Sphere, Mesh BVH) into an Instance with a
  // transformation matrix. It assigns a unique ID to keep track of it in Python
  // (for Gizmo selection).
  // ---------------------------------------------------------------------------------------------
  int create_and_register_instance(std::shared_ptr<Hittable> geo,
                                   const Matrix4 &m, const Matrix4 &inv,
                                   bool is_light) {
    int id = next_instance_id++;
    auto instance = std::make_shared<Instance>(geo, m, inv, id);

    world.add(instance);
    instances_map[id] = instance;

    // SPECIAL HANDLING FOR LIGHTS:
    // If an object is emissive, we must ALSO add it to the explicit 'lights'
    // list so that the renderer can sample it directly (NEE).
    if (is_light) {
      lights.add(instance);
    }

    world_bvh = nullptr; // Invalidate BVH to force rebuild on next render
    return id;
  }

  // --- PRIMITIVES (Wrappers Magiques) ---

  // Retourne l'ID (int) pour le suivi Python
  int add_sphere(const Vec3 &center, Real radius, std::string mat_type,
                 const Vec3 &color, Real fuzz = 0, Real ir = 1.5f) {
    auto mat = create_material(mat_type, color, fuzz, ir);

    // 1. On crée une Sphère UNITAIRE (r=1) à l'origine (0,0,0)
    // Elle servira de base géométrique.
    auto unit_sphere = std::make_shared<Sphere>(Vec3(0, 0, 0), 1.0f, mat);

    // 2. On calcule les matrices pour la placer et la dimensionner
    // Transform = Translate(center) * Scale(radius)
    Matrix4 m;
    m.m[0][0] = radius;
    m.m[1][1] = radius;
    m.m[2][2] = radius;
    m.m[0][3] = center.x();
    m.m[1][3] = center.y();
    m.m[2][3] = center.z();

    // Inverse = Scale(1/radius) * Translate(-center)
    Matrix4 inv;
    Real inv_r = 1.0f / radius;
    inv.m[0][0] = inv_r;
    inv.m[1][1] = inv_r;
    inv.m[2][2] = inv_r;
    inv.m[0][3] = -center.x() * inv_r;
    inv.m[1][3] = -center.y() * inv_r;
    inv.m[2][3] = -center.z() * inv_r;

    return create_and_register_instance(unit_sphere, m, inv,
                                        mat_type == "light");
  }

  int add_checker_sphere(const Vec3 &center, Real radius, const Vec3 &c1,
                         const Vec3 &c2, Real scale) {
    auto mat = std::make_shared<LambertianChecker>(c1, c2, scale);
    auto unit_sphere = std::make_shared<Sphere>(Vec3(0, 0, 0), 1.0f, mat);

    // Même logique matricielle
    Matrix4 m;
    m.m[0][0] = radius;
    m.m[1][1] = radius;
    m.m[2][2] = radius;
    m.m[0][3] = center.x();
    m.m[1][3] = center.y();
    m.m[2][3] = center.z();

    Matrix4 inv;
    Real inv_r = 1.0f / radius;
    inv.m[0][0] = inv_r;
    inv.m[1][1] = inv_r;
    inv.m[2][2] = inv_r;
    inv.m[0][3] = -center.x() * inv_r;
    inv.m[1][3] = -center.y() * inv_r;
    inv.m[2][3] = -center.z() * inv_r;

    return create_and_register_instance(unit_sphere, m, inv, false);
  }

  int add_invisible_sphere_light(const Vec3 &center, Real radius,
                                 const Vec3 &color) {
    auto mat = std::make_shared<InvisibleLight>(color);
    auto unit_sphere = std::make_shared<Sphere>(Vec3(0, 0, 0), 1.0f, mat);

    Matrix4 m;
    m.m[0][0] = radius;
    m.m[1][1] = radius;
    m.m[2][2] = radius;
    m.m[0][3] = center.x();
    m.m[1][3] = center.y();
    m.m[2][3] = center.z();

    Matrix4 inv;
    Real inv_r = 1.0f / radius;
    inv.m[0][0] = inv_r;
    inv.m[1][1] = inv_r;
    inv.m[2][2] = inv_r;
    inv.m[0][3] = -center.x() * inv_r;
    inv.m[1][3] = -center.y() * inv_r;
    inv.m[2][3] = -center.z() * inv_r;

    // C'est une lumière (true)
    return create_and_register_instance(unit_sphere, m, inv, true);
  }

  int add_quad(const Vec3 &Q, const Vec3 &u, const Vec3 &v,
               std::string mat_type, const Vec3 &color, Real fuzz = 0,
               Real ir = 1.5f) {
    std::shared_ptr<Material> mat = create_material(mat_type, color, fuzz, ir);
    auto quad = std::make_shared<Quad>(Q, u, v, mat);

    // Pour les Quads arbitraires, on garde la géométrie telle quelle et on met
    // une matrice Identité. L'utilisateur pourra ensuite le bouger via la
    // matrice.
    Matrix4 identity;
    return create_and_register_instance(quad, identity, identity,
                                        mat_type == "light");
  }

  // --- MESHES ---

  void load_mesh_asset(std::string name,
                       nb::ndarray<float, nb::shape<-1, 3>> vertices,
                       nb::ndarray<int, nb::shape<-1, 3>> indices,
                       nb::ndarray<float, nb::shape<-1, 3>> normals,
                       std::string mat_type, const Vec3 &color,
                       Real fuzz = 0.0f, Real ir = 1.5f) {
    HittableList mesh_list;
    std::shared_ptr<Material> mat = create_material(mat_type, color, fuzz, ir);

    auto v_view = vertices.view();
    auto i_view = indices.view();
    auto n_view = normals.view();
    size_t num_triangles = i_view.shape(0);

    for (size_t k = 0; k < num_triangles; ++k) {
      int idx0 = i_view(k, 0);
      int idx1 = i_view(k, 1);
      int idx2 = i_view(k, 2);
      Vec3 v0(v_view(idx0, 0), v_view(idx0, 1), v_view(idx0, 2));
      Vec3 v1(v_view(idx1, 0), v_view(idx1, 1), v_view(idx1, 2));
      Vec3 v2(v_view(idx2, 0), v_view(idx2, 1), v_view(idx2, 2));
      Vec3 n0(n_view(idx0, 0), n_view(idx0, 1), n_view(idx0, 2));
      Vec3 n1(n_view(idx1, 0), n_view(idx1, 1), n_view(idx1, 2));
      Vec3 n2(n_view(idx2, 0), n_view(idx2, 1), n_view(idx2, 2));

      auto tri = std::make_shared<Triangle>(v0, v1, v2, n0, n1, n2, mat);
      mesh_list.add(tri);
    }
    // Création du BLAS (BVH local)
    auto mesh_bvh = std::make_shared<BVHNode>(mesh_list);
    mesh_assets[name] = mesh_bvh;
  }

  int add_instance(std::string mesh_name,
                   nb::ndarray<float, nb::shape<4, 4>> transform_array,
                   nb::ndarray<float, nb::shape<4, 4>> inv_transform_array) {
    if (mesh_assets.find(mesh_name) == mesh_assets.end()) {
      std::cerr << "Error: Mesh asset '" << mesh_name << "' not found!\n";
      return -1;
    }

    auto t_view = transform_array.view();
    auto i_view = inv_transform_array.view();
    Matrix4 m, inv;
    for (int r = 0; r < 4; r++)
      for (int c = 0; c < 4; c++) {
        m.m[r][c] = t_view(r, c);
        inv.m[r][c] = i_view(r, c);
      }

    return create_and_register_instance(mesh_assets[mesh_name], m, inv, false);
  }

  // --- GIZMO TOOLS ---

  void update_instance_transform(
      int id, nb::ndarray<float, nb::shape<4, 4>> transform_array,
      nb::ndarray<float, nb::shape<4, 4>> inv_transform_array) {
    if (instances_map.find(id) == instances_map.end())
      return;

    auto t_view = transform_array.view();
    auto i_view = inv_transform_array.view();
    Matrix4 m, inv;
    for (int r = 0; r < 4; r++)
      for (int c = 0; c < 4; c++) {
        m.m[r][c] = t_view(r, c);
        inv.m[r][c] = i_view(r, c);
      }

    // Mise à jour instantanée
    instances_map[id]->set_transform(m, inv);

    // [CRITIQUE] On détruit le BVH pour forcer sa reconstruction au prochain
    // render C'est ce qui permet le mouvement en temps réel.
    world_bvh = nullptr;

    // On reset l'accumulation pour éviter le ghosting
    reset_accumulation();
  }

  // Picking (Quel objet est sous la souris ?)
  int pick_instance_id(int width, int height, int mouse_x, int mouse_y) {
    if (!camera)
      return -1;
    if (!world_bvh) {
      if (world.owned_objects.empty())
        world_bvh = std::make_shared<HittableList>();
      else
        world_bvh = std::make_shared<BVHNode>(world);
    }

    auto u = (mouse_x + 0.5f) / width;
    auto v = 1.0f - ((mouse_y + 0.5f) / height); // Inversion Y
    Ray r = camera->get_ray(u, v);
    r.is_primary = true;

    HitRecord rec;
    if (world_bvh->hit(r, 0.001f, INFINITY_REAL, rec)) {
      return rec.instance_id;
    }
    return -1; // Rien touché
  }

  // --- MATERIAL EDITING ---

  void update_instance_material(int id, std::string mat_type, const Vec3 &color,
                                Real fuzz = 0.0f, Real ir = 1.5f) {
    // 1. On cherche l'instance
    if (instances_map.find(id) == instances_map.end()) {
      std::cerr << "Warning: Instance ID " << id
                << " not found for material update.\n";
      return;
    }

    // 2. On crée le nouveau matériau
    std::shared_ptr<Material> new_mat =
        create_material(mat_type, color, fuzz, ir);

    // 3. On l'assigne à l'instance (via le mécanisme d'override)
    instances_map[id]->set_material(new_mat);

    // 4. On reset l'accumulation pour voir le changement immédiatement
    reset_accumulation();
  }

  void remove_instance(int id) {
    // 1. Vérifier si l'objet existe
    auto it = instances_map.find(id);
    if (it == instances_map.end()) {
      return; // Objet non trouvé ou déjà supprimé
    }

    std::shared_ptr<Instance> ptr_to_remove = it->second;

    // 2. Supprimer de la liste principale (World)
    // On utilise l'idiome erase-remove sur le vecteur 'owned_objects'
    auto &objs = world.owned_objects;
    objs.erase(std::remove(objs.begin(), objs.end(), ptr_to_remove),
               objs.end());

    // 3. Supprimer de la liste des lumières (Lights) - si applicable
    auto &l_objs = lights.owned_objects;
    l_objs.erase(std::remove(l_objs.begin(), l_objs.end(), ptr_to_remove),
                 l_objs.end());

    // 4. Supprimer de la map de gestion
    instances_map.erase(it);

    // 5. Invalider le BVH pour forcer la reconstruction
    world_bvh = nullptr;

    // 6. Reset du rendu
    reset_accumulation();

    std::cout << "[Engine] Instance " << id << " removed." << std::endl;
  }

  void set_env_rotation(Real degrees) {
    if (background) {
      background->set_rotation(degrees);
      // Important : Reset le rendu progressif car l'image change complètement
      reset_accumulation();
    }
  }

  // --- AJOUT DIRECT (Legacy - Non Editable) ---
  void add_mesh(nb::ndarray<float, nb::shape<-1, 3>> vertices,
                nb::ndarray<int, nb::shape<-1, 3>> indices,
                nb::ndarray<float, nb::shape<-1, 3>> normals,
                std::string mat_type, const Vec3 &color, Real fuzz = 0.0f,
                Real ir = 1.5f) {
    // Ce code crée des triangles bruts, pas des instances.
    // Ils ne seront PAS sélectionnables par le Gizmo (id = -1 par défaut).
    // C'est normal.
    std::shared_ptr<Material> mat = create_material(mat_type, color, fuzz, ir);
    auto v_view = vertices.view();
    auto i_view = indices.view();
    auto n_view = normals.view();
    size_t num_triangles = i_view.shape(0);

    for (size_t k = 0; k < num_triangles; ++k) {
      int idx0 = i_view(k, 0);
      int idx1 = i_view(k, 1);
      int idx2 = i_view(k, 2);
      Vec3 v0(v_view(idx0, 0), v_view(idx0, 1), v_view(idx0, 2));
      Vec3 v1(v_view(idx1, 0), v_view(idx1, 1), v_view(idx1, 2));
      Vec3 v2(v_view(idx2, 0), v_view(idx2, 1), v_view(idx2, 2));
      Vec3 n0(n_view(idx0, 0), n_view(idx0, 1), n_view(idx0, 2));
      Vec3 n1(n_view(idx1, 0), n_view(idx1, 1), n_view(idx1, 2));
      Vec3 n2(n_view(idx2, 0), n_view(idx2, 1), n_view(idx2, 2));
      auto tri = std::make_shared<Triangle>(v0, v1, v2, n0, n1, n2, mat);
      world.add(tri);
      if (mat_type == "light")
        lights.add(tri);
    }
  }

  // --- BOILERPLATE (Camera, Env, Render) ---

  void set_camera(const Vec3 &from, const Vec3 &at, const Vec3 &up, Real vfov,
                  Real aspect, Real ap, Real dist) {
    camera = std::make_shared<Camera>(from, at, up, vfov, aspect, ap, dist);
  }

  void set_environment(nb::object image) {
    PyObject *obj = image.ptr();
    Py_buffer view;
    if (PyObject_GetBuffer(obj, &view,
                           PyBUF_STRIDES | PyBUF_FORMAT | PyBUF_ND) != 0)
      throw std::runtime_error("Numpy array required");
    struct BufferGuard {
      Py_buffer *v;
      ~BufferGuard() { PyBuffer_Release(v); }
    } guard{&view};
    size_t h = view.shape[0];
    size_t w = view.shape[1];
    const char *buf = (const char *)view.buf;
    std::vector<Real> data(w * h * 3);
    for (size_t y = 0; y < h; ++y) {
      for (size_t x = 0; x < w; ++x) {
        for (size_t k = 0; k < 3; ++k) {
          float val = *reinterpret_cast<const float *>(
              buf + y * view.strides[0] + x * view.strides[1] +
              k * view.strides[2]);
          data[(y * w + x) * 3 + k] = static_cast<Real>(val);
        }
      }
    }
    background = std::make_shared<EnvironmentMap>(data, (int)w, (int)h);
  }

  void set_env_levels(Real back, Real dir, Real indir) {
    if (background)
      background->set_scales(back, dir, indir);
  }

  std::pair<Vec3, Vec3> get_env_sun_info() {
    if (background)
      return background->find_sun_hotspot();
    return {Vec3(0, 1, 0), Vec3(0, 0, 0)};
  }

  // --- MOTEUR DE RENDU ---

  // Rendu Final (Offline)
  nb::dict render(int width, int height, int spp, int depth, int n_threads) {
    if (world.owned_objects.empty())
      world_bvh = std::make_shared<HittableList>();
    else
      world_bvh = std::make_shared<BVHNode>(world);

    total_scanlines = height;
    completed_scanlines = 0;
    size_t num_pixels = (size_t)width * height;
    float *beauty = new float[num_pixels * 3];
    float *albedo = new float[num_pixels * 3];
    float *normal = new float[num_pixels * 3];

    try {
      nb::gil_scoped_release release;
      if (n_threads > 0)
        omp_set_num_threads(n_threads);
#pragma omp parallel for schedule(dynamic)
      for (int j = 0; j < height; ++j) {
        for (int i = 0; i < width; ++i) {
          Vec3 acc_c(0, 0, 0), acc_a(0, 0, 0), acc_n(0, 0, 0);
          for (int s = 0; s < spp; ++s) {
            auto u = (i + random_real()) / (width - 1);
            auto v = (j + random_real()) / (height - 1);
            Ray r = camera->get_ray(u, v);
            r.is_primary = true;

            // Appel au Renderer Core
            acc_c +=
                ray_color(r, *world_bvh, lights, background.get(), depth, true);

            // AOV (Premier hit)
            HitRecord rec;
            if (world_bvh->hit(r, 0.001f, INFINITY_REAL, rec)) {
              acc_a += rec.mat_ptr->get_albedo(rec);
              acc_n += 0.5f * (unit_vector(rec.normal) + Vec3(1, 1, 1));
            }
          }
          int idx = ((height - 1 - j) * width + i) * 3;
          beauty[idx + 0] = acc_c.x() / spp;
          beauty[idx + 1] = acc_c.y() / spp;
          beauty[idx + 2] = acc_c.z() / spp;
          albedo[idx + 0] = acc_a.x() / spp;
          albedo[idx + 1] = acc_a.y() / spp;
          albedo[idx + 2] = acc_a.z() / spp;
          normal[idx + 0] = acc_n.x() / spp;
          normal[idx + 1] = acc_n.y() / spp;
          normal[idx + 2] = acc_n.z() / spp;
        }
        completed_scanlines++;
      }
    } catch (...) {
      delete[] beauty;
      delete[] albedo;
      delete[] normal;
      throw;
    }

    nb::capsule ob(beauty, [](void *p) noexcept { delete[] (float *)p; });
    nb::capsule oa(albedo, [](void *p) noexcept { delete[] (float *)p; });
    nb::capsule on(normal, [](void *p) noexcept { delete[] (float *)p; });
    size_t shape[3] = {(size_t)height, (size_t)width, 3ul};
    nb::dict res;
    res["color"] = nb::ndarray<nb::numpy, float>(beauty, 3, shape, ob);
    res["albedo"] = nb::ndarray<nb::numpy, float>(albedo, 3, shape, oa);
    res["normal"] = nb::ndarray<nb::numpy, float>(normal, 3, shape, on);
    return res;
  }

  // Rendu Temps Réel (Preview)
  nb::ndarray<nb::numpy, float> render_preview(int width, int height, int mode,
                                               int n_threads) {
    if (!camera)
      throw std::runtime_error("Camera not set");

    // Auto-build BVH si nécessaire (dirty flag plus tard ?)
    if (!world_bvh) {
      if (world.owned_objects.empty())
        world_bvh = std::make_shared<HittableList>();
      else
        world_bvh = std::make_shared<BVHNode>(world);
    }

    size_t num_pixels = (size_t)width * height;
    float *buffer = new float[num_pixels * 3];

    try {
      nb::gil_scoped_release release;
      if (n_threads > 0)
        omp_set_num_threads(n_threads);

#pragma omp parallel for schedule(dynamic)
      for (int j = 0; j < height; ++j) {
        for (int i = 0; i < width; ++i) {
          auto u = (i + 0.5f) / width;
          auto v = (j + 0.5f) / height;
          Ray r = camera->get_ray(u, v);
          r.is_primary = true;
          HitRecord rec;
          Vec3 col;
          if (world_bvh->hit(r, 0.001f, INFINITY_REAL, rec)) {
            if (mode == 1) { // Clay
              Vec3 light = unit_vector(Vec3(-1, 1, 1));
              float diff = std::max(0.0f, dot(unit_vector(rec.normal), light));
              float val = 0.2f + 0.7f * diff;
              col = Vec3(val, val, val);
            } else { // Normals
              col = 0.5f * (unit_vector(rec.normal) + Vec3(1, 1, 1));
            }
          } else { // Fond
            if (background) {
              Vec3 bg = background->sample(r.dir, 0);
              // col = Vec3(bg.x() / (1 + bg.x()), bg.y() / (1 + bg.y()),
              //            bg.z() / (1 + bg.z())); // Tone map
              col = aces_filmic(bg);
            } else {
              // Fond par défaut (gradient bleu) - On peut aussi le tone-mapper
              // ou le laisser
              Vec3 unit_dir = unit_vector(r.dir);
              auto t = 0.5f * (unit_dir.y() + 1.0f);
              Vec3 raw_sky =
                  (1.0f - t) * Vec3(1, 1, 1) + t * Vec3(0.5, 0.7, 1.0);
              col = aces_filmic(raw_sky);
            }
          }
          int idx = ((height - 1 - j) * width + i) * 3;
          buffer[idx + 0] = col.x();
          buffer[idx + 1] = col.y();
          buffer[idx + 2] = col.z();
        }
      }
    } catch (...) {
      delete[] buffer;
      throw;
    }
    nb::capsule owner(buffer, [](void *p) noexcept { delete[] (float *)p; });
    size_t shape[3] = {(size_t)height, (size_t)width, 3ul};
    return nb::ndarray<nb::numpy, float>(buffer, 3, shape, owner);
  }

  // ---------------------------------------------------------------------------------------------
  // RENDER LOOP: PROGRESSIVE ACCUMULATION
  // ---------------------------------------------------------------------------------------------
  // This function is called repeatedly by the Python UI loop.
  // - It adds 'spp' samples to the existing buffer.
  // - It averages the result (Total Color / Total Samples) and returns it for
  // display.
  // ---------------------------------------------------------------------------------------------
  nb::ndarray<nb::numpy, float> render_accumulate(int width, int height,
                                                  int spp, int n_threads) {
    size_t num_pixels = (size_t)width * height;

    // Resize/Reset buffer if resolution changes
    if (width != acc_width || height != acc_height ||
        accumulation_buffer.size() != num_pixels * 3) {
      accumulation_buffer.assign(num_pixels * 3, 0.0f);
      accumulated_spp = 0;
      acc_width = width;
      acc_height = height;
    }

    // Auto-build BVH
    if (!world_bvh) {
      if (world.owned_objects.empty())
        world_bvh = std::make_shared<HittableList>();
      else
        world_bvh = std::make_shared<BVHNode>(world);
    }

    float *display = new float[num_pixels * 3];

    try {
      nb::gil_scoped_release release;
      if (n_threads > 0)
        omp_set_num_threads(n_threads);

#pragma omp parallel for schedule(dynamic)
      for (int j = 0; j < height; ++j) {
        for (int i = 0; i < width; ++i) {
          Vec3 batch_color(0, 0, 0);

          // BOUCLE DE SAMPLING (Le travail effectif)
          // On lance 'spp' rayons pour ce pixel dans ce thread
          for (int s = 0; s < spp; ++s) {
            auto u = (i + random_real()) / (width - 1);
            auto v = (j + random_real()) / (height - 1);
            Ray r = camera->get_ray(u, v);
            r.is_primary = true;
            // Depth fixe à 6 pour la preview (ou paramétrable si besoin)
            batch_color +=
                ray_color(r, *world_bvh, lights, background.get(), 6, true);
          }

          int idx = ((height - 1 - j) * width + i) * 3;

          // Accumulation dans le buffer permanent
          accumulation_buffer[idx + 0] += batch_color.x();
          accumulation_buffer[idx + 1] += batch_color.y();
          accumulation_buffer[idx + 2] += batch_color.z();

          // Moyenne pour l'affichage (Total Accumulé / Nombre Total de Passes)
          float count = (float)(accumulated_spp + spp);
          display[idx + 0] = accumulation_buffer[idx + 0] / count;
          display[idx + 1] = accumulation_buffer[idx + 1] / count;
          display[idx + 2] = accumulation_buffer[idx + 2] / count;
        }
      }
    } catch (...) {
      delete[] display;
      throw;
    }

    // Mise à jour du compteur global
    accumulated_spp += spp;

    nb::capsule owner(display, [](void *p) noexcept { delete[] (float *)p; });
    size_t shape[3] = {(size_t)height, (size_t)width, 3ul};
    return nb::ndarray<nb::numpy, float>(display, 3, shape, owner);
  }

  void reset_accumulation() {
    std::fill(accumulation_buffer.begin(), accumulation_buffer.end(), 0.0f);
    accumulated_spp = 0;
  }

  float get_progress() const {
    int t = total_scanlines.load();
    return t == 0 ? 0.0f : (float)completed_scanlines.load() / t;
  }

  // Outil: Picking (Focus)
  std::tuple<float, float, float, float>
  pick_focus_distance(int width, int height, int mouse_x, int mouse_y) {
    if (!camera)
      return {-1.0f, 0.0f, 0.0f, 0.0f};
    if (!world_bvh) {
      if (world.owned_objects.empty())
        world_bvh = std::make_shared<HittableList>();
      else
        world_bvh = std::make_shared<BVHNode>(world);
    }

    auto u = (mouse_x + 0.5f) / width;
    auto v = 1.0f - ((mouse_y + 0.5f) / height); // Flip Y
    Ray r = camera->get_ray(u, v);
    r.is_primary = true;

    HitRecord rec;
    if (world_bvh->hit(r, 0.001f, INFINITY_REAL, rec)) {
      float dist = (rec.p - r.orig).length();
      return {dist, (float)rec.p.x(), (float)rec.p.y(), (float)rec.p.z()};
    }
    return {-1.0f, 0.0f, 0.0f, 0.0f};
  }

private:
  // Helper pour créer les matériaux proprement
  std::shared_ptr<Material> create_material(const std::string &type,
                                            const Vec3 &col, Real fuzz,
                                            Real ir) {
    if (type == "lambertian")
      return std::make_shared<Lambertian>(col);
    if (type == "metal")
      return std::make_shared<Metal>(col, fuzz);
    if (type == "dielectric")
      return std::make_shared<Dielectric>(ir, col, fuzz);
    if (type == "plastic")
      return std::make_shared<Plastic>(col, ir, fuzz);
    if (type == "light")
      return std::make_shared<DiffuseLight>(col);
    if (type == "invisible_light")
      return std::make_shared<InvisibleLight>(col);
    return std::make_shared<Lambertian>(Vec3(0.5, 0.5, 0.5));
  }
};

// ===============================================================================================
// BINDINGS PYTHON (Nanobind)
// ===============================================================================================

NB_MODULE(cpp_engine, m) {
  nb::class_<PyScene>(m, "Engine")
      .def(nb::init<>())
      .def("add_sphere", &PyScene::add_sphere, nb::arg("center"),
           nb::arg("radius"), nb::arg("mat_type"), nb::arg("color"),
           nb::arg("fuzz") = 0.0f, nb::arg("ir") = 1.5f)
      .def("add_invisible_sphere_light", &PyScene::add_invisible_sphere_light)
      .def("add_checker_sphere", &PyScene::add_checker_sphere)
      .def("add_quad", &PyScene::add_quad)
      .def("add_mesh", &PyScene::add_mesh, "Ajout direct de triangles",
           nb::arg("vertices"), nb::arg("indices"), nb::arg("normals"),
           nb::arg("mat_type"), nb::arg("color"), nb::arg("fuzz") = 0.0f,
           nb::arg("ir") = 1.5f)
      .def("load_mesh_asset", &PyScene::load_mesh_asset, nb::arg("name"),
           nb::arg("vertices"), nb::arg("indices"), nb::arg("normals"),
           nb::arg("mat_type"), nb::arg("color"), nb::arg("fuzz") = 0.0f,
           nb::arg("ir") = 1.5f)
      .def("add_instance", &PyScene::add_instance, nb::arg("mesh_name"),
           nb::arg("transform"), nb::arg("inv_transform"))
      .def("update_instance_transform", &PyScene::update_instance_transform)
      .def("pick_instance_id", &PyScene::pick_instance_id)
      .def("update_instance_material", &PyScene::update_instance_material,
           nb::arg("id"), nb::arg("mat_type"), nb::arg("color"),
           nb::arg("fuzz") = 0.0f, nb::arg("ir") = 1.5f)
      .def("remove_instance", &PyScene::remove_instance, nb::arg("id"))
      .def("set_camera", &PyScene::set_camera)
      .def("set_environment", &PyScene::set_environment)
      .def("set_env_levels", &PyScene::set_env_levels, nb::arg("back"),
           nb::arg("dir"), nb::arg("indir") = 1.0f)
      .def("set_env_rotation", &PyScene::set_env_rotation, nb::arg("degrees"))
      .def("get_progress", &PyScene::get_progress)
      .def("render", &PyScene::render, nb::arg("width"), nb::arg("height"),
           nb::arg("spp"), nb::arg("depth"), nb::arg("n_threads") = 0)
      .def("render_preview", &PyScene::render_preview, nb::arg("width"),
           nb::arg("height"), nb::arg("mode") = 0, nb::arg("n_threads") = 0)
      .def("render_accumulate", &PyScene::render_accumulate, nb::arg("width"),
           nb::arg("height"), nb::arg("spp") = 1, nb::arg("n_threads") = 0)
      .def("reset_accumulation", &PyScene::reset_accumulation)
      .def("get_env_sun_info", &PyScene::get_env_sun_info)
      .def("pick_focus_distance", &PyScene::pick_focus_distance);

  nb::class_<Vec3>(m, "Vec3")
      .def(nb::init<Real, Real, Real>())
      .def("x", &Vec3::x)
      .def("y", &Vec3::y)
      .def("z", &Vec3::z);
}