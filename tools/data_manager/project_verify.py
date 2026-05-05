import os
import sys
import importlib.util
import json
import pandas as pd

# --- DYNAMIC ROOT DETECTION ---
def get_root():
    """Detects project root regardless of where script is executed."""
    current = os.path.dirname(os.path.abspath(__file__))
    # If script is in tools/data_manager, root is 2 levels up
    if "tools" in current and "data_manager" in current:
        return os.path.abspath(os.path.join(current, "..", ".."))
    return current

ROOT_DIR = get_root()
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

class WintraVerifier:
    def __init__(self):
        self.results = []
        self.config = {
            "universe": "core/data/idx80_list.json",
            "daily_dir": "core/data/master_ticker/daily",
            "intra_dir": "core/data/master_ticker/intraday",
            "models_dir": "core/models"
        }
        # Model associations for reporting
        self.model_map = {
            "m1": "Daily", "m2": "Daily", "m4": "Daily", "m5": "Daily",
            "m3": "Intraday", "m6": "Intraday", "m7": "Intraday", "m8": "Intraday",
            "m9": "Global"
        }

    def log(self, category, name, status, message=""):
        self.results.append({
            "category": category,
            "name": name,
            "status": status,
            "message": message
        })

    def verify_paths(self):
        print(f"[*] Project Root: {ROOT_DIR}")
        self.log("PATHS", "Root Dir", "PASS", ROOT_DIR)

    def verify_environment(self):
        print("[*] Verifying Environment...")
        env_path = os.path.join(ROOT_DIR, ".env")
        if not os.path.exists(env_path):
            self.log("ENV", ".env file", "FAIL", "Missing .env file in root")
        else:
            self.log("ENV", ".env file", "PASS")

    def verify_data_sources(self):
        print("[*] Verifying Data Sources...")
        # 1. Check Universe
        univ_path = os.path.join(ROOT_DIR, self.config["universe"])
        if not os.path.exists(univ_path):
            self.log("DATA", "Universe JSON", "FAIL", "Missing idx80_list.json")
        else:
            try:
                with open(univ_path, 'r') as f:
                    json.load(f)
                self.log("DATA", "Universe JSON", "PASS")
            except:
                self.log("DATA", "Universe JSON", "FAIL", "Invalid JSON format")

        # 2. Check Daily Cache
        daily_path = os.path.join(ROOT_DIR, self.config["daily_dir"])
        if not os.path.exists(daily_path):
            self.log("DATA", "Daily Cache", "FAIL", "Folder 'daily/' missing")
        else:
            files = [f for f in os.listdir(daily_path) if f.endswith('.csv')]
            self.log("DATA", "Daily Cache", "PASS" if files else "WARN", f"Found {len(files)} tickers")

        # 3. Check Intraday Cache
        intra_path = os.path.join(ROOT_DIR, self.config["intra_dir"])
        if not os.path.exists(intra_path):
            self.log("DATA", "Intraday Cache", "FAIL", "Folder 'intraday/' missing")
        else:
            files = [f for f in os.listdir(intra_path) if f.endswith('.csv')]
            self.log("DATA", "Intraday Cache", "PASS" if files else "WARN", f"Found {len(files)} tickers")

    def verify_models(self):
        print("[*] Verifying Models (Dry Run)...")
        models_path = os.path.join(ROOT_DIR, self.config["models_dir"])
        
        for file in sorted(os.listdir(models_path)):
            if file.endswith(".py") and not file.startswith("__"):
                m_id = file.split('_')[0]
                source = self.model_map.get(m_id, "Unknown")
                
                module_name = file[:-3]
                full_path = os.path.join(models_path, file)
                
                try:
                    spec = importlib.util.spec_from_file_location(module_name, full_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    classes = [getattr(module, x) for x in dir(module) if isinstance(getattr(module, x), type)]
                    if not classes:
                        self.log("MODELS", file, "WARN", f"Source: {source} | No class found")
                    else:
                        try:
                            classes[0]()
                            self.log("MODELS", file, "PASS", f"Source: {source} | Instantiated")
                        except Exception as e:
                            self.log("MODELS", file, "FAIL", f"Source: {source} | Init error: {str(e)[:30]}")
                except Exception as e:
                    self.log("MODELS", file, "FAIL", f"Source: {source} | Import error")

    def print_report(self):
        print("\n" + "="*80)
        print(f"{'CATEGORY':<10} | {'COMPONENT':<25} | {'STATUS':<6} | {'MESSAGE'}")
        print("-" * 80)
        fails = 0
        for res in self.results:
            if res['status'] == "FAIL": fails += 1
            print(f"{res['category']:<10} | {res['name']:<25} | {res['status']:<6} | {res['message']}")
        print("="*80)
        if fails == 0:
            print("✔ SYSTEM HEALTHY: Data streams and models are synchronized.")
        else:
            print(f"✘ SYSTEM UNSTABLE: Found {fails} critical failures.")
        print("="*80 + "\n")

if __name__ == "__main__":
    verifier = WintraVerifier()
    verifier.verify_paths()
    verifier.verify_environment()
    verifier.verify_data_sources()
    verifier.verify_models()
    verifier.print_report()
