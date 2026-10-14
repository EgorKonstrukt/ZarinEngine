# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from core.components.lighting.lightp.light import Light, LightType, LightAreaType, DirectionalLight, PointLight, SpotLight
from core.components.lighting.lightp.shadows import AreaLight, get_for_entity, iter_scene_lights, find_directional
from core.components.lighting.lightp.ibl import _planck_white, point_lumen_to_candela, spot_solid_angle, spot_lumen_to_candela, candela_to_lux, _smoothstep, compute_sun_light, _compute_sun_light_uncached, shader_radiance
Light.get_for_entity = staticmethod(get_for_entity)
Light.iter_scene_lights = staticmethod(iter_scene_lights)
Light.find_directional = staticmethod(find_directional)
Light._planck_white = staticmethod(_planck_white)
Light.point_lumen_to_candela = staticmethod(point_lumen_to_candela)
Light.spot_solid_angle = staticmethod(spot_solid_angle)
Light.spot_lumen_to_candela = staticmethod(spot_lumen_to_candela)
Light.candela_to_lux = staticmethod(candela_to_lux)
Light._smoothstep = staticmethod(_smoothstep)
Light.compute_sun_light = staticmethod(compute_sun_light)
Light._compute_sun_light_uncached = staticmethod(_compute_sun_light_uncached)
Light.shader_radiance = staticmethod(shader_radiance)
LIGHT_TYPES = (DirectionalLight, PointLight, SpotLight, AreaLight)
__all__ = ["Light", "LightType", "LightAreaType", "DirectionalLight", "PointLight", "SpotLight", "AreaLight", "LIGHT_TYPES"]
