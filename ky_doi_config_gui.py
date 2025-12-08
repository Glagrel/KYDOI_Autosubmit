import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

SETTINGS_PATH = Path(r"C:\KY_DOI\settings.json")

DEFAULT_SETTINGS = {
    "TESTING_MODE": True,
    "HEADLESS_MODE": False,
    "ZIP_DROPDOWN_STEPS": 0,  # allow 0 by default
}

def save_settings(testing, headless, zip_steps):
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "TESTING_MODE": testing,
        "HEADLESS_MODE": headless,
        "ZIP_DROPDOWN_STEPS": zip_steps,
    }
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def load_settings():
    cfg = DEFAULT_SETTINGS.copy()
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            cfg.update(loaded)
        except:
            pass
    return cfg

def main():
    cfg = load_settings()

    root = tk.Tk()
    root.title("KY DOI Auto-Submitter Settings")
    root.geometry("380x230")

    frame = ttk.Frame(root, padding=20)
    frame.pack(fill="both", expand=True)

    test_var = tk.BooleanVar(value=cfg.get("TESTING_MODE", True))
    headless_var = tk.BooleanVar(value=cfg.get("HEADLESS_MODE", False))
    zip_steps_var = tk.StringVar(value=str(cfg.get("ZIP_DROPDOWN_STEPS", 0)))

    ttk.Checkbutton(frame, text="Testing Mode", variable=test_var).pack(anchor="w", pady=5)
    ttk.Checkbutton(frame, text="Headless Mode (no browser window)", variable=headless_var).pack(anchor="w", pady=5)

    zip_frame = ttk.Frame(frame)
    zip_frame.pack(anchor="w", pady=10, fill="x")

    ttk.Label(zip_frame, text="ZIP dropdown steps (ArrowDown presses):").pack(anchor="w")
    ttk.Entry(zip_frame, textvariable=zip_steps_var, width=10).pack(anchor="w", pady=2)

    def apply():
        try:
            steps = int(zip_steps_var.get().strip())
            if steps < 0:
                raise ValueError
        except:
            messagebox.showerror("Error", "ZIP dropdown steps must be a whole number (0 or more).")
            return

        save_settings(test_var.get(), headless_var.get(), steps)
        messagebox.showinfo("Saved", "Settings updated successfully!")

    ttk.Button(frame, text="Save Settings", command=apply).pack(pady=20)

    root.mainloop()

if __name__ == "__main__":
    main()
