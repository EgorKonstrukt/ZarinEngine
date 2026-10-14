# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from .fit import FitMode, register_fit_mode, get_fit_modes, get_fit_mode
from .fit import _gaussian_fit, _gaussian_formula, _logistic_fit, _logistic_formula, _double_exp_fit
from .fit import _exp_fit, _exp_formula, _power_fit, _power_formula, _log_fit, _log_formula
from .fit import _sinusoidal_fit, _moving_average_fit
from .fit import _fit_linear_origin, _formula_linear_origin, _fit_linear, _formula_linear
from .fit import _make_poly_fit, _make_poly_formula
from .fit import _fit_pchip, _fit_cubic_spline, _fit_exp, _fit_power, _fit_log
from .fit import _fit_gaussian, _fit_logistic, _fit_double_exp, fmt
from .stats import derivative, second_derivative, cumulative_integral
from .stats import fft_spectrum, fft_spectrum_numpy, histogram, autocorrelation
from .stats import normalize, peak_find, weighted_mean, moving_std
from .stats import linspace, _sort_unique, _gauss_solve, _polyfit, _polyval
from .stats import _pchip_eval, _cubic_spline_eval
from .stats import trapezoid_integral, rms, percentile, correlation, r_squared
from .stats import nice_ticks, nice_log_ticks, to_log, decimated

__all__ = ["FitMode", "register_fit_mode", "get_fit_modes", "get_fit_mode",
    "derivative", "second_derivative", "cumulative_integral",
    "fft_spectrum", "fft_spectrum_numpy", "histogram", "autocorrelation",
    "normalize", "peak_find", "weighted_mean", "moving_std",
    "linspace", "trapezoid_integral", "rms", "percentile", "correlation", "r_squared",
    "nice_ticks", "nice_log_ticks", "to_log", "decimated", "fmt", "_sort_unique"]
