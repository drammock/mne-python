"""
.. _tut-visualize-evoked:

=======================
Visualizing Evoked data
=======================

This tutorial shows the different visualization methods for
:class:`~mne.Evoked` objects.

As usual we'll start by importing the modules we need:
"""

# Authors: The MNE-Python contributors.
# License: BSD-3-Clause
# Copyright the MNE-Python contributors.

# %%
# test
import numpy as np

import mne

# %%
# Instead of creating the :class:`~mne.Evoked` object from an
# :class:`~mne.Epochs` object, we'll load an existing :class:`~mne.Evoked`
# object from disk. Remember, the :file:`.fif` format can store multiple
# :class:`~mne.Evoked` objects, so we'll end up with a `list` of
# :class:`~mne.Evoked` objects after loading. Recall also from the
# :ref:`tut-section-load-evk` section of :ref:`the introductory Evoked tutorial
# <tut-evoked-class>` that the sample :class:`~mne.Evoked` objects have not
# been baseline-corrected and have unapplied projectors, so we'll take care of
# that when loading:

root = mne.datasets.sample.data_path() / "MEG" / "sample"
evoked_file = root / "sample_audvis-ave.fif"
evokeds_list = mne.read_evokeds(
    evoked_file, baseline=(None, 0), proj=True, verbose=False
)

# Show condition names and baseline intervals
for e in evokeds_list:
    print(f"Condition: {e.comment}, baseline: {e.baseline}")

# %%
# To make our life easier, let's convert that list of :class:`~mne.Evoked`
# objects into a :class:`dictionary <dict>`. We'll use ``/``-separated
# dictionary keys to encode the conditions (like is often done when epoching)
# because some of the plotting methods can take advantage of that style of
# coding.

conds = ("aud/left", "aud/right", "vis/left", "vis/right")
evks = dict(zip(conds, evokeds_list))
#      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ this is equivalent to:
# {'aud/left': evokeds_list[0], 'aud/right': evokeds_list[1],
#  'vis/left': evokeds_list[2], 'vis/right': evokeds_list[3]}

# %%
# Plotting signal traces
# ^^^^^^^^^^^^^^^^^^^^^^
#
# .. admonition:: Butterfly plots
#    :class: sidebar note
#
#    Plots of superimposed sensor timeseries are called "butterfly plots"
#    because the positive- and negative-going traces can resemble butterfly
#    wings.
#
# The most basic plot of :class:`~mne.Evoked` objects is a butterfly plot of
# each channel type, generated by the `evoked.plot() <mne.Evoked.plot>`
# method. By default, channels marked as "bad" are suppressed, but you can
# control this by passing an empty :class:`list` to the ``exclude`` parameter
# (default is ``exclude='bads'``):

evks["aud/left"].plot(exclude=[])

# %%
# Notice the completely flat EEG channel and the noisy gradiometer channel
# plotted in red color. Like many MNE-Python plotting functions,
# `evoked.plot() <mne.Evoked.plot>` has a ``picks`` parameter that can
# select channels to plot by name, index, or type. In the next plot, we'll show
# only magnetometer channels and also color-code the channel traces by their
# location by passing ``spatial_colors=True``. Finally, we'll superimpose a
# trace of the root mean square (RMS) of the signal across channels by
# passing ``gfp=True``. This parameter is called ``gfp`` for historical
# reasons and behaves correctly for all supported channel types: for MEG data,
# it will plot the RMS; while for EEG, it would plot the
# :term:`global field power <GFP>` (an average-referenced RMS), hence its
# name:

evks["aud/left"].plot(picks="mag", spatial_colors=True, gfp=True)

# %%
# Interesting time periods can be highlighted via the ``highlight`` parameter.

time_ranges_of_interest = [(0.05, 0.14), (0.22, 0.27)]
evks["aud/left"].plot(
    picks="mag", spatial_colors=True, gfp=True, highlight=time_ranges_of_interest
)

# %%
# Plotting scalp topographies
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^
#
# In an interactive session, the butterfly plots seen above can be
# click-dragged to select a time region, which will pop up a map of the average
# field distribution over the scalp for the selected time span. You can also
# generate scalp topographies at specific times or time spans using the
# :meth:`~mne.Evoked.plot_topomap` method:

times = np.linspace(0.05, 0.13, 5)
evks["aud/left"].plot_topomap(ch_type="mag", times=times, colorbar=True)

# %%

fig = evks["aud/left"].plot_topomap(ch_type="mag", times=times, average=0.1)

# %%
# It is also possible to pass different time durations to average over for each
# time point. Passing a value of ``None`` will disable averaging for that
# time point:

averaging_durations = [0.01, 0.02, 0.03, None, None]
fig = evks["aud/left"].plot_topomap(
    ch_type="mag", times=times, average=averaging_durations
)

# %%
# Additional examples of plotting scalp topographies can be found in
# :ref:`ex-evoked-topomap`.
#
#
# Arrow maps
# ^^^^^^^^^^
#
# Scalp topographies at a given time point can be augmented with arrows to show
# the estimated magnitude and direction of the magnetic field, using the
# function :func:`mne.viz.plot_arrowmap`:

mags = evks["aud/left"].copy().pick(picks="mag")
mne.viz.plot_arrowmap(mags.data[:, 175], mags.info, extrapolate="local")

# %%
# Joint plots
# ^^^^^^^^^^^
#
# Joint plots combine butterfly plots with scalp topographies, and provide an
# excellent first-look at evoked data; by default, topographies will be
# automatically placed based on peak finding. Here we plot the
# right-visual-field condition; if no ``picks`` are specified we get a separate
# figure for each channel type:

evks["vis/right"].plot_joint()

# %%
# Like :meth:`~mne.Evoked.plot_topomap`, you can specify the ``times`` at which
# you want the scalp topographies calculated, and you can customize the plot in
# various other ways as well. See :meth:`mne.Evoked.plot_joint` for details.
#
#
# Comparing ``Evoked`` objects
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#
# To compare :class:`~mne.Evoked` objects from different experimental
# conditions, the function :func:`mne.viz.plot_compare_evokeds` can take a
# :class:`list` or :class:`dict` of :class:`~mne.Evoked` objects and plot them
# all on the same axes. Like most MNE-Python visualization functions, it has a
# ``picks`` parameter for selecting channels, but by default will generate one
# figure for each channel type, and combine information across channels of the
# same type by calculating the :term:`global field power`. Information
# may be combined across channels in other ways too; support for combining via
# mean, median, or standard deviation are built-in, and custom callable
# functions may also be used, as shown here:


def custom_func(x):
    return x.max(axis=1)


for combine in ("mean", "median", "gfp", custom_func):
    mne.viz.plot_compare_evokeds(evks, picks="eeg", combine=combine)

# %%
# One nice feature of :func:`~mne.viz.plot_compare_evokeds` is that when
# passing evokeds in a dictionary, it allows specifying plot styles based on
# ``/``-separated substrings of the dictionary keys (similar to epoch
# selection; see :ref:`tut-section-subselect-epochs`). Here, we specify colors
# for "aud" and "vis" conditions, and linestyles for "left" and "right"
# conditions, and the traces and legend are styled accordingly. Here we also
# show the ``time_unit='ms'`` parameter in action.

# sphinx_gallery_thumbnail_number = 15
mne.viz.plot_compare_evokeds(
    evks,
    picks="MEG 1811",
    colors=dict(aud=0, vis=1),
    linestyles=dict(left="solid", right="dashed"),
    time_unit="ms",
)

# %%
# The legends generated by :func:`~mne.viz.plot_compare_evokeds` above used the
# dictionary keys provided by the ``evks`` variable. If instead you pass a
# :class:`list` or :class:`tuple` of :class:`~mne.Evoked` objects, the legend
# keys will be generated automatically from the ``comment`` attribute of the
# :class:`~mne.Evoked` objects (or, as sequential integers if the comment
# attribute is empty or ambiguous). To illustrate this, we'll make a list of
# five :class:`~mne.Evoked` objects: two with identical comments, two with
# empty comments (either an empty string or ``None``), and one with a unique
# non-empty comment:

temp_list = list()
for idx, _comment in enumerate(("foo", "foo", "", None, "bar"), start=1):
    _evk = evokeds_list[0].copy()
    _evk.comment = _comment
    _evk.data *= idx  # so we can tell the traces apart
    temp_list.append(_evk)

mne.viz.plot_compare_evokeds(temp_list, picks="mag")

# %%
# Image plots
# ^^^^^^^^^^^
#
# Like :class:`~mne.Epochs`, :class:`~mne.Evoked` objects also have a
# :meth:`~mne.Evoked.plot_image` method, but unlike `epochs.plot_image()
# <mne.Epochs.plot_image>`, `evoked.plot_image() <mne.Evoked.plot_image>`
# shows one *channel* per row instead of one *epoch* per row. Again, a
# ``picks`` parameter is available, as well as several other customization
# options; see :meth:`~mne.Evoked.plot_image` for details.

evks["vis/right"].plot_image(picks="meg")

# %%
# Topographical subplots
# ^^^^^^^^^^^^^^^^^^^^^^
#
# For sensor-level analyses, it can be useful to plot the response at each
# sensor in a topographical layout. The :func:`~mne.viz.plot_compare_evokeds`
# function can do this if you pass ``axes='topo'``, but it can be quite slow
# if the number of sensors is too large, so here we'll plot only the EEG
# channels:

mne.viz.plot_compare_evokeds(
    evks,
    picks="eeg",
    colors=dict(aud=0, vis=1),
    linestyles=dict(left="solid", right="dashed"),
    axes="topo",
    styles=dict(aud=dict(linewidth=1), vis=dict(linewidth=1)),
)

# %%
# For a larger number of sensors, the method `evoked.plot_topo()
# <mne.Evoked.plot_topo>` and the function :func:`mne.viz.plot_evoked_topo`
# can both be used. The :meth:`~mne.Evoked.plot_topo` method will plot only a
# single condition, while the :func:`~mne.viz.plot_evoked_topo` function can
# plot one or more conditions on the same axes, if passed a list of
# :class:`~mne.Evoked` objects. The legend entries will be automatically drawn
# from the :class:`~mne.Evoked` objects' ``comment`` attribute:

mne.viz.plot_evoked_topo(evokeds_list)

# %%
# By default, :func:`~mne.viz.plot_evoked_topo` will plot all MEG sensors (if
# present), so to get EEG sensors you would need to modify the evoked objects
# first (e.g., using `mne.pick_types`).
#
# .. note::
#
#     In interactive sessions, both approaches to topographical plotting allow
#     you to click one of the sensor subplots to open a larger version of the
#     evoked plot at that sensor.
#
#
# 3D Field Maps
# ^^^^^^^^^^^^^
#
# The scalp topographies above were all projected into two-dimensional overhead
# views of the field, but it is also possible to plot field maps in 3D. This
# requires a :term:`trans` file to transform locations between the coordinate
# systems of the MEG device and the head surface (based on the MRI). You *can*
# compute 3D field maps without a ``trans`` file, but it will only work for
# calculating the field *on the MEG helmet from the MEG sensors*.

subjects_dir = root.parents[1] / "subjects"
trans_file = root / "sample_audvis_raw-trans.fif"

# %%
# By default, MEG sensors will be used to estimate the field on the helmet
# surface, while EEG sensors will be used to estimate the field on the scalp.
# Once the maps are computed, you can plot them with `evoked.plot_field()
# <mne.Evoked.plot_field>`:

maps = mne.make_field_map(
    evks["aud/left"], trans=str(trans_file), subject="sample", subjects_dir=subjects_dir
)
evks["aud/left"].plot_field(maps, time=0.1)

# %%
# You can also use MEG sensors to estimate the *scalp* field by passing
# ``meg_surf='head'``. By selecting each sensor type in turn, you can compare
# the scalp field estimates from each.

for ch_type in ("mag", "grad", "eeg"):
    evk = evks["aud/right"].copy().pick(ch_type)
    _map = mne.make_field_map(
        evk,
        trans=str(trans_file),
        subject="sample",
        subjects_dir=subjects_dir,
        meg_surf="head",
    )
    fig = evk.plot_field(_map, time=0.1)
    mne.viz.set_3d_title(fig, ch_type, size=20)
