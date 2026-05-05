import os
import shutil
import sys

# --- CONFIGURATION ---
OLD_CACHE_NAME = "intraday_cache"
NEW_CACHE_NAME = "master_ticker"

# Map of current files in root -> their new home
FILE_RELOCATION = {
    # Tools & Data Management
    "scraper.py": "tools/data_manager",
    "cache_cleaner.py": "tools/data_manager",
    "sys_sync.py": "tools/data_manager",
    "wintra_db_diag.py": "tools/data_manager",
    
    # Optimization (Move existing optimize scripts into a subfolder)
    "optimize_m1.py": "tools/optimization",
    "optimize_m2.py": "tools/optimization",
    "optimize_m3.py": "tools/optimization",
    "optimize_m4.py": "tools/optimization",
    "optimize_m5.py": "tools/optimization",
    "optimize_m6.py": "tools/optimization",
    "optimize_m7.py": "tools/optimization",
    "optimize_m8.py": "tools/optimization",
    "optimize_m9.py": "tools/optimization",
    
    # Reports
    "intraday_report.py": "reports",
    "morning_report.py": "reports",
    "messenger.py": "reports",
    "wintra_scheduled_report.md": "reports",
    
    # Tests & Performance
    "stress_test_slots.py": "tests",
    "test_swing.py": "tests",
    "test_timeframes.py": "tests",
    "train_watchdog_performance.py": "tests",
}

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

def create_dirs():
    """Ensures the new structure exists."""
    dirs = [
        "tools/data_manager",
        "tools/optimization",
        "reports",
        "tests",
        "logs",
        "core/data/master_ticker"
    ]
    for d in dirs:
        path = os.path.join(ROOT_DIR, d)
        if not os.path.exists(path):
            os.makedirs(path)
            print(f"[+] Created directory: {d}")

def migrate_files():
    """Moves files while checking for existence (deletion-safe)."""
    print("[*] Checking for files to relocate...")
    moved_count = 0
    
    for filename, target_dir in FILE_RELOCATION.items():
        # Check in root first
        source_path = os.path.join(ROOT_DIR, filename)
        
        # Also check in /tools/ if they were already there (for optimize scripts)
        if not os.path.exists(source_path) and "optimize" in filename:
            source_path = os.path.join(ROOT_DIR, "tools", filename)

        if os.path.exists(source_path):
            dest_folder = os.path.join(ROOT_DIR, target_dir)
            try:
                # Use shutil.move to handle cross-device/folder moves
                shutil.move(source_path, os.path.join(dest_folder, filename))
                print(f"    -> Moved {filename} to {target_dir}/")
                moved_count += 1
            except Exception as e:
                print(f"    [!] Error moving {filename}: {e}")
        else:
            # Silent skip if file was already deleted or moved
            pass
            
    print(f"[✔] Relocation finished. {moved_count} files moved.")

def rename_data_cache():
    """Renames intraday_cache to master_ticker inside core/data/."""
    old_path = os.path.join(ROOT_DIR, "core", "data", OLD_CACHE_NAME)
    new_path = os.path.join(ROOT_DIR, "core", "data", NEW_CACHE_NAME)
    
    if os.path.exists(old_path):
        try:
            # If new path exists and is empty, remove it to allow rename
            if os.path.exists(new_path) and not os.listdir(new_path):
                os.rmdir(new_path)
            
            os.rename(old_path, new_path)
            print(f"[+] Renamed {OLD_CACHE_NAME} -> {NEW_CACHE_NAME}")
        except Exception as e:
            print(f"[!] Could not rename cache folder: {e}")
    else:
        print(f"[-] Cache folder '{OLD_CACHE_NAME}' not found or already renamed.")

def update_code_references():
    """Scans all text files to update path strings."""
    print("[*] Updating string references in code...")
    exts = ('.py', '.json', '.txt', '.yml', '.md')
    update_count = 0
    
    for root, dirs, files in os.walk(ROOT_DIR):
        # Skip hidden and cache folders
        dirs[:] = [d for d in dirs if not d.startswith(('.', '__'))]
        
        for f in files:
            if f.endswith(exts) and f != "project_manager.py":
                f_path = os.path.join(root, f)
                try:
                    with open(f_path, 'r', encoding='utf-8') as file_obj:
                        content = file_obj.read()
                    
                    if OLD_CACHE_NAME in content:
                        new_content = content.replace(OLD_CACHE_NAME, NEW_CACHE_NAME)
                        with open(f_path, 'w', encoding='utf-8') as file_obj:
                            file_obj.write(new_content)
                        update_count += 1
                        print(f"    [Updated] {os.path.relpath(f_path, ROOT_DIR)}")
                except Exception as e:
                    pass # Skip files with encoding issues
                    
    print(f"[✔] Code references updated in {update_count} files.")

def main():
    print("=== WINTRA PROJECT MANAGER: TIDY & MIGRATE ===")
    create_dirs()
    migrate_files()
    rename_data_cache()
    update_code_references()
    print("\n[COMPLETE] Your project is now organized and synced.")
    print("Tip: Run your scripts from the root using 'python tools/data_manager/scraper.py'")

if __name__ == "__main__":
    main()