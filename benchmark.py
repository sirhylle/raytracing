import os
import sys
import time
import json
import shutil
import argparse
import statistics
import multiprocessing
import numpy as np
from PIL import Image

import cpp_engine
import loader
import scenes
from config import EnvironmentSettings

BENCHMARK_DIR = "benchmark"


def setup_engine_scene(scene_name, width, height):
    """Set up the engine and load a scene."""
    engine = cpp_engine.Engine()
    builder = loader.SceneBuilder(engine)
    
    if scene_name in scenes.AVAILABLE_SCENES:
        scene = scenes.AVAILABLE_SCENES[scene_name]
        config_data = scene.setup(builder)
        
        def v3(l): return cpp_engine.Vec3(float(l[0]), float(l[1]), float(l[2]))
        aspect = width / height
        vup = config_data.vup if config_data.vup else [0, 1, 0]
        engine.set_camera(
            v3(config_data.lookfrom), v3(config_data.lookat), v3(vup),
            float(config_data.vfov), float(aspect),
            float(config_data.aperture or 0.0),
            float(config_data.focus_dist or 10.0)
        )
        
        env_source = config_data.environment
        if env_source is not None:
            env_settings = EnvironmentSettings(
                source=env_source,
                exposure=getattr(config_data, 'env_exposure', 1.0),
                background=getattr(config_data, 'env_background', 1.0),
                diffuse=getattr(config_data, 'env_diffuse', 0.5),
                specular=getattr(config_data, 'env_specular', 0.5),
            )
            loader.load_environment(builder, env_settings)
    else:
        # Fallback to a custom benchmark scene if not found
        engine.set_camera(cpp_engine.Vec3(13, 2, 3), cpp_engine.Vec3(0, 0, 0), cpp_engine.Vec3(0, 1, 0), 20.0, width/height, 0.0, 10.0)
        engine.add_checker_sphere(cpp_engine.Vec3(0, -1000, 0), 1000)
        engine.add_sphere(cpp_engine.Vec3(0, 1, 0), 1.0, "glass", cpp_engine.Vec3(1, 1, 1), 0.0, 0.0, 1.5, 1.0)
        engine.add_sphere(cpp_engine.Vec3(-4, 1, 0), 1.0, "metal", cpp_engine.Vec3(0.8, 0.8, 0.9), 0.1, 1.0, 1.5, 0.0)
        engine.add_sphere(cpp_engine.Vec3(4, 1, 0), 1.0, "diffuse", cpp_engine.Vec3(0.8, 0.2, 0.2), 0.8, 0.0, 1.5, 0.0)
        engine.add_sphere(cpp_engine.Vec3(0, 5, 0), 0.5, "light", cpp_engine.Vec3(10, 10, 10), 0.0, 0.0, 1.5, 0.0)

    engine.set_build_method(cpp_engine.SplitMethod.SAH)
    return engine, builder


def micro_benchmark(scene_name, width, height, spp, depth, runs, n_threads):
    """Run a small performance loop."""
    print(f"\n[Micro-Benchmark] Scene: {scene_name} | {width}x{height} | {spp} SPP")
    engine, _ = setup_engine_scene(scene_name, width, height)
    
    # Warmup
    print("  Warmup...")
    engine.render(width, height, 1, depth, n_threads, 1)
    
    times = []
    for i in range(runs):
        t0 = time.perf_counter()
        engine.render(width, height, spp, depth, n_threads, 1)
        t = time.perf_counter() - t0
        times.append(t)
        print(f"  Run {i+1}/{runs}: {t:.3f}s")
        
    avg = statistics.mean(times)
    mrays = (width * height * spp) / avg / 1e6
    print(f"  Average: {avg:.3f}s ({mrays:.2f} Mrays/s)")
    return {"avg_time_s": avg, "mrays_s": mrays, "times": times}


def get_image_array(engine, width, height, n_threads):
    """Get the rendered image as an 8-bit RGB uint8 numpy array."""
    res = engine.render(width, height, 1, 6, n_threads, 1)
    buf = res["color"]
    # We apply gamma correction.
    buf_gamma = np.power(np.clip(buf, 0.0, 1.0), 1.0 / 2.2)
    return (buf_gamma * 255.0).astype(np.uint8)


def create_side_by_side_zoom(img_a_path, img_b_path, out_path, center_x, center_y, zoom=2.0, out_width=3840, out_height=2160, separator_width=4):
    """Create a 16:9 composite side-by-side zoom."""
    if not os.path.exists(img_a_path) or not os.path.exists(img_b_path):
        return False
        
    imgA = Image.open(img_a_path).convert("RGB")
    imgB = Image.open(img_b_path).convert("RGB")
    
    if imgA.size != imgB.size:
        print(f"  [Warning] Resolution mismatch for zoom: {imgA.size} vs {imgB.size}. Skipping.")
        return False
    
    # Target size for each half
    half_width = (out_width - separator_width) // 2
    
    # We want to crop an area from the original image that, when scaled by `zoom`, yields `half_width x out_height`.
    crop_w = int(half_width / zoom)
    crop_h = int(out_height / zoom)
    
    # Calculate crop box (ensure it stays within image bounds)
    left = max(0, min(imgA.width - crop_w, center_x - crop_w // 2))
    top = max(0, min(imgA.height - crop_h, center_y - crop_h // 2))
    right = left + crop_w
    bottom = top + crop_h
    
    cropA = imgA.crop((left, top, right, bottom)).resize((half_width, out_height), Image.Resampling.LANCZOS)
    cropB = imgB.crop((left, top, right, bottom)).resize((half_width, out_height), Image.Resampling.LANCZOS)
    
    # Create composite
    composite = Image.new("RGB", (out_width, out_height), (255, 255, 255))
    composite.paste(cropA, (0, 0))
    composite.paste(cropB, (half_width + separator_width, 0))
    
    composite.save(out_path)
    return True


def create_diff_map(img_a_path, img_b_path, out_path, multiplier=10.0):
    if not os.path.exists(img_a_path) or not os.path.exists(img_b_path):
        return None, None
        
    arrA = np.array(Image.open(img_a_path).convert("RGB")).astype(np.float32)
    arrB = np.array(Image.open(img_b_path).convert("RGB")).astype(np.float32)
    
    if arrA.shape != arrB.shape:
        print(f"  [Warning] Resolution mismatch for diff: {arrA.shape} vs {arrB.shape}. Skipping.")
        return None, None
    
    abs_diff = np.abs(arrA - arrB)
    diff = abs_diff * multiplier
    diff = np.clip(diff, 0, 255).astype(np.uint8)
    
    Image.fromarray(diff).save(out_path)
    
    # Return MSE
    mse = np.mean(abs_diff ** 2)
    
    # Calculate percentage of pixels with a noticeable difference (threshold > 2 out of 255)
    diff_mask = np.any(abs_diff > 2.0, axis=-1)
    diff_percent = np.mean(diff_mask) * 100.0
    
    return mse, diff_percent


def generate_markdown_report(data_cur, data_prec, data_ref):
    lines = []
    lines.append("# Raytracing Benchmark Report\n")
    
    lines.append("## 1. Performance (Micro-Benchmark)\n")
    lines.append("| Metric | Reference | Previous | Current | Diff vs Ref | Diff vs Prev |")
    lines.append("|---|---|---|---|---|---|")
    
    def format_diff(val, base):
        if base is None or base == 0: return "N/A"
        pct = (val - base) / base * 100.0
        sign = "+" if pct > 0 else ""
        return f"{sign}{pct:.2f}%"

    micro_cur = data_cur.get("micro", {})
    micro_prec = data_prec.get("micro", {}) if data_prec else {}
    micro_ref = data_ref.get("micro", {}) if data_ref else {}
    
    lines.append(f"| Average Time (s) | {micro_ref.get('avg_time_s', 'N/A')} | {micro_prec.get('avg_time_s', 'N/A')} | **{micro_cur.get('avg_time_s', 0):.3f}** | {format_diff(micro_cur.get('avg_time_s', 0), micro_ref.get('avg_time_s'))} | {format_diff(micro_cur.get('avg_time_s', 0), micro_prec.get('avg_time_s'))} |")
    lines.append(f"| Mrays / s | {micro_ref.get('mrays_s', 'N/A')} | {micro_prec.get('mrays_s', 'N/A')} | **{micro_cur.get('mrays_s', 0):.2f}** | {format_diff(micro_cur.get('mrays_s', 0), micro_ref.get('mrays_s'))} | {format_diff(micro_cur.get('mrays_s', 0), micro_prec.get('mrays_s'))} |")
    
    lines.append("\n## 2. Quality Rendering (Macro-Benchmark)\n")
    lines.append(f"- **Resolution:** {data_cur.get('macro_width')}x{data_cur.get('macro_height')}")
    
    lines.append("\n### Rendering Performance\n")
    lines.append("| Metric | Reference | Previous | Current | Diff vs Ref | Diff vs Prev |")
    lines.append("|---|---|---|---|---|---|")
    
    macro_time_cur = data_cur.get('macro_time_s', 0)
    macro_time_prec = data_prec.get('macro_time_s') if data_prec else None
    macro_time_ref = data_ref.get('macro_time_s') if data_ref else None
    
    str_time_ref = f"{macro_time_ref:.3f}" if macro_time_ref else "N/A"
    str_time_prec = f"{macro_time_prec:.3f}" if macro_time_prec else "N/A"
    
    lines.append(f"| Render Time (s) | {str_time_ref} | {str_time_prec} | **{macro_time_cur:.3f}** | {format_diff(macro_time_cur, macro_time_ref)} | {format_diff(macro_time_cur, macro_time_prec)} |")
    
    lines.append("\n### Visual Differences\n")
    lines.append("| Comparison | MSE | Diff Pixels (%) |")
    lines.append("|---|---|---|")
    
    diff_ref = data_cur.get("diff_ref", {})
    diff_prec = data_cur.get("diff_prec", {})
    
    lines.append(f"| **Current vs Reference** | {diff_ref.get('mse', 'N/A')} | {diff_ref.get('diff_percent', 'N/A')}% |")
    lines.append(f"| **Current vs Previous** | {diff_prec.get('mse', 'N/A')} | {diff_prec.get('diff_percent', 'N/A')}% |")
    
    lines.append("\n### Images\n")
    lines.append("#### Current Render (RAW)")
    lines.append("![Current Render](image_cur.png)\n")
    
    if os.path.exists(os.path.join(BENCHMARK_DIR, "composite_ref_vs_cur.png")):
        lines.append("#### Zoom: Reference (Left) vs Current (Right)")
        lines.append("![Zoom Ref vs Cur](composite_ref_vs_cur.png)\n")
        lines.append("#### Difference Map (Ref vs Cur)")
        lines.append("![Diff Ref vs Cur](diff_ref_vs_cur.png)\n")
        
    if os.path.exists(os.path.join(BENCHMARK_DIR, "composite_prec_vs_cur.png")):
        lines.append("#### Zoom: Previous (Left) vs Current (Right)")
        lines.append("![Zoom Prec vs Cur](composite_prec_vs_cur.png)\n")
        lines.append("#### Difference Map (Prec vs Cur)")
        lines.append("![Diff Prec vs Cur](diff_prec_vs_cur.png)\n")
        
    with open(os.path.join(BENCHMARK_DIR, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[Report] Generated {BENCHMARK_DIR}/report.md")


def main():
    parser = argparse.ArgumentParser(description="Raytracing Benchmark Suite")
    parser.add_argument("--new-reference", action="store_true", help="Force overwrite of the reference image and data")
    parser.add_argument("--quick", action="store_true", help="Run a faster version of the benchmark (lower res/spp)")
    parser.add_argument("--no-shift", action="store_true", help="Do not shift current results to previous (overwrites cur without modifying prec)")
    args = parser.parse_args()
    
    n_threads = max(1, multiprocessing.cpu_count() - 2)
    print(f"Using {n_threads} threads for rendering.")
    
    os.makedirs(BENCHMARK_DIR, exist_ok=True)
    
    # 0. Shift files
    cur_img = os.path.join(BENCHMARK_DIR, "image_cur.png")
    cur_data = os.path.join(BENCHMARK_DIR, "data_cur.json")
    prec_img = os.path.join(BENCHMARK_DIR, "image_prec.png")
    prec_data = os.path.join(BENCHMARK_DIR, "data_prec.json")
    ref_img = os.path.join(BENCHMARK_DIR, "image_ref.png")
    ref_data = os.path.join(BENCHMARK_DIR, "data_ref.json")
    
    if not args.no_shift:
        if os.path.exists(cur_img):
            shutil.move(cur_img, prec_img)
        if os.path.exists(cur_data):
            shutil.move(cur_data, prec_data)
    else:
        print("\n[Info] --no-shift used: keeping existing 'prec' files.")
        
    data_cur = {}
    
    # 1. Micro Benchmark
    micro_scene = "showcase"
    m_w, m_h, m_spp, m_runs = (480, 360, 64, 1) if args.quick else (960, 720, 128, 3)
    data_cur["micro"] = micro_benchmark(micro_scene, m_w, m_h, m_spp, 6, m_runs, n_threads)
    
    # 2. Macro Benchmark (Quality)
    # Always use 4K for quality rendering
    macro_w, macro_h = 3840, 2160
    macro_spp = 64 if args.quick else 128
    print(f"\n[Macro-Benchmark] Quality Render | {macro_w}x{macro_h} | {macro_spp} SPP")
    
    engine, _ = setup_engine_scene("showcase", macro_w, macro_h)
    
    # Fix the seed for deterministic rendering!
    engine.set_seed(42)
    
    print("  Rendering Image (Macro)...", end=" ", flush=True)
    t0 = time.perf_counter()
    
    # render() returns a dict with 'color', 'albedo', 'normal'.
    render_result = engine.render(macro_w, macro_h, macro_spp, 10, n_threads, 1)
    raw_float_array = render_result["color"]
    
    t_render = time.perf_counter() - t0
    print(f"done in {t_render:.2f}s")
    
    data_cur["macro_width"] = macro_w
    data_cur["macro_height"] = macro_h
    data_cur["macro_spp"] = macro_spp
    data_cur["macro_time_s"] = t_render
    
    # Gamma correction and saving
    buf_gamma = np.power(np.clip(raw_float_array, 0.0, 1.0), 1.0 / 2.2)
    img_uint8 = (buf_gamma * 255.0).astype(np.uint8)
    Image.fromarray(img_uint8).save(cur_img)
    print(f"  Saved {cur_img}")
    
    # 3. Reference Management
    if not os.path.exists(ref_img) or args.new_reference:
        print("\n[Reference] Creating new reference baseline.")
        shutil.copy(cur_img, ref_img)
        # We will save data_cur to data_ref later
        data_ref = data_cur.copy()
        with open(ref_data, "w", encoding="utf-8") as f:
            json.dump(data_ref, f, indent=4)
    
    # 4. Comparisons
    print("\n[Analysis] Generating comparisons...")
    
    # Load past data
    def load_json(path):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
        
    data_prec = load_json(prec_data)
    data_ref = load_json(ref_data)
    
    # Center for zoom (e.g. center of image)
    cx, cy = macro_w // 2, macro_h // 2
    
    if os.path.exists(ref_img):
        res_zoom = create_side_by_side_zoom(ref_img, cur_img, os.path.join(BENCHMARK_DIR, "composite_ref_vs_cur.png"), cx, cy, zoom=2.0)
        mse, d_pct = create_diff_map(ref_img, cur_img, os.path.join(BENCHMARK_DIR, "diff_ref_vs_cur.png"))
        if mse is not None:
            data_cur["diff_ref"] = {"mse": float(round(mse, 4)), "diff_percent": float(round(d_pct, 4))}
            print(f"  Ref vs Cur -> MSE: {mse:.4f}, Diff: {d_pct:.2f}%")
        
    if os.path.exists(prec_img):
        res_zoom = create_side_by_side_zoom(prec_img, cur_img, os.path.join(BENCHMARK_DIR, "composite_prec_vs_cur.png"), cx, cy, zoom=2.0)
        mse, d_pct = create_diff_map(prec_img, cur_img, os.path.join(BENCHMARK_DIR, "diff_prec_vs_cur.png"))
        if mse is not None:
            data_cur["diff_prec"] = {"mse": float(round(mse, 4)), "diff_percent": float(round(d_pct, 4))}
            print(f"  Prec vs Cur -> MSE: {mse:.4f}, Diff: {d_pct:.2f}%")
        
    # 5. Save and Report
    with open(cur_data, "w", encoding="utf-8") as f:
        json.dump(data_cur, f, indent=4)
        
    generate_markdown_report(data_cur, data_prec, data_ref)
    
    print("\n[Done] Benchmark complete.")

if __name__ == "__main__":
    main()
