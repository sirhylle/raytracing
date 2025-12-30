import sys
from scene import HittableList
from sphere import Sphere
from quad import Quad
from material import Lambertian, Metal, Dielectric, DiffuseLight
from vec3 import point3, color, vec3
from camera import Camera
from renderer import render_scene
import numpy as np
from PIL import Image
import os
import time
import argparse

def main():
    parser = argparse.ArgumentParser(description='Python Path Tracer')
    parser.add_argument('--width', type=int, default=800, help='Image width')
    parser.add_argument('--height', type=int, help='Image height (optional, default square)')
    parser.add_argument('--spp', type=int, default=20, help='Samples per pixel')
    parser.add_argument('--depth', type=int, default=50, help='Max recursion depth')
    
    args = parser.parse_args()

    # Image
    aspect_ratio = 1.0
    image_width = args.width
    if args.height:
        image_height = args.height
    else:
        image_height = int(image_width / aspect_ratio)
        
    samples_per_pixel = args.spp
    max_depth = args.depth
    
    print(f"Setting up scene with {image_width}x{image_height}...")

    # World
    world = HittableList()
    
    # Cornell Box Materials
    red = Lambertian(color(0.65, 0.05, 0.05))
    white = Lambertian(color(0.73, 0.73, 0.73))
    green = Lambertian(color(0.12, 0.45, 0.15))
    light = DiffuseLight(color(15, 15, 15))
    
    # Walls
    world.add(Quad(point3(555,0,0), vec3(0,555,0), vec3(0,0,555), green))
    world.add(Quad(point3(0,0,0), vec3(0,555,0), vec3(0,0,555), red))
    world.add(Quad(point3(343, 554, 332), vec3(-130,0,0), vec3(0,0,-105), light)) # Light
    world.add(Quad(point3(0,0,0), vec3(555,0,0), vec3(0,0,555), white)) # Floor
    world.add(Quad(point3(555,555,555), vec3(-555,0,0), vec3(0,0,-555), white)) # Ceiling
    world.add(Quad(point3(0,0,555), vec3(555,0,0), vec3(0,555,0), white)) # Back
    
    # Objects
    # Mirror Sphere
    world.add(Sphere(point3(200, 100, 200), 100, Metal(color(0.8, 0.85, 0.88), 0.0)))
    
    # Glass Sphere
    world.add(Sphere(point3(400, 100, 300), 100, Dielectric(1.5)))

    # Lights (for sampling)
    lights = HittableList()
    lights.add(Quad(point3(343, 554, 332), vec3(-130,0,0), vec3(0,0,-105), light))
    # We could add the glass sphere to lights if we wanted caustics sampling via NEE (unlikely for glass)
    
    # Camera
    lookfrom = point3(278, 278, -800)
    lookat = point3(278, 278, 0)
    vup = vec3(0, 1, 0)
    dist_to_focus = 10.0
    aperture = 0.0
    
    cam = Camera(lookfrom, lookat, vup, 40.0, aspect_ratio, aperture, dist_to_focus)
    
    # Render
    t0 = time.time()
    pixels = render_scene(image_width, image_height, samples_per_pixel, max_depth, cam, world, lights)
    t1 = time.time()
    print(f"\nRender complete in {t1-t0:.2f}s")
    
    
    # Denoise (Optional)
    denoised_pixels = pixels.copy()
    try:
        from denoise import denoise_image
        print("Denoising...")
        denoised_pixels = denoise_image(pixels) # Pass Linear
        print("Denoising complete.")
    except ImportError:
        print("Denoise module not found or failed, skipping.")
    except Exception as e:
        print(f"Denoising failed: {e}")

    # Gamma Correction
    # color^(1/2.2)
    pixels = np.clip(pixels, 0.0, 1.0)
    pixels = np.power(pixels, 1.0/2.2)
    
    denoised_pixels = np.clip(denoised_pixels, 0.0, 1.0)
    denoised_pixels = np.power(denoised_pixels, 1.0/2.2)
    
    # Save Raw
    img_data = (pixels * 255).astype(np.uint8)
    img = Image.fromarray(img_data, 'RGB')
    img.save('output_raw.png')
    print("Saved output_raw.png")
    
    # Save Denoised
    denoised_data = (denoised_pixels * 255).astype(np.uint8)
    img_denoised = Image.fromarray(denoised_data, 'RGB')
    img_denoised.save('output_denoised.png')
    print("Saved output_denoised.png")

if __name__ == "__main__":
    main()
