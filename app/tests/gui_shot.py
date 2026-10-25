"""Headless GUI smoke test helper: python gui_shot.py <app> <out.png> [args]  (run under xvfb-run)."""
import os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
app, out = sys.argv[1], sys.argv[2]
if app == "auditor":
    from nes_auditor import AuditorApp
    w = AuditorApp(sys.argv[3] if len(sys.argv) > 3 else None)
else:
    from nes_colorizer import ColorizerApp
    w = ColorizerApp()
    if len(sys.argv) > 3:
        w.script(sys.argv[3:])
def shot():
    w.update(); w.update_idletasks()
    subprocess.run(["import", "-window", "root", out], check=True)
    w.destroy()
w.after(int(os.environ.get("WAIT_MS", "2500")), shot)
w.mainloop()
