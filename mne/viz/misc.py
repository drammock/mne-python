"""Functions to make simple plots with M/EEG data."""

# Authors: The MNE-Python contributors.
# License: BSD-3-Clause
# Copyright the MNE-Python contributors.

import copy
import io
import os
import os.path as op
import warnings
from collections import defaultdict
from glob import glob
from itertools import cycle
from pathlib import Path

import numpy as np
from scipy.signal import filtfilt, freqz, group_delay, lfilter, sosfilt, sosfiltfilt

from .._fiff.constants import FIFF
from .._fiff.pick import (
    _DATA_CH_TYPES_SPLIT,
    _picks_by_type,
    pick_channels,
    pick_info,
    pick_types,
)
from .._fiff.proj import make_projector
from .._freesurfer import _check_mri, _mri_orientation, _read_mri_info, _reorient_image
from ..defaults import DEFAULTS
from ..filter import estimate_ringing_samples
from ..fixes import _safe_svd
from ..rank import compute_rank
from ..surface import read_surface
from ..transforms import _get_trans, apply_trans
from ..utils import (
    _check_option,
    _mask_to_onsets_offsets,
    _on_missing,
    _pl,
    fill_doc,
    get_subjects_dir,
    logger,
    verbose,
    warn,
)
from .utils import (
    _figure_agg,
    _get_color_list,
    _prepare_trellis,
    _validate_type,
    plt_show,
)


def _index_info_cov(info, cov, exclude):
    if exclude == "bads":
        exclude = info["bads"]
    info = pick_info(info, pick_channels(info["ch_names"], cov["names"], exclude))
    del exclude
    picks_list = _picks_by_type(info, meg_combined=False, ref_meg=False, exclude=())
    picks_by_type = dict(picks_list)

    ch_names = [n for n in cov.ch_names if n in info["ch_names"]]
    ch_idx = [cov.ch_names.index(n) for n in ch_names]

    info_ch_names = info["ch_names"]
    idx_by_type = defaultdict(list)
    for ch_type, sel in picks_by_type.items():
        idx_by_type[ch_type] = [
            ch_names.index(info_ch_names[c])
            for c in sel
            if info_ch_names[c] in ch_names
        ]
    idx_names = [
        (
            idx_by_type[key],
            f"{DEFAULTS['titles'][key]} covariance",
            DEFAULTS["units"][key],
            DEFAULTS["scalings"][key],
            key,
        )
        for key in _DATA_CH_TYPES_SPLIT
        if len(idx_by_type[key]) > 0
    ]
    C = cov.data[ch_idx][:, ch_idx]
    return info, C, ch_names, idx_names


@verbose
def plot_cov(
    cov,
    info,
    exclude=(),
    colorbar=True,
    proj=False,
    show_svd=True,
    show=True,
    verbose=None,
):
    """Plot Covariance data.

    Parameters
    ----------
    cov : instance of Covariance
        The covariance matrix.
    %(info_not_none)s
    exclude : list of str | str
        List of channels to exclude. If empty do not exclude any channel.
        If 'bads', exclude info['bads'].
    colorbar : bool
        Show colorbar or not.
    proj : bool
        Apply projections or not.
    show_svd : bool
        Plot also singular values of the noise covariance for each sensor
        type. We show square roots ie. standard deviations.
    show : bool
        Show figure if True.
    %(verbose)s

    Returns
    -------
    fig_cov : instance of matplotlib.figure.Figure
        The covariance plot.
    fig_svd : instance of matplotlib.figure.Figure | None
        The SVD plot of the covariance (i.e., the eigenvalues or "matrix spectrum").

    See Also
    --------
    mne.compute_rank

    Notes
    -----
    For each channel type, the rank is estimated using
    :func:`mne.compute_rank`.

    .. versionchanged:: 0.19
       Approximate ranks for each channel type are shown with red dashed lines.
    """
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize

    from ..cov import Covariance

    info, C, ch_names, idx_names = _index_info_cov(info, cov, exclude)
    del cov, exclude

    projs = []
    if proj:
        projs = copy.deepcopy(info["projs"])

        #   Activate the projection items
        for p in projs:
            p["active"] = True

        P, ncomp, _ = make_projector(projs, ch_names)
        if ncomp > 0:
            logger.info(f"    Created an SSP operator (subspace dimension = {ncomp:d})")
            C = np.dot(P, np.dot(C, P.T))
        else:
            logger.info("    The projection vectors do not apply to these channels.")

    if np.iscomplexobj(C):
        C = np.sqrt((C * C.conj()).real)

    fig_cov, axes = plt.subplots(
        1,
        len(idx_names),
        squeeze=False,
        figsize=(3.8 * len(idx_names), 3.7),
        layout="constrained",
    )
    for k, (idx, name, _, _, _) in enumerate(idx_names):
        vlim = np.max(np.abs(C[idx][:, idx]))
        im = axes[0, k].imshow(
            C[idx][:, idx],
            interpolation="nearest",
            norm=Normalize(vmin=-vlim, vmax=vlim),
            cmap="RdBu_r",
        )
        axes[0, k].set(title=name)

        if colorbar:
            from mpl_toolkits.axes_grid1 import make_axes_locatable

            divider = make_axes_locatable(axes[0, k])
            cax = divider.append_axes("right", size="5.5%", pad=0.05)
            cax.grid(False)  # avoid mpl warning about auto-removal
            plt.colorbar(im, cax=cax, format="%.0e")

    fig_svd = None
    if show_svd:
        fig_svd, axes = plt.subplots(
            1,
            len(idx_names),
            squeeze=False,
            figsize=(3.8 * len(idx_names), 3.7),
            layout="constrained",
        )
        for k, (idx, name, unit, scaling, key) in enumerate(idx_names):
            this_C = C[idx][:, idx]
            s = _safe_svd(this_C, compute_uv=False)
            this_C = Covariance(this_C, [info["ch_names"][ii] for ii in idx], [], [], 0)
            this_info = pick_info(info, idx)
            with this_info._unlock():
                this_info["projs"] = []
            this_rank = compute_rank(this_C, info=this_info)
            # Protect against true zero singular values
            s[s <= 0] = 1e-10 * s[s > 0].min()
            s = np.sqrt(s) * scaling
            axes[0, k].plot(s, color="k", zorder=3)
            this_rank = this_rank[key]
            axes[0, k].axvline(
                this_rank - 1, ls="--", color="r", alpha=0.5, zorder=4, clip_on=False
            )
            axes[0, k].text(
                this_rank - 1,
                axes[0, k].get_ylim()[1],
                f"rank ≈ {this_rank:d}",
                ha="right",
                va="top",
                color="r",
                alpha=0.5,
                zorder=4,
            )
            axes[0, k].set(
                ylabel=f"Noise σ ({unit})",
                yscale="log",
                xlabel="Eigenvalue index",
                title=name,
                xlim=[0, len(s) - 1],
            )

    plt_show(show)
    return fig_cov, fig_svd


def plot_source_spectrogram(
    stcs, freq_bins, tmin=None, tmax=None, source_index=None, colorbar=False, show=True
):
    """Plot source power in time-freqency grid.

    Parameters
    ----------
    stcs : list of SourceEstimate
        Source power for consecutive time windows, one SourceEstimate object
        should be provided for each frequency bin.
    freq_bins : list of tuples of float
        Start and end points of frequency bins of interest.
    tmin : float
        Minimum time instant to show.
    tmax : float
        Maximum time instant to show.
    source_index : int | None
        Index of source for which the spectrogram will be plotted. If None,
        the source with the largest activation will be selected.
    colorbar : bool
        If true, a colorbar will be added to the plot.
    show : bool
        Show figure if True.

    Returns
    -------
    fig : instance of Figure
        The figure.
    """
    import matplotlib.pyplot as plt

    # Input checks
    if len(stcs) == 0:
        raise ValueError("cannot plot spectrogram if len(stcs) == 0")

    stc = stcs[0]
    if tmin is not None and tmin < stc.times[0]:
        raise ValueError(
            "tmin cannot be smaller than the first time point provided in stcs"
        )
    if tmax is not None and tmax > stc.times[-1] + stc.tstep:
        raise ValueError(
            "tmax cannot be larger than the sum of the last time "
            "point and the time step, which are provided in stcs"
        )

    # Preparing time-frequency cell boundaries for plotting
    if tmin is None:
        tmin = stc.times[0]
    if tmax is None:
        tmax = stc.times[-1] + stc.tstep
    time_bounds = np.arange(tmin, tmax + stc.tstep, stc.tstep)
    freq_bounds = sorted(set(np.ravel(freq_bins)))
    freq_ticks = copy.deepcopy(freq_bounds)

    # Reject time points that will not be plotted and gather results
    source_power = []
    for stc in stcs:
        stc = stc.copy()  # copy since crop modifies inplace
        stc.crop(tmin, tmax - stc.tstep)
        source_power.append(stc.data)
    source_power = np.array(source_power)

    # Finding the source with maximum source power
    if source_index is None:
        source_index = np.unravel_index(source_power.argmax(), source_power.shape)[1]

    # If there is a gap in the frequency bins record its locations so that it
    # can be covered with a gray horizontal bar
    gap_bounds = []
    for i in range(len(freq_bins) - 1):
        lower_bound = freq_bins[i][1]
        upper_bound = freq_bins[i + 1][0]
        if lower_bound != upper_bound:
            freq_bounds.remove(lower_bound)
            gap_bounds.append((lower_bound, upper_bound))

    # Preparing time-frequency grid for plotting
    time_grid, freq_grid = np.meshgrid(time_bounds, freq_bounds)

    # Plotting the results
    fig = plt.figure(figsize=(9, 6), layout="constrained")
    plt.pcolor(time_grid, freq_grid, source_power[:, source_index, :], cmap="Reds")
    ax = plt.gca()

    ax.set(title="Source power", xlabel="Time (s)", ylabel="Frequency (Hz)")

    time_tick_labels = [str(np.round(t, 2)) for t in time_bounds]
    n_skip = 1 + len(time_bounds) // 10
    for i in range(len(time_bounds)):
        if i % n_skip != 0:
            time_tick_labels[i] = ""

    ax.set_xticks(time_bounds)
    ax.set_xticklabels(time_tick_labels)
    plt.xlim(time_bounds[0], time_bounds[-1])
    plt.yscale("log")
    ax.set_yticks(freq_ticks)
    ax.set_yticklabels([np.round(freq, 2) for freq in freq_ticks])
    plt.ylim(freq_bounds[0], freq_bounds[-1])

    plt.grid(True, ls="-")
    if colorbar:
        plt.colorbar()

    # Covering frequency gaps with horizontal bars
    for lower_bound, upper_bound in gap_bounds:
        plt.barh(
            lower_bound,
            time_bounds[-1] - time_bounds[0],
            upper_bound - lower_bound,
            time_bounds[0],
            color="#666666",
        )

    plt_show(show)
    return fig


def _plot_mri_contours(
    *,
    mri_fname,
    surfaces,
    src,
    trans=None,
    orientation="coronal",
    slices=None,
    show=True,
    show_indices=False,
    show_orientation=False,
    width=512,
    slices_as_subplots=True,
):
    """Plot BEM contours on anatomical MRI slices.

    Parameters
    ----------
    slices_as_subplots : bool
        Whether to add all slices as subplots to a single figure, or to
        create a new figure for each slice. If ``False``, return NumPy
        arrays instead of Matplotlib figures.

    Returns
    -------
    matplotlib.figure.Figure | list of array
        The plotted slices.
    """
    import matplotlib.pyplot as plt
    from matplotlib import patheffects

    from ..source_space._source_space import _ensure_src

    # For ease of plotting, we will do everything in voxel coordinates.
    _validate_type(show_orientation, (bool, str), "show_orientation")
    if isinstance(show_orientation, str):
        _check_option(
            "show_orientation", show_orientation, ("always",), extra="when str"
        )
    _check_option("orientation", orientation, ("coronal", "axial", "sagittal"))

    # Load the T1 data
    _, _, _, _, _, nim = _read_mri_info(mri_fname, units="mm", return_img=True)

    data, rasvox_mri_t = _reorient_image(nim)
    mri_rasvox_t = np.linalg.inv(rasvox_mri_t)
    axis, x, y = _mri_orientation(orientation)

    n_slices = data.shape[axis]

    # if no slices were specified, pick some equally-spaced ones automatically
    if slices is None:
        slices = np.round(np.linspace(start=0, stop=n_slices - 1, num=14)).astype(int)

        # omit first and last one (not much brain visible there anyway…)
        slices = slices[1:-1]

    slices = np.atleast_1d(slices).copy()
    slices[slices < 0] += n_slices  # allow negative indexing
    if (
        not np.array_equal(np.sort(slices), slices)
        or slices.ndim != 1
        or slices.size < 1
        or slices[0] < 0
        or slices[-1] >= n_slices
        or slices.dtype.kind not in "iu"
    ):
        raise ValueError(
            "slices must be a sorted 1D array of int with unique "
            "elements, at least one element, and no elements "
            f"greater than {n_slices - 1:d}, got {slices}"
        )

    # create of list of surfaces
    surfs = list()
    for file_name, color in surfaces:
        surf = dict()
        surf["rr"], surf["tris"] = read_surface(file_name)
        # move surface to voxel coordinate system
        surf["rr"] = apply_trans(mri_rasvox_t, surf["rr"])
        surfs.append((surf, color))

    sources = list()
    if src is not None:
        _ensure_src(src, extra=" or None")
        for src_ in src:
            points = src_["rr"][src_["vertno"]]
            if src_["coord_frame"] != FIFF.FIFFV_COORD_MRI:
                trans, _ = _get_trans(
                    trans,
                    fro="head",
                    to="mri",
                    allow_none=False,
                    extra="when src is in head coordinates",
                )
                points = apply_trans(np.linalg.inv(trans["trans"]), points)
            sources.append(apply_trans(mri_rasvox_t, points * 1e3))
        sources = np.concatenate(sources, axis=0)

    # get the figure dimensions right
    if slices_as_subplots:
        n_col = 4
        fig, axs, _, _ = _prepare_trellis(len(slices), n_col)
        fig.set_facecolor("k")
        dpi = fig.get_dpi()
        n_axes = len(axs)
    else:
        n_col = n_axes = 1
        dpi = 96
        # 2x standard MRI resolution is probably good enough for the
        # traces
        w = width / dpi
        figsize = (w, w / data.shape[x] * data.shape[y])

    bounds = np.concatenate(
        [[-np.inf], slices[:-1] + np.diff(slices) / 2.0, [np.inf]]
    )  # float
    slicer = [slice(None)] * 3
    ori_labels = dict(R="LR", A="PA", S="IS")
    xlabels, ylabels = ori_labels["RAS"[x]], ori_labels["RAS"[y]]
    path_effects = [patheffects.withStroke(linewidth=4, foreground="k", alpha=0.75)]
    figs = []
    for ai, (sl, lower, upper) in enumerate(zip(slices, bounds[:-1], bounds[1:])):
        if slices_as_subplots:
            ax = axs[ai]
        else:
            # No need for constrained layout here because we make our axes fill the
            # entire figure
            fig = _figure_agg(figsize=figsize, dpi=dpi, facecolor="k")
            ax = fig.add_axes([0, 0, 1, 1], frame_on=False, facecolor="k")

        # adjust the orientations for good view
        slicer[axis] = sl
        dat = data[tuple(slicer)].T

        # First plot the anatomical data
        ax.imshow(dat, cmap=plt.cm.gray, origin="lower")
        ax.set_autoscale_on(False)
        ax.axis("off")
        ax.set_aspect("equal")  # XXX eventually could deal with zooms

        # and then plot the contours on top
        for surf, color in surfs:
            with warnings.catch_warnings(record=True):  # ignore contour warn
                warnings.simplefilter("ignore")
                ax.tricontour(
                    surf["rr"][:, x],
                    surf["rr"][:, y],
                    surf["tris"],
                    surf["rr"][:, axis],
                    levels=[sl],
                    colors=color,
                    linewidths=1.0,
                    zorder=1,
                )

        if len(sources):
            in_slice = (sources[:, axis] >= lower) & (sources[:, axis] < upper)
            ax.scatter(
                sources[in_slice, x],
                sources[in_slice, y],
                marker=".",
                color="#FF00FF",
                s=1,
                zorder=2,
            )
        if show_indices:
            ax.text(
                dat.shape[1] // 8 + 0.5,
                0.5,
                str(sl),
                color="w",
                fontsize="x-small",
                va="bottom",
                ha="left",
            )
        # label the axes
        kwargs = dict(
            color="#66CCEE",
            fontsize="medium",
            path_effects=path_effects,
            family="monospace",
            clip_on=False,
            zorder=5,
            weight="bold",
        )
        always = show_orientation == "always"
        if show_orientation:
            if ai % n_col == 0 or always:  # left
                ax.text(
                    0, dat.shape[0] / 2.0, xlabels[0], va="center", ha="left", **kwargs
                )
            if ai % n_col == n_col - 1 or ai == n_axes - 1 or always:  # right
                ax.text(
                    dat.shape[1] - 1,
                    dat.shape[0] / 2.0,
                    xlabels[1],
                    va="center",
                    ha="right",
                    **kwargs,
                )
            if ai >= n_axes - n_col or always:  # bottom
                ax.text(
                    dat.shape[1] / 2.0,
                    0,
                    ylabels[0],
                    ha="center",
                    va="bottom",
                    **kwargs,
                )
            if ai < n_col or n_col == 1 or always:  # top
                ax.text(
                    dat.shape[1] / 2.0,
                    dat.shape[0] - 1,
                    ylabels[1],
                    ha="center",
                    va="top",
                    **kwargs,
                )

        if not slices_as_subplots:
            # convert to NumPy array
            with io.BytesIO() as buff:
                fig.savefig(
                    buff, format="raw", bbox_inches="tight", pad_inches=0, dpi=dpi
                )
                w_, h_ = fig.canvas.get_width_height()
                plt.close(fig)
                buff.seek(0)
                fig_array = np.frombuffer(buff.getvalue(), dtype=np.uint8)

            fig = fig_array.reshape((int(h_), int(w_), -1))
            figs.append(fig)

    if slices_as_subplots:
        plt_show(show, fig=fig)
        return fig
    else:
        return figs


@fill_doc
def plot_bem(
    subject,
    subjects_dir=None,
    orientation="coronal",
    slices=None,
    brain_surfaces=None,
    src=None,
    *,
    trans=None,
    show=True,
    show_indices=True,
    mri="T1.mgz",
    show_orientation=True,
):
    """Plot BEM contours on anatomical MRI slices.

    Parameters
    ----------
    %(subject)s
    %(subjects_dir)s
    orientation : str
        'coronal' or 'axial' or 'sagittal'.
    slices : list of int | None
        The indices of the MRI slices to plot. If ``None``, automatically
        pick 12 equally-spaced slices.
    brain_surfaces : str | list of str | None
        One or more brain surface to plot (optional). Entries should correspond
        to files in the subject's ``surf`` directory (e.g. ``"white"``).
    src : SourceSpaces | path-like | None
        SourceSpaces instance or path to a source space to plot individual
        sources as scatter-plot. Sources will be shown on exactly one slice
        (whichever slice is closest to each source in the given orientation
        plane). Path can be absolute or relative to the subject's ``bem``
        folder.

        .. versionchanged:: 0.20
           All sources are shown on the nearest slice rather than some
           being omitted.
    %(trans)s

        .. versionadded:: 1.10
    show : bool
        Show figure if True.
    show_indices : bool
        Show slice indices if True.

        .. versionadded:: 0.20
    mri : str
        The name of the MRI to use. Can be a standard FreeSurfer MRI such as
        ``'T1.mgz'``, or a full path to a custom MRI file.

        .. versionadded:: 0.21
    show_orientation : bool | str
        Show the orientation (L/R, P/A, I/S) of the data slices.
        True (default) will only show it on the outside most edges of the
        figure, False will never show labels, and "always" will label each
        plot.

        .. versionadded:: 0.21
        .. versionchanged:: 0.24
           Added support for "always".

    Returns
    -------
    fig : instance of matplotlib.figure.Figure
        The figure.

    See Also
    --------
    mne.viz.plot_alignment

    Notes
    -----
    Images are plotted in MRI voxel coordinates.

    If ``src`` is not None, for a given slice index, all source points are
    shown that are halfway between the previous slice and the given slice,
    and halfway between the given slice and the next slice.
    For large slice decimations, this can
    make some source points appear outside the BEM contour, which is shown
    for the given slice index. For example, in the case where the single
    midpoint slice is used ``slices=[128]``, all source points will be shown
    on top of the midpoint MRI slice with the BEM boundary drawn for that
    slice.
    """
    from ..source_space import SourceSpaces, read_source_spaces

    subjects_dir = get_subjects_dir(subjects_dir, raise_error=True)
    mri_fname = _check_mri(mri, subject, subjects_dir)

    # Get the BEM surface filenames
    bem_path = subjects_dir / subject / "bem"

    if not bem_path.is_dir():
        raise OSError(f'Subject bem directory "{bem_path}" does not exist')

    surfaces = _get_bem_plotting_surfaces(bem_path)
    if brain_surfaces is not None:
        if isinstance(brain_surfaces, str):
            brain_surfaces = (brain_surfaces,)
        for surf_name in brain_surfaces:
            for hemi in ("lh", "rh"):
                surf_fname = subjects_dir / subject / "surf" / f"{hemi}.{surf_name}"
                if surf_fname.exists():
                    surfaces.append((surf_fname, "#00DD00"))
                else:
                    raise OSError(f"Surface {surf_fname} does not exist.")

    # TODO: Refactor with / improve _ensure_src to do this
    if isinstance(src, str | Path | os.PathLike):
        src = Path(src)
        if not src.exists():
            # convert to Path until get_subjects_dir returns a Path object
            src_ = Path(subjects_dir) / subject / "bem" / src
            if not src_.exists():
                raise OSError(f"{src} does not exist")
            src = src_
        src = read_source_spaces(src)
    elif src is not None and not isinstance(src, SourceSpaces):
        raise TypeError(
            f"src needs to be None, path-like or SourceSpaces instance, not {repr(src)}"
        )

    if len(surfaces) == 0:
        raise OSError(
            "No surface files found. Surface files must end with "
            "inner_skull.surf, outer_skull.surf or outer_skin.surf"
        )

    # Plot the contours
    fig = _plot_mri_contours(
        mri_fname=mri_fname,
        surfaces=surfaces,
        src=src,
        trans=trans,
        orientation=orientation,
        slices=slices,
        show=show,
        show_indices=show_indices,
        show_orientation=show_orientation,
        slices_as_subplots=True,
    )
    return fig


def _get_bem_plotting_surfaces(bem_path):
    surfaces = []
    for surf_name, color in (
        ("*inner_skull", "#FF0000"),
        ("*outer_skull", "#FFFF00"),
        ("*outer_skin", "#FFAA80"),
    ):
        surf_fname = glob(op.join(bem_path, surf_name + ".surf"))
        if len(surf_fname) > 0:
            surf_fname = surf_fname[0]
            logger.info(f"Using surface: {surf_fname}")
            surfaces.append((surf_fname, color))
    return surfaces


@verbose
def plot_events(
    events,
    sfreq=None,
    first_samp=0,
    color=None,
    event_id=None,
    axes=None,
    equal_spacing=True,
    show=True,
    on_missing="raise",
    verbose=None,
):
    """Plot :term:`events` to get a visual display of the paradigm.

    Parameters
    ----------
    %(events)s
    sfreq : float | None
        The sample frequency. If None, data will be displayed in samples (not
        seconds).
    first_samp : int
        The index of the first sample. Recordings made on Neuromag systems
        number samples relative to the system start (not relative to the
        beginning of the recording). In such cases the ``raw.first_samp``
        attribute can be passed here. Default is 0.
    color : dict | None
        Dictionary of event_id integers as keys and colors as values. If None,
        colors are automatically drawn from a default list (cycled through if
        number of events longer than list of default colors). Color can be any
        valid :ref:`matplotlib color <matplotlib:colors_def>`.
    event_id : dict | None
        Dictionary of event labels (e.g. 'aud_l') as keys and their associated
        event_id values. Labels are used to plot a legend. If None, no legend
        is drawn.
    axes : instance of Axes
       The subplot handle.
    equal_spacing : bool
        Use equal spacing between events in y-axis.
    show : bool
        Show figure if True.
    %(on_missing_events)s
    %(verbose)s

    Returns
    -------
    fig : matplotlib.figure.Figure
        The figure object containing the plot.

    Notes
    -----
    .. versionadded:: 0.9.0
    """
    if sfreq is None:
        sfreq = 1.0
        xlabel = "Samples"
    else:
        xlabel = "Time (s)"

    events = np.asarray(events)
    if len(events) == 0:
        raise ValueError("No events in events array, cannot plot.")
    unique_events = np.unique(events[:, 2])

    if event_id is not None:
        # get labels and unique event ids from event_id dict,
        # sorted by value
        event_id_rev = {v: k for k, v in event_id.items()}
        conditions, unique_events_id = zip(
            *sorted(event_id.items(), key=lambda x: x[1])
        )

        keep = np.ones(len(unique_events_id), bool)
        for ii, this_event in enumerate(unique_events_id):
            if this_event not in unique_events:
                msg = f"{this_event} from event_id is not present in events."
                _on_missing(on_missing, msg)
                keep[ii] = False
        conditions = [cond for cond, k in zip(conditions, keep) if k]
        unique_events_id = [id_ for id_, k in zip(unique_events_id, keep) if k]
        if len(unique_events_id) == 0:
            raise RuntimeError("No usable event IDs found")

        for this_event in unique_events:
            if this_event not in unique_events_id:
                warn(f"event {this_event} missing from event_id will be ignored")

    else:
        unique_events_id = unique_events

    color = _handle_event_colors(color, unique_events, event_id)
    import matplotlib.pyplot as plt

    unique_events_id = np.array(unique_events_id)

    fig = None
    figsize = plt.rcParams["figure.figsize"]
    # assuming the user did not change matplotlib default params, the figsize of
    # (6.4, 4.8) becomes too big if scaled beyond twice its size, so maximum 2
    _scaling = min(max(1, len(unique_events_id) / 10), 2)
    figsize_scaled = np.array(figsize) * _scaling
    if axes is None:
        fig = plt.figure(layout="constrained", figsize=tuple(figsize_scaled))
    ax = axes if axes else plt.gca()

    min_event = np.min(unique_events_id)
    max_event = np.max(unique_events_id)
    max_x = (
        events[np.isin(events[:, 2], unique_events_id), 0].max() - first_samp
    ) / sfreq

    handles, labels = list(), list()
    for idx, ev in enumerate(unique_events_id):
        ev_mask = events[:, 2] == ev
        count = ev_mask.sum()
        if count == 0:
            continue
        y = np.full(count, idx + 1 if equal_spacing else events[ev_mask, 2][0])
        if event_id is not None:
            event_label = f"{event_id_rev[ev]}\n(id:{ev}; N:{count})"
        else:
            event_label = f"id:{ev}; N:{count:d}"
        labels.append(event_label)
        kwargs = {}
        if ev in color:
            kwargs["color"] = color[ev]
        handles.append(
            ax.plot(
                (events[ev_mask, 0] - first_samp) / sfreq,
                y,
                ".",
                clip_on=False,
                **kwargs,
            )[0]
        )

    if equal_spacing:
        ax.set_ylim(0, unique_events_id.size + 1)
        ax.set_yticks(1 + np.arange(unique_events_id.size))
        ax.set_yticklabels(unique_events_id)
    else:
        ax.set_ylim([min_event - 1, max_event + 1])

    ax.set(xlabel=xlabel, ylabel="Event id", xlim=[0, max_x])

    ax.grid(True)

    fig = fig if fig is not None else plt.gcf()
    # reverse order so that the highest numbers are at the top
    # (match plot order)
    handles, labels = handles[::-1], labels[::-1]

    # spread legend entries over more columns, 25 still ~fit in one column
    # (assuming non-user supplied fig), max at 3 columns
    ncols = min(int(np.ceil(len(unique_events_id) / 25)), 3)

    # Make space for legend
    box = ax.get_position()
    factor = 0.8 if event_id is not None else 0.9
    factor -= 0.1 * (ncols - 1)
    ax.set_position([box.x0, box.y0, box.width * factor, box.height])

    # Try some adjustments to squeeze as much information into the legend
    # without cutting off the ends
    ax.legend(
        handles,
        labels,
        loc="center left",
        bbox_to_anchor=(1, 0.5),
        fontsize="small",
        borderpad=0,  # default 0.4
        labelspacing=0.25,  # default 0.5
        columnspacing=1.0,  # default 2
        handletextpad=0,  # default 0.8
        markerscale=2,  # default 1
        borderaxespad=0.2,  # default 0.5
        ncols=ncols,
    )
    fig.canvas.draw()
    plt_show(show)
    return fig


def _get_presser(fig):
    """Get our press callback."""
    callbacks = fig.canvas.callbacks.callbacks["button_press_event"]
    func = None
    for key, val in callbacks.items():
        func = val()
        if func.__class__.__name__ == "partial":
            break
        else:
            func = None
    assert func is not None
    return func


def plot_dipole_amplitudes(dipoles, colors=None, show=True):
    """Plot the amplitude traces of a set of dipoles.

    Parameters
    ----------
    dipoles : list of instance of Dipole
        The dipoles whose amplitudes should be shown.
    colors : list of color | None
        Color to plot with each dipole. If None default colors are used.
    show : bool
        Show figure if True.

    Returns
    -------
    fig : matplotlib.figure.Figure
        The figure object containing the plot.

    Notes
    -----
    .. versionadded:: 0.9.0
    """
    import matplotlib.pyplot as plt

    if colors is None:
        colors = cycle(_get_color_list())
    fig, ax = plt.subplots(1, 1, layout="constrained")
    xlim = [np.inf, -np.inf]
    for dip, color in zip(dipoles, colors):
        ax.plot(dip.times, dip.amplitude * 1e9, color=color, linewidth=1.5)
        xlim[0] = min(xlim[0], dip.times[0])
        xlim[1] = max(xlim[1], dip.times[-1])
    ax.set(xlim=xlim, xlabel="Time (s)", ylabel="Amplitude (nAm)")
    if show:
        fig.show(warn=False)
    return fig


def adjust_axes(axes, remove_spines=("top", "right"), grid=True):
    """Adjust some properties of axes.

    Parameters
    ----------
    axes : list
        List of axes to process.
    remove_spines : list of str
        Which axis spines to remove.
    grid : bool
        Turn grid on (True) or off (False).
    """
    axes = [axes] if not isinstance(axes, list | tuple | np.ndarray) else axes
    for ax in axes:
        if grid:
            ax.grid(zorder=0)
        for key in remove_spines:
            ax.spines[key].set_visible(False)


def _filter_ticks(lims, fscale):
    """Create approximately spaced ticks between lims."""
    if fscale == "linear":
        return None, None  # let matplotlib handle it
    lims = np.array(lims)
    ticks = list()
    if lims[1] > 20 * lims[0]:
        base = np.array([1, 2, 4])
    else:
        base = np.arange(1, 11)
    for exp in range(
        int(np.floor(np.log10(lims[0]))), int(np.floor(np.log10(lims[1]))) + 1
    ):
        ticks += (base * (10**exp)).tolist()
    ticks = np.array(ticks)
    ticks = ticks[(ticks >= lims[0]) & (ticks <= lims[1])]
    ticklabels = [(f"{t:g}" if t < 1 else f"{t}") for t in ticks]
    return ticks, ticklabels


def _get_flim(flim, fscale, freq, sfreq=None):
    """Get reasonable frequency limits."""
    if flim is None:
        if freq is None:
            flim = [0.1 if fscale == "log" else 0.0, sfreq / 2.0]
        else:
            if fscale == "linear":
                flim = [freq[0]]
            else:
                flim = [freq[0] if freq[0] > 0 else 0.1 * freq[1]]
            flim += [freq[-1]]
    if fscale == "log":
        if flim[0] <= 0:
            raise ValueError(f"flim[0] must be positive, got {flim[0]}")
    elif flim[0] < 0:
        raise ValueError(f"flim[0] must be non-negative, got {flim[0]}")
    return flim


_DEFAULT_ALIM = (-80, 10)


def plot_filter(
    h,
    sfreq,
    freq=None,
    gain=None,
    title=None,
    color="#1f77b4",
    flim=None,
    fscale="log",
    alim=_DEFAULT_ALIM,
    show=True,
    compensate=False,
    plot=("time", "magnitude", "delay"),
    axes=None,
    *,
    dlim=None,
):
    """Plot properties of a filter.

    Parameters
    ----------
    h : dict or ndarray
        An IIR dict or 1D ndarray of coefficients (for FIR filter).
    sfreq : float
        Sample rate of the data (Hz).
    freq : array-like or None
        The ideal response frequencies to plot (must be in ascending order).
        If None (default), do not plot the ideal response.
    gain : array-like or None
        The ideal response gains to plot.
        If None (default), do not plot the ideal response.
    title : str | None
        The title to use. If None (default), determine the title based
        on the type of the system.
    color : color object
        The color to use (default '#1f77b4').
    flim : tuple or None
        If not None, the x-axis frequency limits (Hz) to use.
        If None, freq will be used. If None (default) and freq is None,
        ``(0.1, sfreq / 2.)`` will be used.
    fscale : str
        Frequency scaling to use, can be "log" (default) or "linear".
    alim : tuple
        The y-axis amplitude limits (dB) to use (default: (-60, 10)).
    show : bool
        Show figure if True (default).
    compensate : bool
        If True, compensate for the filter delay (phase will not be shown).

        - For linear-phase FIR filters, this visualizes the filter coefficients
          assuming that the output will be shifted by ``N // 2``.
        - For IIR filters, this changes the filter coefficient display
          by filtering backward and forward, and the frequency response
          by squaring it.

        .. versionadded:: 0.18
    plot : list | tuple | str
        A list of the requested plots from ``time``, ``magnitude`` and
        ``delay``. Default is to plot all three filter properties
        ('time', 'magnitude', 'delay').

        .. versionadded:: 0.21.0
    axes : instance of Axes | list | None
        The axes to plot to. If list, the list must be a list of Axes of
        the same length as the number of requested plot types. If instance of
        Axes, there must be only one filter property plotted.
        Defaults to ``None``.

        .. versionadded:: 0.21.0
    dlim : None | tuple
        The y-axis delay limits (s) to use (default:
        ``(-tmax / 2., tmax / 2.)``).

        .. versionadded:: 1.1.0

    Returns
    -------
    fig : matplotlib.figure.Figure
        The figure containing the plots.

    See Also
    --------
    mne.filter.create_filter
    plot_ideal_filter

    Notes
    -----
    .. versionadded:: 0.14
    """
    import matplotlib.pyplot as plt

    sfreq = float(sfreq)
    _check_option("fscale", fscale, ["log", "linear"])
    if isinstance(plot, str):
        plot = [plot]
    for xi, x in enumerate(plot):
        _check_option(f"plot[{xi}]", x, ("magnitude", "delay", "time"))

    flim = _get_flim(flim, fscale, freq, sfreq)
    if fscale == "log":
        omega = np.logspace(np.log10(flim[0]), np.log10(flim[1]), 1000)
    else:
        omega = np.linspace(flim[0], flim[1], 1000)
    xticks, xticklabels = _filter_ticks(flim, fscale)
    omega /= sfreq / (2 * np.pi)
    if isinstance(h, dict):  # IIR h.ndim == 2:  # second-order sections
        if "sos" in h:
            H = np.ones(len(omega), np.complex128)
            gd = np.zeros(len(omega))
            for section in h["sos"]:
                this_H = freqz(section[:3], section[3:], omega)[1]
                H *= this_H
                if compensate:
                    H *= this_H.conj()  # time reversal is freq conj
                else:
                    # Assume the forward-backward delay zeros out, which it
                    # mostly should
                    with warnings.catch_warnings(record=True):  # singular GD
                        warnings.simplefilter("ignore")
                        gd += group_delay((section[:3], section[3:]), omega)[1]
            n = estimate_ringing_samples(h["sos"])
            delta = np.zeros(n)
            delta[0] = 1
            if compensate:
                delta = np.pad(delta, [(n - 1, 0)], "constant")
                func = sosfiltfilt
                gd += (len(delta) - 1) // 2
            else:
                func = sosfilt
            h = func(h["sos"], delta)
        else:
            H = freqz(h["b"], h["a"], omega)[1]
            if compensate:
                H *= H.conj()
            with warnings.catch_warnings(record=True):  # singular GD
                warnings.simplefilter("ignore")
                gd = group_delay((h["b"], h["a"]), omega)[1]
                if compensate:
                    gd += group_delay((h["b"].conj(), h["a"].conj()), omega)[1]
            n = estimate_ringing_samples((h["b"], h["a"]))
            delta = np.zeros(n)
            delta[0] = 1
            if compensate:
                delta = np.pad(delta, [(n - 1, 0)], "constant")
                func = filtfilt
            else:
                func = lfilter
            h = func(h["b"], h["a"], delta)
        if title is None:
            title = "SOS (IIR) filter"
        if compensate:
            title += " (forward-backward)"
    else:
        H = freqz(h, worN=omega)[1]
        with warnings.catch_warnings(record=True):  # singular GD
            warnings.simplefilter("ignore")
            gd = group_delay((h, [1.0]), omega)[1]
        title = "FIR filter" if title is None else title
        if compensate:
            title += " (delay-compensated)"

    fig = None
    if axes is None:
        fig, axes = plt.subplots(len(plot), 1, layout="constrained")
    if isinstance(axes, plt.Axes):
        axes = [axes]
    elif isinstance(axes, np.ndarray):
        axes = list(axes)
    if fig is None:
        fig = axes[0].get_figure()
    if len(axes) != len(plot):
        raise ValueError(
            f"Length of axes ({len(axes)}) must be the same as number of "
            f"requested filter properties ({len(plot)})"
        )

    t = np.arange(len(h))
    if dlim is None:
        dlim = np.abs(t).max() / 2.0
        dlim = [-dlim, dlim]
    if compensate:
        n_shift = (len(h) - 1) // 2
        t -= n_shift
        assert t[0] == -t[-1]
        gd -= n_shift
    t = t / sfreq
    gd = gd / sfreq
    f = omega * sfreq / (2 * np.pi)
    sl = slice(0 if fscale == "linear" else 1, None, None)
    mag = 10 * np.log10(np.maximum((H * H.conj()).real, 1e-20))

    if "time" in plot:
        ax_time_idx = np.where([p == "time" for p in plot])[0][0]
        axes[ax_time_idx].plot(t, h, color=color, linewidth=1.2)
        axes[ax_time_idx].grid(visible=True, which="major", axis="both", linewidth=0.15)
        axes[ax_time_idx].set(
            xlim=t[[0, -1]], xlabel="Time (s)", ylabel="Amplitude", title=title
        )
    # Magnitude
    if "magnitude" in plot:
        ax_mag_idx = np.where([p == "magnitude" for p in plot])[0][0]
        axes[ax_mag_idx].plot(f[sl], mag[sl], color=color, linewidth=1.2, zorder=4)
        axes[ax_mag_idx].grid(visible=True, which="major", axis="both", linewidth=0.15)
        if freq is not None and gain is not None:
            plot_ideal_filter(freq, gain, axes[ax_mag_idx], fscale=fscale, show=False)
        axes[ax_mag_idx].set(ylabel="Magnitude (dB)", xlabel="", xscale=fscale)
        if xticks is not None:
            axes[ax_mag_idx].set(xticks=xticks)
            axes[ax_mag_idx].set(xticklabels=xticklabels)
        axes[ax_mag_idx].set(
            xlim=flim, ylim=alim, xlabel="Frequency (Hz)", ylabel="Amplitude (dB)"
        )
    # Delay
    if "delay" in plot:
        ax_delay_idx = np.where([p == "delay" for p in plot])[0][0]
        axes[ax_delay_idx].plot(f[sl], gd[sl], color=color, linewidth=1.2, zorder=4)
        axes[ax_delay_idx].grid(
            visible=True, which="major", axis="both", linewidth=0.15
        )
        # shade nulled regions
        for start, stop in zip(*_mask_to_onsets_offsets(mag <= -39.9)):
            axes[ax_delay_idx].axvspan(
                f[start], f[stop - 1], facecolor="k", alpha=0.05, zorder=5
            )
        axes[ax_delay_idx].set(
            xlim=flim, ylabel="Group delay (s)", xlabel="Frequency (Hz)", xscale=fscale
        )
        if xticks is not None:
            axes[ax_delay_idx].set(xticks=xticks)
            axes[ax_delay_idx].set(xticklabels=xticklabels)
        axes[ax_delay_idx].set(
            xlim=flim, ylim=dlim, xlabel="Frequency (Hz)", ylabel="Delay (s)"
        )

    adjust_axes(axes)
    plt_show(show)
    return fig


def plot_ideal_filter(
    freq,
    gain,
    axes=None,
    title="",
    flim=None,
    fscale="log",
    alim=_DEFAULT_ALIM,
    color="r",
    alpha=0.5,
    linestyle="--",
    show=True,
):
    """Plot an ideal filter response.

    Parameters
    ----------
    freq : array-like
        The ideal response frequencies to plot (must be in ascending order).
    gain : array-like or None
        The ideal response gains to plot.
    axes : instance of Axes | None
        The subplot handle. With None (default), axes are created.
    title : str
        The title to use, (default: '').
    flim : tuple or None
        If not None, the x-axis frequency limits (Hz) to use.
        If None (default), freq used.
    fscale : str
        Frequency scaling to use, can be "log" (default) or "linear".
    alim : tuple
        If not None (default), the y-axis limits (dB) to use.
    color : color object
        The color to use (default: 'r').
    alpha : float
        The alpha to use (default: 0.5).
    linestyle : str
        The line style to use (default: '--').
    show : bool
        Show figure if True (default).

    Returns
    -------
    fig : instance of matplotlib.figure.Figure
        The figure.

    See Also
    --------
    plot_filter

    Notes
    -----
    .. versionadded:: 0.14

    Examples
    --------
    Plot a simple ideal band-pass filter::

        >>> from mne.viz import plot_ideal_filter
        >>> freq = [0, 1, 40, 50]
        >>> gain = [0, 1, 1, 0]
        >>> plot_ideal_filter(freq, gain, flim=(0.1, 100))  #doctest: +SKIP
        <...Figure...>
    """
    import matplotlib.pyplot as plt

    my_freq, my_gain = list(), list()
    if freq[0] != 0:
        raise ValueError(
            "freq should start with DC (zero) and end with "
            f"Nyquist, but got {freq[0]} for DC"
        )
    freq = np.array(freq)
    # deal with semilogx problems @ x=0
    _check_option("fscale", fscale, ["log", "linear"])
    if fscale == "log":
        freq[0] = 0.1 * freq[1] if flim is None else min(flim[0], freq[1])
    flim = _get_flim(flim, fscale, freq)
    transitions = list()
    for ii in range(len(freq)):
        if ii < len(freq) - 1 and gain[ii] != gain[ii + 1]:
            transitions += [[freq[ii], freq[ii + 1]]]
            my_freq += np.linspace(freq[ii], freq[ii + 1], 20, endpoint=False).tolist()
            my_gain += np.linspace(gain[ii], gain[ii + 1], 20, endpoint=False).tolist()
        else:
            my_freq.append(freq[ii])
            my_gain.append(gain[ii])
    my_gain = 10 * np.log10(np.maximum(my_gain, 10 ** (alim[0] / 10.0)))
    if axes is None:
        axes = plt.subplots(1, layout="constrained")[1]
    for transition in transitions:
        axes.axvspan(*transition, color=color, alpha=0.1)
    axes.plot(
        my_freq,
        my_gain,
        color=color,
        linestyle=linestyle,
        alpha=alpha,
        linewidth=2,
        zorder=3,
    )
    xticks, xticklabels = _filter_ticks(flim, fscale)
    axes.set(ylim=alim, xlabel="Frequency (Hz)", ylabel="Amplitude (dB)", xscale=fscale)
    if xticks is not None:
        axes.set(xticks=xticks)
        axes.set(xticklabels=xticklabels)
    axes.set(xlim=flim)
    if title:
        axes.set(title=title)
    adjust_axes(axes)
    plt_show(show)
    return axes.figure


def _handle_event_colors(color_dict, unique_events, event_id):
    """Create event-integer-to-color mapping, assigning defaults as needed."""
    default_colors = dict(zip(sorted(unique_events), cycle(_get_color_list())))
    # warn if not enough colors
    if color_dict is None:
        if len(unique_events) > len(_get_color_list()):
            warn(
                "More events than default colors available. You should pass "
                "a list of unique colors."
            )
    else:
        custom_colors = dict()
        for key, color in color_dict.items():
            if key in unique_events:  # key was a valid event integer
                custom_colors[key] = color
            elif key in event_id:  # key was an event label
                custom_colors[event_id[key]] = color
            else:  # key not a valid event, warn and ignore
                warn(
                    f"Event ID {key} is in the color dict but is not "
                    "present in events or event_id."
                )
        # warn if color_dict is missing any entries
        unassigned = sorted(set(unique_events) - set(custom_colors))
        if len(unassigned):
            unassigned_str = ", ".join(str(e) for e in unassigned)
            warn(
                f"Color was not assigned for event{_pl(unassigned)} {unassigned_str}. "
                "Default colors will be used."
            )
        default_colors.update(custom_colors)
    return default_colors


@fill_doc
def plot_csd(
    csd, info=None, mode="csd", colorbar=True, cmap=None, n_cols=None, show=True
):
    """Plot CSD matrices.

    A sub-plot is created for each frequency. If an info object is passed to
    the function, different channel types are plotted in different figures.

    Parameters
    ----------
    csd : instance of CrossSpectralDensity
        The CSD matrix to plot.
    %(info)s
        Used to split the figure by channel-type, if provided.
        By default, the CSD matrix is plotted as a whole.
    mode : 'csd' | 'coh'
        Whether to plot the cross-spectral density ('csd', the default), or
        the coherence ('coh') between the channels.
    colorbar : bool
        Whether to show a colorbar. Defaults to ``True``.
    cmap : str | None
        The matplotlib colormap to use. Defaults to None, which means the
        colormap will default to matplotlib's default.
    n_cols : int | None
        CSD matrices are plotted in a grid. This parameter controls how
        many matrix to plot side by side before starting a new row. By
        default, a number will be chosen to make the grid as square as
        possible.
    show : bool
        Whether to show the figure. Defaults to ``True``.

    Returns
    -------
    fig : list of Figure
        The figures created by this function.
    """
    import matplotlib.pyplot as plt

    if mode not in ["csd", "coh"]:
        raise ValueError('"mode" should be either "csd" or "coh".')

    if info is not None:
        info_ch_names = info["ch_names"]
        sel_eeg = pick_types(info, meg=False, eeg=True, ref_meg=False, exclude=[])
        sel_mag = pick_types(info, meg="mag", eeg=False, ref_meg=False, exclude=[])
        sel_grad = pick_types(info, meg="grad", eeg=False, ref_meg=False, exclude=[])
        idx_eeg = [
            csd.ch_names.index(info_ch_names[c])
            for c in sel_eeg
            if info_ch_names[c] in csd.ch_names
        ]
        idx_mag = [
            csd.ch_names.index(info_ch_names[c])
            for c in sel_mag
            if info_ch_names[c] in csd.ch_names
        ]
        idx_grad = [
            csd.ch_names.index(info_ch_names[c])
            for c in sel_grad
            if info_ch_names[c] in csd.ch_names
        ]
        indices = [idx_eeg, idx_mag, idx_grad]
        titles = ["EEG", "Magnetometers", "Gradiometers"]

        if mode == "csd":
            # The units in which to plot the CSD
            units = dict(eeg="µV²", grad="fT²/cm²", mag="fT²")
            scalings = dict(eeg=1e12, grad=1e26, mag=1e30)
    else:
        indices = [np.arange(len(csd.ch_names))]
        if mode == "csd":
            titles = ["Cross-spectral density"]
            # Units and scaling unknown
            units = dict()
            scalings = dict()
        elif mode == "coh":
            titles = ["Coherence"]

    n_freqs = len(csd.frequencies)

    if n_cols is None:
        n_cols = int(np.ceil(np.sqrt(n_freqs)))
    n_rows = int(np.ceil(n_freqs / float(n_cols)))

    figs = []
    for ind, title, ch_type in zip(indices, titles, ["eeg", "mag", "grad"]):
        if len(ind) == 0:
            continue

        fig, axes = plt.subplots(
            n_rows,
            n_cols,
            squeeze=False,
            figsize=(2 * n_cols + 1, 2.2 * n_rows),
            layout="constrained",
        )

        csd_mats = []
        for i in range(len(csd.frequencies)):
            cm = csd.get_data(index=i)[ind][:, ind]
            if mode == "csd":
                cm = np.abs(cm) * scalings.get(ch_type, 1)
            elif mode == "coh":
                # Compute coherence from the CSD matrix
                psd = np.diag(cm).real
                cm = np.abs(cm) ** 2 / psd[np.newaxis, :] / psd[:, np.newaxis]
            csd_mats.append(cm)

        vmax = np.max(csd_mats)

        for i, (freq, mat) in enumerate(zip(csd.frequencies, csd_mats)):
            ax = axes[i // n_cols][i % n_cols]
            im = ax.imshow(mat, interpolation="nearest", cmap=cmap, vmin=0, vmax=vmax)
            ax.set_xticks([])
            ax.set_yticks([])
            if csd._is_sum:
                ax.set_title(f"{np.min(freq):.1f}-{np.max(freq):.1f} Hz.")
            else:
                ax.set_title(f"{freq:.1f} Hz.")

        plt.suptitle(title)
        if colorbar:
            cb = plt.colorbar(im, ax=[a for ax_ in axes for a in ax_])
            if mode == "csd":
                label = "CSD"
                if ch_type in units:
                    label += f" ({units[ch_type]})"
                cb.set_label(label)
            elif mode == "coh":
                cb.set_label("Coherence")

        figs.append(fig)

    plt_show(show)
    return figs


def plot_chpi_snr(snr_dict, axes=None):
    """Plot time-varying SNR estimates of the HPI coils.

    Parameters
    ----------
    snr_dict : dict
        The dictionary returned by `~mne.chpi.compute_chpi_snr`. Must have keys
        ``times``, ``freqs``, ``TYPE_snr``, ``TYPE_power``, and ``TYPE_resid``
        (where ``TYPE`` can be ``mag`` or ``grad`` or both).
    axes : None | list of matplotlib.axes.Axes
        Figure axes in which to draw the SNR, power, and residual plots. The
        number of axes should be 3× the number of MEG sensor types present in
        ``snr_dict``. If ``None`` (the default), a new
        `~matplotlib.figure.Figure` is created with the required number of
        axes.

    Returns
    -------
    fig : instance of matplotlib.figure.Figure
        A figure with subplots for SNR, power, and residual variance,
        separately for magnetometers and/or gradiometers (depending on what is
        present in ``snr_dict``).

    Notes
    -----
    If you supply a list of existing `~matplotlib.axes.Axes`, then the figure
    legend will not be drawn automatically. If you still want it, running
    ``fig.legend(loc='right', title='cHPI frequencies')`` will recreate it.

    .. versionadded:: 0.24
    """
    import matplotlib.pyplot as plt

    valid_keys = list(snr_dict)[2:]
    titles = dict(snr="SNR", power="cHPI power", resid="Residual variance")
    full_names = dict(mag="magnetometers", grad="gradiometers")
    axes_was_none = axes is None
    if axes_was_none:
        fig, axes = plt.subplots(len(valid_keys), 1, sharex=True, layout="constrained")
    else:
        fig = axes[0].get_figure()
    if len(axes) != len(valid_keys):
        raise ValueError(
            f"axes must be a list of {len(valid_keys)} axes, got "
            f"length {len(axes)} ({axes})."
        )
    fig.set_size_inches(10, 10)
    legend_labels_exist = False
    for key, ax in zip(valid_keys, axes):
        ch_type, kind = key.split("_")
        scaling = 1 if kind == "snr" else DEFAULTS["scalings"][ch_type]
        plot_kwargs = dict(color="k") if kind == "resid" else dict()
        lines = ax.plot(snr_dict["times"], snr_dict[key] * scaling**2, **plot_kwargs)
        # the freqs should be the same for all sensor types (and for SNR and
        # power subplots), so we only need to label the lines on one axes
        # (otherwise we get duplicate legend entries).
        if not legend_labels_exist:
            for line, freq in zip(lines, snr_dict["freqs"]):
                line.set_label(f"{freq} Hz")
            legend_labels_exist = True
        unit = DEFAULTS["units"][ch_type]
        unit = f"({unit})" if "/" in unit else unit
        set_kwargs = dict(
            title=f"{titles[kind]}, {full_names[ch_type]}",
            ylabel="dB" if kind == "snr" else f"{unit}²",
        )
        if not axes_was_none:
            set_kwargs.update(xlabel="Time (s)")
        ax.set(**set_kwargs)
    if axes_was_none:
        ax.set(xlabel="Time (s)")
        fig.align_ylabels()
        fig.legend(loc="right", title="cHPI frequencies")
    return fig
