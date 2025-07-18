# Authors: The MNE-Python contributors.
# License: BSD-3-Clause
# Copyright the MNE-Python contributors.

import pathlib
import re
from contextlib import contextmanager
from functools import partial
from pathlib import Path

import numpy as np
import pytest
from numpy.testing import assert_allclose, assert_array_equal
from scipy import sparse

import mne
from mne import compute_raw_covariance, concatenate_raws, pick_info, pick_types
from mne._fiff.constants import FIFF
from mne.annotations import _annotations_starts_stops
from mne.chpi import filter_chpi, read_head_pos
from mne.datasets import testing
from mne.fixes import sph_harm_y
from mne.forward import _prep_meg_channels, use_coil_def
from mne.io import (
    BaseRaw,
    read_info,
    read_raw_bti,
    read_raw_ctf,
    read_raw_fif,
    read_raw_kit,
)
from mne.preprocessing import (
    annotate_amplitude,
    annotate_movement,
    compute_maxwell_basis,
    find_bad_channels_maxwell,
    maxwell_filter_prepare_emptyroom,
)
from mne.preprocessing import (
    maxwell_filter as _maxwell_filter_ola,
)
from mne.preprocessing.maxwell import (
    _bases_complex_to_real,
    _bases_real_to_complex,
    _get_n_moments,
    _prep_mf_coils,
    _sh_complex_to_real,
    _sh_negate,
    _sh_real_to_complex,
    _sss_basis_basic,
    _trans_sss_basis,
)
from mne.rank import _compute_rank_int, _get_rank_sss, compute_rank
from mne.utils import (
    _record_warnings,
    assert_meg_snr,
    buggy_mkl_svd,
    catch_logging,
    object_diff,
    use_log_level,
)

io_path = Path(__file__).parents[2] / "io" / "tests" / "data"
raw_small_fname = io_path / "test_raw.fif"

data_path = testing.data_path(download=False)
sss_path = data_path / "SSS"
raw_fname = sss_path / "test_move_anon_raw.fif"
sss_std_fname = sss_path / "test_move_anon_stdOrigin_raw_sss.fif"
sss_nonstd_fname = sss_path / "test_move_anon_nonStdOrigin_raw_sss.fif"
sss_bad_recon_fname = sss_path / "test_move_anon_badRecon_raw_sss.fif"
sss_reg_in_fname = sss_path / "test_move_anon_regIn_raw_sss.fif"
sss_fine_cal_fname = sss_path / "test_move_anon_fineCal_raw_sss.fif"
sss_ctc_fname = sss_path / "test_move_anon_crossTalk_raw_sss.fif"
sss_trans_default_fname = sss_path / "test_move_anon_transDefault_raw_sss.fif"
sss_trans_sample_fname = sss_path / "test_move_anon_transSample_raw_sss.fif"
sss_st1FineCalCrossTalkRegIn_fname = (
    sss_path / "test_move_anon_st1FineCalCrossTalkRegIn_raw_sss.fif"
)
sss_st1FineCalCrossTalkRegInTransSample_fname = (
    sss_path / "test_move_anon_st1FineCalCrossTalkRegInTransSample_raw_sss.fif"
)
sss_movecomp_fname = sss_path / "test_move_anon_movecomp_raw_sss.fif"
sss_movecomp_reg_in_fname = sss_path / "test_move_anon_movecomp_regIn_raw_sss.fif"
sss_movecomp_reg_in_st4s_fname = (
    sss_path / "test_move_anon_movecomp_regIn_st4s_raw_sss.fif"
)
skip_fname = data_path / "misc" / "intervalrecording_raw.fif"
erm_fname = sss_path / "test_move_anon_erm_raw.fif"
sss_erm_std_fname = sss_path / "test_move_anon_erm_devOrigin_raw_sss.fif"
sss_erm_reg_in_fname = sss_path / "test_move_anon_erm_regIn_raw_sss.fif"
sss_erm_fine_cal_fname = sss_path / "test_move_anon_erm_fineCal_raw_sss.fif"
sss_erm_ctc_fname = sss_path / "test_move_anon_erm_crossTalk_raw_sss.fif"
sss_erm_st_fname = sss_path / "test_move_anon_erm_st1_raw_sss.fif"
sss_erm_st1FineCalCrossTalk_fname = (
    sss_path / "test_move_anon_erm_st1FineCalCrossTalk_raw_sss.fif"
)
sss_erm_st1FineCalCrossTalkRegIn_fname = (
    sss_path / "test_move_anon_erm_st1FineCalCrossTalkRegIn_raw_sss.fif"
)

sample_fname = data_path / "MEG" / "sample" / "sample_audvis_trunc_raw.fif"
sss_samp_reg_in_fname = data_path / "SSS" / "sample_audvis_trunc_regIn_raw_sss.fif"
sss_samp_fname = data_path / "SSS" / "sample_audvis_trunc_raw_sss.fif"

pos_fname = data_path / "SSS" / "test_move_anon_raw.pos"

bases_fname = sss_path / "sss_data.mat"
fine_cal_fname = sss_path / "sss_cal_3053.dat"
fine_cal_fname_3d = sss_path / "sss_cal_3053_3d.dat"
ctc_fname = sss_path / "ct_sparse.fif"
fine_cal_mgh_fname = sss_path / "sss_cal_mgh.dat"
ctc_mgh_fname = sss_path / "ct_sparse_mgh.fif"

triux_path = data_path / "SSS" / "TRIUX"
tri_fname = triux_path / "triux_bmlhus_erm_raw.fif"
tri_sss_fname = triux_path / "triux_bmlhus_erm_raw_sss.fif"
tri_sss_reg_fname = triux_path / "triux_bmlhus_erm_regIn_raw_sss.fif"
tri_sss_st4_fname = triux_path / "triux_bmlhus_erm_st4_raw_sss.fif"
tri_sss_ctc_fname = triux_path / "triux_bmlhus_erm_ctc_raw_sss.fif"
tri_sss_cal_fname = triux_path / "triux_bmlhus_erm_cal_raw_sss.fif"
tri_sss_ctc_cal_fname = triux_path / "triux_bmlhus_erm_ctc_cal_raw_sss.fif"
tri_sss_ctc_cal_reg_in_fname = triux_path / "triux_bmlhus_erm_ctc_cal_regIn_raw_sss.fif"
tri_ctc_fname = triux_path / "ct_sparse_BMLHUS.fif"
tri_cal_fname = triux_path / "sss_cal_BMLHUS.dat"

io_dir = Path(__file__).parents[2] / "io"
fname_ctf_raw = io_dir / "tests" / "data" / "test_ctf_comp_raw.fif"
ctf_fname_continuous = data_path / "CTF" / "testdata_ctf.ds"

# In some of the tests, use identical coil defs to what is used in
# MaxFilter
elekta_def_fname = Path(mne.__file__).parent / "data" / "coil_def_Elekta.dat"

int_order, ext_order = 8, 3
mf_head_origin = (0.0, 0.0, 0.04)
mf_meg_origin = (0.0, 0.013, -0.006)

# 30 random bad MEG channels (20 grad, 10 mag) that were used in generation
bads = [
    "MEG0912",
    "MEG1722",
    "MEG2213",
    "MEG0132",
    "MEG1312",
    "MEG0432",
    "MEG2433",
    "MEG1022",
    "MEG0442",
    "MEG2332",
    "MEG0633",
    "MEG1043",
    "MEG1713",
    "MEG0422",
    "MEG0932",
    "MEG1622",
    "MEG1343",
    "MEG0943",
    "MEG0643",
    "MEG0143",
    "MEG2142",
    "MEG0813",
    "MEG2143",
    "MEG1323",
    "MEG0522",
    "MEG1123",
    "MEG0423",
    "MEG2122",
    "MEG2532",
    "MEG0812",
]


def _assert_n_free(raw_sss, lower, upper=None):
    """Check the DOF."""
    __tracebackhide__ = True
    upper = lower if upper is None else upper
    n_free = raw_sss.info["proc_history"][0]["max_info"]["sss_info"]["nfree"]
    assert lower <= n_free <= upper, f"nfree fail: {lower} <= {n_free} <= {upper}"


def _assert_mag_coil_type(info, coil_type):
    __tracebackhide__ = True
    picks = pick_types(info, meg="mag", exclude=())
    coil_types = set(info["chs"][pick]["coil_type"] for pick in picks)
    assert coil_types == {coil_type}


def read_crop(fname, lims=(0, None)):
    """Read and crop."""
    return read_raw_fif(fname, allow_maxshield="yes").crop(*lims)


# For backward compat and to be most like MaxFilter, we make "maxwell_filter"
# the one that behaves like MaxFilter. _maxwell_filter is left to
# be the advanced/better one.
maxwell_filter = partial(_maxwell_filter_ola, st_overlap=False, mc_interp="zero")


@pytest.mark.slowtest
@testing.requires_testing_data
def test_movement_compensation_basic(tmp_path):
    """Test movement compensation."""
    lims = (0, 4)
    raw = read_crop(raw_fname, lims).load_data()
    head_pos = read_head_pos(pos_fname)

    #
    # Movement compensation, no regularization, no tSSS
    #
    _assert_mag_coil_type(raw.info, FIFF.FIFFV_COIL_VV_MAG_T3)
    assert_allclose(raw.info["chs"][2]["cal"], 4.14e-11, rtol=1e-6)
    raw.info["chs"][2]["coil_type"] = FIFF.FIFFV_COIL_VV_MAG_T2
    raw_sss = maxwell_filter(
        raw,
        head_pos=head_pos,
        origin=mf_head_origin,
        regularize=None,
        bad_condition="ignore",
    )
    _assert_mag_coil_type(raw_sss.info, FIFF.FIFFV_COIL_VV_MAG_T3)
    assert_meg_snr(
        raw_sss, read_crop(sss_movecomp_fname, lims), 4.6, 12.4, chpi_med_tol=58
    )
    # IO
    temp_fname = tmp_path / "test_raw_sss.fif"
    raw_sss.save(temp_fname)
    raw_sss = read_crop(temp_fname)
    assert_meg_snr(
        raw_sss, read_crop(sss_movecomp_fname, lims), 4.6, 12.4, chpi_med_tol=58
    )

    #
    # Movement compensation,    regularization, no tSSS
    #
    raw_sss = maxwell_filter(raw, head_pos=head_pos, origin=mf_head_origin)
    assert_meg_snr(
        raw_sss, read_crop(sss_movecomp_reg_in_fname, lims), 0.5, 1.9, chpi_med_tol=121
    )

    #
    # Movement compensation,    regularization,    tSSS at the end
    #
    raw_nohpi = filter_chpi(raw.copy(), t_window=0.2)
    with pytest.warns(RuntimeWarning, match="untested"):
        raw_sss_mv = maxwell_filter(
            raw_nohpi,
            head_pos=head_pos,
            st_duration=4.0,
            origin=mf_head_origin,
            st_fixed=False,
        )
    # Neither match is particularly good because our algorithm actually differs
    assert_meg_snr(
        raw_sss_mv, read_crop(sss_movecomp_reg_in_st4s_fname, lims), 0.6, 1.3
    )
    tSSS_fname = sss_path / "test_move_anon_st4s_raw_sss.fif"
    assert_meg_snr(raw_sss_mv, read_crop(tSSS_fname, lims), 0.6, 1.0, chpi_med_tol=None)
    assert_meg_snr(
        read_crop(sss_movecomp_reg_in_st4s_fname),
        read_crop(tSSS_fname),
        0.8,
        1.0,
        chpi_med_tol=None,
    )

    #
    # Movement compensation,    regularization,    tSSS at the beginning
    #
    raw_sss_mc = maxwell_filter(
        raw_nohpi, head_pos=head_pos, st_duration=4.0, origin=mf_head_origin
    )
    assert_meg_snr(raw_sss_mc, read_crop(tSSS_fname, lims), 0.6, 1.0, chpi_med_tol=None)
    assert_meg_snr(raw_sss_mc, raw_sss_mv, 0.6, 1.4)

    # some degenerate cases
    raw_erm = read_crop(erm_fname)
    with pytest.raises(ValueError, match="positions can only be used"):
        maxwell_filter(raw_erm, coord_frame="meg", head_pos=head_pos)
    with pytest.raises(ValueError, match=r"of shape \(N, 10\)"):
        maxwell_filter(raw, head_pos=head_pos[:, :9])
    with pytest.raises(TypeError, match="instance of ndarray"):
        maxwell_filter(raw, head_pos="foo")
    with pytest.raises(ValueError, match="ascending"):
        maxwell_filter(raw, head_pos=head_pos[::-1])
    head_pos_bad = head_pos.copy()
    head_pos_bad[0, 0] = raw._first_time - 1e-2
    with pytest.raises(ValueError, match="greater than"):
        maxwell_filter(raw, head_pos=head_pos_bad)

    head_pos_bad = head_pos.copy()
    head_pos_bad[0, 4] = 1.0  # off by more than 1 m
    with pytest.warns(RuntimeWarning, match="greater than 1 m"):
        maxwell_filter(
            raw.copy().crop(0, 0.1), head_pos=head_pos_bad, bad_condition="ignore"
        )

    # make sure numerical error doesn't screw it up, though
    head_pos_bad = head_pos.copy()
    head_pos_bad[0, 0] = raw._first_time - 5e-4
    raw_sss_tweak = maxwell_filter(
        raw.copy().crop(0, 0.05), head_pos=head_pos_bad, origin=mf_head_origin
    )
    assert_meg_snr(
        raw_sss_tweak, raw_sss.copy().crop(0, 0.05), 1.4, 8.0, chpi_med_tol=5
    )
    # smoke test a zero-like t[0]
    head_pos_bad[0, 0] = raw._first_time + 0.1 / raw.info["sfreq"]
    maxwell_filter(
        raw.copy().crop(0, 0.05), head_pos=head_pos_bad, origin=mf_head_origin
    )


@pytest.mark.slowtest
@testing.requires_testing_data
def test_movement_compensation_smooth():
    """Test movement compensation with smooth interpolation."""
    lims = (0, 10)
    raw = read_crop(raw_fname, lims).load_data()
    mag_picks = pick_types(raw.info, meg="mag", exclude=())
    power = np.sqrt(np.sum(raw[mag_picks][0] ** 2))
    head_pos = read_head_pos(pos_fname)
    kwargs = dict(
        head_pos=head_pos,
        origin=mf_head_origin,
        regularize=None,
        bad_condition="ignore",
    )
    # Naive MC increases noise relative to raw
    raw_sss = maxwell_filter(raw, **kwargs)
    _assert_shielding(raw_sss, power, 0.258, max_factor=0.259)
    # OLA MC decreases noise relative to raw
    raw_sss_smooth = _maxwell_filter_ola(raw, mc_interp="hann", **kwargs)
    _assert_shielding(raw_sss_smooth, raw_sss, 1.01, max_factor=1.02)

    # now with time-varying regularization
    kwargs["regularize"] = "in"
    raw_sss = maxwell_filter(raw, **kwargs)
    _assert_shielding(raw_sss, power, 0.84, max_factor=0.85)
    raw_sss_smooth = _maxwell_filter_ola(raw, mc_interp="hann", **kwargs)
    _assert_shielding(raw_sss_smooth, raw_sss, 1.008, max_factor=1.012)

    # now with tSSS
    kwargs["st_duration"] = 10
    with catch_logging() as log:
        raw_tsss = maxwell_filter(raw, verbose=True, **kwargs)
    log = log.getvalue()
    want_re = re.compile(".*Projecting 25 intersecting.*across 24 pos.*", re.DOTALL)
    assert want_re.match(log) is not None, log
    _assert_shielding(raw_tsss, power, 31.2, max_factor=31.3)
    with catch_logging() as log:
        raw_tsss_smooth = _maxwell_filter_ola(
            raw, mc_interp="hann", st_overlap=True, verbose=True, **kwargs
        )
    log = log.getvalue()
    assert want_re.match(log) is not None, log
    _assert_shielding(raw_tsss_smooth, power, 31.5, max_factor=31.7)


@pytest.mark.slowtest
def test_other_systems():
    """Test Maxwell filtering on KIT, BTI, and CTF files."""
    # KIT
    kit_dir = io_dir / "kit" / "tests" / "data"
    sqd_path = kit_dir / "test.sqd"
    mrk_path = kit_dir / "test_mrk.sqd"
    elp_path = kit_dir / "test_elp.txt"
    hsp_path = kit_dir / "test_hsp.txt"
    raw_kit = read_raw_kit(sqd_path, str(mrk_path), str(elp_path), str(hsp_path))
    with (
        pytest.raises(NotImplementedError, match="Cannot create forward solution with"),
    ):
        maxwell_filter(raw_kit, verbose=True)
    with catch_logging() as log:
        raw_sss = maxwell_filter(
            raw_kit, origin=(0.0, 0.0, 0.04), ignore_ref=True, verbose=True
        )
    assert "12/15 out" in log.getvalue()  # homogeneous fields removed
    _assert_n_free(raw_sss, 65, 65)
    raw_sss_auto = maxwell_filter(
        raw_kit, origin=(0.0, 0.0, 0.04), ignore_ref=True, mag_scale="auto"
    )
    assert_allclose(raw_sss._data, raw_sss_auto._data)
    with catch_logging() as log:
        pytest.raises(
            RuntimeError, maxwell_filter, raw_kit, ignore_ref=True, regularize=None
        )  # bad condition
        raw_sss = maxwell_filter(
            raw_kit,
            origin="auto",
            ignore_ref=True,
            bad_condition="info",
            verbose=True,
        )
    log = log.getvalue()
    assert "badly conditioned" not in log
    assert "more than 20 mm from" not in log
    _assert_n_free(raw_sss, 67, 67)
    # Let's set the origin
    with catch_logging() as log:
        raw_sss = maxwell_filter(
            raw_kit,
            origin=(0.0, 0.0, 0.04),
            ignore_ref=True,
            bad_condition="info",
            regularize=None,
            verbose=True,
        )
    log = log.getvalue()
    assert "badly conditioned" in log
    assert "80/80 in, 12/15 out" in log
    _assert_n_free(raw_sss, 80)
    # Now with reg
    with catch_logging() as log:
        raw_sss = maxwell_filter(
            raw_kit, origin=(0.0, 0.0, 0.04), ignore_ref=True, verbose=True
        )
    log = log.getvalue()
    assert "badly conditioned" not in log
    assert "12/15 out" in log
    _assert_n_free(raw_sss, 65)

    # BTi
    bti_dir = io_dir / "bti" / "tests" / "data"
    bti_pdf = bti_dir / "test_pdf_linux"
    bti_config = bti_dir / "test_config_linux"
    bti_hs = bti_dir / "test_hs_linux"
    raw_bti = read_raw_bti(bti_pdf, bti_config, bti_hs, preload=False)
    picks = pick_types(raw_bti.info, meg="mag", exclude=())
    power = np.sqrt(np.sum(raw_bti[picks][0] ** 2))
    raw_sss = maxwell_filter(raw_bti)
    _assert_n_free(raw_sss, 70)
    _assert_shielding(raw_sss, power, 0.5)
    raw_sss_auto = maxwell_filter(raw_bti, mag_scale="auto", verbose=True)
    _assert_shielding(raw_sss_auto, power, 0.7)

    # CTF
    raw_ctf_3 = read_crop(fname_ctf_raw)
    assert raw_ctf_3.compensation_grade == 3
    raw_ctf_0 = raw_ctf_3.copy().apply_gradient_compensation(0)
    assert raw_ctf_0.compensation_grade == 0
    # 3rd-order gradient compensation works really well (better than MF here)
    _assert_shielding(raw_ctf_3, raw_ctf_0, 20, 21)
    origin = (0.0, 0.0, 0.04)
    raw_sss_3 = maxwell_filter(raw_ctf_3, origin=origin, verbose=True)
    _assert_n_free(raw_sss_3, 70)
    _assert_shielding(raw_sss_3, raw_ctf_3, 0.12, 0.14)
    _assert_shielding(raw_sss_3, raw_ctf_0, 2.63, 2.66)
    assert raw_sss_3.compensation_grade == 3
    raw_sss_3.apply_gradient_compensation(0)
    assert raw_sss_3.compensation_grade == 0
    _assert_shielding(raw_sss_3, raw_ctf_3, 0.15, 0.17)
    _assert_shielding(raw_sss_3, raw_ctf_0, 3.18, 3.20)
    with pytest.raises(ValueError, match="digitization points"):
        maxwell_filter(raw_ctf_0)
    raw_sss_0 = maxwell_filter(raw_ctf_0, origin=origin, verbose=True)
    _assert_n_free(raw_sss_0, 68)
    _assert_shielding(raw_sss_0, raw_ctf_3, 0.07, 0.09)
    _assert_shielding(raw_sss_0, raw_ctf_0, 1.8, 1.9)
    raw_sss_0.apply_gradient_compensation(3)
    _assert_shielding(raw_sss_0, raw_ctf_3, 0.07, 0.09)
    _assert_shielding(raw_sss_0, raw_ctf_0, 1.63, 1.67)
    with pytest.raises(RuntimeError, match="ignore_ref"):
        maxwell_filter(raw_ctf_3, ignore_ref=True)
    # ignoring ref outperforms including it in maxwell filtering
    with catch_logging() as log:
        raw_sss = maxwell_filter(
            raw_ctf_0, origin=origin, ignore_ref=True, verbose=True
        )
    assert ", 12/15 out" in log.getvalue()  # homogeneous fields removed
    _assert_n_free(raw_sss, 70)
    _assert_shielding(raw_sss, raw_ctf_0, 12, 13)
    # if ignore_ref=True, we remove compensators because they will not
    # work the way people expect (it puts noise back in the data!)
    with pytest.raises(ValueError, match="Desired compensation.*not found"):
        raw_sss.copy().apply_gradient_compensation(3)
    raw_sss_auto = maxwell_filter(
        raw_ctf_0, origin=origin, ignore_ref=True, mag_scale="auto"
    )
    assert_allclose(raw_sss._data, raw_sss_auto._data)
    with catch_logging() as log:
        maxwell_filter(
            raw_ctf_0, origin=origin, regularize=None, ignore_ref=True, verbose=True
        )
    assert "80/80 in, 12/15 out" in log.getvalue()  # homogeneous fields


def test_spherical_conversions():
    """Test spherical harmonic conversions."""
    # Test our real<->complex conversion functions
    az, pol = np.meshgrid(np.linspace(0, 2 * np.pi, 30), np.linspace(0, np.pi, 20))
    for degree in range(1, int_order):
        for order in range(0, degree + 1):
            sph = sph_harm_y(degree, order, pol, az)
            # ensure that we satisfy the conjugation property
            assert_allclose(_sh_negate(sph, order), sph_harm_y(degree, -order, pol, az))
            # ensure our conversion functions work
            sph_real_pos = _sh_complex_to_real(sph, order)
            sph_real_neg = _sh_complex_to_real(sph, -order)
            sph_2 = _sh_real_to_complex([sph_real_pos, sph_real_neg], order)
            assert_allclose(sph, sph_2, atol=1e-7)


@testing.requires_testing_data
def test_multipolar_bases():
    """Test multipolar moment basis calculation using sensor information."""
    from scipy.io import loadmat

    # Test our basis calculations
    info = read_info(raw_fname)
    with use_coil_def(elekta_def_fname):
        coils = _prep_meg_channels(info, do_es=True)["defs"]
    # Check against a known benchmark
    sss_data = loadmat(bases_fname)
    exp = dict(int_order=int_order, ext_order=ext_order)
    for origin in ((0, 0, 0.04), (0, 0.02, 0.02)):
        o_str = "".join(f"{int(1000 * n)}" for n in origin)
        exp.update(origin=origin)
        S_tot = _sss_basis_basic(exp, coils, method="alternative")
        # Test our real<->complex conversion functions
        S_tot_complex = _bases_real_to_complex(S_tot, int_order, ext_order)
        S_tot_round = _bases_complex_to_real(S_tot_complex, int_order, ext_order)
        assert_allclose(S_tot, S_tot_round, atol=1e-7)

        S_tot_mat = np.concatenate(
            [sss_data["Sin" + o_str], sss_data["Sout" + o_str]], axis=1
        )
        S_tot_mat_real = _bases_complex_to_real(S_tot_mat, int_order, ext_order)
        S_tot_mat_round = _bases_real_to_complex(S_tot_mat_real, int_order, ext_order)
        assert_allclose(S_tot_mat, S_tot_mat_round, atol=1e-7)
        assert_allclose(S_tot_complex, S_tot_mat, rtol=1e-4, atol=1e-8)
        assert_allclose(S_tot, S_tot_mat_real, rtol=1e-4, atol=1e-8)

        # Now normalize our columns
        S_tot /= np.sqrt(np.sum(S_tot * S_tot, axis=0))[np.newaxis]
        S_tot_complex /= np.sqrt(
            np.sum((S_tot_complex * S_tot_complex.conj()).real, axis=0)
        )[np.newaxis]
        # Check against a known benchmark
        S_tot_mat = np.concatenate(
            [sss_data["SNin" + o_str], sss_data["SNout" + o_str]], axis=1
        )
        # Check this roundtrip
        S_tot_mat_real = _bases_complex_to_real(S_tot_mat, int_order, ext_order)
        S_tot_mat_round = _bases_real_to_complex(S_tot_mat_real, int_order, ext_order)
        assert_allclose(S_tot_mat, S_tot_mat_round, atol=1e-7)
        assert_allclose(S_tot_complex, S_tot_mat, rtol=1e-4, atol=1e-8)

        # Now test our optimized version
        S_tot = _sss_basis_basic(exp, coils)
        with use_coil_def(elekta_def_fname):
            S_tot_fast = _trans_sss_basis(
                exp, all_coils=_prep_mf_coils(info), trans=info["dev_head_t"]
            )
        # there are some sign differences for columns (order/degrees)
        # in here, likely due to Condon-Shortley. Here we use a
        # Magnetometer channel to figure out the flips because the
        # gradiometer channels have effectively zero values for first three
        # external components (i.e., S_tot[grad_picks, 80:83])
        flips = np.sign(S_tot_fast[2]) != np.sign(S_tot[2])
        flips = 1 - 2 * flips
        assert_allclose(S_tot, S_tot_fast * flips, atol=1e-16)


@testing.requires_testing_data
def test_basic():
    """Test Maxwell filter basic version."""
    # Load testing data (raw, SSS std origin, SSS non-standard origin)
    raw = read_crop(raw_fname, (0.0, 1.0))
    raw_err = read_crop(raw_fname).apply_proj()
    raw_erm = read_crop(erm_fname)
    with pytest.raises(RuntimeError, match="cannot be applied"):
        maxwell_filter(raw_err)
    with pytest.raises(TypeError, match="instance of BaseRaw"):
        maxwell_filter(1.0)
    with pytest.raises(ValueError, match="Number of requested bases"):
        maxwell_filter(raw, int_order=20)  # too many

    n_int_bases = int_order**2 + 2 * int_order
    n_ext_bases = ext_order**2 + 2 * ext_order
    nbases = n_int_bases + n_ext_bases

    # Check number of bases computed correctly
    assert _get_n_moments([int_order, ext_order]).sum() == nbases

    # Test SSS computation at the standard head origin
    assert len(raw.info["projs"]) == 12  # 11 MEG projs + 1 AVG EEG
    with use_coil_def(elekta_def_fname):
        raw_sss = maxwell_filter(
            raw, origin=mf_head_origin, regularize=None, bad_condition="ignore"
        )
    assert len(raw_sss.info["projs"]) == 1  # avg EEG
    assert raw_sss.info["projs"][0]["desc"] == "Average EEG reference"
    assert_meg_snr(raw_sss, read_crop(sss_std_fname), 200.0, 1000.0)
    py_cal = raw_sss.info["proc_history"][0]["max_info"]["sss_cal"]
    assert len(py_cal) == 0
    py_ctc = raw_sss.info["proc_history"][0]["max_info"]["sss_ctc"]
    assert len(py_ctc) == 0
    py_st = raw_sss.info["proc_history"][0]["max_info"]["max_st"]
    assert len(py_st) == 0
    with pytest.raises(RuntimeError, match="cannot reapply"):
        maxwell_filter(raw_sss)

    # Test SSS computation at non-standard head origin
    with use_coil_def(elekta_def_fname):
        raw_sss = maxwell_filter(
            raw, origin=[0.0, 0.02, 0.02], regularize=None, bad_condition="ignore"
        )
    assert_meg_snr(raw_sss, read_crop(sss_nonstd_fname), 250.0, 700.0)

    # Test SSS computation at device origin
    sss_erm_std = read_crop(sss_erm_std_fname)
    raw_sss = maxwell_filter(
        raw_erm,
        coord_frame="meg",
        origin=mf_meg_origin,
        regularize=None,
        bad_condition="ignore",
    )
    assert_meg_snr(raw_sss, sss_erm_std, 70.0, 260.0)
    for key in ("job", "frame"):
        vals = [
            x.info["proc_history"][0]["max_info"]["sss_info"][key]
            for x in [raw_sss, sss_erm_std]
        ]
        assert vals[0] == vals[1]

    # Two equivalent things: at device origin in device coords (0., 0., 0.)
    # and at device origin at head coords info['dev_head_t'][:3, 3]
    raw_sss_meg = maxwell_filter(raw, coord_frame="meg", origin=(0.0, 0.0, 0.0))
    raw_sss_head = maxwell_filter(raw, origin=raw.info["dev_head_t"]["trans"][:3, 3])
    assert_meg_snr(raw_sss_meg, raw_sss_head, 100.0, 900.0)

    # Check against SSS functions from proc_history
    assert _get_n_moments(int_order) == _get_rank_sss(raw_sss)

    # Degenerate cases
    with pytest.raises(ValueError, match="Invalid value"):
        maxwell_filter(raw, coord_frame="foo")
    with pytest.raises(ValueError, match="numerical array"):
        maxwell_filter(raw, origin="foo")
    with pytest.raises(ValueError, match="3-element array"):
        maxwell_filter(raw, origin=[0] * 4)
    with pytest.raises(ValueError, match="must be a float"):
        maxwell_filter(raw, mag_scale="foo")
    raw_missing = raw.copy().load_data()
    raw_missing.info["bads"] = ["MEG0111"]
    raw_missing.pick("meg", exclude="bads")  # will be missing the bad
    maxwell_filter(raw_missing)
    with pytest.warns(RuntimeWarning, match="not in data"):
        maxwell_filter(raw_missing, calibration=fine_cal_fname)


@testing.requires_testing_data
def test_maxwell_filter_additional(tmp_path):
    """Test processing of Maxwell filtered data."""
    # TODO: Future tests integrate with mne/io/tests/test_proc_history

    # Load testing data (raw, SSS std origin, SSS non-standard origin)
    file_name = "test_move_anon"
    raw_fname = data_path / "SSS" / (file_name + "_raw.fif")

    # Use 2.0 seconds of data to get stable cov. estimate
    raw = read_crop(raw_fname, (0.0, 2.0))

    # Get MEG channels, compute Maxwell filtered data
    raw.load_data()
    raw.pick("meg")
    int_order = 8
    raw_sss = maxwell_filter(
        raw, origin=mf_head_origin, regularize=None, bad_condition="ignore"
    )

    # Test io on processed data
    test_outname = tmp_path / "test_raw_sss.fif"
    raw_sss.save(test_outname)
    raw_sss_loaded = read_crop(test_outname).load_data()

    # Some numerical imprecision since save uses 'single' fmt
    assert_allclose(raw_sss_loaded[:][0], raw_sss[:][0], rtol=1e-6, atol=1e-20)

    # Test rank of covariance matrices for raw and SSS processed data
    cov_raw = compute_raw_covariance(raw)
    cov_sss = compute_raw_covariance(raw_sss)

    scalings = None
    cov_raw_rank = _compute_rank_int(
        cov_raw, scalings=scalings, info=raw.info, proj=False
    )
    cov_sss_rank = _compute_rank_int(
        cov_sss, scalings=scalings, info=raw_sss.info, proj=False
    )

    assert cov_raw_rank == raw.info["nchan"]
    assert cov_sss_rank == _get_n_moments(int_order)


@pytest.mark.slowtest
@testing.requires_testing_data
def test_bads_reconstruction():
    """Test Maxwell filter reconstruction of bad channels."""
    raw = read_crop(raw_fname, (0.0, 1.0))
    raw.info["bads"] = bads
    with use_coil_def(elekta_def_fname):
        raw_sss = maxwell_filter(
            raw, origin=mf_head_origin, regularize=None, bad_condition="ignore"
        )
    assert_meg_snr(raw_sss, read_crop(sss_bad_recon_fname), 300.0)


@pytest.mark.slowtest
@buggy_mkl_svd
@testing.requires_testing_data
def test_spatiotemporal():
    """Test Maxwell filter (tSSS) spatiotemporal processing."""
    # Load raw testing data
    raw = read_crop(raw_fname)
    mag_picks = pick_types(raw.info, meg="mag", exclude=())
    power = np.sqrt(np.sum(raw[mag_picks][0] ** 2))

    # Test that window is less than length of data
    with pytest.raises(ValueError, match="must be"):
        maxwell_filter(raw, st_duration=1000.0)

    # We could check both 4 and 10 seconds because Elekta handles them
    # differently (to ensure that std/non-std tSSS windows are correctly
    # handled), but the 4-s case should hopefully be sufficient.
    st_durations = [4.0]  # , 10.]
    tols = [(80, 100)]  # , 200.]
    kwargs = dict(origin=mf_head_origin, regularize=None, bad_condition="ignore")
    for st_duration, tol in zip(st_durations, tols):
        # Load tSSS data depending on st_duration and get data
        tSSS_fname = sss_path / f"test_move_anon_st{int(st_duration)}s_raw_sss.fif"
        tsss_bench = read_crop(tSSS_fname)
        # Because Elekta's tSSS sometimes(!) lumps the tail window of data
        # onto the previous buffer if it's shorter than st_duration, we have to
        # crop the data here to compensate for Elekta's tSSS behavior.
        # if st_duration == 10.:
        #     tsss_bench.crop(0, st_duration)
        #     raw.crop(0, st_duration)

        # Test sss computation at the standard head origin. Same cropping issue
        # as mentioned above.
        raw_tsss = maxwell_filter(raw, st_duration=st_duration, **kwargs)
        assert _compute_rank_int(raw_tsss, proj=False) == 140
        assert_meg_snr(raw_tsss, tsss_bench, *tol)
        py_st = raw_tsss.info["proc_history"][0]["max_info"]["max_st"]
        assert len(py_st) > 0
        assert py_st["buflen"] == st_duration
        assert py_st["subspcorr"] == 0.98
        _assert_shielding(raw_tsss, power, 20.8)

    # Degenerate cases
    with pytest.raises(ValueError, match="Need 0 < st_correlation"):
        maxwell_filter(raw, st_duration=10.0, st_correlation=0.0)


@buggy_mkl_svd
@testing.requires_testing_data
def test_st_overlap():
    """Test st_overlap."""
    raw = read_crop(raw_fname).crop(0, 1.0)
    mag_picks = pick_types(raw.info, meg="mag", exclude=())
    power = np.sqrt(np.sum(raw[mag_picks][0] ** 2))
    kwargs = dict(
        origin=mf_head_origin, regularize=None, bad_condition="ignore", st_duration=0.5
    )
    raw_tsss = maxwell_filter(raw, **kwargs)
    assert _compute_rank_int(raw_tsss, proj=False) == 140
    _assert_shielding(raw_tsss, power, 35.8, max_factor=35.9)
    raw_tsss = _maxwell_filter_ola(raw, st_overlap=True, **kwargs)
    assert _compute_rank_int(raw_tsss, proj=False) == 140
    _assert_shielding(raw_tsss, power, 35.6, max_factor=35.7)


@pytest.mark.slowtest
@testing.requires_testing_data
def test_spatiotemporal_only():
    """Test tSSS-only processing."""
    # Load raw testing data
    tmax = 0.5
    raw = read_crop(raw_fname, (0, tmax)).load_data()
    picks = pick_types(raw.info, meg=True, exclude="bads")[::2]
    raw.pick([raw.ch_names[pick] for pick in picks])
    mag_picks = pick_types(raw.info, meg="mag", exclude=())
    power = np.sqrt(np.sum(raw[mag_picks][0] ** 2))
    # basics
    raw_tsss = maxwell_filter(raw, st_duration=tmax / 2.0, st_only=True)
    assert len(raw.info["projs"]) == len(raw_tsss.info["projs"])
    assert _compute_rank_int(raw_tsss, proj=False) == len(picks)
    _assert_shielding(raw_tsss, power, 9.2)
    # with movement
    head_pos = read_head_pos(pos_fname)
    raw_tsss = maxwell_filter(
        raw, st_duration=tmax / 2.0, st_only=True, head_pos=head_pos
    )
    assert _compute_rank_int(raw_tsss, proj=False) == len(picks)
    _assert_shielding(raw_tsss, power, 9.2)
    with pytest.warns(RuntimeWarning, match="st_fixed"):
        raw_tsss = maxwell_filter(
            raw, st_duration=tmax / 2.0, st_only=True, head_pos=head_pos, st_fixed=False
        )
    assert _compute_rank_int(raw_tsss, proj=False) == len(picks)
    _assert_shielding(raw_tsss, power, 9.2, max_factor=9.4)
    # COLA
    raw_tsss = maxwell_filter(
        raw,
        st_duration=tmax / 2.0,
        st_only=True,
        head_pos=head_pos,
        st_overlap=True,
        mc_interp="hann",
    )
    assert _compute_rank_int(raw_tsss, proj=False) == len(picks)
    _assert_shielding(raw_tsss, power, 9.5, max_factor=9.6)
    # should do nothing
    raw_tsss = maxwell_filter(raw, st_duration=tmax, st_correlation=1.0, st_only=True)
    assert_allclose(raw[:][0], raw_tsss[:][0])
    # degenerate
    with pytest.raises(ValueError, match="must not be None if st_only"):
        maxwell_filter(raw, st_only=True)
    # two-step process equivalent to single-step process
    raw_tsss = maxwell_filter(raw, st_duration=tmax, st_only=True)
    raw_tsss = maxwell_filter(raw_tsss)
    raw_tsss_2 = maxwell_filter(raw, st_duration=tmax)
    assert_meg_snr(raw_tsss, raw_tsss_2, 1e5)
    # now also with head movement, and a bad MEG channel
    assert len(raw.info["bads"]) == 0
    bads = [raw.ch_names[0]]
    raw.info["bads"] = list(bads)
    raw_tsss = maxwell_filter(raw, st_duration=tmax, st_only=True, head_pos=head_pos)
    assert raw.info["bads"] == bads
    assert raw_tsss.info["bads"] == bads  # don't reset
    raw_tsss = maxwell_filter(raw_tsss, head_pos=head_pos)
    assert raw_tsss.info["bads"] == []  # do reset MEG bads
    raw_tsss_2 = maxwell_filter(raw, st_duration=tmax, head_pos=head_pos)
    assert raw_tsss_2.info["bads"] == []
    assert_meg_snr(raw_tsss, raw_tsss_2, 1e5)


@testing.requires_testing_data
def test_fine_calibration():
    """Test Maxwell filter fine calibration."""
    # Load testing data (raw, SSS std origin, SSS non-standard origin)
    raw = read_crop(raw_fname, (0.0, 1.0))
    sss_fine_cal = read_crop(sss_fine_cal_fname)

    # Test 1D SSS fine calibration
    with use_coil_def(elekta_def_fname):
        with catch_logging() as log:
            raw_sss = maxwell_filter(
                raw,
                calibration=fine_cal_fname,
                origin=mf_head_origin,
                regularize=None,
                bad_condition="ignore",
                verbose=True,
            )
    log = log.getvalue()
    assert "Using fine calibration" in log
    assert fine_cal_fname.stem in log
    assert_meg_snr(raw_sss, sss_fine_cal, 1.3, 180)  # similar to MaxFilter
    py_cal = raw_sss.info["proc_history"][0]["max_info"]["sss_cal"]
    assert py_cal is not None
    assert len(py_cal) > 0
    mf_cal = sss_fine_cal.info["proc_history"][0]["max_info"]["sss_cal"]
    # we identify these differently
    mf_cal["cal_chans"][mf_cal["cal_chans"][:, 1] == 3022, 1] = 3024
    assert_allclose(py_cal["cal_chans"], mf_cal["cal_chans"])
    assert_allclose(py_cal["cal_corrs"], mf_cal["cal_corrs"], rtol=1e-3, atol=1e-3)
    # with missing channels
    raw_missing = raw.copy().load_data()
    raw_missing.info["bads"] = ["MEG0111", "MEG0943"]  # 1 mag, 1 grad
    raw_missing.info._check_consistency()
    raw_sss_bad = maxwell_filter(
        raw_missing,
        calibration=fine_cal_fname,
        origin=mf_head_origin,
        regularize=None,
        bad_condition="ignore",
    )
    raw_missing.pick("meg", exclude="bads")  # actually remove bads
    raw_sss_bad.pick(raw_missing.ch_names)  # remove them here, too
    with pytest.warns(RuntimeWarning, match="cal channels not in data"):
        raw_sss_missing = maxwell_filter(
            raw_missing,
            calibration=fine_cal_fname,
            origin=mf_head_origin,
            regularize=None,
            bad_condition="ignore",
        )
    assert_meg_snr(raw_sss_missing, raw_sss_bad, 1000.0, 10000.0)

    # Test 3D SSS fine calibration (no equivalent func in MaxFilter yet!)
    # very low SNR as proc differs, eventually we should add a better test
    raw_sss_3D = maxwell_filter(
        raw,
        calibration=fine_cal_fname_3d,
        origin=mf_head_origin,
        regularize=None,
        bad_condition="ignore",
    )
    assert_meg_snr(raw_sss_3D, sss_fine_cal, 0.9, 6.0)
    assert_meg_snr(raw_sss_3D, raw_sss, 1.1, 6.0)  # slightly better than 1D
    raw_ctf = read_crop(fname_ctf_raw).apply_gradient_compensation(0)
    with pytest.raises(RuntimeError, match="Not all MEG channels"):
        maxwell_filter(raw_ctf, origin=(0.0, 0.0, 0.04), calibration=fine_cal_fname)


@pytest.mark.slowtest
@testing.requires_testing_data
def test_regularization():
    """Test Maxwell filter regularization."""
    # Load testing data (raw, SSS std origin, SSS non-standard origin)
    min_tols = (20.0, 2.6, 1.0)
    med_tols = (200.0, 21.0, 3.7)
    origins = ((0.0, 0.0, 0.04), (0.0,) * 3, (0.0, 0.02, 0.02))
    coord_frames = ("head", "meg", "head")
    raw_fnames = (raw_fname, erm_fname, sample_fname)
    sss_fnames = (sss_reg_in_fname, sss_erm_reg_in_fname, sss_samp_reg_in_fname)
    comp_tols = [0, 1, 4]
    for ii, rf in enumerate(raw_fnames):
        raw = read_crop(rf, (0.0, 1.0))
        sss_reg_in = read_crop(sss_fnames[ii])

        # Test "in" regularization
        raw_sss = maxwell_filter(raw, coord_frame=coord_frames[ii], origin=origins[ii])
        assert_meg_snr(raw_sss, sss_reg_in, min_tols[ii], med_tols[ii], msg=rf)

        # check components match
        _check_reg_match(raw_sss, sss_reg_in, comp_tols[ii])


def _check_reg_match(sss_py, sss_mf, comp_tol):
    """Check regularization."""
    info_py = sss_py.info["proc_history"][0]["max_info"]["sss_info"]
    assert info_py is not None
    assert len(info_py) > 0
    info_mf = sss_mf.info["proc_history"][0]["max_info"]["sss_info"]
    n_in = None
    for inf in (info_py, info_mf):
        if n_in is None:
            n_in = _get_n_moments(inf["in_order"])
        else:
            assert n_in == _get_n_moments(inf["in_order"])
        assert inf["components"][:n_in].sum() == inf["nfree"]
    assert_allclose(
        info_py["nfree"], info_mf["nfree"], atol=comp_tol, err_msg=sss_py.filenames[0]
    )


@testing.requires_testing_data
def test_cross_talk(tmp_path):
    """Test Maxwell filter cross-talk cancellation."""
    raw = read_crop(raw_fname, (0.0, 1.0))
    raw.info["bads"] = bads
    sss_ctc = read_crop(sss_ctc_fname)
    with use_coil_def(elekta_def_fname):
        raw_sss = maxwell_filter(
            raw,
            cross_talk=pathlib.Path(ctc_fname),
            origin=mf_head_origin,
            regularize=None,
            bad_condition="ignore",
        )
    assert_meg_snr(raw_sss, sss_ctc, 275.0)
    py_ctc = raw_sss.info["proc_history"][0]["max_info"]["sss_ctc"]
    assert len(py_ctc) > 0
    with pytest.raises(TypeError, match="path-like"):
        maxwell_filter(raw, cross_talk=raw)
    with pytest.raises(ValueError, match="Invalid cross-talk FIF"):
        maxwell_filter(raw, cross_talk=raw_fname)
    mf_ctc = sss_ctc.info["proc_history"][0]["max_info"]["sss_ctc"]
    del mf_ctc["block_id"]  # we don't write this
    assert isinstance(py_ctc["decoupler"], sparse.csc_array)
    assert isinstance(mf_ctc["decoupler"], sparse.csc_array)
    assert_array_equal(py_ctc["decoupler"].toarray(), mf_ctc["decoupler"].toarray())
    # I/O roundtrip
    fname = tmp_path / "test_sss_raw.fif"
    sss_ctc.save(fname)
    sss_ctc_read = read_raw_fif(fname)
    mf_ctc_read = sss_ctc_read.info["proc_history"][0]["max_info"]["sss_ctc"]
    assert isinstance(mf_ctc_read["decoupler"], sparse.csc_array)
    assert_array_equal(
        mf_ctc_read["decoupler"].toarray(), mf_ctc["decoupler"].toarray()
    )
    assert object_diff(py_ctc, mf_ctc) == ""
    raw_ctf = read_crop(fname_ctf_raw).apply_gradient_compensation(0)
    raw_sss = maxwell_filter(raw_ctf, origin=(0.0, 0.0, 0.04))
    _assert_n_free(raw_sss, 68)
    raw_sss = maxwell_filter(raw_ctf, origin=(0.0, 0.0, 0.04), ignore_ref=True)
    _assert_n_free(raw_sss, 70)
    raw_missing = (
        raw.copy()
        .crop(0, 0.1)
        .load_data()
        .pick(
            [raw.ch_names[pi] for pi in pick_types(raw.info, meg=True, exclude=())[3:]]
        )
    )
    with pytest.warns(RuntimeWarning, match="Not all cross-talk channels"):
        maxwell_filter(raw_missing, cross_talk=ctc_fname)
    # MEG channels not in cross-talk
    with pytest.raises(RuntimeError, match="Missing MEG channels"):
        maxwell_filter(raw_ctf, origin=(0.0, 0.0, 0.04), cross_talk=ctc_fname)


@testing.requires_testing_data
def test_head_translation():
    """Test Maxwell filter head translation."""
    raw = read_crop(raw_fname, (0.0, 1.0))
    # First try with an unchanged destination
    with use_coil_def(elekta_def_fname):
        raw_sss = maxwell_filter(
            raw,
            destination=raw_fname,
            origin=mf_head_origin,
            regularize=None,
            bad_condition="ignore",
        )
    assert_meg_snr(raw_sss, read_crop(sss_std_fname, (0.0, 1.0)), 200.0)
    # Now with default
    with use_coil_def(elekta_def_fname):
        with pytest.warns(RuntimeWarning, match="over 25 mm"):
            raw_sss = maxwell_filter(
                raw,
                destination=mf_head_origin,
                origin=mf_head_origin,
                regularize=None,
                bad_condition="ignore",
                verbose=True,
            )
    assert_meg_snr(raw_sss, read_crop(sss_trans_default_fname), 125.0)
    destination = np.eye(4)
    destination[2, 3] = 0.04
    assert_allclose(raw_sss.info["dev_head_t"]["trans"], destination)
    # Now to sample's head pos
    with pytest.warns(RuntimeWarning, match="= 25.6 mm"):
        raw_sss = maxwell_filter(
            raw,
            destination=str(sample_fname),
            origin=mf_head_origin,
            regularize=None,
            bad_condition="ignore",
            verbose=True,
        )
    assert_meg_snr(raw_sss, read_crop(sss_trans_sample_fname), 13.0, 100.0)
    assert_allclose(
        raw_sss.info["dev_head_t"]["trans"],
        read_info(sample_fname)["dev_head_t"]["trans"],
    )
    # Degenerate cases
    with pytest.raises(RuntimeError, match=".* can only be set .* head .*"):
        maxwell_filter(raw, destination=mf_head_origin, coord_frame="meg")
    with pytest.raises(ValueError, match="destination must be"):
        maxwell_filter(raw, destination=[0.0] * 4)


# TODO: Eventually add simulation tests mirroring Taulu's original paper
# that calculates the localization error:
# http://ieeexplore.ieee.org/xpl/articleDetails.jsp?arnumber=1495874


def _assert_shielding(raw_sss, erm_power, min_factor, max_factor=np.inf, meg="mag"):
    """Assert a minimum shielding factor using empty-room power."""
    __tracebackhide__ = True
    picks = pick_types(raw_sss.info, meg=meg, ref_meg=False)
    if isinstance(erm_power, BaseRaw):
        picks_erm = pick_types(raw_sss.info, meg=meg, ref_meg=False)
        assert_allclose(picks, picks_erm)
        erm_power = np.sqrt((erm_power[picks_erm][0] ** 2).sum())
    sss_power = raw_sss[picks][0].ravel()
    sss_power = np.sqrt(np.sum(sss_power * sss_power))
    factor = erm_power / sss_power
    assert min_factor <= factor < max_factor, (
        f"Shielding factor not {min_factor:0.3f} <= {factor:0.3f} < {max_factor:0.3f}"
    )


@buggy_mkl_svd
@testing.requires_testing_data
@pytest.mark.parametrize("regularize", ("in", None))
@pytest.mark.parametrize("bads", ([], ["MEG0111"]))
def test_esss(regularize, bads):
    """Test extended-basis SSS."""
    # Make some fake "projectors" that actually contain external SSS bases
    raw_erm = read_crop(erm_fname).load_data().pick("meg")
    raw_erm.info["bads"] = bads
    proj_sss = mne.compute_proj_raw(
        raw_erm, meg="combined", verbose="error", n_mag=15, n_grad=15
    )
    good_info = pick_info(raw_erm.info, pick_types(raw_erm.info, meg=True))
    S_tot = _trans_sss_basis(
        dict(int_order=0, ext_order=3, origin=(0.0, 0.0, 0.0)),
        all_coils=_prep_mf_coils(good_info),
        coil_scale=1.0,
        trans=None,
    )
    assert S_tot.shape[-1] == len(proj_sss)
    for a, b in zip(proj_sss, S_tot.T):
        a["data"]["data"][:] = b
    with catch_logging() as log:
        raw_sss = maxwell_filter(
            raw_erm, coord_frame="meg", regularize=regularize, verbose=True
        )
    log = log.getvalue()
    assert "xtend" not in log
    with catch_logging() as log:
        raw_sss_2 = maxwell_filter(
            raw_erm,
            coord_frame="meg",
            regularize=regularize,
            ext_order=0,
            extended_proj=proj_sss,
            verbose=True,
        )
    log = log.getvalue()
    assert "Extending external SSS basis using 15 projection" in log
    assert_allclose(raw_sss_2._data, raw_sss._data, atol=1e-20)

    # This should work, as the projectors should be a superset
    raw_erm.info["bads"] = raw_erm.info["bads"] + ["MEG0112"]
    maxwell_filter(raw_erm, coord_frame="meg", extended_proj=proj_sss)

    # Degenerate condititons
    proj_sss = proj_sss[:2]
    proj_sss[0]["data"]["col_names"] = proj_sss[0]["data"]["col_names"][:-1]
    with pytest.raises(ValueError, match="were missing"):
        maxwell_filter(raw_erm, coord_frame="meg", extended_proj=proj_sss)
    proj_sss[0] = 1.0
    with pytest.raises(TypeError, match=r"extended_proj\[0\] must be an inst"):
        maxwell_filter(raw_erm, coord_frame="meg", extended_proj=proj_sss)
    with pytest.raises(TypeError, match="extended_proj must be an inst"):
        maxwell_filter(raw_erm, coord_frame="meg", extended_proj=1.0)


@contextmanager
def get_n_projected():
    """Get the number of projected tSSS components from the log."""
    count = list()
    with use_log_level(True):
        with catch_logging() as log:
            yield count
    log = log.getvalue()
    assert "Processing data using tSSS" in log
    log = log.splitlines()
    reg = re.compile(r"\s+Projecting\s+([0-9])+\s+intersecting tSSS .*")
    for line in log:
        m = reg.match(line)
        if m:
            count.append(int(m.group(1)))


@buggy_mkl_svd
@pytest.mark.slowtest
@testing.requires_testing_data
def test_shielding_factor(tmp_path):
    """Test Maxwell filter shielding factor using empty room."""
    raw_erm = read_crop(erm_fname).load_data().pick("meg")
    erm_power = raw_erm[pick_types(raw_erm.info, meg="mag")][0]
    erm_power = np.sqrt(np.sum(erm_power * erm_power))
    erm_power_grad = raw_erm[pick_types(raw_erm.info, meg="grad")][0]
    erm_power_grad = np.sqrt(np.sum(erm_power * erm_power))

    # Vanilla SSS (second value would be for meg=True instead of meg='mag')
    _assert_shielding(read_crop(sss_erm_std_fname), erm_power, 10)  # 1.5)
    raw_sss = maxwell_filter(raw_erm, coord_frame="meg", regularize=None)
    _assert_shielding(raw_sss, erm_power, 12, 13)  # 1.5)
    _assert_shielding(raw_sss, erm_power_grad, 0.45, 0.55, "grad")  # 1.5)

    # No external basis
    raw_sss_0 = maxwell_filter(raw_erm, coord_frame="meg", regularize=None, ext_order=0)
    _assert_shielding(raw_sss_0, erm_power, 1.0, 1.1)
    del raw_sss_0

    # Regularization
    _assert_shielding(read_crop(sss_erm_std_fname), erm_power, 10)  # 1.5)
    raw_sss = maxwell_filter(raw_erm, coord_frame="meg")
    _assert_shielding(raw_sss, erm_power, 14.5, 15.5)

    #
    # Extended (eSSS)
    #

    # Show that using empty-room projectors increase shielding factor
    proj = mne.compute_proj_raw(
        raw_erm, meg="combined", verbose="error", n_mag=15, n_grad=15
    )
    raw_sss = maxwell_filter(
        raw_erm, coord_frame="meg", regularize=None, extended_proj=proj[:3]
    )
    _assert_shielding(raw_sss, erm_power, 38, 39)
    raw_sss = maxwell_filter(
        raw_erm, coord_frame="meg", regularize=None, extended_proj=proj
    )
    _assert_shielding(raw_sss, erm_power, 49, 51)
    # Now with reg
    raw_sss = maxwell_filter(raw_erm, coord_frame="meg", extended_proj=proj[:3])
    _assert_shielding(raw_sss, erm_power, 42, 44)
    raw_sss = maxwell_filter(raw_erm, coord_frame="meg", extended_proj=proj)
    _assert_shielding(raw_sss, erm_power, 59, 61)

    #
    # Different mag_scale values
    #
    raw_sss = maxwell_filter(
        raw_erm, coord_frame="meg", regularize=None, mag_scale="auto"
    )
    _assert_shielding(raw_sss, erm_power, 12, 13)
    _assert_shielding(raw_sss, erm_power_grad, 0.48, 0.58, "grad")
    raw_sss = maxwell_filter(
        raw_erm, coord_frame="meg", regularize=None, mag_scale=1.0
    )  # not a good choice
    _assert_shielding(raw_sss, erm_power, 7.3, 8.0)
    _assert_shielding(raw_sss, erm_power_grad, 0.2, 0.3, "grad")
    raw_sss = maxwell_filter(
        raw_erm,
        coord_frame="meg",
        regularize=None,
        mag_scale=1000.0,
        bad_condition="ignore",
    )
    _assert_shielding(raw_sss, erm_power, 4.0, 5.0)
    _assert_shielding(raw_sss, erm_power_grad, 0.1, 0.2, "grad")

    #
    # Fine cal
    #
    _assert_shielding(read_crop(sss_erm_fine_cal_fname), erm_power, 12)  # 2.0)
    raw_sss = maxwell_filter(
        raw_erm,
        coord_frame="meg",
        regularize=None,
        origin=mf_meg_origin,
        calibration=pathlib.Path(fine_cal_fname),
    )
    _assert_shielding(raw_sss, erm_power, 12, 13)  # 2.0)

    #
    # Crosstalk
    #
    _assert_shielding(read_crop(sss_erm_ctc_fname), erm_power, 12)  # 2.1)
    raw_sss = maxwell_filter(
        raw_erm,
        coord_frame="meg",
        regularize=None,
        origin=mf_meg_origin,
        cross_talk=ctc_fname,
    )
    _assert_shielding(raw_sss, erm_power, 12, 13)  # 2.1)

    # Fine cal + Crosstalk
    raw_sss = maxwell_filter(
        raw_erm,
        coord_frame="meg",
        regularize=None,
        calibration=fine_cal_fname,
        origin=mf_meg_origin,
        cross_talk=ctc_fname,
    )
    _assert_shielding(raw_sss, erm_power, 13, 14)  # 2.2)
    # Fine cal + Crosstalk + Extended
    raw_sss = maxwell_filter(
        raw_erm,
        coord_frame="meg",
        regularize=None,
        calibration=fine_cal_fname,
        origin=mf_meg_origin,
        cross_talk=ctc_fname,
        extended_proj=proj,
    )
    _assert_shielding(raw_sss, erm_power, 28, 30)
    raw_sss = maxwell_filter(
        raw_erm,
        coord_frame="meg",
        regularize=None,
        calibration=fine_cal_fname,
        origin=mf_meg_origin,
        cross_talk=ctc_fname,
        extended_proj=proj[:3],
    )
    _assert_shielding(raw_sss, erm_power, 25, 27)

    # tSSS
    _assert_shielding(read_crop(sss_erm_st_fname), erm_power, 37)  # 5.8)
    raw_sss = maxwell_filter(
        raw_erm,
        coord_frame="meg",
        regularize=None,
        origin=mf_meg_origin,
        st_duration=1.0,
    )
    _assert_shielding(raw_sss, erm_power, 37, 38)  # 5.8)

    # Crosstalk + tSSS
    with get_n_projected() as counts:
        raw_sss = maxwell_filter(
            raw_erm,
            coord_frame="meg",
            regularize=None,
            cross_talk=ctc_fname,
            origin=mf_meg_origin,
            st_duration=1.0,
        )
    _assert_shielding(raw_sss, erm_power, 38, 39)  # 5.91)
    assert counts[0] == 4

    # Fine cal + tSSS
    with get_n_projected() as counts:
        raw_sss = maxwell_filter(
            raw_erm,
            coord_frame="meg",
            regularize=None,
            calibration=fine_cal_fname,
            origin=mf_meg_origin,
            st_duration=1.0,
        )
    _assert_shielding(raw_sss, erm_power, 38, 39)  # 5.98)
    assert counts[0] == 4

    # Extended + tSSS
    with get_n_projected() as counts:
        raw_sss = maxwell_filter(
            raw_erm,
            coord_frame="meg",
            regularize=None,
            origin=mf_meg_origin,
            st_duration=1.0,
            extended_proj=proj,
        )
    _assert_shielding(raw_sss, erm_power, 40, 42)
    assert counts[0] == 0
    with get_n_projected() as counts:
        raw_sss = maxwell_filter(
            raw_erm,
            coord_frame="meg",
            regularize=None,
            origin=mf_meg_origin,
            st_duration=1.0,
            extended_proj=proj[:3],
        )
    _assert_shielding(raw_sss, erm_power, 35, 37)
    assert counts[0] == 1

    # Fine cal + Crosstalk + tSSS
    _assert_shielding(
        read_crop(sss_erm_st1FineCalCrossTalk_fname), erm_power, 39, 40
    )  # 6.07)
    raw_sss = maxwell_filter(
        raw_erm,
        coord_frame="meg",
        regularize=None,
        calibration=fine_cal_fname,
        origin=mf_meg_origin,
        cross_talk=ctc_fname,
        st_duration=1.0,
    )
    _assert_shielding(raw_sss, erm_power, 39, 40)  # 6.05)

    # Fine cal + Crosstalk + tSSS + Extended (a bit worse)
    _assert_shielding(
        read_crop(sss_erm_st1FineCalCrossTalk_fname), erm_power, 39, 40
    )  # 6.07)
    raw_sss = maxwell_filter(
        raw_erm,
        coord_frame="meg",
        regularize=None,
        calibration=fine_cal_fname,
        origin=mf_meg_origin,
        cross_talk=ctc_fname,
        st_duration=1.0,
        extended_proj=proj[:3],
    )
    _assert_shielding(raw_sss, erm_power, 34, 36)

    # Fine cal + Crosstalk + tSSS + Reg-in
    _assert_shielding(
        read_crop(sss_erm_st1FineCalCrossTalkRegIn_fname), erm_power, 57, 58
    )  # 6.97)
    raw_sss = maxwell_filter(
        raw_erm,
        calibration=fine_cal_fname,
        cross_talk=ctc_fname,
        st_duration=1.0,
        origin=mf_meg_origin,
        coord_frame="meg",
        regularize="in",
    )
    _assert_shielding(raw_sss, erm_power, 53, 54)  # 6.64)
    with get_n_projected() as counts:
        raw_sss = maxwell_filter(
            raw_erm,
            calibration=fine_cal_fname,
            cross_talk=ctc_fname,
            st_duration=1.0,
            coord_frame="meg",
            regularize="in",
        )
    _assert_shielding(raw_sss, erm_power, 58, 59)  # 7.0)
    _assert_shielding(raw_sss, erm_power_grad, 1.6, 1.7, "grad")
    assert counts[0] == 4
    with get_n_projected() as counts:
        raw_sss = maxwell_filter(
            raw_erm,
            calibration=fine_cal_fname,
            cross_talk=ctc_fname,
            st_duration=1.0,
            coord_frame="meg",
            regularize="in",
            mag_scale="auto",
        )
    _assert_shielding(raw_sss, erm_power, 51, 52)
    _assert_shielding(raw_sss, erm_power_grad, 1.5, 1.6, "grad")
    assert counts[0] == 3
    with get_n_projected() as counts:
        with _record_warnings():  # SVD convergence on arm64
            raw_sss = maxwell_filter(
                raw_erm,
                calibration=fine_cal_fname_3d,
                cross_talk=ctc_fname,
                st_duration=1.0,
                coord_frame="meg",
                regularize="in",
            )
    # Our 3D cal has worse defaults for this ERM than the 1D file
    _assert_shielding(raw_sss, erm_power, 57, 58)
    assert counts[0] == 3
    # Show it by rewriting the 3D as 1D and testing it
    temp_fname = tmp_path / "test_cal.dat"
    with open(fine_cal_fname_3d) as fid:
        with open(temp_fname, "w") as fid_out:
            for line in fid:
                fid_out.write(" ".join(line.strip().split(" ")[:14]) + "\n")
    with get_n_projected() as counts:
        with _record_warnings():  # SVD convergence sometimes
            raw_sss = maxwell_filter(
                raw_erm,
                calibration=temp_fname,
                cross_talk=ctc_fname,
                st_duration=1.0,
                coord_frame="meg",
                regularize="in",
            )
    # Our 3D cal has worse defaults for this ERM than the 1D file
    _assert_shielding(raw_sss, erm_power, 44, 45)
    assert counts[0] == 3

    # Fine cal + Crosstalk + tSSS + Reg-in + Extended
    with get_n_projected() as counts:
        raw_sss = maxwell_filter(
            raw_erm,
            calibration=fine_cal_fname,
            cross_talk=ctc_fname,
            st_duration=1.0,
            coord_frame="meg",
            regularize="in",
            extended_proj=proj[:3],
        )
    _assert_shielding(raw_sss, erm_power, 48, 50)
    assert counts[0] == 1


@pytest.mark.slowtest
@testing.requires_testing_data
def test_all():
    """Test maxwell filter using all options."""
    raw_fnames = (raw_fname, raw_fname, erm_fname, sample_fname)
    sss_fnames = (
        sss_st1FineCalCrossTalkRegIn_fname,
        sss_st1FineCalCrossTalkRegInTransSample_fname,
        sss_erm_st1FineCalCrossTalkRegIn_fname,
        sss_samp_fname,
    )
    fine_cals = (fine_cal_fname, fine_cal_fname, fine_cal_fname, fine_cal_mgh_fname)
    coord_frames = ("head", "head", "meg", "head")
    ctcs = (ctc_fname, ctc_fname, ctc_fname, ctc_mgh_fname)
    mins = (3.5, 3.5, 1.2, 0.9)
    meds = (10.8, 10.2, 3.2, 5.9)
    st_durs = (1.0, 1.0, 1.0, None)
    destinations = (None, sample_fname, None, None)
    origins = (mf_head_origin, mf_head_origin, mf_meg_origin, mf_head_origin)
    for ii, rf in enumerate(raw_fnames):
        raw = read_crop(rf, (0.0, 1.0))
        with _record_warnings():  # sometimes the fit is bad
            sss_py = maxwell_filter(
                raw,
                calibration=fine_cals[ii],
                cross_talk=ctcs[ii],
                st_duration=st_durs[ii],
                coord_frame=coord_frames[ii],
                destination=destinations[ii],
                origin=origins[ii],
            )
        sss_mf = read_crop(sss_fnames[ii])
        assert_meg_snr(sss_py, sss_mf, mins[ii], meds[ii], msg=rf)


@pytest.mark.slowtest
@testing.requires_testing_data
def test_triux():
    """Test TRIUX system support."""
    raw = read_crop(tri_fname, (0, 0.999))
    _assert_mag_coil_type(raw.info, FIFF.FIFFV_COIL_VV_MAG_T1)
    assert_allclose(raw.info["chs"][2]["cal"], 1.33e-10, rtol=1e-6)
    # standard
    with use_coil_def(elekta_def_fname):
        sss_py = maxwell_filter(raw, coord_frame="meg", regularize=None)
    _assert_mag_coil_type(sss_py.info, FIFF.FIFFV_COIL_VV_MAG_T3)
    assert_meg_snr(sss_py, read_crop(tri_sss_fname), 37, 700)
    # cross-talk
    sss_py = maxwell_filter(
        raw, coord_frame="meg", regularize=None, cross_talk=tri_ctc_fname
    )
    assert_meg_snr(sss_py, read_crop(tri_sss_ctc_fname), 31, 250)
    # fine cal
    sss_py = maxwell_filter(
        raw, coord_frame="meg", regularize=None, calibration=tri_cal_fname
    )
    assert_meg_snr(sss_py, read_crop(tri_sss_cal_fname), 5, 100)
    # ctc+cal
    sss_py = maxwell_filter(
        raw,
        coord_frame="meg",
        regularize=None,
        calibration=tri_cal_fname,
        cross_talk=tri_ctc_fname,
    )
    assert_meg_snr(sss_py, read_crop(tri_sss_ctc_cal_fname), 5, 100)
    # regularization
    sss_py = maxwell_filter(raw, coord_frame="meg", regularize="in")
    sss_mf = read_crop(tri_sss_reg_fname)
    assert_meg_snr(sss_py, sss_mf, 0.6, 9)
    _check_reg_match(sss_py, sss_mf, 1)
    # all three
    sss_py = maxwell_filter(
        raw,
        coord_frame="meg",
        regularize="in",
        calibration=tri_cal_fname,
        cross_talk=tri_ctc_fname,
    )
    sss_mf = read_crop(tri_sss_ctc_cal_reg_in_fname)
    assert_meg_snr(sss_py, sss_mf, 0.6, 9)
    _check_reg_match(sss_py, sss_mf, 1)
    # tSSS
    raw = read_crop(tri_fname).fix_mag_coil_types()
    with use_coil_def(elekta_def_fname):
        sss_py = maxwell_filter(
            raw, coord_frame="meg", regularize=None, st_duration=4.0, verbose=True
        )
    assert_meg_snr(sss_py, read_crop(tri_sss_st4_fname), 700.0, 1600)


@testing.requires_testing_data
def test_MGH_cross_talk():
    """Test cross-talk."""
    raw = read_crop(raw_fname, (0.0, 1.0))
    raw_sss = maxwell_filter(raw, cross_talk=ctc_mgh_fname)
    py_ctc = raw_sss.info["proc_history"][0]["max_info"]["sss_ctc"]
    assert len(py_ctc) > 0


@testing.requires_testing_data
def test_mf_skips():
    """Test processing of data with skips."""
    raw = read_raw_fif(skip_fname, preload=True)
    raw.fix_mag_coil_types()
    raw.pick(raw.ch_names[:50])  # fast and inaccurate
    kwargs = dict(st_only=True, coord_frame="meg", int_order=4, ext_order=3)
    # smoke test that this runs
    maxwell_filter(raw, st_duration=17.0, skip_by_annotation=(), **kwargs)
    # and this one, too, which will process some all-zero data
    maxwell_filter(raw, st_duration=2.0, skip_by_annotation=(), **kwargs)
    with pytest.raises(ValueError, match="duration"):
        # skips decrease acceptable duration
        maxwell_filter(raw, st_duration=17.0, **kwargs)
    onsets, ends = _annotations_starts_stops(raw, ("edge", "bad_acq_skip"), invert=True)
    assert (ends - onsets).min() / raw.info["sfreq"] == 2.0
    assert (ends - onsets).max() / raw.info["sfreq"] == 3.0
    for st_duration in (2.0, 3.0):
        raw_sss = maxwell_filter(raw, st_duration=st_duration, **kwargs)
        for start, stop in zip(onsets, ends):
            orig_data = raw[:, start:stop][0]
            new_data = raw_sss[:, start:stop][0]
            if (stop - start) / raw.info["sfreq"] >= st_duration:
                # Should be modified
                assert not np.allclose(new_data, orig_data, atol=1e-20)
            else:
                # Should not be modified
                assert_allclose(new_data, orig_data, atol=1e-20)
    # Processing an individual file and concat should be equivalent to
    # concat then process
    raw.crop(0, 1)
    raw_sss = maxwell_filter(raw, st_duration=1.0, **kwargs)
    raw_sss_concat = concatenate_raws([raw_sss, raw_sss.copy()])
    raw_concat = concatenate_raws([raw.copy(), raw.copy()])
    raw_concat_sss = maxwell_filter(raw_concat, st_duration=1.0, **kwargs)
    raw_concat_sss_bad = maxwell_filter(
        raw_concat, st_duration=1.0, skip_by_annotation=(), **kwargs
    )
    data_c = raw_concat[:][0]
    data_sc = raw_sss_concat[:][0]
    data_cs = raw_concat_sss[:][0]
    data_csb = raw_concat_sss_bad[:][0]
    assert not np.allclose(data_cs, data_c, atol=1e-20)
    assert not np.allclose(data_cs, data_csb, atol=1e-20)
    assert_allclose(data_sc, data_cs, atol=1e-20)


@testing.requires_testing_data
@pytest.mark.parametrize(
    (
        "fname",
        "bads",
        "annot",
        "add_ch",
        "ignore_ref",
        "want_bads",
        "return_scores",
        "h_freq",
        "meas_date",
    ),
    [
        # Neuromag data tested against MF
        pytest.param(
            sample_fname,
            [],
            False,
            False,
            False,
            ["MEG 2443"],
            False,
            None,
            "raw",
            id="Neuromag no bads",
        ),
        # add 0111 to test picking, add annot to test it, and prepend chs for
        # idx
        pytest.param(
            sample_fname,
            ["MEG 0111"],
            True,
            True,
            False,
            ["MEG 2443"],
            False,
            None,
            "raw",
            id="Neuromag with bads and annot",
        ),
        # CTF data seems to be sensitive to linalg lib (?) because some
        # channels are very close to the limit, so we just check that one shows
        # up
        pytest.param(
            ctf_fname_continuous,
            [],
            False,
            False,
            False,
            {"BR1-4304"},
            False,
            None,
            "raw",
            id="CTF no bads",
        ),
        # faked
        pytest.param(
            ctf_fname_continuous,
            [],
            False,
            False,
            True,
            ["MLC24-4304"],
            False,
            None,
            "raw",
            id="CTF ignore ref",
        ),
        # For `return_scores=True`
        pytest.param(
            sample_fname,
            ["MEG 0111"],
            True,
            True,
            False,
            ["MEG 2443"],
            True,
            50,
            "raw",
            id="Neuromag return scores",
        ),
        pytest.param(
            sample_fname,
            ["MEG 0111"],
            True,
            True,
            False,
            ["MEG 2443"],
            True,
            50,
            None,
            id="Neuromag return scores no meas date",
        ),
    ],
)
def test_find_bad_channels_maxwell(
    fname, bads, annot, add_ch, ignore_ref, want_bads, return_scores, h_freq, meas_date
):
    """Test automatic bad channel detection."""
    if fname.suffix == ".ds":
        raw = read_raw_ctf(fname).load_data()
        flat_idx = 33
    else:
        raw = read_raw_fif(fname)
        raw.fix_mag_coil_types().load_data().pick("meg", exclude=())
        flat_idx = 1
    if meas_date is None:
        raw.set_meas_date(None)
    else:
        assert meas_date == "raw"
    raw.filter(None, 40)
    raw.info["bads"] = bads
    raw._data[flat_idx] = 0  # MaxFilter didn't have this but doesn't affect it
    want_flats = [raw.ch_names[flat_idx]]
    raw.apply_gradient_compensation(0)

    min_count = 5

    if add_ch:
        raw_eeg = read_raw_fif(fname)
        raw_eeg.pick("eeg", exclude=()).load_data()
        with raw_eeg.info._unlock():
            raw_eeg.info["lowpass"] = 40.0
        raw = raw_eeg.add_channels([raw])  # prepend the EEG channels
        assert 0 in pick_types(raw.info, meg=False, eeg=True)
    if ignore_ref:
        # Fake a bad one, otherwise we don't find any
        assert 42 in pick_types(raw.info, meg=True, ref_meg=False)
        assert raw.ch_names[42:43] == want_bads
        raw._data[42] += np.random.RandomState(0).randn(len(raw.times))
    # maxfilter -autobad on -v -f test_raw.fif -force -cal off -ctc off -regularize off -list -o test_raw.fif -f ~/mne_data/MNE-testing-data/MEG/sample/sample_audvis_trunc_raw.fif  # noqa: E501
    if annot:
        # do a problematic one (gh-7741): exactly one "step" unit
        step = int(round(raw.info["sfreq"] * 5.0))
        dt = 1.0 / raw.info["sfreq"]
        assert step == 1502
        raw.annotations.append(step * dt + raw._first_time, dt, "BAD")
    with catch_logging() as log:
        return_vals = find_bad_channels_maxwell(
            raw,
            origin=(0.0, 0.0, 0.04),
            regularize=None,
            bad_condition="ignore",
            skip_by_annotation="BAD",
            verbose=True,
            ignore_ref=ignore_ref,
            min_count=min_count,
            return_scores=return_scores,
            h_freq=h_freq,
        )

    if return_scores:
        assert len(return_vals) == 3
        got_bads, got_flats, got_scores = return_vals
    else:
        assert len(return_vals) == 2
        got_bads, got_flats = return_vals

    if isinstance(want_bads, list):
        assert got_bads == want_bads  # from MaxFilter
    else:
        assert want_bads.intersection(set(got_bads))
    assert got_flats == want_flats
    log = log.getvalue()
    assert "Interval   1:    0.00" in log
    assert "Interval   2:    5.00" in log

    if h_freq is not None and h_freq > raw.info["lowpass"]:
        assert "data has already been low-pass filtered" in log

    if return_scores:
        meg_chs = raw.copy().pick("meg", exclude=[]).ch_names
        ch_types = raw.get_channel_types(meg_chs)

        assert list(got_scores["ch_names"]) == meg_chs
        assert list(got_scores["ch_types"]) == ch_types
        # Check that time is monotonically increasing.
        assert (np.diff(got_scores["bins"].flatten()) >= 0).all()

        assert (
            got_scores["scores_flat"].shape
            == got_scores["scores_noisy"].shape
            == (len(meg_chs), len(got_scores["bins"]))
        )

        assert (
            got_scores["limits_flat"].shape
            == got_scores["limits_noisy"].shape
            == (len(meg_chs), 1)
        )

        # Check "flat" scores.
        scores_flat = got_scores["scores_flat"]
        limits_flat = got_scores["limits_flat"]
        # Deal with NaN's in the scores (can't use np.less directly because of
        # https://github.com/numpy/numpy/issues/17198)
        scores_flat[np.isnan(scores_flat)] = np.inf
        limits_flat[np.isnan(limits_flat)] = -np.inf
        n_segments_below_limit = (scores_flat < limits_flat).sum(-1)
        ch_idx = np.where(
            n_segments_below_limit >= min(min_count, len(got_scores["bins"]))
        )
        flats = set(got_scores["ch_names"][ch_idx])
        assert flats == set(want_flats)

        # Check "noisy" scores.
        scores_noisy = got_scores["scores_noisy"]
        limits_noisy = got_scores["limits_noisy"]
        scores_noisy[np.isnan(scores_noisy)] = -np.inf
        limits_noisy[np.isnan(limits_noisy)] = np.inf
        n_segments_beyond_limit = (scores_noisy > limits_noisy).sum(-1)
        ch_idx = np.where(
            n_segments_beyond_limit >= min(min_count, len(got_scores["bins"]))
        )
        bads = set(got_scores["ch_names"][ch_idx])
        assert bads == set(want_bads)


def test_find_bads_maxwell_flat():
    """Test find_bads_maxwell when there are flat channels."""
    # See gh-9479
    raw = mne.io.read_raw_fif(raw_small_fname).load_data()
    assert_allclose(raw.times[-1], 23.97, atol=1e-2)
    noisy, flat = find_bad_channels_maxwell(raw, min_count=1)
    assert noisy == ["MEG 1032", "MEG 2313", "MEG 2443"]
    assert flat == []
    n = int(round(raw.info["sfreq"] * 10))
    assert (len(raw.times) - n) / raw.info["sfreq"] > 10  # at least 10 s
    with catch_logging() as log:
        want_noisy, want_flat = find_bad_channels_maxwell(
            raw.copy().crop(n / raw.info["sfreq"], None), min_count=1, verbose="debug"
        )
    log = log.getvalue()
    assert "in 2 intervals " in log
    assert want_noisy == ["MEG 2313", "MEG 2443"]
    assert want_flat == []
    raw._data[:, :n] = 0
    with pytest.warns(RuntimeWarning, match="All-flat segment detected"):
        with catch_logging() as log:
            noisy, flat = find_bad_channels_maxwell(raw, min_count=1, verbose="debug")
    log = log.getvalue()
    assert " in 4 intervals " in log
    assert flat == raw.ch_names[:306]
    assert noisy == []  # none found because all flat
    # now do what we suggest in the warning
    annot, _ = annotate_amplitude(raw, flat=0.0, bad_percent=100, min_duration=1.0)
    assert_allclose(annot.duration, 10.0, atol=1e-2)  # not even divisor sfreq
    raw.info["bads"] = []
    raw.set_annotations(annot)
    data_good = raw.get_data(reject_by_annotation="omit")
    assert data_good.shape[1] / raw.info["sfreq"] / 5.0 > 2  # at least 10 s
    with catch_logging() as log:
        noisy, flat = find_bad_channels_maxwell(
            raw, min_count=1, skip_by_annotation="bad_flat", verbose="debug"
        )
    log = log.getvalue()
    assert " in 2 intervals " in log, log
    assert flat == want_flat
    assert noisy == want_noisy


@pytest.mark.parametrize(
    "regularize, n, int_order",
    [
        (None, 80, 8),
        ("in", 71, 8),
        (None, 0, 0),
        ("in", 0, 0),
    ],
)
def test_compute_maxwell_basis(regularize, n, int_order):
    """Test compute_maxwell_basis."""
    raw = read_raw_fif(raw_small_fname).crop(0, 2)
    assert raw.info["bads"] == []
    raw.del_proj()
    rank = compute_rank(raw)["meg"]
    assert rank == 306
    raw.info["bads"] = ["MEG 2443"]
    kwargs = dict(regularize=regularize, int_order=int_order, verbose=True)
    raw_sss = maxwell_filter(raw, **kwargs)
    want = raw_sss.get_data("meg")
    rank = compute_rank(raw_sss)["meg"]
    assert rank == n
    S, pS, reg_moments, n_use_in = compute_maxwell_basis(raw.info, **kwargs)
    assert n_use_in == n
    assert n_use_in == len(reg_moments) - 15  # no externals removed
    xform = S[:, :n_use_in] @ pS[:n_use_in]
    got = xform @ raw.pick(picks="meg", exclude="bads").get_data()
    assert_allclose(got, want, atol=1e-16)


@testing.requires_testing_data
@pytest.mark.parametrize("bads", ("from_raw", "union", "keep"))
def test_prepare_emptyroom_bads(bads):
    """Test prepare_emptyroom."""
    raw = read_raw_fif(raw_fname, allow_maxshield="yes", verbose=False)
    names = [name for name in raw.ch_names if "EEG" not in name]
    raw.pick(names)
    raw_er = read_raw_fif(erm_fname, allow_maxshield="yes", verbose=False)
    raw_er.pick(names)
    assert raw.ch_names == raw_er.ch_names
    assert raw_er.info["dev_head_t"] is None
    assert raw.info["dev_head_t"] is not None
    raw_er.set_montage(None)

    if bads == "from_raw":
        raw_bads_orig = ["MEG0113", "MEG2313"]
        raw_er_bads_orig = []
    elif bads == "union":
        raw_bads_orig = ["MEG0113"]
        raw_er_bads_orig = ["MEG2313"]
    elif bads == "keep":
        raw_bads_orig = []
        raw_er_bads_orig = ["MEG0113", "MEG2313"]

    raw.info["bads"] = raw_bads_orig
    raw_er.info["bads"] = raw_er_bads_orig

    raw_er_prepared = maxwell_filter_prepare_emptyroom(
        raw_er=raw_er, raw=raw, bads=bads
    )
    assert raw_er_prepared.info["bads"] == ["MEG0113", "MEG2313"]
    assert raw_er_prepared.info["dev_head_t"] == raw.info["dev_head_t"]

    montage_expected = raw.pick(picks="meg").get_montage()
    assert raw_er_prepared.get_montage() == montage_expected

    # Ensure the originals were not modified
    assert raw.info["bads"] == raw_bads_orig
    assert raw_er.info["bads"] == raw_er_bads_orig
    assert raw_er.info["dev_head_t"] is None
    assert raw_er.get_montage() is None


@testing.requires_testing_data
def test_prepare_empty_room_with_eeg() -> None:
    """Test preparation of MEG empty-room which was acquired with EEG enabled."""
    raw = read_raw_fif(raw_fname, allow_maxshield="yes", verbose=False)
    raw_er = read_raw_fif(erm_fname, allow_maxshield="yes", verbose=False)
    assert "eeg" in raw
    assert "eeg" in raw_er
    raw_er_prepared = maxwell_filter_prepare_emptyroom(raw_er=raw_er, raw=raw)
    assert raw_er_prepared.info["dev_head_t"] == raw.info["dev_head_t"]
    montage_expected = raw.get_montage()
    assert raw_er_prepared.get_montage() == montage_expected

    raw_er = raw_er.pick("meg")
    assert "eeg" in raw
    assert "eeg" not in raw_er
    raw_er_prepared = maxwell_filter_prepare_emptyroom(raw_er=raw_er, raw=raw)
    assert raw_er_prepared.info["dev_head_t"] == raw.info["dev_head_t"]
    montage_expected = raw.pick("meg").get_montage()
    assert raw_er_prepared.get_montage() == montage_expected


@testing.requires_testing_data
@pytest.mark.slowtest  # lots of params
@pytest.mark.parametrize("set_annot_when", ("before", "after"))
@pytest.mark.parametrize("raw_meas_date", ("orig", None))
@pytest.mark.parametrize("raw_er_meas_date", ("orig", None))
@pytest.mark.parametrize("equal_sfreq", (False, True))
def test_prepare_emptyroom_annot_first_samp(
    set_annot_when, raw_meas_date, raw_er_meas_date, equal_sfreq
):
    """Test prepare_emptyroom."""
    raw = read_raw_fif(raw_fname, allow_maxshield="yes", verbose=False)
    raw_er = read_raw_fif(erm_fname, allow_maxshield="yes", verbose=False)
    names = raw.ch_names[:3]  # make it faster
    raw.pick(names)
    raw_er.pick(names)
    assert raw.ch_names == raw_er.ch_names
    assert raw.info["meas_date"] != raw_er.info["meas_date"]
    if raw_meas_date is None:
        raw.set_meas_date(None)
    if raw_er_meas_date is None:
        raw_er.set_meas_date(None)
    # to make life easier, make it the same duration
    n_rep = max(int(np.ceil(len(raw.times) / len(raw_er.times))), 1)
    raw_er = mne.concatenate_raws([raw_er] * n_rep).crop(0, raw.times[-1])
    assert_allclose(raw.times, raw_er.times)
    raw_er_first_samp_orig = raw_er.first_samp
    assert len(raw.annotations) == 0
    pos = mne.chpi.read_head_pos(pos_fname)
    annot, _ = annotate_movement(raw, pos, 1.0)
    # Add an annotation right at the beginning and end to make sure nothing
    # gets cropped
    onset = raw.times[[0, -1]]
    duration = 1.0 / raw.info["sfreq"]
    annot.append(
        onset + raw.first_time * (raw.info["meas_date"] is not None),
        duration,
        ["BAD_CUSTOM"],
    )
    want_annot = 7  # 5 from annotate_movement plus our first and last samps
    if set_annot_when == "before":
        raw.set_annotations(annot)
        meas_date = "keep"
        want_date = raw_er.info["meas_date"]
    else:
        assert set_annot_when == "after"
        meas_date = "from_raw"
        want_date = raw.info["meas_date"]
    if not equal_sfreq:
        with raw_er.info._unlock():
            raw_er.info["sfreq"] -= 100
    raw_er_prepared = maxwell_filter_prepare_emptyroom(
        raw_er=raw_er, raw=raw, meas_date=meas_date, emit_warning=True
    )
    assert raw_er.first_samp == raw_er_first_samp_orig
    assert raw_er_prepared.info["meas_date"] == want_date
    assert raw_er_prepared.first_time == raw.first_time

    # Ensure (movement) annotations carry over regardless of whether they're
    # set before or after preparation
    assert len(annot) == want_annot
    if set_annot_when == "after":
        raw.set_annotations(annot)
        raw_er_prepared.set_annotations(annot)
    assert len(raw.annotations) == want_annot
    prop_bad = np.isnan(raw.get_data([0], reject_by_annotation="nan")).mean()
    assert 0.3 < prop_bad < 0.4
    assert len(raw_er_prepared.annotations) == want_annot
    if equal_sfreq:
        prop_bad_er = np.isnan(
            raw_er_prepared.get_data([0], reject_by_annotation="nan")
        ).mean()
        assert_allclose(prop_bad, prop_bad_er)


@pytest.mark.slowtest
@testing.requires_testing_data
@pytest.mark.parametrize("mc_interp", ("zero", "hann", False))
@pytest.mark.parametrize("st_fixed", (False, True, False))
@pytest.mark.parametrize("st_only", (True, False))
@pytest.mark.filterwarnings("ignore:st_fixed=False is untested.*:RuntimeWarning")
def test_feed_avg(st_fixed, st_only, mc_interp):
    """Test that feed_avg gives the correct data for tSSS."""
    if mc_interp is False:
        movecomp = False
        mc_interp = "zero"
    else:
        movecomp = True
    raw = read_crop(raw_fname, (0, 3.0)).load_data()  # 0-1, 0.5-1.5, ...
    # Use every third mag just for speed
    raw.pick("mag")
    raw.pick(raw.ch_names[::3])
    if movecomp:
        head_pos = read_head_pos(pos_fname)
        # Trim just to make debugging easier
        head_pos = head_pos[head_pos[:, 0] < head_pos[0, 0] + 5]
    else:
        head_pos = None
    kwargs = dict(
        int_order=3, st_duration=1, st_fixed=st_fixed, st_only=st_only, verbose="debug"
    )
    # These were empirically determined -- the importart thing is that they
    # only change under specific (expected) circumstances, e.g., not dependent
    # on st_only at all
    n = 8 if (movecomp and mc_interp == "hann" and not st_fixed) else 4
    st_0_1 = f"Projecting  {n} intersecting tSSS components for    0.000 -    0.999 s"
    if st_fixed:
        n = 4
    else:
        if movecomp:
            n = 12 if mc_interp == "hann" else 8
        else:
            n = 4
    st_0p5_1p5 = (
        f"Projecting {n:2d} intersecting tSSS components for    0.000 -    0.999 s"
    )
    if movecomp and st_fixed:
        st_0p5_1p5 += " (across  2 positions)\n"
    n = 8 if (movecomp and mc_interp == "hann" and not st_fixed) else 4
    log_1_2 = (
        f"Projecting  {n} intersecting tSSS components for    1.000 -    1.999 s\n"
    )
    with catch_logging() as log:
        _maxwell_filter_ola(
            raw, head_pos=head_pos, st_overlap=False, mc_interp=mc_interp, **kwargs
        )
    log = log.getvalue()
    # Leave these print statements in because they'll be captured by pytest but
    # are valuable during failures
    print(log)
    assert st_0_1 in log
    assert log_1_2 in log
    assert "Eval @ 0 (0)" in log
    if movecomp:
        assert raw.first_time == 9.0
        this_head_pos = head_pos[np.where(head_pos[:, 0] >= 9.5)[0][0] - 1 :].copy()
        this_head_pos[0, 0] = 9.5
        assert this_head_pos[1, 0] > this_head_pos[0, 0]
    else:
        this_head_pos = None
    with catch_logging() as log_crop:
        _maxwell_filter_ola(
            raw.copy().crop(0.5, None),
            head_pos=this_head_pos,
            st_overlap=False,
            mc_interp=mc_interp,
            **kwargs,
        )
    log_crop = log_crop.getvalue()
    print(log_crop)
    assert st_0p5_1p5 in log_crop
    # The full / OLA version of this will reflect the actual offset
    st_0p5_1p5 = st_0p5_1p5.replace("0.000", "0.500").replace("0.999", "1.499")
    with catch_logging() as log_ola:
        _maxwell_filter_ola(
            raw,
            st_overlap=True,
            mc_interp=mc_interp,
            head_pos=head_pos,
            **kwargs,
        )
    log_ola = log_ola.getvalue()
    print(log_ola)
    assert st_0_1 in log_ola
    assert log_1_2 in log_ola
    assert st_0p5_1p5 in log_ola
