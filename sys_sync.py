import os
import inspect
import importlib.util
import sys

# ANSI Colors for Terminal
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
GRAY = "\033[90m"
RESET = "\033[0m"

def get_signature(class_obj, method_name):
    try:
        method = getattr(class_obj, method_name)
        return str(inspect.signature(method))
    except AttributeError:
        return "Not Found"

def run_sync():
    print(f"\n{CYAN}🔄 WINTRA SYSTEM SYNCHRONIZATION | {GRAY}04/05/2026 16:14{RESET}")
    print("═"*80)

    # 1. DIRECTORY TREE
    print(f"{MAGENTA}📂 1. PROJECT STRUCTURE{RESET}")
    exclude = {'.git', '__pycache__', '.ipynb_checkpoints', 'venv'}
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in exclude]
        level = root.replace('.', '').count(os.sep)
        indent = ' ' * 4 * (level)
        print(f'{indent}{os.path.basename(root)}/')
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            if not f.startswith('.'):
                print(f'{subindent}{f}')
    
    # 2. MODEL SIGNATURES (The Interface Contract)
    print(f"\n{MAGENTA}📜 2. MODEL SIGNATURE REGISTRY{RESET}")
    print("─"*80)
    
    models = {
        "M1": ("core.models.m1_trend", "TrendModel"),
        "M2": ("core.models.m2_revert", "RevertModel"),
        "M3": ("core.models.m3_breakout", "BreakoutModel"),
        "M4": ("core.models.m4_leadership", "LeadershipModel"),
        "M5": ("core.models.m5_defensive", "DefensiveModel"),
        "M6": ("core.models.m6_high_beta", "HighBetaModel"),
        "M7": ("core.models.m7_washout", "WashoutModel"),
        "M8": ("core.models.m8_camarilla", "RangeScalperModel"),
        "M9": ("core.models.m9_controller", "PortfolioController")
    }

    for m_id, (path, c_name) in models.items():
        try:
            # Dynamic import
            spec = importlib.util.find_spec(path)
            if spec:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                cls = getattr(module, c_name)
                
                init_sig = get_signature(cls, "__init__")
                eval_sig = get_signature(cls, "evaluate") if m_id != "M9" else get_signature(cls, "rank_signals")
                
                print(f"{GREEN}[{m_id}]{RESET} {c_name}")
                print(f"  {GRAY}init{RESET} : {init_sig}")
                print(f"  {GRAY}eval{RESET} : {eval_sig}")
            else:
                print(f"{YELLOW}[{m_id}]{RESET} {path} - {GRAY}File not found{RESET}")
        except Exception as e:
            print(f"{RED}[{m_id}]{RESET} Error: {str(e)}")

    # 3. MODEL 9 LOGIC (The General's Priorities)
    print(f"\n{MAGENTA}⚖️ 3. M9 REGIME PRIORITY MATRIX{RESET}")
    print("─"*80)
    try:
        from core.models.m9_controller import PortfolioController
        m9 = PortfolioController()
        for regime, weights in m9.REGIME_PRIORITY.items():
            weight_str = ", ".join([f"{k}:{v}" for k, v in weights.items()])
            print(f"  {regime:<10}: {YELLOW}{weight_str}{RESET}")
    except Exception as e:
        print(f"  {RED}Could not load M9 weights: {e}{RESET}")

    print("\n" + "═"*80)
    print(f"{CYAN}SYNC COMPLETE. Paste this output into the chat to align context.{RESET}\n")

if __name__ == "__main__":
    run_sync()
