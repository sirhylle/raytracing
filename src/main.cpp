#include <nanobind/nanobind.h>

// ===============================================================================================
// MODULE: PYTHON BINDINGS (NANOBIND) - GGX PBR CHECKED
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

Real EPSILON = 0.001f;
Real FIREFLY_CLAMP_LIMIT = 100.0f;

namespace nb = nanobind;
using namespace nb::literals;

// ===============================================================================================
// SCENE MANAGER
// ===============================================================================================

class PyScene {
public:
  HittableList world;
  HittableList lights;
  std::shared_ptr<Hittable> world_bvh;
  std::shared_ptr<Camera> camera;
  std::shared_ptr<EnvironmentMap> background;
  std::map<std::string, std::shared_ptr<Hittable>> mesh_assets;
  std::map<int, std::shared_ptr<Instance>> instances_map;
  int next_instance_id = 0;

  std::atomic<int> completed_scanlines{0};
  std::atomic<int> total_scanlines{1};
  std::vector<float> accumulation_buffer;
  int accumulated_spp = 0;
  int acc_width = 0;
  int acc_height = 0;

  PyScene() {
    std::vector<Real> d = {0, 0, 0};
    background = std::make_shared<EnvironmentMap>(d, 1, 1);
  }

  int create_and_register_instance(std::shared_ptr<Hittable> geo,
                                   const Matrix4 &m, const Matrix4 &inv,
                                   bool is_light) {
    int id = next_instance_id++;
    auto instance = std::make_shared<Instance>(geo, m, inv, id);
    world.add(instance);
    instances_map[id] = instance;
    if (is_light)
      lights.add(instance);
    world_bvh = nullptr;
    return id;
  }

  // --- PRIMITIVES (PBR UPDATED) ---

  // NOTE: On ajoute 'metallic' et 'transmission' aux arguments
  int add_sphere(const Vec3 &center, Real radius, std::string mat_type,
                 const Vec3 &color, Real roughness = 0.5f, Real metallic = 0.0f,
                 Real ir = 1.5f, Real transmission = 0.0f) {
    auto mat =
        create_material(mat_type, color, roughness, metallic, ir, transmission);
    auto unit_sphere = std::make_shared<Sphere>(Vec3(0, 0, 0), 1.0f, mat);

    Matrix4 m;
    m.m[0][0] = radius;
    m.m[1][1] = radius;
    m.m[2][2] = radius;
    m.m[0][3] = center.x();
    m.m[1][3] = center.y();
    m.m[2][3] = center.z(); // Translate

    Matrix4 inv;
    Real inv_r = 1.0f / radius;
    inv.m[0][0] = inv_r;
    inv.m[1][1] = inv_r;
    inv.m[2][2] = inv_r;
    inv.m[0][3] = -center.x() * inv_r;
    inv.m[1][3] = -center.y() * inv_r;
    inv.m[2][3] = -center.z() * inv_r;

    bool is_light = (mat_type == "light" || mat_type == "invisible_light");
    return create_and_register_instance(unit_sphere, m, inv, is_light);
  }

  int add_checker_sphere(const Vec3 &center, Real radius, const Vec3 &c1,
                         const Vec3 &c2, Real scale) {
    auto mat = std::make_shared<LambertianChecker>(c1, c2, scale);
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
    return create_and_register_instance(unit_sphere, m, inv, true);
  }

  int add_quad(const Vec3 &Q, const Vec3 &u, const Vec3 &v,
               std::string mat_type, const Vec3 &color, Real roughness = 0.5f,
               Real metallic = 0.0f, Real ir = 1.5f, Real transmission = 0.0f) {
    std::shared_ptr<Material> mat =
        create_material(mat_type, color, roughness, metallic, ir, transmission);
    auto quad = std::make_shared<Quad>(Q, u, v, mat);
    Matrix4 identity;
    bool is_light = (mat_type == "light");
    return create_and_register_instance(quad, identity, identity, is_light);
  }

  void load_mesh_asset(std::string name,
                       nb::ndarray<float, nb::shape<-1, 3>> vertices,
                       nb::ndarray<int, nb::shape<-1, 3>> indices,
                       nb::ndarray<float, nb::shape<-1, 3>> normals,
                       std::string mat_type, const Vec3 &color,
                       Real roughness = 0.5f, Real metallic = 0.0f,
                       Real ir = 1.5f, Real transmission = 0.0f) {
    HittableList mesh_list;
    std::shared_ptr<Material> mat =
        create_material(mat_type, color, roughness, metallic, ir, transmission);

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
    instances_map[id]->set_transform(m, inv);
    world_bvh = nullptr;
    reset_accumulation();
  }

  // Picking
  int pick_instance_id(int width, int height, int mouse_x, int mouse_y) {
    if (!camera)
      return -1;
    if (!world_bvh)
      world_bvh = std::make_shared<BVHNode>(world);
    auto u = (mouse_x + 0.5f) / width;
    auto v = 1.0f - ((mouse_y + 0.5f) / height);
    Ray r = camera->get_ray(u, v);
    r.is_primary = true;
    HitRecord rec;
    if (world_bvh->hit(r, 0.001f, INFINITY_REAL, rec))
      return rec.instance_id;
    return -1;
  }

  void update_instance_material(int id, std::string mat_type, const Vec3 &color,
                                Real roughness = 0.5f, Real metallic = 0.0f,
                                Real ir = 1.5f, Real transmission = 0.0f) {
    if (instances_map.find(id) == instances_map.end())
      return;
    std::shared_ptr<Material> new_mat =
        create_material(mat_type, color, roughness, metallic, ir, transmission);
    instances_map[id]->set_material(new_mat);
    reset_accumulation();
  }

  void remove_instance(int id) {
    auto it = instances_map.find(id);
    if (it == instances_map.end())
      return;

    std::shared_ptr<Instance> ptr_to_remove = it->second;

    // Remove from World
    auto &objs = world.owned_objects;
    objs.erase(std::remove(objs.begin(), objs.end(), ptr_to_remove),
               objs.end());

    // Remove from Lights
    auto &l_objs = lights.owned_objects;
    l_objs.erase(std::remove(l_objs.begin(), l_objs.end(), ptr_to_remove),
                 l_objs.end());

    // Update Raw Objects (CRITICAL: HittableList::hit uses raw_objects!)
    world.raw_objects.clear();
    for (auto &o : world.owned_objects)
      world.raw_objects.push_back(o.get());

    lights.raw_objects.clear();
    for (auto &o : lights.owned_objects)
      lights.raw_objects.push_back(o.get());

    instances_map.erase(it);
    world_bvh = nullptr;
    reset_accumulation();
  }

  void set_env_rotation(Real degrees) {
    if (background) {
      background->set_rotation(degrees);
      reset_accumulation();
    }
  }

  // --- BOILERPLATE ---
  void set_camera(const Vec3 &from, const Vec3 &at, const Vec3 &up, Real vfov,
                  Real aspect, Real ap, Real dist) {
    camera = std::make_shared<Camera>(from, at, up, vfov, aspect, ap, dist);
  }

  void set_environment(nb::object image,
                       Real clipping_threshold = INFINITY_REAL) {
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
    for (size_t y = 0; y < h; ++y)
      for (size_t x = 0; x < w; ++x)
        for (size_t k = 0; k < 3; ++k) {
          float val = *reinterpret_cast<const float *>(
              buf + y * view.strides[0] + x * view.strides[1] +
              k * view.strides[2]);
          data[(y * w + x) * 3 + k] = static_cast<Real>(val);
        }
    background = std::make_shared<EnvironmentMap>(data, (int)w, (int)h,
                                                  clipping_threshold);
  }

  void set_env_levels(Real exposure, Real back, Real diffuse, Real specular) {
    if (background)
      background->set_scales(exposure, back, diffuse, specular);
  }

  // ...

  std::pair<Vec3, Vec3> get_env_sun_info() {
    if (background)
      return background->find_sun_hotspot();
    return {Vec3(0, 1, 0), Vec3(0, 0, 0)};
  }

  void set_env_clipping_threshold(Real t) {
    if (background)
      background->set_clipping_threshold(t);
  }

  Real get_env_clipping_threshold() const {
    if (background)
      return background->clipping_threshold;
    return INFINITY_REAL;
  }

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
            acc_c +=
                ray_color(r, *world_bvh, lights, background.get(), depth, true);
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

  nb::ndarray<nb::numpy, float> render_preview(int width, int height, int mode,
                                               int n_threads) {
    if (!camera)
      throw std::runtime_error("Camera not set");
    if (!world_bvh)
      world_bvh = std::make_shared<BVHNode>(world);

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
          } else {
            if (background)
              col = aces_filmic(background->sample(r.dir, 0));
            else
              col = Vec3(0, 0, 0);
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

  nb::ndarray<nb::numpy, float> render_accumulate(int width, int height,
                                                  int spp, int n_threads) {
    size_t num_pixels = (size_t)width * height;
    if (width != acc_width || height != acc_height ||
        accumulation_buffer.size() != num_pixels * 3) {
      accumulation_buffer.assign(num_pixels * 3, 0.0f);
      accumulated_spp = 0;
      acc_width = width;
      acc_height = height;
    }
    if (!world_bvh)
      world_bvh = std::make_shared<BVHNode>(world);

    float *display = new float[num_pixels * 3];
    try {
      nb::gil_scoped_release release;
      if (n_threads > 0)
        omp_set_num_threads(n_threads);
#pragma omp parallel for schedule(dynamic)
      for (int j = 0; j < height; ++j) {
        for (int i = 0; i < width; ++i) {
          Vec3 batch_color(0, 0, 0);
          for (int s = 0; s < spp; ++s) {
            auto u = (i + random_real()) / (width - 1);
            auto v = (j + random_real()) / (height - 1);
            Ray r = camera->get_ray(u, v);
            r.is_primary = true;
            batch_color +=
                ray_color(r, *world_bvh, lights, background.get(), 6, true);
          }
          int idx = ((height - 1 - j) * width + i) * 3;
          accumulation_buffer[idx + 0] += batch_color.x();
          accumulation_buffer[idx + 1] += batch_color.y();
          accumulation_buffer[idx + 2] += batch_color.z();

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

  std::tuple<float, float, float, float>
  pick_focus_distance(int width, int height, int mouse_x, int mouse_y) {
    if (!camera)
      return {-1.0f, 0.0f, 0.0f, 0.0f};
    if (!world_bvh)
      world_bvh = std::make_shared<BVHNode>(world);
    auto u = (mouse_x + 0.5f) / width;
    auto v = 1.0f - ((mouse_y + 0.5f) / height);
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
  std::shared_ptr<Material> create_material(const std::string &type,
                                            const Vec3 &col, Real roughness,
                                            Real metallic, Real ir,
                                            Real transmission) {
    if (type == "light")
      return std::make_shared<DiffuseLight>(col);
    if (type == "invisible_light")
      return std::make_shared<InvisibleLight>(col);

    // UNIFIED PBR:
    // We strictly respect the passed parameters.
    // Legacy types ("metal", "dielectric") from older files will rely on the
    // Python loader to provide the correct default parameters for those types.
    return std::make_shared<GgxMaterial>(col, roughness, metallic, ir,
                                         transmission);
  }
};

NB_MODULE(cpp_engine, m) {
  nb::class_<Vec3>(m, "Vec3")
      .def(nb::init<Real, Real, Real>())
      .def("x", &Vec3::x)
      .def("y", &Vec3::y)
      .def("z", &Vec3::z)
      .def("__add__", [](const Vec3 &a, const Vec3 &b) { return a + b; })
      .def("__sub__", [](const Vec3 &a, const Vec3 &b) { return a - b; })
      .def("__mul__", [](const Vec3 &a, Real t) { return a * t; })
      .def("__rmul__", [](const Vec3 &a, Real t) { return a * t; })
      .def("__truediv__", [](const Vec3 &a, Real t) { return a / t; })
      .def("__repr__", [](const Vec3 &a) {
        return "Vec3(" + std::to_string(a.x()) + ", " + std::to_string(a.y()) +
               ", " + std::to_string(a.z()) + ")";
      });

  nb::class_<PyScene>(m, "Engine")
      .def(nb::init<>())
      .def("add_sphere", &PyScene::add_sphere, nb::arg("center"),
           nb::arg("radius"), nb::arg("mat_type"), nb::arg("color"),
           nb::arg("roughness") = 0.5f, nb::arg("metallic") = 0.0f,
           nb::arg("ir") = 1.5f, nb::arg("transmission") = 0.0f)
      .def("add_invisible_sphere_light", &PyScene::add_invisible_sphere_light)
      .def("add_checker_sphere", &PyScene::add_checker_sphere)
      .def("add_quad", &PyScene::add_quad, nb::arg("Q"), nb::arg("u"),
           nb::arg("v"), nb::arg("mat_type"), nb::arg("color"),
           nb::arg("roughness") = 0.5f, nb::arg("metallic") = 0.0f,
           nb::arg("ir") = 1.5f, nb::arg("transmission") = 0.0f)
      .def("load_mesh_asset", &PyScene::load_mesh_asset, nb::arg("name"),
           nb::arg("vertices"), nb::arg("indices"), nb::arg("normals"),
           nb::arg("mat_type"), nb::arg("color"), nb::arg("roughness") = 0.5f,
           nb::arg("metallic") = 0.0f, nb::arg("ir") = 1.5f,
           nb::arg("transmission") = 0.0f)
      .def("add_instance", &PyScene::add_instance, nb::arg("mesh_name"),
           nb::arg("transform"), nb::arg("inv_transform"))
      .def("update_instance_transform", &PyScene::update_instance_transform)
      .def("pick_instance_id", &PyScene::pick_instance_id)
      .def(
          "update_instance_material",
          [](PyScene &self, int id, const std::string &type, const Vec3 &color,
             Real roughness, Real metallic, Real ir, Real transmission) {
            // DIRECT UPDATE: We bypass create_material() overrides to respect
            // UI sliders. If user selects "GLASS" but drags Metal to 1.0, they
            // get Metal Glass.

            // Handle special types
            std::shared_ptr<Material> new_mat;
            if (type == "light")
              new_mat = std::make_shared<DiffuseLight>(color);
            else if (type == "invisible_light")
              new_mat = std::make_shared<InvisibleLight>(color);
            else {
              // All standard types (lambertian, metal, dielectric, standard)
              // use explicit params
              new_mat = std::make_shared<GgxMaterial>(
                  color, roughness, metallic, ir, transmission);
            }

            self.instances_map[id]->set_material(new_mat);
            self.reset_accumulation();
          },
          nb::arg("id"), nb::arg("mat_type"), nb::arg("color"),
          nb::arg("roughness") = 0.5f, nb::arg("metallic") = 0.0f,
          nb::arg("ir") = 1.5f, nb::arg("transmission") = 0.0f)
      .def("remove_instance", &PyScene::remove_instance, nb::arg("id"))
      .def("set_camera", &PyScene::set_camera)
      .def("set_environment", &PyScene::set_environment, nb::arg("image"),
           nb::arg("clipping_threshold") = INFINITY_REAL)
      .def("set_env_levels", &PyScene::set_env_levels, nb::arg("exposure"),
           nb::arg("back"), nb::arg("diffuse"), nb::arg("specular") = 1.0f)
      .def("set_env_rotation", &PyScene::set_env_rotation, nb::arg("degrees"))
      .def("get_progress", &PyScene::get_progress)
      .def("render", &PyScene::render, nb::arg("width"), nb::arg("height"),
           nb::arg("spp"), nb::arg("depth"), nb::arg("n_threads") = 0)
      .def("render_preview", &PyScene::render_preview)
      .def("render_accumulate", &PyScene::render_accumulate)
      .def("reset_accumulation", &PyScene::reset_accumulation)
      .def("pick_focus_distance", &PyScene::pick_focus_distance)
      .def("get_env_clipping_threshold", &PyScene::get_env_clipping_threshold)
      .def("set_env_clipping_threshold", &PyScene::set_env_clipping_threshold)
      .def("get_env_sun_info", &PyScene::get_env_sun_info);

  m.def("get_epsilon", []() { return EPSILON; });
  m.def("set_epsilon", [](Real val) { EPSILON = val; });
  m.def("get_firefly_clamp", []() { return FIREFLY_CLAMP_LIMIT; });
  m.def("set_firefly_clamp", [](Real val) { FIREFLY_CLAMP_LIMIT = val; });
}