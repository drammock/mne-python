# -*- coding: utf-8 -*-
"""
.. _projectors-background-tutorial:

Background: projectors and projections
======================================

.. include:: ../../tutorial_links.inc

This tutorial provides background information on :term:`projectors <projector>`
and Signal Space Projection (SSP). As usual we'll start by importing the
modules we need; we'll also define a short function to make it easier to make
several plots that look similar, and define a few colorblind-friendly colors:
"""

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 lgtm[py/unused-import]
from scipy.linalg import svd

blueish = '#004488'
reddish = '#BB5566'
yellowish = '#DDAA33'


def setup_3d_axes():
    ax = plt.axes(projection='3d', aspect='equal')
    ax.view_init(azim=-105, elev=20)
    ax.set_xlabel('x')
    ax.set_ylabel('y')
    ax.set_zlabel('z')
    ax.set_xlim(-1, 5)
    ax.set_ylim(-1, 5)
    ax.set_zlim(0, 5)
    return ax

###############################################################################
# What is a projection?
# ^^^^^^^^^^^^^^^^^^^^^
#
# In the most basic terms, a *projection* is an operation that converts one set
# of points into another set of points, where repeating the projection
# operation on the resulting points has no effect. To give a simple geometric
# example, imagine the point :math:`(3, 2, 5)` in 3-dimensional space. A
# projection of that point onto the :math:`x, y` plane looks a lot like a
# shadow cast by that point if the sun were directly above it:

ax = setup_3d_axes()

# plot the vector (3, 2, 5)
origin = np.zeros((3, 1))
point = np.array([[3, 2, 5]]).T
vector = np.hstack([origin, point])
ax.plot(*vector, color='k')
ax.plot(*point, color='k', marker='o')

# project the vector onto the x,y plane and plot it
xy_projection_matrix = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 0]])
projected_point = xy_projection_matrix @ point
projected_vector = xy_projection_matrix @ vector
ax.plot(*projected_vector, color=blueish)
ax.plot(*projected_point, color=blueish, marker='o')

# add dashed arrow showing projection
arrow_coords = np.concatenate([point, projected_point - point]).flatten()
ax.quiver3D(*arrow_coords, length=0.96, arrow_length_ratio=0.1, color=reddish,
            linewidth=1, linestyle='dashed')

###############################################################################
#
# .. note::
#
#     The ``@`` symbol indicates matrix multiplication on NumPy arrays, and was
#     introduced in Python 3.5 / NumPy 1.10. The notation ``plot(*point)`` uses
#     Python `argument expansion`_ to "unpack" the elements of ``point`` into
#     separate positional arguments to the function. In other words,
#     ``plot(*point)`` expands to ``plot(3, 2, 5)``.
#
# Notice that we used matrix multiplication to compute the projection of our
# point :math:`(3, 2, 5)`onto the :math:`x, y` plane:
#
# .. math::
#
#     \left[
#       \begin{matrix} 1 & 0 & 0 \\ 0 & 1 & 0 \\ 0 & 0 & 0 \end{matrix}
#     \right]
#     \left[ \begin{matrix} 3 \\ 5 \\ 7 \end{matrix} \right] =
#     \left[ \begin{matrix} 3 \\ 5 \\ 0 \end{matrix} \right]
#
# ...and that applying the projection again to the result just gives back the
# result again:
#
# .. math::
#
#     \left[
#       \begin{matrix} 1 & 0 & 0 \\ 0 & 1 & 0 \\ 0 & 0 & 0 \end{matrix}
#     \right]
#     \left[ \begin{matrix} 3 \\ 5 \\ 0 \end{matrix} \right] =
#     \left[ \begin{matrix} 3 \\ 5 \\ 0 \end{matrix} \right]
#
# From an information perspective, this projection has taken the point
# :math:`x, y, z` and removed the information about how far in the :math:`z`
# direction our point was located; all we know now is its position in the
# :math:`x, y` plane. Moreover, applying our projection matrix to *any point*
# in :math:`x, y, z` space will reduce it to a corresponding point on the
# :math:`x, y` plane. The term for this is a *subspace*: the projection matrix
# projects points in the original space into a *subspace* of lower dimension
# than the original. The reason our subspace is the :math:`x,y` plane (instead
# of, say, the :math:`y,z` plane) is a direct result of the particular values
# in our projection matrix.
#
# Another way to describe this "loss of information" or "projection into a
# subspace" is to say that projection reduces the rank (or "degrees of
# freedom") of the measurement — here, from 3 dimensions down to 2. On the
# other hand, if you know that measurement component in the :math:`z` direction
# is just noise due to your measurement method, and all you care about are the
# :math:`x` and :math:`y` components, then projecting your 3-dimensional
# measurement into the :math:`x, y` plane could be seen as a form of noise
# reduction.
#
# Of course, it would be very lucky indeed if all the measurement noise were
# concentrated in the :math:`z` direction; you could just discard the :math:`z`
# component without bothering to construct a projection matrix or do the matrix
# multiplication. Suppose instead that in order to take that measurement you
# had to pull a trigger on a measurement device, and the act of pulling the
# trigger causes the device to move a little. If you measure how
# trigger-pulling affects measurement device position, you could then "correct"
# your real measurements to "project out" the effect of the trigger pulling.
# Here we'll suppose that the average effect of the trigger is to move the
# measurement device by :math:`(3, -1, 1)`:

trigger_effect = np.array([[3, -1, 1]]).T

###############################################################################
# Knowing that, we can compute a plane that is orthogonal to the effect of the
# trigger, and project our real measurements onto that plane:

# compute the plane orthogonal to trigger_effect
xx, yy = np.meshgrid(np.linspace(-1, 5, 61), np.linspace(-1, 5, 61))
zz = (-trigger_effect[0] * xx - trigger_effect[1] * yy) / trigger_effect[2]
# cut off the plane below z=0 (just to make the plot nicer)
mask = np.where(zz >= 0)
xx = xx[mask]
yy = yy[mask]
zz = zz[mask]

# plot the trigger effect and its orthogonal plane
ax = setup_3d_axes()
ax.plot_trisurf(xx, yy, zz, color=yellowish, shade=False, alpha=0.25)
ax.quiver3D(*np.concatenate([origin, trigger_effect]).flatten(),
            arrow_length_ratio=0.1, color=yellowish, alpha=0.5)

# plot the original vector
ax.plot(*vector, color='k')
ax.plot(*point, color='k', marker='o')

# compute the projection matrix
U, S, V = svd(trigger_effect, full_matrices=False)
trigger_projection_matrix = np.eye(3, 3) - U @ U.T

# project the vector onto the orthogonal plane and plot it
projected_point = trigger_projection_matrix @ point
projected_vector = trigger_projection_matrix @ vector
ax.plot(*projected_vector, color=blueish)
ax.plot(*projected_point, color=blueish, marker='o')

# add dashed arrow showing projection
arrow_coords = np.concatenate([point, projected_point - point]).flatten()
ax.quiver3D(*arrow_coords, length=0.96, arrow_length_ratio=0.1,
            color=reddish, linewidth=1, linestyle='dashed')

###############################################################################
# Just as before, the projection matrix will map *any point* in :math:`x, y, z`
# space onto that plane, and once a point has been projected onto that plane,
# applying the projection again will have no effect. For that reason, it should
# be clear that although the projected points vary in all three :math:`x`,
# :math:`y`, and :math:`z` directions, the set of projected points have only
# two *effective* dimensions (i.e., they are constrained to a plane).
#
# Projections of EEG or MEG signals work in very much the same way: the point
# :math:`x, y, z` corresponds to the value of each sensor at a single time
# point, and the projection matrix varies depending on what aspects of the
# signal (i.e., what kind of noise) you are trying to project out. The only
# real difference is that instead of a single 3-dimensional point :math:`(x, y,
# z)` you're dealing with a time series of :math:`N`-dimensional "points" (one
# at each sampling time), where :math:`N` is usually in the tens or hundreds
# (depending on how many sensors your EEG/MEG system has). Fortunately, because
# projection is a matrix operation, it can be done very quickly even on signals
# with hundreds of dimensions and tens of thousands of time points.
#
# .. note::
#
#     In MNE-Python, the matrix used to project a raw signal into a subspace is
#     usually called a *projector* or a *projection operator* — these terms are
#     interchangeable with the term *projection matrix* used above.
#
#
# .. _ssp-tutorial:
#
# Signal-space projection (SSP)
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#
# We mentioned above that the projection matrix will vary depending on what
# kind of noise you are trying to project away. Signal-space projection (SSP)
# [1]_ is a way of estimating what that projection matrix should be, by
# comparing measurements with and without the signal of interest. For example,
# you can take additional "empty room" measurements that record activity at the
# sensors when no subject is present. By looking at the spatial pattern of
# activity across MEG sensors in an empty room measurement, you can create one
# or more :math:`N`-dimensional vector(s) giving the "direction(s)" of
# environmental noise in sensor space (analogous to the vector for "effect of
# the trigger" in our example above).
#
# Once you know those vectors, you can create a hyperplane that is orthogonal
# to them, and construct a projection matrix to project your experimental
# recordings onto that hyperplane. In that way, the component of your
# measurements associated with environmental noise can be removed. Again, it
# should be clear that the projection reduces the dimensionality of your data —
# you'll still have the same number of sensor signals, but they won't all be
# *linearly independent* — but typically there are tens or hundreds of sensors
# and the noise subspace that you are eliminating has only 3-5 dimensions, so
# the loss of degrees of freedom is usually not problematic.
#
# The next few tutorials will describe how to work with projectors in
# MNE-Python, how to compute projectors yourself, and how to visualize the
# effects that projectors are having on your data.
#
#
# References
# ^^^^^^^^^^
#
# .. [1] Uusitalo MA and Ilmoniemi RJ. (1997). Signal-space projection method
#        for separating MEG or EEG into components. *Med Biol Eng Comput*
#        35(2), 135–140. doi:10.1007/BF02534144
