import os
import shutil
import sys

# --- CONFIGURATION ---
OLD_CACHE_NAME = "intraday_cache"
NEW_CACHE_NAME = "master_ticker"

FILE_RELOCATION = {
    "scraper.py": "tools/data_manager",
    "cache_cleaner.py": "tools/data_manager",
    "sys_sync.py": "tools/data_manager",
    "wintra_db_diag.py": "tools/data_manager",
    "project_verify.py": "tools/data_manager",
    "optimize_m1.py": "tools/optimization",
    "optimize_m2.py": "tools/optimization",
    "optimize_m3.py": "tools/optimization",
    "optimize_m4.py": "tools/optimization",
    "optimize_m5.py": "tools/optimization",
    "optimize_m6.py": "tools/optimization",
    "optimize_m7.py": "tools/optimization",
    "optimize_m8.py": "tools/optimization",
    "optimize_m9.py": "tools/optimization",
    "intraday_report.py": "reports",
    "morning_report.py": "reports",
    "messenger.py": "reports",
    "test_m1.py": "tests",
    "test_swing.py": "tests",
    "test_timeframes.py": "tests",
    "stress_test_slots.py": "tests"
}

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

def create_dirs():
    dirs = ["tools/data_manager", "tools/optimization", "reports", "tests", "logs", "core/data/master_ticker"]
    for d in dirs:
        path = os.path.join(ROOT_DIR, d)
        if not os.path.exists(path):
            os.makedirs(path)

def migrate_files():
    print("[*] Relocating files...")
    for filename, target_dir in FILE_RELOCATION.items():
        # Check root and current tools folder for files
        sources = [os.path.join(ROOT_DIR, filename), os.path.join(ROOT_DIR, "tools", filename)]
        for src in sources:
            if os.path.exists(src):
                dest_dir = os.path.join(ROOT_DIR, target_dir)
                try:
                    shutil.move(src, os.path.join(dest_dir, filename))
                    print(f"    -> Moved {filename} to {target_dir}/")
                except Exception as e:
                    print(f"    [!] Error moving {filename}: {e}")

def rename_data_cache():
    old = os.path.join(ROOT_DIR, "core", "data", OLD_CACHE_NAME)
    new = os.path.join(ROOT_DIR, "core", "data", NEW_CACHE_NAME)
    if os.path.exists(old):
        if os.path.exists(new):
            for item in os.listdir(old):
                shutil.move(os.path.join(old, item), os.path.join(new, item))
            os.rmdir(old)
        else:
            os.rename(old, new)
        print(f"[+] Synced data cache to {NEW_CACHE_NAME}")

def update_references():
    print("[*] Updating string references...")
    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if not d.startswith(('.', '__'))]
        for f in files:
            if f.endswith(('.py', '.json', '.yml', '.md')) and f != "project_manager.py":
                f_path = os.path.join(root, f)
                try:
                    with open(f_path, 'r', encoding='utf-8') as file_obj:
                        content = file_obj.read()
                    if OLD_CACHE_NAME in content:
                        with open(f_path, 'w', encoding='utf-8') as file_obj:
                            file_obj.write(content.replace(OLD_CACHE_NAME, NEW_CACHE_NAME))
                except: pass

def main():
    print("\n=== WINTRA PROJECT MANAGER ===")
    create_dirs()
    migrate_files()
    rename_data_cache()
    update_references()
    print("\n[COMPLETE] Run 'python tools/data_manager/project_verify.py' to verify health.")

if __name__ == "__main__":
    main()
