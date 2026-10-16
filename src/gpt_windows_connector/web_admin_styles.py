"""Scoped mobile Admin layout without clipping controls or changing behavior."""
from __future__ import annotations

ADMIN_RESPONSIVE_STYLE = r'''<style>
@media(max-width:850px){
  #admin .toolbar{flex-wrap:wrap}
  #admin .toolbar>.input,#admin .toolbar>select{min-width:0;max-width:100%}
}
</style>'''
