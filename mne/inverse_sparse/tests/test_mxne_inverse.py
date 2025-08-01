# Authors: The MNE-Python contributors.
# License: BSD-3-Clause
# Copyright the MNE-Python contributors.

import numpy as np
import pytest
from numpy.testing import (
    assert_allclose,
    assert_array_almost_equal,
    assert_array_equal,
    assert_array_less,
)

import mne
from mne import convert_forward_solution, read_cov, read_evokeds, read_forward_solution
from mne.datasets import testing
from mne.dipole import Dipole
from mne.inverse_sparse import mixed_norm, tf_mixed_norm
from mne.inverse_sparse.mxne_inverse import (
    _compute_mxne_sure,
    _split_gof,
    make_stc_from_dipoles,
)
from mne.inverse_sparse.mxne_optim import norm_l2inf
from mne.label import read_label
from mne.minimum_norm import apply_inverse, make_inverse_operator
from mne.minimum_norm.tests.test_inverse import assert_stc_res, assert_var_exp_log
from mne.simulation import simulate_evoked, simulate_sparse_stc
from mne.source_estimate import VolSourceEstimate
from mne.utils import _record_warnings, assert_stcs_equal, catch_logging

data_path = testing.data_path(download=False)
# NOTE: These use the ave and cov from sample dataset (no _trunc)
fname_data = data_path / "MEG" / "sample" / "sample_audvis-ave.fif"
fname_cov = data_path / "MEG" / "sample" / "sample_audvis-cov.fif"
fname_raw = data_path / "MEG" / "sample" / "sample_audvis_trunc_raw.fif"
fname_fwd = data_path / "MEG" / "sample" / "sample_audvis_trunc-meg-eeg-oct-6-fwd.fif"
label = "Aud-rh"
fname_label = data_path / "MEG" / "sample" / "labels" / f"{label}.label"


@pytest.fixture(scope="module", params=[testing._pytest_param])
def forward():
    """Get a forward solution."""
    # module scope it for speed (but don't overwrite in use!)
    return read_forward_solution(fname_fwd)


@testing.requires_testing_data
@pytest.mark.timeout(150)  # ~30 s on Travis Linux
@pytest.mark.slowtest
def test_mxne_inverse_standard(forward):
    """Test (TF-)MxNE inverse computation."""
    # Read noise covariance matrix
    cov = read_cov(fname_cov)

    # Handling average file
    loose = 0.0
    depth = 0.9

    evoked = read_evokeds(fname_data, condition=0, baseline=(None, 0))
    evoked.crop(tmin=-0.05, tmax=0.2)

    evoked_l21 = evoked.copy()
    evoked_l21.crop(tmin=0.081, tmax=0.1)
    label = read_label(fname_label)
    assert label.hemi == "rh"

    forward = convert_forward_solution(forward, surf_ori=True)

    # Reduce source space to make test computation faster
    inverse_operator = make_inverse_operator(
        evoked_l21.info,
        forward,
        cov,
        loose=loose,
        depth=depth,
        fixed=True,
        use_cps=True,
    )
    stc_dspm = apply_inverse(
        evoked_l21, inverse_operator, lambda2=1.0 / 9.0, method="dSPM"
    )
    stc_dspm.data[np.abs(stc_dspm.data) < 12] = 0.0
    stc_dspm.data[np.abs(stc_dspm.data) >= 12] = 1.0
    weights_min = 0.5

    # MxNE tests
    alpha = 70  # spatial regularization parameter

    with _record_warnings():  # CD
        stc_cd = mixed_norm(
            evoked_l21,
            forward,
            cov,
            alpha,
            loose=loose,
            depth=depth,
            maxit=300,
            tol=1e-8,
            active_set_size=10,
            weights=stc_dspm,
            weights_min=weights_min,
            solver="cd",
        )
    stc_bcd = mixed_norm(
        evoked_l21,
        forward,
        cov,
        alpha,
        loose=loose,
        depth=depth,
        maxit=300,
        tol=1e-8,
        active_set_size=10,
        weights=stc_dspm,
        weights_min=weights_min,
        solver="bcd",
    )
    assert_array_almost_equal(stc_cd.times, evoked_l21.times, 5)
    assert_array_almost_equal(stc_bcd.times, evoked_l21.times, 5)
    assert_allclose(stc_cd.data, stc_bcd.data, rtol=1e-3, atol=0.0)
    assert stc_cd.vertices[1][0] in label.vertices
    assert stc_bcd.vertices[1][0] in label.vertices

    # vector
    with _record_warnings():  # no convergence
        stc = mixed_norm(evoked_l21, forward, cov, alpha, loose=1, maxit=2)
    with _record_warnings():  # no convergence
        stc_vec = mixed_norm(
            evoked_l21, forward, cov, alpha, loose=1, maxit=2, pick_ori="vector"
        )
    assert_stcs_equal(stc_vec.magnitude(), stc)
    with _record_warnings(), pytest.raises(ValueError, match="pick_ori="):
        mixed_norm(evoked_l21, forward, cov, alpha, loose=0, maxit=2, pick_ori="vector")

    with _record_warnings(), catch_logging() as log:  # CD
        dips = mixed_norm(
            evoked_l21,
            forward,
            cov,
            alpha,
            loose=loose,
            depth=depth,
            maxit=300,
            tol=1e-8,
            active_set_size=10,
            weights=stc_dspm,
            weights_min=weights_min,
            solver="cd",
            return_as_dipoles=True,
            verbose=True,
        )
    stc_dip = make_stc_from_dipoles(dips, forward["src"])
    assert isinstance(dips[0], Dipole)
    assert stc_dip.subject == "sample"
    assert_stcs_equal(stc_cd, stc_dip)
    assert_var_exp_log(log.getvalue(), 51, 53)  # 51.8

    # Single time point things should match
    with _record_warnings(), catch_logging() as log:
        dips = mixed_norm(
            evoked_l21.copy().crop(0.081, 0.081),
            forward,
            cov,
            alpha,
            loose=loose,
            depth=depth,
            maxit=300,
            tol=1e-8,
            active_set_size=10,
            weights=stc_dspm,
            weights_min=weights_min,
            solver="cd",
            return_as_dipoles=True,
            verbose=True,
        )
    assert_var_exp_log(log.getvalue(), 37.8, 38.0)  # 37.9
    gof = sum(dip.gof[0] for dip in dips)  # these are now partial exp vars
    assert_allclose(gof, 37.9, atol=0.1)

    with _record_warnings(), catch_logging() as log:
        stc, res = mixed_norm(
            evoked_l21,
            forward,
            cov,
            alpha,
            loose=loose,
            depth=depth,
            maxit=300,
            tol=1e-8,
            weights=stc_dspm,  # gh-6382
            active_set_size=10,
            return_residual=True,
            solver="cd",
            verbose=True,
        )
    assert_array_almost_equal(stc.times, evoked_l21.times, 5)
    assert stc.vertices[1][0] in label.vertices
    assert_var_exp_log(log.getvalue(), 51, 53)  # 51.8
    assert stc.data.min() < -1e-9  # signed
    assert_stc_res(evoked_l21, stc, forward, res)

    # irMxNE tests
    with _record_warnings(), catch_logging() as log:  # CD
        stc, residual = mixed_norm(
            evoked_l21,
            forward,
            cov,
            alpha,
            n_mxne_iter=5,
            loose=0.0001,
            depth=depth,
            maxit=300,
            tol=1e-8,
            active_set_size=10,
            solver="cd",
            return_residual=True,
            pick_ori="vector",
            verbose=True,
        )
    assert_array_almost_equal(stc.times, evoked_l21.times, 5)
    assert stc.vertices[1][0] in label.vertices
    assert stc.vertices == [[63152], [79017]]
    assert_var_exp_log(log.getvalue(), 51, 53)  # 51.8
    assert_stc_res(evoked_l21, stc, forward, residual)

    # Do with TF-MxNE for test memory savings
    alpha = 60.0  # overall regularization parameter
    l1_ratio = 0.01  # temporal regularization proportion

    stc, _ = tf_mixed_norm(
        evoked,
        forward,
        cov,
        loose=loose,
        depth=depth,
        maxit=100,
        tol=1e-4,
        tstep=4,
        wsize=16,
        window=0.1,
        weights=stc_dspm,
        weights_min=weights_min,
        return_residual=True,
        alpha=alpha,
        l1_ratio=l1_ratio,
    )
    assert_array_almost_equal(stc.times, evoked.times, 5)
    assert stc.vertices[1][0] in label.vertices

    # vector
    stc_nrm = tf_mixed_norm(
        evoked,
        forward,
        cov,
        loose=1,
        depth=depth,
        maxit=2,
        tol=1e-4,
        tstep=4,
        wsize=16,
        window=0.1,
        weights=stc_dspm,
        weights_min=weights_min,
        alpha=alpha,
        l1_ratio=l1_ratio,
    )
    stc_vec, residual = tf_mixed_norm(
        evoked,
        forward,
        cov,
        loose=1,
        depth=depth,
        maxit=2,
        tol=1e-4,
        tstep=4,
        wsize=16,
        window=0.1,
        weights=stc_dspm,
        weights_min=weights_min,
        alpha=alpha,
        l1_ratio=l1_ratio,
        pick_ori="vector",
        return_residual=True,
    )
    assert_stcs_equal(stc_vec.magnitude(), stc_nrm)

    pytest.raises(
        ValueError, tf_mixed_norm, evoked, forward, cov, alpha=101, l1_ratio=0.03
    )
    pytest.raises(
        ValueError, tf_mixed_norm, evoked, forward, cov, alpha=50.0, l1_ratio=1.01
    )


@pytest.mark.slowtest
@testing.requires_testing_data
def test_mxne_vol_sphere():
    """Test (TF-)MxNE with a sphere forward and volumic source space."""
    evoked = read_evokeds(fname_data, condition=0, baseline=(None, 0))
    evoked.crop(tmin=-0.05, tmax=0.2)
    cov = read_cov(fname_cov)

    evoked_l21 = evoked.copy()
    evoked_l21.crop(tmin=0.081, tmax=0.1)

    info = evoked.info
    sphere = mne.make_sphere_model(r0=(0.0, 0.0, 0.0), head_radius=0.080)
    src = mne.setup_volume_source_space(
        subject=None,
        pos=15.0,
        mri=None,
        sphere=(0.0, 0.0, 0.0, 0.08),
        bem=None,
        mindist=5.0,
        exclude=2.0,
        sphere_units="m",
    )
    fwd = mne.make_forward_solution(
        info, trans=None, src=src, bem=sphere, eeg=False, meg=True
    )

    alpha = 80.0

    # Computing inverse with restricted orientations should also work, since
    # we have a discrete source space.
    stc = mixed_norm(
        evoked_l21,
        fwd,
        cov,
        alpha,
        loose=0.2,
        return_residual=False,
        maxit=3,
        tol=1e-8,
        active_set_size=10,
    )
    assert_array_almost_equal(stc.times, evoked_l21.times, 5)

    # irMxNE tests
    with catch_logging() as log:
        stc = mixed_norm(
            evoked_l21,
            fwd,
            cov,
            alpha,
            n_mxne_iter=1,
            maxit=30,
            tol=1e-8,
            active_set_size=10,
            verbose=True,
        )
    assert isinstance(stc, VolSourceEstimate)
    assert_array_almost_equal(stc.times, evoked_l21.times, 5)
    assert_var_exp_log(log.getvalue(), 9, 11)  # 10.2

    # Compare orientation obtained using fit_dipole and gamma_map
    # for a simulated evoked containing a single dipole
    stc = mne.VolSourceEstimate(
        50e-9 * np.random.RandomState(42).randn(1, 4),
        vertices=[stc.vertices[0][:1]],
        tmin=stc.tmin,
        tstep=stc.tstep,
    )
    evoked_dip = mne.simulation.simulate_evoked(
        fwd,
        stc,
        info,
        cov,
        nave=1e9,
        use_cps=True,
        random_state=0,
    )

    dip_mxne = mixed_norm(
        evoked_dip,
        fwd,
        cov,
        alpha=80,
        n_mxne_iter=1,
        maxit=30,
        tol=1e-8,
        active_set_size=10,
        return_as_dipoles=True,
    )

    amp_max = [np.max(d.amplitude) for d in dip_mxne]
    dip_mxne = dip_mxne[np.argmax(amp_max)]
    assert dip_mxne.pos[0] in src[0]["rr"][stc.vertices[0]]

    dip_fit = mne.fit_dipole(evoked_dip, cov, sphere)[0]
    assert np.abs(np.dot(dip_fit.ori[0], dip_mxne.ori[0])) > 0.99
    dist = 1000 * np.linalg.norm(dip_fit.pos[0] - dip_mxne.pos[0])
    assert dist < 4.0  # within 4 mm

    # Do with TF-MxNE for test memory savings
    alpha = 60.0  # overall regularization parameter
    l1_ratio = 0.01  # temporal regularization proportion

    stc, _ = tf_mixed_norm(
        evoked,
        fwd,
        cov,
        maxit=3,
        tol=1e-4,
        tstep=16,
        wsize=32,
        window=0.1,
        alpha=alpha,
        l1_ratio=l1_ratio,
        return_residual=True,
    )
    assert isinstance(stc, VolSourceEstimate)
    assert_array_almost_equal(stc.times, evoked.times, 5)


@pytest.mark.parametrize("mod", (None, "mult", "augment", "sign", "zero", "less"))
def test_split_gof_basic(mod):
    """Test splitting the goodness of fit."""
    # first a trivial case
    gain = np.array([[0.0, 1.0, 1.0], [1.0, 1.0, 0.0]]).T
    M = np.ones((3, 1))
    X = np.ones((2, 1))
    M_est = gain @ X
    assert_allclose(M_est, np.array([[1.0, 2.0, 1.0]]).T)  # a reasonable estimate
    if mod == "mult":
        gain *= [1.0, -0.5]
        X[1] *= -2
    elif mod == "augment":
        gain = np.concatenate((gain, np.zeros((3, 1))), axis=1)
        X = np.concatenate((X, [[1.0]]))
    elif mod == "sign":
        gain[1] *= -1
        M[1] *= -1
        M_est[1] *= -1
    elif mod in ("zero", "less"):
        gain = np.array([[1, 1.0, 1.0], [1.0, 1.0, 1.0]]).T
        if mod == "zero":
            X[:, 0] = [1.0, 0.0]
        else:
            X[:, 0] = [1.0, 0.5]
        M_est = gain @ X
    else:
        assert mod is None
    res = M - M_est
    gof = 100 * (1.0 - (res * res).sum() / (M * M).sum())
    gof_split = _split_gof(M, X, gain)
    assert_allclose(gof_split.sum(), gof)
    want = gof_split[[0, 0]]
    if mod == "augment":
        want = np.concatenate((want, [[0]]))
    if mod in ("mult", "less"):
        assert_array_less(gof_split[1], gof_split[0])
    elif mod == "zero":
        assert_allclose(gof_split[0], gof_split.sum(0))
        assert_allclose(gof_split[1], 0.0, atol=1e-6)
    else:
        assert_allclose(gof_split, want, atol=1e-12)


@testing.requires_testing_data
@pytest.mark.parametrize(
    "idx, weights",
    [
        # empirically determined approximately orthogonal columns: 0, 15157, 19448
        ([0], [1]),
        ([0, 15157], [1, 1]),
        ([0, 15157], [1, 3]),
        ([0, 15157], [5, -1]),
        ([0, 15157, 19448], [1, 1, 1]),
        ([0, 15157, 19448], [1e-2, 1, 5]),
    ],
)
def test_split_gof_meg(forward, idx, weights):
    """Test GOF splitting on MEG data."""
    gain = forward["sol"]["data"][:, idx]
    # close to orthogonal
    norms = np.linalg.norm(gain, axis=0)
    triu = np.triu_indices(len(idx), 1)
    prods = np.abs(np.dot(gain.T, gain) / np.outer(norms, norms))[triu]
    assert_array_less(prods, 5e-3)  # approximately orthogonal
    # first, split across time (one dipole per time point)
    M = gain * weights
    gof_split = _split_gof(M, np.diag(weights), gain)
    assert_allclose(gof_split.sum(0), 100.0, atol=1e-5)  # all sum to 100
    assert_allclose(gof_split, 100 * np.eye(len(weights)), atol=1)  # loc
    # next, summed to a single time point (all dipoles active at one time pt)
    weights = np.array(weights)[:, np.newaxis]
    x = gain @ weights
    assert x.shape == (gain.shape[0], 1)
    gof_split = _split_gof(x, weights, gain)
    want = (norms * weights.T).T ** 2
    want = 100 * want / want.sum()
    assert_allclose(gof_split, want, atol=1e-3, rtol=1e-2)
    assert_allclose(gof_split.sum(), 100, rtol=1e-5)


@pytest.mark.parametrize(
    "n_sensors, n_dipoles, n_times",
    [
        (10, 15, 7),
        (20, 60, 20),
    ],
)
@pytest.mark.parametrize("nnz", [2, 4])
@pytest.mark.parametrize("corr", [0.75])
@pytest.mark.parametrize("n_orient", [1, 3])
def test_mxne_inverse_sure_synthetic(
    n_sensors, n_dipoles, n_times, nnz, corr, n_orient, snr=4
):
    """Tests SURE criterion for automatic alpha selection on synthetic data."""
    rng = np.random.RandomState(0)
    sigma = np.sqrt(1 - corr**2)
    U = rng.randn(n_sensors)
    # generate gain matrix
    G = np.empty([n_sensors, n_dipoles], order="F")
    G[:, :n_orient] = np.expand_dims(U, axis=-1)
    n_dip_per_pos = n_dipoles // n_orient
    for j in range(1, n_dip_per_pos):
        U *= corr
        U += sigma * rng.randn(n_sensors)
        G[:, j * n_orient : (j + 1) * n_orient] = np.expand_dims(U, axis=-1)
    # generate coefficient matrix
    support = rng.choice(n_dip_per_pos, nnz, replace=False)
    X = np.zeros((n_dipoles, n_times))
    for k in support:
        X[k * n_orient : (k + 1) * n_orient, :] = rng.normal(size=(n_orient, n_times))
    # generate measurement matrix
    M = G @ X
    noise = rng.randn(n_sensors, n_times)
    sigma = 1 / np.linalg.norm(noise) * np.linalg.norm(M) / snr
    M += sigma * noise
    # inverse modeling with sure
    alpha_max = norm_l2inf(np.dot(G.T, M), n_orient, copy=False)
    alpha_grid = np.geomspace(alpha_max, alpha_max / 10, num=15)
    _, active_set, _ = _compute_mxne_sure(
        M,
        G,
        alpha_grid,
        sigma=sigma,
        n_mxne_iter=5,
        maxit=3000,
        tol=1e-4,
        n_orient=n_orient,
        active_set_size=10,
        debias=True,
        solver="auto",
        dgap_freq=10,
        random_state=0,
        verbose=False,
    )
    assert np.count_nonzero(active_set, axis=-1) == n_orient * nnz


@pytest.mark.slowtest  # slow on Azure
@testing.requires_testing_data
def test_mxne_inverse_sure_meg():
    """Tests SURE criterion for automatic alpha selection on MEG data."""

    def data_fun(times):
        data = np.zeros(times.shape)
        data[times >= 0] = 50e-9
        return data

    n_dipoles = 2
    raw = mne.io.read_raw_fif(fname_raw).pick_types("grad", exclude="bads")
    raw.del_proj()
    info = raw.info
    del raw
    noise_cov = mne.make_ad_hoc_cov(info)
    label_names = ["Aud-lh", "Aud-rh"]
    labels = [
        mne.read_label(data_path / "MEG" / "sample" / "labels" / f"{ln}.label")
        for ln in label_names
    ]
    fname_fwd = (
        data_path / "MEG" / "sample" / "sample_audvis_trunc-meg-eeg-oct-4-fwd.fif"
    )
    forward = mne.read_forward_solution(fname_fwd)
    forward = mne.pick_channels_forward(forward, info["ch_names"])
    times = np.arange(100, dtype=np.float64) / info["sfreq"] - 0.1
    stc = simulate_sparse_stc(
        forward["src"],
        n_dipoles=n_dipoles,
        times=times,
        random_state=1,
        labels=labels,
        data_fun=data_fun,
    )
    assert len(stc.vertices) == 2
    assert_array_equal(stc.vertices[0], [89259])
    assert_array_equal(stc.vertices[1], [70279])
    nave = 30
    evoked = simulate_evoked(
        forward,
        stc,
        info,
        noise_cov,
        nave=nave,
        use_cps=False,
        iir_filter=None,
        random_state=0,
    )
    evoked = evoked.crop(tmin=0, tmax=10e-3)
    stc_ = mixed_norm(
        evoked, forward, noise_cov, loose=0.9, n_mxne_iter=5, depth=0.9, random_state=1
    )
    assert len(stc_.vertices) == len(stc.vertices) == 2
    for si in range(len(stc_.vertices)):
        assert_array_equal(stc_.vertices[si], stc.vertices[si], err_msg=f"{si=}")


@pytest.mark.slowtest  # slow on Azure
@testing.requires_testing_data
def test_mxne_inverse_empty():
    """Tests solver with too high alpha."""
    evoked = read_evokeds(fname_data, condition=0, baseline=(None, 0))
    evoked.pick("grad", exclude="bads")
    fname_fwd = (
        data_path / "MEG" / "sample" / "sample_audvis_trunc-meg-eeg-oct-4-fwd.fif"
    )
    forward = mne.read_forward_solution(fname_fwd)
    forward = mne.pick_types_forward(
        forward, meg="grad", eeg=False, exclude=evoked.info["bads"]
    )
    cov = read_cov(fname_cov)
    with pytest.warns(RuntimeWarning, match="too big"):
        stc, residual = mixed_norm(
            evoked,
            forward,
            cov,
            n_mxne_iter=3,
            alpha=99,
            return_residual=True,
            random_state=0,
        )
        assert stc.data.size == 0
        assert stc.vertices[0].size == 0
        assert stc.vertices[1].size == 0
        assert_allclose(evoked.data, residual.data)
