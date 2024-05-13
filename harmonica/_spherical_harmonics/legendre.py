# Copyright (c) 2018 The Harmonica Developers.
# Distributed under the terms of the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause
#
# This code is part of the Fatiando a Terra project (https://www.fatiando.org)
#
"""
Calculation of associated Legendre functions and their derivatives.
"""
import numba
import numpy as np


@numba.jit(nopython=True)
def assoc_legendre(x, max_degree):
    """
    Unnormalized associated Legendre functions up to a maximum degree.

    The functions :math:`P_n^m` are solutions to Legendre's equation. We
    calculate their values using the recursive relations defined in Alken
    (2022).

    .. note::

        This function does not include the Condon-Shortly phase.

    Parameters
    ----------
    x : float
        The argument of :math:`P_n^m(x)`. Must be in the range [-1, 1].
    max_degree : int
        The maximum degree for the calculation.


    Returns
    -------
    p : 2D numpy.array
        Array with the values of :math:`P_n^m(x)` with shape
        ``(max_degree + 1, max_degree + 1)``. The degree n varies with the
        first axis and the order m varies with the second axis. For example,
        :math:`P_2^1(x)` is ``p[n, m]``. Array values where ``m > n`` are set
        to ``numpy.nan``.

    References
    ----------

    Alken, Patrick (2022). GSL Technical Report #1 - GSL-TR-001-20220827 -
      Implementation of associated Legendre functions in GSL.
      https://www.gnu.org/software/gsl/tr/tr001.pdf
    """
    p = np.full((max_degree + 1, max_degree + 1), np.nan)
    sqrt_x = np.sqrt(1 - x**2)
    p[0, 0] = 1
    for n in range(1, max_degree + 1):
        for m in range(0, n - 1):
            a_nm = (2 * n - 1) / (n - m)
            b_nm = -(n + m - 1) / (n - m)
            p[n, m] = a_nm * x * p[n - 1, m] + b_nm * p[n - 2, m]
        c_nm = 2 * n - 1
        p[n][n - 1] = c_nm * x * p[n - 1, n - 1]
        d_nm = 2 * n - 1
        p[n][n] = d_nm * sqrt_x * p[n - 1, n - 1]
    return p


@numba.jit(nopython=True)
def assoc_legendre_deriv(x, p):
    """
    Derivatives in theta of unnormalized associated Legendre functions.

    Calculates the derivative:

    .. math::

        \\dfrac{\\partial P_n^m}{\\partial \\theta}(\\cos \\theta)

    using the recursive relations defined in Alken (2022).

    Higher-order derivatives can be calculated by passing the output of this
    function as the ``p`` argument.

    .. note::

        This function does not include the Condon-Shortly phase.

    Parameters
    ----------
    x : float
        The argument of :math:`P_n^m(x)`. Must be in the range [-1, 1].
    p : numpy.ndarray
        A 2D array with the unnormalized associated Legendre functions
        calculated for x.

    Returns
    -------
    p_deriv : 2D numpy.array
        Array with the values of the derivative with shape ``(max_degree + 1,
        max_degree + 1)``. The degree n varies with the first axis and the
        order m varies with the second axis. Array values where ``m > n`` are
        set to ``numpy.nan``.

    References
    ----------

    Alken, Patrick (2022). GSL Technical Report #1 - GSL-TR-001-20220827 -
      Implementation of associated Legendre functions in GSL.
      https://www.gnu.org/software/gsl/tr/tr001.pdf
    """
    max_degree = p.shape[0] + 1
    p_deriv = np.full((max_degree + 1, max_degree + 1), np.nan)
    p_deriv[0, 0] = 0
    for n in range(1, max_degree + 1):
        p_deriv[n, 0] = -p[n, 1]
        for m in range(1, n):
            p_deriv[n, m] = 0.5 * ((n + m) * (n - m + 1) * p[n, m - 1] - p[n, m + 1])
        p_deriv[n, n] = n * p[n, n - 1]
    return p_deriv


@numba.jit(nopython=True)
def assoc_legendre_schmidt(x, max_degree):
    """
    Schmidt normalized associated Legendre functions up to maximum degree.

    The functions :math:`P_n^m` are solutions to Legendre's equation. The
    Schmidt normalization is applied to the functions to constrain their value
    range. This normalization if often used in geomagnetic field models. We
    calculate their values using the recursive relations defined in Alken
    (2022).

    .. note::

        This function does not include the Condon-Shortly phase.

    Parameters
    ----------
    x : float
        The argument of :math:`P_n^m(x)`. Must be in the range [-1, 1].
    max_degree : int
        The maximum degree for the calculation.


    Returns
    -------
    p : 2D numpy.array
        Array with the values of :math:`P_n^m(x)` with shape
        ``(max_degree + 1, max_degree + 1)``. The degree n varies with the
        first axis and the order m varies with the second axis. For example,
        :math:`P_2^1(x)` is ``p[n, m]``. Array values where ``m > n`` are set
        to ``numpy.nan``.

    References
    ----------

    Alken, Patrick (2022). GSL Technical Report #1 - GSL-TR-001-20220827 -
      Implementation of associated Legendre functions in GSL.
      https://www.gnu.org/software/gsl/tr/tr001.pdf
    """
    p = np.full((max_degree + 1, max_degree + 1), np.nan)
    sqrt_x = np.sqrt(1 - x**2)
    p[0, 0] = 1
    for n in range(1, max_degree + 1):
        for m in range(0, n - 1):
            a_nm = (2 * n - 1) / np.sqrt((n + m) * (n - m))
            b_nm = -np.sqrt((n + m - 1) * (n - m - 1) / ((n + m) * (n - m)))
            p[n, m] = a_nm * x * p[n - 1, m] + b_nm * p[n - 2, m]
        c_nm = np.sqrt(2 * n - 1)
        p[n][n - 1] = c_nm * x * p[n - 1, n - 1]
        if n == 1:
            d_nm = 1
        else:
            d_nm = np.sqrt(1 - 1 / (2 * n))
        p[n][n] = d_nm * sqrt_x * p[n - 1, n - 1]
    return p


@numba.jit(nopython=True)
def assoc_legendre_full(x, max_degree):
    """
    Fully normalized associated Legendre functions up to maximum degree.

    The functions :math:`P_n^m` are solutions to Legendre's equation. The full
    normalization is applied to the functions to constrain their value range.
    This normalization if often used in gravity field models. We calculate
    their values using the recursive relations defined in Alken (2022).

    .. note::

        This function does not include the Condon-Shortly phase.

    Parameters
    ----------
    x : float
        The argument of :math:`P_n^m(x)`. Must be in the range [-1, 1].
    max_degree : int
        The maximum degree for the calculation.


    Returns
    -------
    p : 2D numpy.array
        Array with the values of :math:`P_n^m(x)` with shape
        ``(max_degree + 1, max_degree + 1)``. The degree n varies with the
        first axis and the order m varies with the second axis. For example,
        :math:`P_2^1(x)` is ``p[n, m]``. Array values where ``m > n`` are set
        to ``numpy.nan``.

    References
    ----------

    Alken, Patrick (2022). GSL Technical Report #1 - GSL-TR-001-20220827 -
      Implementation of associated Legendre functions in GSL.
      https://www.gnu.org/software/gsl/tr/tr001.pdf
    """
    p = np.full((max_degree + 1, max_degree + 1), np.nan)
    sqrt_x = np.sqrt(1 - x**2)
    p[0, 0] = np.sqrt(0.5)
    for n in range(1, max_degree + 1):
        for m in range(0, n - 1):
            a_nm = np.sqrt((2 * n + 1) * (2 * n - 1) / ((n + m) * (n - m)))
            b_nm = -np.sqrt(
                (n + m - 1)
                * (n - m - 1)
                * (2 * n + 1)
                / ((n + m) * (n - m) * (2 * n - 3))
            )
            p[n, m] = a_nm * x * p[n - 1, m] + b_nm * p[n - 2, m]
        c_nm = np.sqrt(2 * n + 1)
        p[n][n - 1] = c_nm * x * p[n - 1, n - 1]
        d_nm = np.sqrt(1 + 1 / (2 * n))
        p[n][n] = d_nm * sqrt_x * p[n - 1, n - 1]
    return p
