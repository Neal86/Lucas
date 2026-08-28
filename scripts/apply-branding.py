from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly 1 match, found {count}")
    return text.replace(old, new, 1)


# Web branding
web_path = ROOT / "src/gpt_windows_connector/webapp.py"
web = web_path.read_text(encoding="utf-8")
web = replace_once(web, "import time\nfrom urllib.parse import unquote", "import time\nfrom pathlib import Path\nfrom urllib.parse import unquote", "web Path import")
web = replace_once(web, "\n\nDASHBOARD_HTML = r'''", "\n\nBRAND_ASSET_DIR = Path(__file__).with_name(\"assets\")\n\nDASHBOARD_HTML = r'''", "web asset dir")
web = replace_once(
    web,
    "</style>\n</head>",
    ".brand img{display:block;width:min(250px,100%);height:auto;margin-bottom:8px}.logo img{display:block;width:184px;height:auto;background:#fff;border-radius:9px;padding:5px 9px}.landing-logo img{display:block;height:44px;width:auto;background:#fff;border-radius:9px;padding:4px 8px}.core-ring img{width:66px;height:66px;object-fit:contain;background:#fff;border-radius:18px;padding:5px}.landing-footer .landing-logo img{height:38px}@media(max-width:850px){.logo img{width:150px}}\n</style>\n<link rel=\"icon\" type=\"image/png\" href=\"/assets/lucas-logo-square.png\" />\n</head>",
    "web logo styles",
)
web = web.replace('<div class="landing-logo"><span class="logo-mark">L</span>Lucas</div>', '<div class="landing-logo"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>')
web = replace_once(web, '<div class="core-ring"><b>L</b></div>', '<div class="core-ring"><img src="/assets/lucas-logo-square.png" alt="Lucas" /></div>', "web core logo")
web = replace_once(web, '<div class="brand">Lucas</div>', '<div class="brand"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>', "web auth logo")
web = replace_once(web, '<aside class="side"><div class="logo">Lucas</div>', '<aside class="side"><div class="logo"><img src="/assets/lucas-logo-horizontal.png" alt="Lucas" /></div>', "web sidebar logo")
asset_endpoint = '''\n\nasync def brand_asset(request: Request):\n    name = str(request.path_params.get("name") or "")\n    if name not in {"lucas-logo-horizontal.png", "lucas-logo-square.png"}:\n        return JSONResponse({"error": "not found"}, status_code=404)\n    return FileResponse(\n        BRAND_ASSET_DIR / name,\n        media_type="image/png",\n        headers={"Cache-Control": "public, max-age=86400"},\n    )\n'''
web = replace_once(web, "\n\nroutes = [", asset_endpoint + "\n\nroutes = [", "web asset endpoint")
web = replace_once(web, 'routes = [\n    Route("/", home, methods=["GET"]),', 'routes = [\n    Route("/assets/{name:str}", brand_asset, methods=["GET"]),\n    Route("/", home, methods=["GET"]),', "web asset route")
web_path.write_text(web, encoding="utf-8")


# Windows Settings branding
settings_path = ROOT / "src/gpt_windows_connector/settings_ui.py"
settings = settings_path.read_text(encoding="utf-8")
settings = replace_once(settings, "        import tkinter as tk\n        from tkinter import filedialog, messagebox, ttk", "        import tkinter as tk\n        from tkinter import filedialog, messagebox, ttk\n        from PIL import Image, ImageTk", "settings PIL import")
settings = replace_once(
    settings,
    '    root.configure(bg=C["window"])\n',
    '    root.configure(bg=C["window"])\n    window_icon_image=None\n    try:\n        icon=Image.open(Path(__file__).with_name("assets")/"lucas-logo-square.png").convert("RGBA")\n        icon.thumbnail((64,64),Image.Resampling.LANCZOS)\n        window_icon_image=ImageTk.PhotoImage(icon)\n        root.iconphoto(True,window_icon_image)\n    except Exception:\n        pass\n',
    "settings window icon",
)
old_brand = '''    brand = tk.Frame(sidebar,bg=C["sidebar"]); brand.pack(fill="x",padx=20,pady=(22,18))\n    tk.Label(brand,text="L",font=(FONT,13,"bold"),fg=C["white"],bg=C["blue"],width=2,height=1).pack(side="left")\n    tk.Label(brand,text="Lucas",font=(FONT,15,"bold"),fg=C["text"],bg=C["sidebar"]).pack(side="left",padx=(10,0))'''
new_brand = '''    brand = tk.Frame(sidebar,bg=C["sidebar"]); brand.pack(fill="x",padx=18,pady=(20,16))\n    brand_logo_image=None\n    try:\n        logo=Image.open(Path(__file__).with_name("assets")/"lucas-logo-horizontal.png").convert("RGBA")\n        logo.thumbnail((180,66),Image.Resampling.LANCZOS)\n        brand_logo_image=ImageTk.PhotoImage(logo)\n        tk.Label(brand,image=brand_logo_image,bg=C["sidebar"],bd=0).pack(side="left")\n    except Exception:\n        tk.Label(brand,text="Lucas",font=(FONT,15,"bold"),fg=C["text"],bg=C["sidebar"]).pack(side="left")'''
settings = replace_once(settings, old_brand, new_brand, "settings brand")
settings_path.write_text(settings, encoding="utf-8")


# Tray icon branding, preserving a small live status indicator.
tray_path = ROOT / "src/gpt_windows_connector/tray.py"
tray = tray_path.read_text(encoding="utf-8")
pattern = re.compile(r"    def _make_icon\(self, status: str\) -> Any:\n.*?\n    def _refresh_icon", re.S)
replacement = '''    def _make_icon(self, status: str) -> Any:\n        from PIL import Image, ImageDraw\n        asset = Path(__file__).with_name("assets") / "lucas-logo-square.png"\n        source = Image.open(asset).convert("RGBA")\n        source.thumbnail((58, 58), Image.Resampling.LANCZOS)\n        image = Image.new("RGBA", (64, 64), (255, 255, 255, 0))\n        image.alpha_composite(source, ((64 - source.width) // 2, (64 - source.height) // 2))\n        palette = {\n            "Online": (33, 180, 92, 255),\n            "Connecting": (245, 166, 35, 255),\n            "Reconnecting": (245, 166, 35, 255),\n            "Disconnected": (120, 126, 137, 255),\n            "Offline": (120, 126, 137, 255),\n        }\n        draw = ImageDraw.Draw(image)\n        draw.ellipse((46, 46, 63, 63), fill=(255, 255, 255, 255))\n        draw.ellipse((49, 49, 60, 60), fill=palette.get(status, palette["Offline"]))\n        return image\n\n    def _refresh_icon'''
tray, count = pattern.subn(replacement, tray, count=1)
if count != 1:
    raise RuntimeError(f"tray icon: expected 1 match, found {count}")
tray_path.write_text(tray, encoding="utf-8")


# Every Node-facing code change gets a real version bump so installed Nodes can update.
project_path = ROOT / "pyproject.toml"
project = project_path.read_text(encoding="utf-8")
project, count = re.subn(r'(?m)^version = "1\.7\.4"$', 'version = "1.7.5"', project, count=1)
if count != 1:
    raise RuntimeError("expected current version 1.7.4")
project_path.write_text(project, encoding="utf-8")

print("Lucas branding applied; Node version bumped to 1.7.5")
