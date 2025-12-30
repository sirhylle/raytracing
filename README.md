# Python + C++ Path Tracer

A physically-based Path Tracer built in Python for pedagogical clarity, accelerated by a C++ core engine for performance.

## Features

- **Core Ray Tracing**: Sphere and Quad primitives, BVH acceleration.
- **Advanced Materials**:
    - **Lambertian**: Standard diffuse.
    - **Metal**: Reficitive conductor with roughness.
    - **Dielectric**: Glass with **Color Tinting** and **Fake Caustics** (Transparent Shadows).
    - **Plastic**: Diffuse base with specular clearcoat.
    - **Diffuse Light**: Emissive material.
- **Global Illumination**: Next Event Estimation (NEE) for reduced noise.
- **Environment**: HDR/Equirectangular Environment Mapping.
- **Camera**: Depth of Field (DoF) and Turntable Animation support.
- **Denoising**: AI-based denoising via Intel Open Image Denoise (OIDN).
- **Performance**: C++ Core (via `nanobind`) provides >100x speedup.

## Installation & Build

This project uses `uv` for Python dependency management and `cmake` for the C++ build.

1.  **Install Dependencies**:
    ```bash
    uv sync
    # Or manually:
    pip install .
    ```

2.  **Build C++ Extension**:
    ```bash
    # Configure
    uv run cmake -S . -B build
    
    # Build (Release mode)
    uv run cmake --build build --config Release
    
    # Install (Copy .pyd to root)
    copy "build\Release\*.pyd" .
    ```

## Usage

All interaction is handled via the `main_cpp.py` driver script.

### Basic Render
Render the default "Cornell Box" scene:
```bash
uv run main_cpp.py --width 800 --spp 100
```

### Scene Selection
Choose different scenes using `--scene`.
- `cornell`: Standard Cornell Box.
- `random`: "One Weekend" style random spheres (includes generic, metal, glass, and plastic).

```bash
uv run main_cpp.py --scene random --width 1200 --spp 50
```

### Animation (Turntable)
Generate a turntable video around the scene center.
```bash
uv run main_cpp.py --scene random --animate --frames 48 --fps 24 --width 600 --spp 20
```
*Outputs `output.mp4`.*

### Lighting & Materials
Control the environment and sun:
- `--sun-intensity`: Brightness of the directional sun (default 0 or 10 depending on scene).
- `--sky-gain`: Intensity of the environment map background.
- `--ambient`: Alias for sky intensity.

```bash
uv run main_cpp.py --scene random --sun-intensity 5.0 --ambient 0.5
```

### Post-Processing (Denoising)
Denoising is applied automatically if the `oidn` package is installed. The raw output is saved as `output.png`, and the denoised version as `output_denoised.png`.

## Code Functionality
- **`src/main.cpp`**: Core C++ implementation (Geometry, Materials, Renderer).
- **`scenes.py`**: Scene definitions (Python side).
- **`main_cpp.py`**: CLI entry point and render loop driver.
