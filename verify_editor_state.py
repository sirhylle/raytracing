
import sys
import os
import numpy as np
import cpp_engine
import loader
from config import RenderConfig
from modes.editor.state import EditorState

def run_verification():
    print("--- Starting EditorState Verification ---")
    
    # 1. Setup
    engine = cpp_engine.Engine()
    builder = loader.SceneBuilder(engine)
    conf = RenderConfig()
    
    # 2. Init State
    state = EditorState(conf, builder)
    
    # 3. Load Scene
    scene_path = "scenes/test_cornell.json"
    if not os.path.exists(scene_path):
        print(f"Error: Scene {scene_path} not found.")
        return
        
    print(f"Loading {scene_path}...")
    state.load_scene(scene_path)
    
    # 4. Verify Load
    print(f"Loaded Camera Pos: {state.cam_pos}")
    # We expect some values. 
    # Let's Modify
    old_pos = state.cam_pos.copy()
    new_pos = old_pos + np.array([1.0, 0.0, 0.0], dtype=np.float32)
    state.cam_pos = new_pos
    
    # Also modify something nested like environment exposure
    old_exp = state.env_exposure
    state.env_exposure = 2.5
    
    print(f"Modified Camera Pos: {state.cam_pos}")
    print(f"Modified Exposure: {state.env_exposure}")
    
    # 5. Save
    save_path = "scenes/verification_save.json"
    print(f"Saving to {save_path}...")
    state.save_scene(save_path)
    
    # 6. Verify Save
    # Create new state to load back
    print("Reloading saved file to verify persistence...")
    engine2 = cpp_engine.Engine()
    builder2 = loader.SceneBuilder(engine2)
    conf2 = RenderConfig()
    state2 = EditorState(conf2, builder2)
    state2.load_scene(save_path)
    
    # Check Camera
    loaded_pos = state2.cam_pos
    if np.allclose(loaded_pos, new_pos, atol=1e-5):
        print("[PASS] Camera Position persisted correctly.")
    else:
        print(f"[FAIL] Camera Position Mismatch: Saw {loaded_pos}, Expected {new_pos}")

    # Check Exposure
    loaded_exp = state2.env_exposure
    if abs(loaded_exp - 2.5) < 1e-5:
        print("[PASS] Environment Exposure persisted correctly.")
    else:
        print(f"[FAIL] Exposure Mismatch: Saw {loaded_exp}, Expected 2.5")
        
    print("--- Verification Complete ---")

if __name__ == "__main__":
    run_verification()
