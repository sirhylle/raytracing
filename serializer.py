"""
================================================================================================
MODULE: SCENE SERIALIZER
================================================================================================

DESCRIPTION:
  Handles the serialization (Save) and deserialization (Load) of scenes to/from JSON.
  
  Design Principles:
  1. Generic: Uses introspection (dataclasses, dicts) to avoid hardcoded field mappings.
     - RenderConfig -> 'render_settings', 'camera', 'environment'
     - SceneBuilder.registry -> 'objects'
  2. Robust: Handles path relativization for portability.
  3. Single Source of Truth: 
     - Global Settings come from RenderConfig.
     - Object Data comes from SceneBuilder.registry.

================================================================================================
"""

import json
import os
import numpy as np
import copy
from dataclasses import asdict

def _sanitize_for_json(data):
    """
    Recursively converts numpy types and other non-serializable objects to standard Python types.
    """
    if isinstance(data, dict):
        return {k: _sanitize_for_json(v) for k, v in data.items()}
    elif isinstance(data, (list, tuple)):
        return [_sanitize_for_json(v) for v in data]
    elif isinstance(data, np.ndarray):
        return data.tolist()
    elif isinstance(data, (np.float32, np.float64)):
        return float(data)
    elif isinstance(data, (np.int32, np.int64)):
        return int(data)
    else:
        return data

def _relativize_paths(data, base_dir):
    """
    Traverses the object dict and converts absolute paths to relative paths 
    where appropriate (e.g. 'asset_name', 'texture_path').
    """
    # Keys known to contain paths
    PATH_KEYS = {'asset_name', 'map_path', 'texture_path', 'albedo_map', 'roughness_map', 'metallic_map', 'normal_map'}
    
    if isinstance(data, dict):
        for k, v in data.items():
            if k in PATH_KEYS and isinstance(v, str) and os.path.isabs(v):
                try:
                    data[k] = os.path.relpath(v, base_dir)
                except ValueError:
                    # Can happen on Windows if paths are on different drives
                    pass 
            else:
                _relativize_paths(v, base_dir)
    elif isinstance(data, list):
        for item in data:
            _relativize_paths(item, base_dir)

def serialize_scene(config, builder, filepath=None):
    """
    Serializes the current scene state (Config + Objects) to a dictionary (and optionally writes to file).
    
    Args:
        config (RenderConfig): The global configuration (Camera, Env, Settings).
        builder (SceneBuilder): The object manager containing the registry.
        filepath (str, optional): If provided, saves the JSON to this path.
    
    Returns:
        dict: The serialized scene data.
    """
    
    # 1. Capture Global Settings (Generic)
    # We rely on RenderConfig's nested structure (RenderSettings, CameraSettings, etc.)
    # matching the desired JSON structure.
    import dataclasses
    raw_conf = dataclasses.asdict(config)
    
    # Structure match for JSON format
    # We start with version
    out = {
        "version": "2.0"
    }
    
    # Minimal mapping to maintain JSON compatibility for top-level keys
    # RenderConfig 'render' -> JSON 'render_settings'
    if 'render' in raw_conf:
        out['render_settings'] = raw_conf.pop('render')
    
    # Copy the rest (camera, environment, system) as is
    out.update(raw_conf)

    # 2. Capture Objects (from Builder Registry)
    out['objects'] = []
    
    cwd = os.getcwd()
    target_dir = os.path.dirname(os.path.abspath(filepath)) if filepath else cwd
    
    for oid, info in builder.registry.items():
        # Skip transient objects (like the auto-sun light which is regenerated on load)
        if info['type'] == 'light_sun': continue 
        
        # Deep copy to safe-guard against modification during sanitization
        # We don't need to manually map anything here, we assume registry matches JSON schema
        obj_data = copy.deepcopy(info)
        out['objects'].append(obj_data)

    # 3. Post-Process
    # A. Relativize Paths
    # If we are saving to a file, we want paths relative to that file.
    _relativize_paths(out, target_dir)
    
    # B. Sanitize (Numpy -> List)
    final_data = _sanitize_for_json(out)
    
    # 4. Write to File
    if filepath:
        try:
            with open(filepath, 'w') as f:
                json.dump(final_data, f, indent=4)
            print(f"[Serializer] Scene saved to {filepath}")
        except Exception as e:
            print(f"[Serializer] Failed to write file: {e}")
            
    return final_data

def deserialize_scene(filepath):
    """
    Loads a JSON scene file. 
    Does not apply it to the engine (Loader does that).
    Just returns the dict.
    """
    if not os.path.exists(filepath):
        print(f"[Serializer] Error: File not found {filepath}")
        return None

    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            return data
    except Exception as e:
        print(f"[Serializer] JSON Load Failed: {e}")
        return None
