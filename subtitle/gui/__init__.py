# -*- coding: utf-8 -*-
import os

# --- Embedded Python Tcl/Tk Fix ---
_base_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_base_dir))
_embed_tcl = os.path.join(_project_root, "python_embed", "Lib", "site-packages", "tcl")
if os.path.exists(_embed_tcl):
    os.environ.setdefault("TCL_LIBRARY", os.path.join(_embed_tcl, "tcl8.6"))
    os.environ.setdefault("TK_LIBRARY", os.path.join(_embed_tcl, "tk8.6"))
