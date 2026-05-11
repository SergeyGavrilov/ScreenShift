"""
First-run setup wizard.

On first launch (no config.json found) the wizard:
  1. Shows connected displays with auto-detected settings
  2. Lets the user configure 3 profiles
  3. Copies the exe to the chosen install directory
  4. Writes config.json
  5. Optionally registers autostart
  6. Launches the installed app and exits

When running from source (not frozen), it skips copying the exe and just
writes config.json next to screenshift.py so the developer can test immediately.
"""

import json
import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from src.autostart import start_menu_shortcut
from src.display import DisplayManager

# ── Defaults ──────────────────────────────────────────────────────────────────

_HOTKEYS = [
    'ctrl+alt+1', 'ctrl+alt+2', 'ctrl+alt+3',
    'ctrl+alt+4', 'ctrl+alt+5',
    'ctrl+shift+1', 'ctrl+shift+2', 'ctrl+shift+3',
]
_PROFILE_NAMES   = ['Work', 'Gaming', 'TV']
_DEFAULT_INSTALL = Path(
    os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))
) / 'ScreenShift'

# Catppuccin Mocha palette
_C = {
    'base':    '#1e1e2e',
    'mantle':  '#181825',
    'surface': '#313244',
    'text':    '#cdd6f4',
    'subtext': '#a6adc8',
    'muted':   '#6c7086',
    'blue':    '#89b4fa',
    'green':   '#a6e3a1',
}


# ── Wizard ────────────────────────────────────────────────────────────────────

class SetupWizard:

    NUM_PROFILES = 3

    def __init__(self):
        self.root = tk.Tk()
        self.root.title('ScreenShift — Setup')
        self.root.geometry('620x540')
        self.root.resizable(False, False)
        self.root.configure(bg=_C['base'])

        self.monitors    = self._detect_monitors()
        self.profile_rows = []   # filled in _build_profile_page
        self.install_path = tk.StringVar(value=str(_DEFAULT_INSTALL))
        self.autostart_var = tk.BooleanVar(value=True)

        self._apply_style()
        self._build_chrome()
        self._build_pages()
        self._show_page(0)

    # ── monitor detection ─────────────────────────────────────────────────────

    def _detect_monitors(self) -> list[dict]:
        result = []
        for d in DisplayManager.list_displays():
            settings = DisplayManager.get_current_settings(d['name']) if d['active'] else None
            result.append({**d, 'settings': settings})
        return result

    # ── UI construction ───────────────────────────────────────────────────────

    def _apply_style(self):
        s = ttk.Style()
        s.theme_use('clam')
        s.configure('TButton',
                    font=('Segoe UI', 10), padding=(12, 6),
                    background=_C['surface'], foreground=_C['text'],
                    borderwidth=0, focuscolor='none')
        s.map('TButton',
              background=[('active', _C['blue']), ('pressed', _C['blue'])],
              foreground=[('active', _C['mantle'])])
        s.configure('TCombobox',
                    fieldbackground=_C['surface'], background=_C['surface'],
                    foreground=_C['text'], arrowcolor=_C['subtext'],
                    selectbackground=_C['surface'], selectforeground=_C['text'])

    def _lbl(self, parent, text, font_size=10, bold=False, color=None, **kw):
        weight = 'bold' if bold else 'normal'
        color  = color or _C['text']
        return tk.Label(parent, text=text, font=('Segoe UI', font_size, weight),
                        bg=parent['bg'], fg=color, **kw)

    def _build_chrome(self):
        # ── header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=_C['mantle'], height=64)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        self._lbl(hdr, 'ScreenShift', 20, bold=True).pack(side='left', padx=20, pady=10)
        self.step_lbl = self._lbl(hdr, '', 9, color=_C['muted'])
        self.step_lbl.pack(side='right', padx=20)

        # ── content ────────────────────────────────────────────────────────────
        self.content = tk.Frame(self.root, bg=_C['base'])
        self.content.pack(fill='both', expand=True)

        # ── footer ────────────────────────────────────────────────────────────
        ftr = tk.Frame(self.root, bg=_C['mantle'], height=54)
        ftr.pack(fill='x', side='bottom')
        ftr.pack_propagate(False)
        self.btn_back = ttk.Button(ftr, text='← Back', command=self._prev)
        self.btn_back.pack(side='left', padx=16, pady=10)
        self.btn_next = ttk.Button(ftr, text='Next →', command=self._next)
        self.btn_next.pack(side='right', padx=16, pady=10)

    def _build_pages(self):
        self.pages = [
            self._build_welcome_page(),
            self._build_monitors_page(),
            self._build_profile_page(),
            self._build_install_page(),
        ]

    # ── page 0: welcome ───────────────────────────────────────────────────────

    def _build_welcome_page(self) -> tk.Frame:
        f = tk.Frame(self.content, bg=_C['base'])
        self._lbl(f, 'Welcome', 18, bold=True).pack(pady=(50, 12))
        self._lbl(f, 'This wizard will set up monitor profiles\nfor instant one-click switching.',
                  11, color=_C['subtext'], justify='center').pack()
        self._lbl(f, f'{len(self.monitors)} display(s) detected on this PC.',
                  10, color=_C['muted']).pack(pady=20)
        return f

    # ── page 1: detected monitors ─────────────────────────────────────────────

    def _build_monitors_page(self) -> tk.Frame:
        f = tk.Frame(self.content, bg=_C['base'])
        self._lbl(f, 'Connected displays', 13, bold=True).pack(anchor='w', padx=25, pady=(20, 8))

        box = tk.Frame(f, bg=_C['mantle'])
        box.pack(fill='x', padx=25)

        if not self.monitors:
            self._lbl(box, 'No displays found.', 10, color=_C['muted']).pack(padx=12, pady=8)

        for m in self.monitors:
            row = tk.Frame(box, bg=_C['mantle'])
            row.pack(fill='x', padx=12, pady=6)
            dot_fg = _C['green'] if m['active'] else _C['muted']
            self._lbl(row, '●', 10, color=dot_fg).pack(side='left')
            dev  = m['name']
            desc = (m['description'][:42] + '…') if len(m['description']) > 42 else m['description']
            res  = ''
            if m['settings']:
                s   = m['settings']
                res = f"  {s['width']}×{s['height']} @ {s['refresh_rate']} Hz"
            tag = '  [primary]' if m['primary'] else ('  [active]' if m['active'] else '  [off]')
            self._lbl(row, f' {dev}  —  {desc}{res}{tag}', 9, color=_C['text']).pack(side='left')

        self._lbl(f, 'Use these names when editing config.json manually.',
                  9, color=_C['muted']).pack(anchor='w', padx=25, pady=(10, 0))
        return f

    # ── page 2: profiles ──────────────────────────────────────────────────────

    def _build_profile_page(self) -> tk.Frame:
        outer = tk.Frame(self.content, bg=_C['base'])
        self._lbl(outer, 'Configure profiles', 13, bold=True).pack(anchor='w', padx=25, pady=(16, 2))
        self._lbl(outer,
                  'Each profile turns on the selected displays and turns off the rest.',
                  9, color=_C['muted']).pack(anchor='w', padx=25)

        canvas  = tk.Canvas(outer, bg=_C['base'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        inner   = tk.Frame(canvas, bg=_C['base'])

        inner.bind('<Configure>',
                   lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=inner, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side='left', fill='both', expand=True, padx=25)
        scrollbar.pack(side='right', fill='y')

        self.profile_rows = []
        for i in range(self.NUM_PROFILES):
            self.profile_rows.append(self._build_one_profile(inner, i))

        return outer

    def _build_one_profile(self, parent, idx: int) -> dict:
        grp = tk.LabelFrame(
            parent,
            text=f'  Profile {idx + 1}  ',
            font=('Segoe UI', 9),
            bg=_C['base'], fg=_C['blue'],
            relief='groove', bd=1, labelanchor='nw',
        )
        grp.pack(fill='x', pady=5, ipady=4)

        top = tk.Frame(grp, bg=_C['base'])
        top.pack(fill='x', padx=8, pady=(4, 2))

        self._lbl(top, 'Name:', 9, color=_C['subtext']).pack(side='left')
        default_name = _PROFILE_NAMES[idx] if idx < len(_PROFILE_NAMES) else f'Profile {idx + 1}'
        name_var = tk.StringVar(value=default_name)
        tk.Entry(top, textvariable=name_var, width=14,
                 font=('Segoe UI', 9), bg=_C['surface'], fg=_C['text'],
                 insertbackground='white', relief='flat').pack(side='left', padx=(4, 16))

        self._lbl(top, 'Hotkey:', 9, color=_C['subtext']).pack(side='left')
        default_hk = _HOTKEYS[idx] if idx < len(_HOTKEYS) else ''
        hk_var = tk.StringVar(value=default_hk)
        ttk.Combobox(top, textvariable=hk_var, values=_HOTKEYS,
                     width=14, font=('Segoe UI', 9)).pack(side='left', padx=4)

        mon_frame = tk.Frame(grp, bg=_C['base'])
        mon_frame.pack(fill='x', padx=8, pady=(2, 4))
        mon_vars = []
        for j, m in enumerate(self.monitors):
            default_on = (j == idx)  # diagonal default: profile 1→display 1, etc.
            var = tk.BooleanVar(value=default_on)
            short = m['name'].replace('\\\\.\\', '')
            if m['settings']:
                s = m['settings']
                short += f" ({s['width']}×{s['height']})"
            tk.Checkbutton(
                mon_frame, text=short, variable=var,
                font=('Segoe UI', 9), bg=_C['base'], fg=_C['text'],
                selectcolor=_C['surface'], activebackground=_C['base'],
                activeforeground=_C['text'],
            ).pack(side='left', padx=(0, 14))
            mon_vars.append(var)

        return {'name_var': name_var, 'hotkey_var': hk_var, 'monitor_vars': mon_vars}

    # ── page 3: install ───────────────────────────────────────────────────────

    def _build_install_page(self) -> tk.Frame:
        f = tk.Frame(self.content, bg=_C['base'])
        self._lbl(f, 'Install', 13, bold=True).pack(anchor='w', padx=25, pady=(25, 16))

        dir_box = tk.Frame(f, bg=_C['base'])
        dir_box.pack(fill='x', padx=25)
        self._lbl(dir_box, 'Install folder:', 10, color=_C['subtext']).pack(anchor='w', pady=(0, 4))
        row = tk.Frame(dir_box, bg=_C['base'])
        row.pack(fill='x')
        tk.Entry(row, textvariable=self.install_path,
                 font=('Segoe UI', 9), bg=_C['surface'], fg=_C['text'],
                 insertbackground='white', relief='flat', width=50
                 ).pack(side='left', ipady=5)
        ttk.Button(row, text='…', width=3, command=self._browse_dir).pack(side='left', padx=6)

        tk.Checkbutton(
            f, text='Launch ScreenShift automatically on Windows startup',
            variable=self.autostart_var,
            font=('Segoe UI', 10), bg=_C['base'], fg=_C['text'],
            selectcolor=_C['surface'], activebackground=_C['base'],
            activeforeground=_C['text'],
        ).pack(anchor='w', padx=25, pady=22)

        note = 'ScreenShift.exe and config.json will be placed in the install folder.'
        self._lbl(f, note, 9, color=_C['muted']).pack(anchor='w', padx=25)
        return f

    # ── navigation ────────────────────────────────────────────────────────────

    def _show_page(self, n: int):
        for p in self.pages:
            p.pack_forget()
        self.pages[n].pack(fill='both', expand=True)
        self.current = n
        total = len(self.pages)
        self.step_lbl.config(text=f'Step {n + 1} of {total}')
        self.btn_back.config(state='normal' if n > 0 else 'disabled')
        self.btn_next.config(text='Install' if n == total - 1 else 'Next →')

    def _prev(self):
        if self.current > 0:
            self._show_page(self.current - 1)

    def _next(self):
        if self.current < len(self.pages) - 1:
            self._show_page(self.current + 1)
        else:
            self._install()

    def _browse_dir(self):
        path = filedialog.askdirectory(title='Select install folder',
                                       initialdir=self.install_path.get())
        if path:
            self.install_path.set(path)

    # ── config builder ────────────────────────────────────────────────────────

    def build_config(self) -> dict:
        """Build config dict from current wizard state. Exposed for testing."""
        profiles = []
        for row in self.profile_rows:
            monitors = {}
            primary_set = False
            for j, m in enumerate(self.monitors):
                enabled = row['monitor_vars'][j].get()
                if enabled:
                    base = m['settings'] or {
                        'width': 1920, 'height': 1080,
                        'refresh_rate': 60,
                    }
                    monitors[m['name']] = {
                        'enabled':    True,
                        'primary':    not primary_set,
                        'width':      base['width'],
                        'height':     base['height'],
                        'refresh_rate': base['refresh_rate'],
                        'position_x': 0,   # always reset to origin for clean single-display switch
                        'position_y': 0,
                    }
                    primary_set = True
                else:
                    monitors[m['name']] = {'enabled': False}
            profiles.append({
                'name':     row['name_var'].get() or f'Profile {len(profiles) + 1}',
                'hotkey':   row['hotkey_var'].get(),
                'monitors': monitors,
            })
        return {'autostart': self.autostart_var.get(), 'profiles': profiles}

    # ── install ───────────────────────────────────────────────────────────────

    def _validate(self) -> bool:
        for i, row in enumerate(self.profile_rows):
            if not any(v.get() for v in row['monitor_vars']):
                messagebox.showwarning(
                    'ScreenShift',
                    f'Profile {i + 1} has no displays enabled.\n'
                    'Enable at least one display per profile.',
                )
                self._show_page(2)
                return False
        return True

    def _install(self):
        if not self._validate():
            return

        frozen = getattr(sys, 'frozen', False)
        install_dir = Path(self.install_path.get()) if frozen else Path(__file__).parent.parent
        config_path = install_dir / 'config.json'
        exe_dst     = install_dir / 'ScreenShift.exe'

        try:
            install_dir.mkdir(parents=True, exist_ok=True)

            if frozen and Path(sys.executable) != exe_dst:
                shutil.copy2(sys.executable, exe_dst)
                start_menu_shortcut()

            with open(config_path, 'w', encoding='utf-8') as fp:
                json.dump(self.build_config(), fp, indent=2, ensure_ascii=False)

            if frozen and self.autostart_var.get():
                import winreg
                key = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Run'
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
                    winreg.SetValueEx(k, 'ScreenShift', 0, winreg.REG_SZ, f'"{exe_dst}"')

            if frozen:
                subprocess.Popen([str(exe_dst)])
                self.root.destroy()
                sys.exit(0)
            else:
                messagebox.showinfo('ScreenShift', f'Config saved to:\n{config_path}')
                self.root.destroy()

        except Exception as exc:
            messagebox.showerror('ScreenShift Setup', f'Installation failed:\n{exc}')

    # ── entry point ───────────────────────────────────────────────────────────

    def run(self):
        self.root.mainloop()


def run_setup():
    SetupWizard().run()
