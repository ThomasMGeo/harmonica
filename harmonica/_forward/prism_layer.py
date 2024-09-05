# Copyright (c) 2018 The Harmonica Developers.
# Distributed under the terms of the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause
#
# This code is part of the Fatiando a Terra project (https://www.fatiando.org)
#
"""
Define a layer of prisms
"""
from typing import Callable
import warnings

import numpy as np
from numpy.typing import NDArray
import verde as vd
import xarray as xr

from ..visualization import prism_to_pyvista
from .prism_gravity import prism_gravity, FIELDS

from numba import jit, prange


def prism_layer(
    coordinates,
    surface,
    reference,
    properties=None,
):
    """
    Create a layer of prisms of equal size

    Build a regular grid of prisms of equal size on the horizontal directions
    with variable top and bottom boundaries and properties like density,
    magnetization, etc. The function returns a :class:`xarray.Dataset`
    containing ``easting``, ``northing``, ``top`` and ``bottom`` coordinates,
    and all physical properties as ``data_var`` s. The ``easting`` and
    ``northing`` coordinates correspond to the location of the center of each
    prism.

    The ``prism_layer`` dataset accessor can be used to access special methods
    and attributes for the layer of prisms, like the horizontal dimensions of
    the prisms, getting the boundaries of each prisms, etc.
    See :class:`DatasetAccessorPrismLayer` for the definition of these methods
    and attributes.

    Parameters
    ----------
    coordinates : tuple
        List containing the coordinates of the centers of the prisms in the
        following order: ``easting``, ``northing``. The arrays must be 1d
        arrays containing the coordinates of the centers per axis, or could be
        2d arrays as the ones returned by :func:`numpy.meshgrid`. All
        coordinates should be in meters and should define a regular grid.
    surface : 2d-array
        Array used to create the uppermost boundary of the prisms layer. All
        heights should be in meters. On every point where ``surface`` is below
        ``reference``, the ``surface`` value will be used to set the
        ``bottom`` boundary of that prism, while the ``reference`` value will
        be used to set the ``top`` boundary of the prism.
    reference : float or 2d-array
        Reference surface used to create the lowermost boundary of the prisms
        layer. It can be either a plane or an irregular surface passed as 2d
        array. Height(s) must be in meters.
    properties : dict or None
        Dictionary containing the physical properties of the prisms. The keys
        must be strings that will be used to name the corresponding ``data_var``
        inside the :class:`xarray.Dataset`, while the values must be 2d-arrays.
        All physical properties must be passed in SI units. If None, no
        ``data_var`` will be added to the :class:`xarray.Dataset`. Default is
        None.

    Returns
    -------
    dataset : :class:`xarray.Dataset`
        Dataset containing the coordinates of the center of each prism, the
        height of its top and bottom boundaries and its corresponding physical
        properties.

    See also
    --------
    harmonica.DatasetAccessorPrismLayer

    Examples
    --------

    >>> # Create a synthetic relief
    >>> import numpy as np
    >>> easting = np.linspace(0, 10, 5)
    >>> northing = np.linspace(2, 8, 4)
    >>> surface = np.arange(20, dtype=float).reshape((4, 5))
    >>> density = 2670.0 * np.ones_like(surface)
    >>> # Define a layer of prisms
    >>> prisms = prism_layer(
    ...     (easting, northing),
    ...     surface,
    ...     reference=0,
    ...     properties={"density": density},
    ... )
    >>> print(prisms) # doctest: +SKIP
    <xarray.Dataset>
    Dimensions:   (northing: 4, easting: 5)
    Coordinates:
      * easting   (easting) float64 0.0 2.5 5.0 7.5 10.0
      * northing  (northing) float64 2.0 4.0 6.0 8.0
        top       (northing, easting) float64 0.0 1.0 2.0 3.0 ... 17.0 18.0 19.0
        bottom    (northing, easting) float64 0.0 0.0 0.0 0.0 ... 0.0 0.0 0.0 0.0
    Data variables:
        density   (northing, easting) float64 2.67e+03 2.67e+03 ... 2.67e+03
    Attributes:
        coords_units:      meters
        properties_units:  SI
    >>> # Get the boundaries of the layer (will exceed the region)
    >>> boundaries = prisms.prism_layer.boundaries
    >>> list(float(b) for b in boundaries)
    [-1.25, 11.25, 1.0, 9.0]
    >>> # Get the boundaries of one of the prisms
    >>> prism = prisms.prism_layer.get_prism((0, 2))
    >>> list(float(b) for b in prism)
    [3.75, 6.25, 1.0, 3.0, 0.0, 2.0]
    """  # noqa: W505
    dims = ("northing", "easting")
    # Initialize data and data_names as None
    data, data_names = None, None
    # If properties were passed, then replace data_names and data for its keys
    # and values, respectively
    if properties:
        data_names = tuple(p for p in properties.keys())
        data = tuple(np.asarray(p) for p in properties.values())
    # Create xr.Dataset for prisms
    prisms = vd.make_xarray_grid(
        coordinates, data=data, data_names=data_names, dims=dims
    )
    _check_regular_grid(prisms.easting.values, prisms.northing.values)
    # Append some attributes to the xr.Dataset
    attrs = {"coords_units": "meters", "properties_units": "SI"}
    prisms.attrs = attrs
    # Create the top and bottom coordinates of the prisms
    prisms.prism_layer.update_top_bottom(surface, reference)
    return prisms


def _check_regular_grid(easting, northing):
    """
    Check if the easting and northing coordinates define a regular grid

    .. note:

        This function should live inside Verde in the future
    """
    if not np.allclose(easting[1] - easting[0], easting[1:] - easting[:-1]):
        raise ValueError("Passed easting coordinates are not evenly spaced.")
    if not np.allclose(northing[1] - northing[0], northing[1:] - northing[:-1]):
        raise ValueError("Passed northing coordinates are not evenly spaced.")


@xr.register_dataset_accessor("prism_layer")
class DatasetAccessorPrismLayer:
    """
    Defines dataset accessor for layer of prisms

    .. warning::

        This class is not intended to be initialized.
        Use the `prism_layer` accessor for accessing the methods and
        attributes of this class.

    See also
    --------
    harmonica.prism_layer
    """

    def __init__(self, xarray_obj):
        self._obj = xarray_obj

    @property
    def dims(self):
        """
        Return the dims tuple of the prism layer

        The tuple follows the xarray order: ``"northing"``, ``"easting"``.
        """
        return ("northing", "easting")

    @property
    def spacing(self):
        """
        Spacing between center of prisms

        Returns
        -------
        s_north : float
            Spacing between center of prisms on the South-North direction.
        s_east : float
            Spacing between center of prisms on the West-East direction.
        """
        easting, northing = self._obj.easting.values, self._obj.northing.values
        _check_regular_grid(easting, northing)
        s_north, s_east = northing[1] - northing[0], easting[1] - easting[0]
        return s_north, s_east

    @property
    def boundaries(self):
        """
        Boundaries of the layer

        Returns
        -------
        boundaries : tuple
            Boundaries of the layer of prisms in the following order: ``west``,
            ``east``, ``south``, ``north``.
        """
        s_north, s_east = self.spacing
        west = self._obj.easting.values.min() - s_east / 2
        east = self._obj.easting.values.max() + s_east / 2
        south = self._obj.northing.values.min() - s_north / 2
        north = self._obj.northing.values.max() + s_north / 2
        return west, east, south, north

    @property
    def size(self):
        """
        Return the total number of prisms on the layer

        Returns
        -------
        size : int
            Total number of prisms in the layer.
        """
        return self._obj.northing.size * self._obj.easting.size

    @property
    def shape(self):
        """
        Return the number of prisms on each direction

        Returns
        -------
        n_north : int
            Number of prisms on the South-North direction.
        n_east : int
            Number of prisms on the West-East direction.
        """
        return (self._obj.northing.size, self._obj.easting.size)

    def _get_prism_horizontal_boundaries(self, easting, northing):
        """
        Compute the horizontal boundaries of the prism

        Parameters
        ----------
        easting : float or array
            Easting coordinate of the center of the prism
        northing : float or array
            Northing coordinate of the center of the prism
        """
        spacing = self.spacing
        west = easting - spacing[1] / 2
        east = easting + spacing[1] / 2
        south = northing - spacing[0] / 2
        north = northing + spacing[0] / 2
        return west, east, south, north

    def update_top_bottom(self, surface, reference):
        """
        Update top and bottom boundaries of the layer

        Change the values of the ``top`` and ``bottom`` coordinates based on
        the passed ``surface`` and ``reference``. The ``top`` and ``bottom``
        boundaries of every
        prism will be equal to the corresponding ``surface`` and ``reference``
        values, respectively, if ``surface`` is above the ``reference`` on that
        point. Otherwise the ``top`` and ``bottom`` boundaries of the prism
        will be equal to its corresponding ``reference`` and ``surface``,
        respectively.

        Parameters
        ----------
        surface : 2d-array
            Array used to create the uppermost boundary of the prisms layer.
            All heights should be in meters. On every point where ``surface``
            is below ``reference``, the ``surface`` value will be used to set
            the ``bottom`` boundary of that prism, while the ``reference``
            value will be used to set the ``top`` boundary of the prism.
        reference : float or 2d-array
            Reference surface used to create the lowermost boundary of the
            prisms layer. It can be either a plane or an irregular surface
            passed as 2d array. Height(s) must be in meters.
        """
        surface, reference = np.asarray(surface), np.asarray(reference)
        if surface.shape != self.shape:
            raise ValueError(
                f"Invalid surface array with shape '{surface.shape}'. "
                + "Its shape should be compatible with the coordinates "
                + "of the layer of prisms."
            )
        if reference.ndim != 0:
            if reference.shape != self.shape:
                raise ValueError(
                    f"Invalid reference array with shape '{reference.shape}'. "
                    + "Its shape should be compatible with the coordinates "
                    + "of the layer of prisms."
                )
        else:
            reference = reference * np.ones(self.shape)
        top = surface.copy()
        bottom = reference.copy()
        reverse = surface < reference
        top[reverse] = reference[reverse]
        bottom[reverse] = surface[reverse]
        self._obj.coords["top"] = (self.dims, top)
        self._obj.coords["bottom"] = (self.dims, bottom)

    def gravity_coarser(
        self,
        coordinates,
        field,
        fine_distance: float,
        factor: int = 2,
        density_name="density",
    ):
        cast = np.broadcast(*coordinates[:3])
        result = np.zeros(cast.size, dtype=np.float64)
        coordinates = tuple(np.atleast_1d(i).ravel() for i in coordinates[:3])
        _check_regular_grid(self._obj.easting.values, self._obj.northing.values)
        gravity_coarser(
            coordinates,
            self._obj.easting.values,
            self._obj.northing.values,
            self._obj.bottom.values,
            self._obj.top.values,
            self._obj[density_name].values,
            FIELDS[field],
            fine_distance,
            factor,
            result,
        )
        # Invert sign of gravity_u, gravity_eu, gravity_nu
        if field in ("g_z", "g_ez", "g_nz"):
            result *= -1
        # Convert to more convenient units
        if field in ("g_e", "g_n", "g_z"):
            result *= 1e5  # SI to mGal
        # Convert to more convenient units
        if field in ("g_ee", "g_nn", "g_zz", "g_en", "g_ez", "g_nz"):
            result *= 1e9  # SI to Eotvos
        return result.reshape(cast.shape)

    def gravity(
        self,
        coordinates,
        field,
        progressbar=False,
        density_name="density",
        thickness_threshold=None,
        **kwargs,
    ):
        """
        Computes the gravity generated by the layer of prisms

        Uses :func:`harmonica.prism_gravity` for computing the gravity field
        generated by the prisms of the layer.
        The density of the prisms will be assigned from the ``data_var`` chosen
        through the ``density_name`` argument.
        Ignores the prisms which ``top`` or ``bottom`` boundaries are
        ``np.nan``s.
        Prisms thinner than a given threshold can be optionally ignored through
        the ``thickness_threshold`` argument.
        All ``kwargs`` will be passed to :func:`harmonica.prism_gravity`.

        Parameters
        ----------
        coordinates : list of arrays
            List of arrays containing the ``easting``, ``northing`` and
            ``upward`` coordinates of the computation points defined on
            a Cartesian coordinate system. All coordinates should be in meters.
        field : str
            Gravitational field that wants to be computed.
            The available fields are:
            - Gravitational potential: ``potential``
            - Eastward acceleration: ``g_e``
            - Northward acceleration: ``g_n``
            - Downward acceleration: ``g_z``
            - Diagonal tensor components: ``g_ee``, ``g_nn``, ``g_zz``
            - Non-diagonal tensor components: ``g_en``, ``g_ez``, ``g_nz``
        progressbar : bool (optional)
            If True, a progress bar of the computation will be printed to
            standard error (stderr). Requires :mod:`numba_progress` to be
            installed. Default to ``False``.
        density_name : str (optional)
            Name of the property layer (or ``data_var`` of the
            :class:`xarray.Dataset`) that will be used for the density of each
            prism in the layer. Default to ``"density"``
        thickness_threshold : float or None
            Prisms thinner than this threshold will be ignored in the
            forward gravity calculation. If None, every prism with non-zero
            volume will be considered. Default to None.

        Returns
        -------
        result : array
            Gravitational potential is returned in :math:`\text{J}/\text{kg}`,
            acceleration components in mGal, and tensor components in Eotvos.

        See also
        --------
        harmonica.prism_gravity
        """
        # Get boundaries and density of the prisms
        boundaries = self._to_prisms()
        density = self._obj[density_name].values
        # Get the mask for selecting only the prisms whose top boundary, bottom
        # boundary and density have no nans
        mask = self._get_nonans_mask(property_name=density_name)
        # Select only the boundaries and density elements for masked prisms
        boundaries = boundaries[mask.ravel()]
        density = density[mask]
        # Discard thin prisms and their densities
        if thickness_threshold is not None:
            boundaries, density = _discard_thin_prisms(
                boundaries,
                density,
                thickness_threshold,
            )
        # Return gravity field of prisms
        return prism_gravity(
            coordinates,
            prisms=boundaries,
            density=density,
            field=field,
            progressbar=progressbar,
            **kwargs,
        )

    def _get_nonans_mask(self, property_name=None):
        """
        Build a mask for prisms with no nans on top, bottom or a property

        Parameters
        ----------
        property_name : str (optional)
            Name of the property layer (or ``data_var`` of the
            :class:`xarray.Dataset`) that will be used for masking the prisms
            in the layer.

        Returns
        -------
        mask : 2d-array
            Array of bools that can be used as a mask for selecting prisms with
            no nans on top boundaries, bottom boundaries and the passed
            property.
        """
        # Mask the prisms that contains no nans on top and bottom boundaries
        mask = np.logical_and(
            np.logical_not(np.isnan(self._obj.top.values)),
            np.logical_not(np.isnan(self._obj.bottom.values)),
        )
        # Mask the prisms that contains nans on the selected property
        if property_name is not None:
            mask_property = np.logical_not(np.isnan(self._obj[property_name].values))
            # Warn if a nan is found within the masked property
            if not mask_property[mask].all():
                warnings.warn(
                    f"Found missing values in '{property_name}' property "
                    + "of the prisms layer. The prisms with a nan as "
                    + f"'{property_name}' will be ignored.",
                    stacklevel=1,
                )
            mask = np.logical_and(mask, mask_property)
        return mask

    def _to_prisms(self):
        """
        Return the boundaries of each prism of the layer

        Returns
        -------
        prisms : 2d-array
            Array containing the boundaries of each prism of the layer.
            Each row contains the boundaries of each prism in the following
            order: ``west``, ``east``, ``south``, ``north``, ``bottom``,
            ``top``.
        """
        easting, northing = np.meshgrid(
            self._obj.easting.values, self._obj.northing.values
        )
        west, east, south, north = self._get_prism_horizontal_boundaries(
            easting.ravel(), northing.ravel()
        )
        bottom = self._obj.bottom.values.ravel()
        top = self._obj.top.values.ravel()
        prisms = np.vstack((west, east, south, north, bottom, top)).T
        return prisms

    def get_prism(self, indices):
        """
        Return the boundaries of the chosen prism

        Parameters
        ----------
        indices : tuple
            Indices of the desired prism of the layer in  the following order:
            ``(index_northing, index_easting)``.

        Returns
        -------
        prism : tuple
           Boundaries of the prisms in the following order:
           ``west``, ``east``, ``south``, ``north``, ``bottom``, ``top``.
        """
        # Get the center of the prism
        center_easting = self._obj.easting.values[indices[1]]
        center_northing = self._obj.northing.values[indices[0]]
        # Calculate the boundaries of the prism
        west, east, south, north = self._get_prism_horizontal_boundaries(
            center_easting, center_northing
        )
        bottom = self._obj.bottom.values[indices]
        top = self._obj.top.values[indices]
        return west, east, south, north, bottom, top

    def to_pyvista(self, drop_null_prisms=True):
        """
        Return a pyvista UnstructuredGrid to plot the PrismLayer

        Parameters
        ----------
        drop_null_prisms : bool (optional)
            If True, prisms with zero volume or with any :class:`numpy.nan` as
            their top or bottom boundaries won't be included in the
            :class:`pyvista.UnstructuredGrid`.
            If False, every prism in the layer will be included.
            Default True.

        Returns
        -------
        pv_grid : :class:`pyvista.UnstructuredGrid`
            :class:`pyvista.UnstructuredGrid` containing each prism of the
            layer as a hexahedron along with their properties.
        """
        prisms = self._to_prisms()
        null_prisms = np.zeros_like(prisms[:, 0], dtype=bool)
        if drop_null_prisms:
            bottom, top = prisms[:, -2], prisms[:, -1]
            null_prisms = (top == bottom) | (np.isnan(top)) | (np.isnan(bottom))
            prisms = prisms[np.logical_not(null_prisms)]
        # Define properties
        properties = None
        if self._obj.data_vars:
            properties = {
                data_var: np.asarray(self._obj[data_var]).ravel()[
                    np.logical_not(null_prisms)
                ]
                for data_var in self._obj.data_vars
            }
        return prism_to_pyvista(prisms, properties=properties)


def _discard_thin_prisms(
    prisms,
    density,
    thickness_threshold,
):
    """
    Discard prisms with a thickness below a threshold

    Parameters
    ----------
    prisms : 2d-array
        Array containing the boundaries of the prisms in the following order:
        ``w``, ``e``, ``s``, ``n``, ``bottom``, ``top``.
        The array must have the following shape: (``n_prisms``, 6), where
        ``n_prisms`` is the total number of prisms.
    density : 1d-array
        Array containing the density of each prism in kg/m^3. Must have the
        same size as the number of prisms.
    thickness_threshold : float
        Prisms thinner than this threshold will be discarded.

    Returns
    -------
    prisms : 2d-array
        A copy of the ``prisms`` array that doesn't include the thin prisms.
    density : 1d-array
        A copy of the ``density`` array that doesn't include the density values
        for thin prisms.
    """
    bottom, top = prisms[:, -2], prisms[:, -1]
    # Mark prisms with thickness < threshold  as null prisms
    thickness = top - bottom
    null_prisms = thickness < thickness_threshold
    # Keep only thick prisms and their densities
    prisms = prisms[np.logical_not(null_prisms), :]
    density = density[np.logical_not(null_prisms)]
    return prisms, density


@jit(nopython=True, parallel=True)
def gravity_coarser(
    coordinates: tuple[NDArray, NDArray, NDArray],
    prisms_easting: NDArray,
    prisms_northing: NDArray,
    prisms_bottom: NDArray,
    prisms_top: NDArray,
    prisms_densities: NDArray,
    forward_func: Callable,
    fine_distance: float,
    factor: int,
    out,
):
    # Unpack coordinates
    easting, northing, upward = coordinates
    # Iterate over computation points and prisms
    for k in prange(easting.size):
        out[k] += _gravity_coarser(
            easting[k],
            northing[k],
            upward[k],
            prisms_easting,
            prisms_northing,
            prisms_bottom,
            prisms_top,
            prisms_densities,
            fine_distance,
            factor,
            forward_func,
        )


@jit(nopython=True)
def _gravity_coarser(
    easting: float,
    northing: float,
    upward: float,
    prisms_easting: NDArray,
    prisms_northing: NDArray,
    prisms_bottom: NDArray,
    prisms_top: NDArray,
    prisms_densities: NDArray,
    fine_distance: float,
    factor: int,
    forward_func: Callable,
) -> float:
    """
    Forward model of prism layer coarsening far prisms
    """
    # Get size of finer prisms
    prism_size_easting = prisms_easting[1] - prisms_easting[0]
    prism_size_northing = prisms_northing[1] - prisms_northing[0]

    # Get size of coarser prisms
    spacing_easting = prism_size_easting * factor
    spacing_northing = prism_size_northing * factor

    # Get bounding indices of the finer box
    easting_min, northing_min = prisms_easting.min(), prisms_northing.min()
    i_min = max(int((easting - easting_min - fine_distance) // spacing_easting), 0)
    i_max = min(
        int((easting - easting_min + fine_distance) // spacing_easting + 1),
        prisms_easting.size,
    )
    j_min = max(int((northing - northing_min - fine_distance) // spacing_northing), 0)
    j_max = min(
        int((northing - northing_min + fine_distance) // spacing_northing + 1),
        prisms_northing.size,
    )

    # Forward model the finer grid
    result = 0
    for i in range(i_min, i_max):
        west = prisms_easting[i] - prism_size_easting / 2
        east = prisms_easting[i] + prism_size_easting / 2
        for j in range(j_min, j_max):
            south = prisms_northing[j] - prism_size_northing / 2
            north = prisms_northing[j] + prism_size_northing / 2
            bottom = prisms_bottom[j, i]
            top = prisms_top[j, i]
            density = prisms_densities[j, i]
            result += forward_func(
                easting,
                northing,
                upward,
                west,
                east,
                south,
                north,
                bottom,
                top,
                density,
            )

    # Forward model the coarser grid
    for i in range(0, prisms_easting.size, factor):
        west = prisms_easting[i] - 0.5 * prism_size_easting
        east = prisms_easting[i] + (factor - 0.5) * prism_size_easting
        for j in range(0, prisms_northing.size, factor):
            if i_min <= i < i_max and j_min <= j < j_max:
                continue
            south = prisms_northing[j] - 0.5 * prism_size_northing
            north = prisms_northing[j] + (factor - 0.5) * prism_size_northing
            bottom = np.mean(prisms_bottom[j : j + factor, i : i + factor])
            top = np.mean(prisms_top[j : j + factor, i : i + factor])
            density = np.mean(prisms_densities[j : j + factor, i : i + factor])
            if np.isnan(density):
                continue
            result += forward_func(
                easting,
                northing,
                upward,
                west,
                east,
                south,
                north,
                bottom,
                top,
                density,
            )
    return result
