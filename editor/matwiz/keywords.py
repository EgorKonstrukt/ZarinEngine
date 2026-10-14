# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

_ALBEDO_KEYWORDS = ("albedo", "diffuse", "base_color", "basecolor", "color", "basecolor",
                     "base_map", "basemap", "tint", "bedo")
_NORMAL_KEYWORDS = ("normal", "nrm", "nrm_map", "normal_map", "norm", "ntex")
_METALLIC_KEYWORDS = ("metallic", "metal", "met", "metalness")
_ROUGHNESS_KEYWORDS = ("roughness", "rough", "rgh")
_SMOOTHNESS_KEYWORDS = ("smoothness", "smooth", "gloss", "glossiness", "specular")
_AO_KEYWORDS = ("ao", "ambient_occlusion", "occlusion", "occ", "lightmap")
_EMISSION_KEYWORDS = ("emission", "emissive", "emit", "glow", "self_illum")
_HEIGHT_KEYWORDS = ("height", "displacement", "disp", "depth", "parallax", "hgt")
_DETAIL_ALBEDO_KEYWORDS = ("detail_albedo", "detail_color", "detail_diffuse", "detail_base")
_DETAIL_NORMAL_KEYWORDS = ("detail_normal", "detail_nrm")
_CLEARCOAT_KEYWORDS = ("clearcoat", "clear_coat", "clear")
_SUBSURFACE_KEYWORDS = ("subsurface", "sss", "translucency", "backlight")
_THIN_FILM_KEYWORDS = ("thin_film", "thin film", "iridescence")
_CHANNEL_HINTS = {
    "metallic": "_Metallic",
    "roughness": "_Smoothness",
    "smoothness": "_Smoothness",
    "ao": "_OcclusionMap",
}
_PRIORITY_ORDER = [
    (_DETAIL_ALBEDO_KEYWORDS, "_DetailAlbedoMap"),
    (_DETAIL_NORMAL_KEYWORDS, "_DetailNormalMap"),
    (_ALBEDO_KEYWORDS, "_BaseMap"),
    (_NORMAL_KEYWORDS, "_NormalMap"),
    (_METALLIC_KEYWORDS, "_Metallic"),
    (_ROUGHNESS_KEYWORDS, "_Smoothness"),
    (_SMOOTHNESS_KEYWORDS, "_Smoothness"),
    (_AO_KEYWORDS, "_OcclusionMap"),
    (_EMISSION_KEYWORDS, "_EmissionMap"),
    (_HEIGHT_KEYWORDS, "_HeightMap"),
    (_CLEARCOAT_KEYWORDS, "_ClearCoat"),
    (_SUBSURFACE_KEYWORDS, "_SubsurfaceColor"),
    (_THIN_FILM_KEYWORDS, "_ThinFilmThickness"),
]
