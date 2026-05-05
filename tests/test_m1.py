import os
import sys
import json
import pandas as pd
from datetime import datetime
import importlib.util

# --- REPO SYNC ---
# Dynamically define the root to ensure absolute paths for imports
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# --- FIXING NAMESPACE COLLISION ---
# Since you have both 'core/models.py' and 'core/models/', we load the 
# specific model file directly from its path to bypass Python's default resolution.
def load_m1_class():
    model_path = os.path.join(REPO_ROOT, 'core', 'models', 'm1_trend.py')
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Could not find model file at {model_path}")
    
    spec = importlib.util.spec_from_file_location("m1_module", model_path)
    m1_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m1_module)
    
    # Try common class names found in the Wintra project
    for class_name in ['M1Trend', 'M1Model', 'Model1', 'TrendModel']:
        if hasattr(m1_module, class_name):
            return getattr(m1_module, class_name)
    
    # If not found, list available classes for the user
    classes = [name for name, obj in vars(m1_module).items() if isinstance(obj, type)]
    raise AttributeError(f"Could not find M1Trend class in {model_path}. Available classes: {classes}")

# --- CONFIGURATION ---
UNIVERSE_PATH = os.path.join(REPO_ROOT, 'core', 'data', 'idx80_list.json')
CACHE_DIR = os.path.join(REPO_ROOT, 'core', 'data', 'master_ticker')
TARGET_DATE = '2026-04-27'

def load_universe(filepath):
    """
    Robustly loads the ticker universe from the project JSON file, 
    accounting for metadata wrappers and filtering invalid strings.
    """
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            
        tickers = []
        
        # Scenario A: It's a flat list -> ["ANTM", "BBCA", ...]
        if isinstance(data, list):
            tickers = data
            
        # Scenario B: It's a dictionary
        elif isinstance(data, dict):
            # Check common keys that might hold the actual list
            for key in ['tickers', 'data', 'list', 'idx80']:
                if key in data and isinstance(data[key], list):
                    tickers = data[key]
                    break
            else:
                # Fallback: Assume the keys themselves are the tickers 
                # e.g., {"ANTM": {...}, "BBCA": {...}}
                tickers = list(data.keys())
                
        # Clean up: Only keep valid 4-letter uppercase IDX tickers
        valid_tickers = [t.strip().upper() for t in tickers if isinstance(t, str) and len(t.strip()) == 4 and t.strip().isalpha()]
        
        if not valid_tickers:
            print("[!] Warning: Parsed universe but found 0 valid 4-letter tickers.")
            
        return valid_tickers

    except FileNotFoundError:
        print(f"[!] Error: {filepath} not found.")
        return []
    except json.JSONDecodeError:
        print(f"[!] Error: {filepath} is not valid JSON.")
        return []

def data_gate_check(ticker):
    """
    Gate logic: Verifies intraday cache files before pandas I/O.
    Returns (file_path, status, absolute_path_checked) for better diagnostics.
    """
    file_path = os.path.join(CACHE_DIR, f"{ticker}_5m.csv")
    
    if not os.path.exists(file_path):
        return None, "MISSING", file_path
        
    size = os.path.getsize(file_path)
    if size < 100: 
        return None, f"TOO_SMALL ({size} bytes)", file_path
        
    return file_path, "OK", file_path

def main():
    print(f"==========================================")
    print(f" RUNNING M1 TEST - TARGET: {TARGET_DATE} ")
    print(f"==========================================\n")
    
    universe = load_universe(UNIVERSE_PATH)
    if not universe:
        print("[!] Execution halted: No valid tickers found in universe.")
        return

    try:
        M1Class = load_m1_class()
        m1_model = M1Class()
        print(f"[*] Successfully loaded {M1Class.__name__} logic.")
        
        # Display Model Parameters
        print(f"--- Model 1 Parameters ---")
        params = vars(m1_model)
        if params:
            for key, val in params.items():
                # Filter out private attributes and large data structures
                if not key.startswith('_') and not isinstance(val, (pd.DataFrame, dict, list)):
                    print(f"  {key}: {val}")
        else:
            print("  No public parameters found.")
        print("-" * 25 + "\n")

    except Exception as e:
        print(f"[!] Critical Error: {e}")
        return

    candidates = []
    target_dt = pd.to_datetime(TARGET_DATE).date()

    # --- DIAGNOSTIC TRACKERS ---
    diag_files_found = 0
    diag_files_missing = 0
    diag_files_small = 0
    diag_empty_df = 0
    diag_errors = 0
    diag_no_buy = 0
    diag_sample_result = None
    sample_path_checked = ""

    for ticker in universe:
        file_path, status, attempt_path = data_gate_check(ticker)
        
        if not sample_path_checked:
            sample_path_checked = attempt_path

        if status == "MISSING":
            diag_files_missing += 1
            continue
        elif status.startswith("TOO_SMALL"):
            diag_files_small += 1
            continue
            
        diag_files_found += 1
            
        try:
            df = pd.read_csv(file_path)
            dt_col = next((col for col in df.columns if col.lower() in ['datetime', 'date', 'time']), None)
            if not dt_col: continue
            
            df['datetime'] = pd.to_datetime(df[dt_col])
            df_day = df[df['datetime'].dt.date <= target_dt].copy()
            
            if df_day.empty or len(df_day) < 2:
                diag_empty_df += 1
                continue

            # Check if the model has 'analyze' or 'evaluate' method
            if hasattr(m1_model, 'analyze'):
                result = m1_model.analyze(ticker, df_day)
            elif hasattr(m1_model, 'evaluate'):
                result = m1_model.evaluate(ticker, df_day)
            else:
                # Fallback to direct call if it's a functional model
                result = m1_model(ticker, df_day)
            
            # Capture the first successful evaluation for inspection
            if diag_sample_result is None:
                diag_sample_result = {"ticker": ticker, "result": result}
            
            # Standard Wintra signal check
            is_buy = False
            if isinstance(result, dict):
                is_buy = result.get('signal') == 'BUY' or result.get('action') == 'BUY'
            elif isinstance(result, bool):
                is_buy = result

            if is_buy:
                close_col = next((c for c in df_day.columns if c.lower() == 'close'), df_day.columns[-1])
                prev_close = df_day.iloc[-2][close_col]
                candidates.append({'ticker': ticker, 'prev_close': prev_close})
            else:
                diag_no_buy += 1
                
        except Exception as e:
            if diag_errors == 0:
                print(f"[Diagnostic] First model exception caught on {ticker}: {repr(e)}")
            diag_errors += 1
            continue
            
        if len(candidates) >= 4:
            break

    # --- DIAGNOSTIC REPORT ---
    print("--- DIAGNOSTICS ---")
    print(f"Total Valid Tickers Checked: {len(universe)}")
    print(f"Files passed gate          : {diag_files_found}")
    print(f"Files missing              : {diag_files_missing}")
    print(f"Files too small            : {diag_files_small}")
    if sample_path_checked:
        print(f"Sample Path Searched       : {sample_path_checked}")
    print(f"Empty/Out-of-Date DF       : {diag_empty_df}")
    print(f"Model Exceptions           : {diag_errors}")
    print(f"Evaluated (No BUY)         : {diag_no_buy}")
    if diag_sample_result:
        print(f"Sample Output ({diag_sample_result['ticker']}) : {diag_sample_result['result']}")
    print("-------------------\n")

    if not candidates:
        print(f"No candidates found matching M1 criteria for {TARGET_DATE}.")
    else:
        print(f"{'No':<3} | {'Ticker':<8} | {'Prev Closing Price':<18}")
        print("-" * 35)
        for i, cand in enumerate(candidates, 1):
            print(f"{i:<3} | {cand['ticker']:<8} | Rp {cand['prev_close']:,.2f}")
    
    print(f"\n[Test Complete]")

if __name__ == "__main__":
    main()