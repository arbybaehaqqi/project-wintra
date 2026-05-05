import os
import sys
import importlib.util
import json

# --- DYNAMIC ROOT DETECTION ---
def get_root():
    """Detects project root regardless of where script is executed."""
    current = os.path.dirname(os.path.abspath(__file__))
    # If script is in tools/data_manager, root is 2 levels up
    if "tools" in current and "data_manager" in current:
        return os.path.abspath(os.path.join(current, "..", ".."))
    # If script is in root
    return current

ROOT_DIR = get_root()
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

class WintraVerifier:
    def __init__(self):
        self.results = []
        self.config = {
            "universe": "core/data/idx80_list.json",
            "data_dir": "core/data/master_ticker",
            "models_dir": "core/models"
        }

    def log(self, category, name, status, message=""):
        self.results.append({
            "category": category,
            "name": name,
            "status": status,
            "message": message
        })

    def verify_paths(self):
        print(f"[*] Project Root detected at: {ROOT_DIR}")
        self.log("PATHS", "Root Detection", "PASS", ROOT_DIR)

    def verify_environment(self):
        print("[*] Verifying Environment...")
        env_path = os.path.join(ROOT_DIR, ".env")
        if not os.path.exists(env_path):
            self.log("ENV", ".env file", "FAIL", "Missing .env file in root")
        else:
            self.log("ENV", ".env file", "PASS")

    def verify_data_sources(self):
        print("[*] Verifying Data Sources...")
        univ_path = os.path.join(ROOT_DIR, self.config["universe"])
        if not os.path.exists(univ_path):
            self.log("DATA", "Universe JSON", "FAIL", f"Missing at {self.config['universe']}")
        else:
            try:
                with open(univ_path, 'r') as f:
                    json.load(f)
                self.log("DATA", "Universe JSON", "PASS")
            except Exception as e:
                self.log("DATA", "Universe JSON", "FAIL", f"Invalid JSON format")

        cache_path = os.path.join(ROOT_DIR, self.config["data_dir"])
        if not os.path.exists(cache_path):
            self.log("DATA", "Ticker Cache", "FAIL", f"Folder {self.config['data_dir']} not found")
        else:
            csv_files = [f for f in os.listdir(cache_path) if f.endswith('.csv')]
            if not csv_files:
                self.log("DATA", "Ticker Cache", "FAIL", "Folder is empty")
            else:
                self.log("DATA", "Ticker Cache", "PASS", f"Found {len(csv_files)} tickers")

    def verify_models(self):
        print("[*] Verifying Models (Dry Run)...")
        models_path = os.path.join(ROOT_DIR, self.config["models_dir"])
        if not os.path.exists(models_path):
            self.log("MODELS", "Models Dir", "FAIL", "Directory missing")
            return

        for file in sorted(os.listdir(models_path)):
            if file.endswith(".py") and not file.startswith("__"):
                module_name = file[:-3]
                full_path = os.path.join(models_path, file)
                
                try:
                    spec = importlib.util.spec_from_file_location(module_name, full_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    classes = [getattr(module, x) for x in dir(module) if isinstance(getattr(module, x), type)]
                    if not classes:
                        self.log("MODELS", file, "WARN", "No class defined")
                    else:
                        try:
                            instance = classes[0]()
                            self.log("MODELS", file, "PASS", f"Instantiated {classes[0].__name__}")
                        except Exception as inst_e:
                            self.log("MODELS", file, "FAIL", f"Init error: {inst_e}")
                except Exception as e:
                    self.log("MODELS", file, "FAIL", f"Import error")

    def print_report(self):
        print("\n" + "="*75)
        print(f"{'CATEGORY':<10} | {'COMPONENT':<25} | {'STATUS':<6} | {'MESSAGE'}")
        print("-" * 75)
        fails = 0
        for res in self.results:
            if res['status'] == "FAIL": fails += 1
            print(f"{res['category']:<10} | {res['name']:<25} | {res['status']:<6} | {res['message']}")
        print("="*75)
        if fails == 0:
            print("✔ SYSTEM HEALTHY: All checks passed.")
        else:
            print(f"✘ SYSTEM UNSTABLE: Found {fails} failures. Check paths/imports.")
        print("="*75 + "\n")

if __name__ == "__main__":
    verifier = WintraVerifier()
    verifier.verify_paths()
    verifier.verify_environment()
    verifier.verify_data_sources()
    verifier.verify_models()
    verifier.print_report()
