import os
import pathlib
from typing import Callable, Literal, Tuple, Union

import pytest
import scvelo as scv
from _helpers import (
    create_failed_model,
    create_model,
    gamr_skip,
    resize_images_to_same_sizes,
)

import numpy as np
import pandas as pd
import scipy.sparse as sp

import matplotlib.cm as cm
import matplotlib.pyplot as plt
from matplotlib.testing import setup
from matplotlib.testing.compare import compare_images

from anndata import AnnData

import cellrank as cr
from cellrank._utils import Lineage
from cellrank._utils._key import Key
from cellrank.estimators import CFLARE, GPCCA
from cellrank.kernels import ConnectivityKernel, PseudotimeKernel, VelocityKernel
from cellrank.models import GAMR

setup()

HERE: str = pathlib.Path(__file__).parent
GT_FIGS = HERE / "_ground_truth_figures"
FIGS = HERE / "figures"
DPI = 40
TOL = 150

# both are for `50` adata
GENES = [
    "Tcea1",
    "Tmeff2",
    "Ndufb3",
    "Rpl37a",
    "Arpc2",
    "Ptma",
    "Cntnap5b",
    "Cntnap5a",
    "Mpc2",
    "2010300C02Rik",
]
RAW_GENES = [
    "Synpr",
    "Rps24",
    "Erc2",
    "Mbnl2",
    "Thoc7",
    "Itm2b",
    "Pcdh9",
    "Fgf14",
    "Rpl37",
    "Cdh9",
]

# TODO(michalk8): move to sessionstart
cr.settings.figdir = FIGS
scv.settings.figdir = str(FIGS)
scv.set_figure_params(transparent=True)


def compare(
    *,
    kind: Literal["adata", "gpcca", "bwd", "gpcca_bwd", "cflare", "lineage", "gamr"] = "adata",
    dirname: Union[str, pathlib.Path] = None,
    tol: int = TOL,
) -> Callable:
    def _compare_images(expected_path: Union[str, pathlib.Path], actual_path: Union[str, pathlib.Path]) -> None:
        resize_images_to_same_sizes(expected_path, actual_path)
        res = compare_images(expected_path, actual_path, tol=tol)
        assert res is None, res

    # TODO: refactor (we can remove the prefix from scvelo
    def _prepare_fname(func: Callable) -> Tuple[str, str]:
        fpath = f"{func.__name__.replace('test_', '')}"
        # scvelo saves figures as pdf
        return fpath, str(fpath[7:] + ".png" if fpath.startswith("scvelo_") else fpath)

    def _assert_equal(fpath: str) -> None:
        if not fpath.endswith(".png"):
            fpath += ".png"
        if dirname is not None:
            for file in os.listdir(FIGS / dirname):
                if "-diff" in file:
                    continue
                _compare_images(GT_FIGS / dirname / file, FIGS / dirname / file)
        else:
            _compare_images(GT_FIGS / fpath, FIGS / fpath)

    def compare_cflare_fwd(
        func: Callable,
    ) -> Callable:  # mustn't use functools.wraps - it think's the fact that `adata` is fixture
        def decorator(self, adata_cflare_fwd) -> None:
            adata, mc = adata_cflare_fwd
            fpath, path = _prepare_fname(func)

            func(self, adata if kind == "adata" else mc, path)

            _assert_equal(fpath)

        return decorator

    def compare_gpcca_fwd(func: Callable) -> Callable:
        def decorator(self, adata_gpcca_fwd) -> None:
            adata, gpcca = adata_gpcca_fwd
            fpath, path = _prepare_fname(func)

            func(self, adata if kind == "adata" else gpcca, path)

            _assert_equal(fpath)

        return decorator

    def compare_gpcca_bwd(func: Callable) -> Callable:
        def decorator(self, adata_gpcca_bwd) -> None:
            adata, gpcca = adata_gpcca_bwd
            fpath, path = _prepare_fname(func)

            func(self, adata if kind == "bwd" else gpcca, path)

            _assert_equal(fpath)

        return decorator

    def compare_lineage(func: Callable):
        def decorator(self, lineage):
            path, fpath = _prepare_fname(func)

            func(self, lineage, path)

            _assert_equal(fpath)

        assert kind == "lineage", "Function `compare_lineage` only supports `kind='lineage'`."

        return decorator

    def compare_gamr(func: Callable):
        def decorator(self, gamr_model: GAMR):
            path, fpath = _prepare_fname(func)

            func(self, gamr_model, path)

            _assert_equal(fpath)

        assert kind == "gamr", "Function `compare_gamr` only supports `kind='gamr'`."

        return decorator

    if kind in ("adata", "gpcca"):
        # `kind='adata'` - don't changes this, otherwise some tests in `TestHighLvlStates` are meaningless
        return compare_gpcca_fwd
    if kind in ("bwd", "gpcca_bwd"):
        return compare_gpcca_bwd
    if kind == "cflare":
        return compare_cflare_fwd
    if kind == "lineage":
        return compare_lineage
    if kind == "gamr":
        return compare_gamr

    raise NotImplementedError(f"Invalid kind `{kind!r}`.")


class TestAggregateAbsorptionProbabilities:
    @compare()
    def test_bar(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(adata, cluster_key="clusters", mode="bar", dpi=DPI, save=fpath)

    @compare(kind="bwd")
    def test_bar_bwd(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(
            adata,
            cluster_key="clusters",
            backward=True,
            mode="bar",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_bar_cluster_subset(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(
            adata,
            cluster_key="clusters",
            mode="bar",
            clusters=["Astrocytes", "GABA"],
            dpi=DPI,
            save=fpath,
        )

    @compare(tol=50)
    def test_bar_cluster_subset_violin(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(
            adata,
            cluster_key="clusters",
            mode="violin",
            clusters=["Endothelial"],
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_bar_lineage_subset(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(
            adata,
            cluster_key="clusters",
            mode="bar",
            lineages=["0"],
            dpi=DPI,
            save=fpath,
        )

    @compare(tol=250)
    def test_paga_pie(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(adata, cluster_key="clusters", mode="paga_pie", dpi=DPI, save=fpath)

    @compare(tol=250)
    def test_paga_pie_title(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(
            adata,
            cluster_key="clusters",
            mode="paga_pie",
            title="foo bar baz",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_paga_pie_embedding(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(
            adata,
            cluster_key="clusters",
            mode="paga_pie",
            basis="umap",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_paga(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(adata, cluster_key="clusters", mode="paga", dpi=DPI, save=fpath)

    @compare()
    def test_paga_lineage_subset(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(
            adata,
            cluster_key="clusters",
            mode="paga",
            lineages=["0"],
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_violin(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(adata, cluster_key="clusters", mode="violin", dpi=DPI, save=fpath)

    @compare()
    def test_violin_no_cluster_key(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(adata, mode="violin", cluster_key=None, dpi=DPI, save=fpath)

    @compare()
    def test_violin_cluster_subset(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(adata, cluster_key="clusters", mode="violin", dpi=DPI, save=fpath)

    @compare()
    def test_violin_lineage_subset(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(
            adata,
            cluster_key="clusters",
            mode="violin",
            lineages=["1"],
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_paga_pie_legend_simple(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(
            adata,
            cluster_key="clusters",
            mode="paga_pie",
            save=fpath,
            dpi=DPI,
            legend_kwargs={"loc": "top"},
        )

    @compare()
    def test_paga_pie_legend_position(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(
            adata,
            cluster_key="clusters",
            mode="paga_pie",
            basis="umap",
            save=fpath,
            dpi=DPI,
            legend_kwargs={"loc": "lower"},
            legend_loc="upper",
        )

    @compare()
    def test_paga_pie_no_legend(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(
            adata,
            cluster_key="clusters",
            mode="paga_pie",
            basis="umap",
            save=fpath,
            dpi=DPI,
            legend_kwargs={"loc": None},
            legend_loc=None,
        )

    @compare()
    def test_paga_pie_only_fate_prob(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(
            adata,
            cluster_key="clusters",
            mode="paga_pie",
            basis="umap",
            save=fpath,
            dpi=DPI,
            legend_kwargs={"loc": "center"},
            legend_loc=None,
        )

    @compare()
    def test_paga_pie_only_clusters(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(
            adata,
            cluster_key="clusters",
            mode="paga_pie",
            basis="umap",
            save=fpath,
            dpi=DPI,
            legend_kwargs={"loc": None},
            legend_loc="on data",
        )

    @compare()
    def test_paga_pie_legend_position_out(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(
            adata,
            cluster_key="clusters",
            mode="paga_pie",
            basis="umap",
            save=fpath,
            dpi=DPI,
            legend_kwargs={"loc": "lower left out"},
            legend_loc="center right out",
        )

    def test_invalid_mode(self, adata_cflare_fwd):
        adata, _ = adata_cflare_fwd
        with pytest.raises(ValueError, match=r"Invalid option"):
            cr.pl.aggregate_fate_probabilities(
                adata,
                cluster_key="clusters",
                mode="foobar",
            )

    def test_paga_pie_wrong_legend_kind_1(self, adata_cflare_fwd):
        adata, _ = adata_cflare_fwd
        with pytest.raises(ValueError, match=r"Invalid legend position"):
            cr.pl.aggregate_fate_probabilities(
                adata,
                cluster_key="clusters",
                mode="paga_pie",
                legend_kwargs={"loc": "foo"},
            )

    def test_paga_pie_wrong_legend_kind_2(self, adata_cflare_fwd):
        adata, _ = adata_cflare_fwd
        with pytest.raises(ValueError, match=r"Invalid legend position"):
            cr.pl.aggregate_fate_probabilities(
                adata,
                cluster_key="clusters",
                mode="paga_pie",
                legend_kwargs={"loc": "lower foo"},
            )

    def test_paga_pie_wrong_legend_kind_3(self, adata_cflare_fwd):
        adata, _ = adata_cflare_fwd
        with pytest.raises(ValueError, match=r"Invalid modifier"):
            cr.pl.aggregate_fate_probabilities(
                adata,
                cluster_key="clusters",
                mode="paga_pie",
                legend_kwargs={"loc": "lower left bar"},
            )

    def test_paga_pie_wrong_legend_kind_4(self, adata_cflare_fwd):
        adata, _ = adata_cflare_fwd
        with pytest.raises(ValueError, match=r"Expected only 1 additional"):
            cr.pl.aggregate_fate_probabilities(
                adata,
                cluster_key="clusters",
                mode="paga_pie",
                legend_kwargs={"loc": "lower left foo bar"},
            )

    @compare()
    def test_mode_heatmap(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(adata, cluster_key="clusters", mode="heatmap", dpi=DPI, save=fpath)

    @compare()
    def test_mode_heatmap_format(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(
            adata,
            cluster_key="clusters",
            mode="heatmap",
            fmt=".1f",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_mode_heatmap_title(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(
            adata,
            cluster_key="clusters",
            mode="heatmap",
            title="foo",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_mode_heatmap_cmap(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(
            adata,
            cluster_key="clusters",
            mode="heatmap",
            cmap="inferno",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_mode_heatmap_xticks_rotation(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(
            adata,
            cluster_key="clusters",
            mode="heatmap",
            xrot=45,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_mode_heatmap_clusters(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(
            adata,
            cluster_key="clusters",
            mode="heatmap",
            clusters=["Astrocytes", "GABA"],
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_mode_heatmap_lineages(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(
            adata,
            cluster_key="clusters",
            mode="heatmap",
            lineages=["0"],
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_mode_clustermap(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(adata, cluster_key="clusters", mode="clustermap", dpi=DPI, save=fpath)

    @compare()
    def test_mode_clustermap_format(self, adata: AnnData, fpath: str):
        cr.pl.aggregate_fate_probabilities(
            adata,
            cluster_key="clusters",
            mode="clustermap",
            fmt=".1f",
            dpi=DPI,
            save=fpath,
        )


class TestClusterTrends:
    @compare()
    def test_cluster_lineage(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.cluster_trends(
            adata,
            model,
            GENES[:10],
            "1",
            "latent_time",
            random_state=0,
            dpi=DPI,
            save=fpath,
        )

    @compare(kind="bwd")
    def test_cluster_lineage_bwd(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.cluster_trends(
            adata,
            model,
            GENES[:10],
            "0",
            "latent_time",
            random_state=0,
            backward=True,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_cluster_lineage_raw(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.cluster_trends(
            adata,
            model,
            RAW_GENES[:5],
            "1",
            "latent_time",
            random_state=0,
            dpi=DPI,
            save=fpath,
            use_raw=True,
        )

    @compare()
    def test_cluster_lineage_no_norm(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.cluster_trends(
            adata,
            model,
            GENES[:10],
            "1",
            "latent_time",
            random_state=0,
            norm=False,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_cluster_lineage_data_key(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.cluster_trends(
            adata,
            model,
            GENES[:10],
            "1",
            "latent_time",
            random_state=0,
            data_key="Ms",
            norm=False,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_cluster_lineage_random_state(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.cluster_trends(
            adata,
            model,
            GENES[:10],
            "1",
            "latent_time",
            random_state=42,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_cluster_lineage_leiden(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.cluster_trends(
            adata,
            model,
            GENES[:10],
            "1",
            "latent_time",
            random_state=0,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_cluster_lineage_2_failed_genes(self, adata: AnnData, fpath: str):
        fm = create_failed_model(adata)
        cr.pl.cluster_trends(
            adata,
            {GENES[0]: fm, GENES[5]: fm, "*": fm.model},
            GENES[:10],
            "1",
            "latent_time",
            random_state=0,
            key="foobar",
            dpi=DPI,
            save=fpath,
        )

        assert isinstance(adata.uns["foobar"], AnnData)
        assert adata.uns["foobar"].shape == (8, 200)

    def test_cluster_lineage_returns_fitted_models(self, adata_cflare: AnnData):
        fm = create_failed_model(adata_cflare)
        models = cr.pl.cluster_trends(
            adata_cflare,
            {GENES[0]: fm, "*": fm.model},
            GENES[:10],
            "1",
            "latent_time",
            random_state=0,
            return_models=True,
        )

        models = pd.DataFrame(models).T
        np.testing.assert_array_equal(models.index, GENES[:10])
        np.testing.assert_array_equal(models.columns, ["1"])
        assert isinstance(models.loc[GENES[0], "1"], cr.models.FailedModel)

        mask = models.astype(bool)
        assert not mask.loc[GENES[0], "1"]
        mask.loc[GENES[0], "1"] = True

        assert np.all(mask)

    def test_cluster_lineage_random_state_same_pca(self, adata_cflare: AnnData):
        model = create_model(adata_cflare)
        cr.pl.cluster_trends(
            adata_cflare,
            model,
            GENES[:10],
            "1",
            "latent_time",
            random_state=42,
            key="foo",
        )

        cr.pl.cluster_trends(
            adata_cflare,
            model,
            GENES[:10],
            "1",
            "latent_time",
            random_state=42,
            key="bar",
        )

        np.allclose(adata_cflare.uns["foo"].obsm["X_pca"], adata_cflare.uns["bar"].obsm["X_pca"])

    def test_cluster_lineage_writes(self, adata_cflare: AnnData):
        model = create_model(adata_cflare)
        cr.pl.cluster_trends(
            adata_cflare,
            model,
            GENES[:10],
            "0",
            time_key="latent_time",
            n_test_points=200,
        )

        assert isinstance(adata_cflare.uns["lineage_0_trend"], AnnData)
        assert adata_cflare.uns["lineage_0_trend"].shape == (10, 200)
        assert isinstance(adata_cflare.uns["lineage_0_trend"].obs["clusters"].dtype, pd.CategoricalDtype)

    def test_cluster_lineage_key(self, adata_cflare: AnnData):
        model = create_model(adata_cflare)
        cr.pl.cluster_trends(
            adata_cflare,
            model,
            GENES[:10],
            "0",
            "latent_time",
            n_test_points=200,
            key="foobar",
        )

        assert isinstance(adata_cflare.uns["foobar"], AnnData)
        assert adata_cflare.uns["foobar"].shape == (10, 200)
        assert isinstance(adata_cflare.uns["foobar"].obs["clusters"].dtype, pd.CategoricalDtype)

    @compare()
    def test_cluster_lineage_covariates(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.cluster_trends(
            adata,
            model,
            GENES[:10],
            "1",
            "latent_time",
            covariate_key=["clusters", "latent_time"],
            random_state=0,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_cluster_lineage_covariates_cmap(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.cluster_trends(
            adata,
            model,
            GENES[:10],
            "1",
            "latent_time",
            covariate_key="latent_time",
            cmap="inferno",
            random_state=0,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_cluster_lineage_covariates_ratio(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.cluster_trends(
            adata,
            model,
            GENES[:10],
            "1",
            "latent_time",
            covariate_key="latent_time",
            ratio=0.25,
            random_state=0,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_cluster_lineage_gene_symbols(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.cluster_trends(
            adata,
            model,
            [f"{g}:gs" for g in GENES[:10]],
            "1",
            "latent_time",
            gene_symbols="symbol",
            random_state=0,
            dpi=DPI,
            save=fpath,
        )


class TestHeatmap:
    @compare(dirname="heatmap_lineages")
    def test_heatmap_lineages(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:10],
            "latent_time",
            mode="lineages",
            dpi=DPI,
            save=fpath,
        )

    @compare(kind="bwd", dirname="heatmap_lineages_bwd")
    def test_heatmap_lineages_bwd(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:10],
            "latent_time",
            backward=True,
            mode="lineages",
            dpi=DPI,
            save=fpath,
        )

    @compare(dirname="heatmap_lineages_raw")
    def test_heatmap_lineages_raw(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            RAW_GENES[:5],
            "latent_time",
            mode="lineages",
            use_raw=True,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_heatmap_genes(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:10],
            "latent_time",
            mode="genes",
            dpi=DPI,
            save=fpath,
        )

    @compare(dirname="heatmap_no_cluster_genes")
    def test_heatmap_no_cluster_genes(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:10],
            "latent_time",
            cluster_genes=False,
            mode="lineages",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_heatmap_cluster_genes(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:10],
            "latent_time",
            lineages="1",
            mode="lineages",
            cluster_genes=True,
            dpi=DPI,
            save=fpath,
        )

    @compare(dirname="heatmap_lineage_height")
    def test_heatmap_lineage_height(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:10],
            "latent_time",
            mode="lineages",
            lineage_height=0.2,
            dpi=DPI,
            save=fpath,
        )

    @compare(dirname="heatmap_time_range")
    def test_heatmap_time_range(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:10],
            "latent_time",
            mode="lineages",
            time_range=(0.2, 0.5),
            dpi=DPI,
            save=fpath,
        )

    @compare(tol=250)
    def test_heatmap_cmap(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:5],
            "latent_time",
            mode="genes",
            cmap=cm.viridis,
            dpi=DPI,
            save=fpath,
        )

    @compare(dirname="heatmap_no_cbar_lineages")
    def test_heatmap_no_cbar_lineages(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:5],
            "latent_time",
            mode="lineages",
            cbar=False,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_heatmap_no_cbar_genes(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:5],
            "latent_time",
            mode="genes",
            cbar=False,
            dpi=DPI,
            save=fpath,
        )

    @compare(dirname="heatmap_fate_probs_lineages")
    def test_heatmap_fate_probs_lineages(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:5],
            "latent_time",
            mode="lineages",
            show_fate_probabilities=True,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_heatmap_fate_probs_genes(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:5],
            "latent_time",
            mode="genes",
            show_fate_probabilities=True,
            dpi=DPI,
            save=fpath,
        )

    @compare(dirname="heatmap_no_convolve")
    def test_heatmap_no_convolve(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:5],
            "latent_time",
            mode="lineages",
            n_convolve=None,
            dpi=DPI,
            save=fpath,
        )

    @compare(dirname="heatmap_no_scale_lineages")
    def test_heatmap_no_scale_lineages(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:5],
            "latent_time",
            mode="lineages",
            scale=False,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_heatmap_no_scale_genes(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:5],
            "latent_time",
            mode="genes",
            scale=False,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_heatmap_cluster_no_scale(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:5],
            "latent_time",
            lineages="1",
            mode="lineages",
            scale=False,
            cluster_genes=True,
            dpi=DPI,
            save=fpath,
        )

    @compare(dirname="heatmap_no_cluster")
    def test_heatmap_no_cluster(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:5],
            "latent_time",
            mode="lineages",
            cluster_genes=False,
            dpi=DPI,
            save=fpath,
        )

    @compare(dirname="heatmap_cluster_key_no_fate_probs")
    def test_heatmap_cluster_key_no_fate_probs(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:5],
            "latent_time",
            cluster_key="clusters",
            show_fate_probabilities=False,
            mode="lineages",
            dpi=DPI,
            save=fpath,
        )

    @compare(dirname="heatmap_cluster_key_fate_probs")
    def test_heatmap_cluster_key_fate_probs(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:5],
            "latent_time",
            cluster_key="clusters",
            show_fate_probabilities=True,
            mode="lineages",
            dpi=DPI,
            save=fpath,
        )

    @compare(dirname="heatmap_multiple_cluster_keys")
    def test_heatmap_multiple_cluster_keys(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:5],
            "latent_time",
            cluster_key=["clusters", "clusters_enlarged", "clusters"],
            show_fate_probabilities=True,
            mode="lineages",
            dpi=DPI,
            save=fpath,
        )

    @compare(dirname="heatmap_multiple_cluster_keys_show_all_genes")
    def test_heatmap_multiple_cluster_keys_show_all_genes(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:10],
            "latent_time",
            mode="lineages",
            dpi=DPI,
            save=fpath,
        )

    @pytest.mark.skip("Hangs using pytest-xdist")
    @compare(dirname="heatmap_n_jobs")
    def test_heatmap_n_jobs(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:5],
            "latent_time",
            n_jobs=2,
            backend="threading",
            cluster_key=["clusters", "clusters_enlarged", "clusters"],
            show_fate_probabilities=True,
            mode="lineages",
            dpi=DPI,
            save=fpath,
        )

    @pytest.mark.skip("Hangs using pytest-xdist")
    @compare(dirname="heatmap_n_jobs_multiprocessing")
    def test_heatmap_n_jobs_multiprocessing(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:5],
            "latent_time",
            n_jobs=2,
            backend="loky",  # uses pickling of objects, such as Lineage
            cluster_key=["clusters", "clusters_enlarged", "clusters"],
            show_fate_probabilities=True,
            mode="lineages",
            dpi=DPI,
            save=fpath,
        )

    @compare(dirname="heatmap_keep_gene_order")
    def test_heatmap_keep_gene_order(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:10],
            "latent_time",
            mode="lineages",
            keep_gene_order=True,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_heatmap_show_dendrogram(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            GENES[:10],
            "latent_time",
            mode="lineages",
            lineages="1",
            cluster_genes=True,
            dendrogram=True,
            dpi=DPI,
            save=fpath,
        )

    @compare(dirname="heatmap_lineages_1_lineage_failed")
    def test_heatmap_lineages_1_lineage_failed(self, adata: AnnData, fpath: str):
        fm = create_failed_model(adata)
        cr.pl.heatmap(
            adata,
            {g: {"0": fm, "*": fm.model} for g in GENES[:10]},
            GENES[:10],
            "latent_time",
            mode="lineages",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_heatmap_genes_1_gene_failed(self, adata: AnnData, fpath: str):
        fm = create_failed_model(adata)
        cr.pl.heatmap(
            adata,
            {GENES[0]: fm, "*": fm.model},
            GENES[:10],
            "latent_time",
            mode="genes",
            dpi=DPI,
            save=fpath,
        )

    @compare(dirname="heatmap_gene_symbols")
    def test_heatmap_gene_symbols(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.heatmap(
            adata,
            model,
            [f"{g}:gs" for g in GENES[:10]],
            "latent_time",
            gene_symbols="symbol",
            dpi=DPI,
            save=fpath,
        )


class TestHeatmapReturns:
    def test_heatmap_lineages_return_genes(self, adata_cflare: AnnData):
        model = create_model(adata_cflare)
        df = cr.pl.heatmap(
            adata_cflare,
            model,
            GENES[:10],
            "latent_time",
            mode="lineages",
            return_genes=True,
            dpi=DPI,
        )

        assert isinstance(df, pd.DataFrame)
        np.testing.assert_array_equal(df.columns, adata_cflare.obsm[Key.obsm.fate_probs(False)].names)
        assert len(df) == 10
        assert set(df.iloc[:, 0].values) == set(GENES[:10])

    def test_heatmap_lineages_return_models(self, adata_cflare: AnnData):
        model = create_model(adata_cflare)
        models = cr.pl.heatmap(
            adata_cflare,
            model,
            GENES[:10],
            "latent_time",
            mode="lineages",
            return_models=True,
            dpi=DPI,
        )

        models = pd.DataFrame(models).T
        np.testing.assert_array_equal(models.index, GENES[:10])
        np.testing.assert_array_equal(models.columns, adata_cflare.obsm[Key.obsm.fate_probs(False)].names)
        assert np.all(models.astype(bool))

    def test_heatmap_lineages_return_models_and_genes(self, adata_cflare: AnnData):
        model = create_model(adata_cflare)
        models, df = cr.pl.heatmap(
            adata_cflare,
            model,
            GENES[:10],
            "latent_time",
            mode="lineages",
            return_models=True,
            return_genes=True,
            dpi=DPI,
        )

        lnames = adata_cflare.obsm[Key.obsm.fate_probs(False)].names

        models = pd.DataFrame(models).T
        np.testing.assert_array_equal(models.index, GENES[:10])
        np.testing.assert_array_equal(models.columns, lnames)
        assert np.all(models.astype(bool))

        assert isinstance(df, pd.DataFrame)
        np.testing.assert_array_equal(df.columns, lnames)
        assert len(df) == 10
        assert set(df.iloc[:, 0].values) == set(GENES[:10])

    def test_heatmap_lineages_return_genes_large_number(self, adata_cflare: AnnData):
        model = create_model(adata_cflare)
        genes = adata_cflare.var_names[:100]
        df = cr.pl.heatmap(
            adata_cflare,
            model,
            genes,
            "latent_time",
            mode="lineages",
            return_genes=True,
            dpi=DPI,
        )

        assert isinstance(df, pd.DataFrame)
        np.testing.assert_array_equal(df.columns, adata_cflare.obsm[Key.obsm.fate_probs(False)].names)
        assert len(df) == len(genes)
        assert set(df.iloc[:, 0].values) == set(genes)

    def test_heatmap_lineages_return_genes_same_order(self, adata_cflare: AnnData):
        model = create_model(adata_cflare)
        df = cr.pl.heatmap(
            adata_cflare,
            model,
            GENES[:10],
            "latent_time",
            keep_gene_order=True,
            mode="lineages",
            return_genes=True,
            dpi=DPI,
        )

        assert isinstance(df, pd.DataFrame)
        np.testing.assert_array_equal(df.columns, adata_cflare.obsm[Key.obsm.fate_probs(False)].names)
        assert len(df) == 10
        assert set(df.iloc[:, 0].values) == set(GENES[:10])

        ref = df.iloc[:, 0].values
        for i in range(1, len(df.columns)):
            np.testing.assert_array_equal(df.iloc[:, i].values, ref)

    def test_heatmap_genes_return_no_genes(self, adata_cflare: AnnData):
        model = create_model(adata_cflare)
        df = cr.pl.heatmap(
            adata_cflare,
            model,
            GENES[:10],
            "latent_time",
            mode="genes",
            cluster_genes=True,
            dendrogram=True,
            return_genes=True,
            dpi=DPI,
        )

        assert df is None


class TestGeneTrend:
    @compare()
    def test_trends(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[:3],
            time_key="latent_time",
            data_key="Ms",
            dpi=DPI,
            save=fpath,
        )

    @compare(kind="bwd")
    def test_trends_bwd(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[:3],
            time_key="latent_time",
            backward=True,
            data_key="Ms",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_raw(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            RAW_GENES[:5],
            time_key="latent_time",
            data_key="X",
            use_raw=True,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_same_plot(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[:3],
            time_key="latent_time",
            data_key="Ms",
            same_plot=True,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_hide_cells(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[0],
            time_key="latent_time",
            data_key="Ms",
            same_plot=True,
            hide_cells=True,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_conf_int(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[0],
            time_key="latent_time",
            data_key="Ms",
            same_plot=True,
            conf_int=False,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_sharey(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[:3],
            time_key="latent_time",
            data_key="Ms",
            sharey="row",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_sharex(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[:10],
            time_key="latent_time",
            ncols=3,
            data_key="Ms",
            sharex="all",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_gene_as_title(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[:10],
            time_key="latent_time",
            gene_as_title=False,
            same_plot=True,
            data_key="Ms",
            sharex="all",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_gene_no_legend(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[:10],
            time_key="latent_time",
            legend_loc=None,
            data_key="Ms",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_gene_legend_out(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[:2],
            time_key="latent_time",
            same_plot=True,
            legend_loc="bottom right out",
            data_key="Ms",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_no_cbar(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[0],
            time_key="latent_time",
            data_key="Ms",
            same_plot=True,
            cbar=False,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_lineage_cmap(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[0],
            time_key="latent_time",
            data_key="Ms",
            same_plot=True,
            lineage_cmap=cm.Set2,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_fate_prob_cmap(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[0],
            time_key="latent_time",
            data_key="Ms",
            same_plot=False,
            hide_cells=False,
            fate_prob_cmap=cm.inferno,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_lineage_cell_color(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[0],
            time_key="latent_time",
            data_key="Ms",
            same_plot=True,
            cell_color="red",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_lineage_cell_color_gene(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[0],
            time_key="latent_time",
            data_key="Ms",
            same_plot=True,
            cell_color=adata.var_names[0],
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_lineage_cell_color_clusters(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[0],
            time_key="latent_time",
            data_key="Ms",
            same_plot=True,
            cell_color="clusters",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_lineage_cell_color_clusters_obs_legend_loc(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[0],
            time_key="latent_time",
            data_key="Ms",
            same_plot=True,
            cell_color="clusters",
            obs_legend_loc="top left out",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_lw(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[0],
            time_key="latent_time",
            data_key="Ms",
            same_plot=True,
            lw=10,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_suptitle(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[:10],
            time_key="latent_time",
            suptitle="FOOBAR",
            data_key="Ms",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_size(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[0],
            time_key="latent_time",
            data_key="Ms",
            same_plot=True,
            size=30,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_margins(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[0],
            time_key="latent_time",
            data_key="Ms",
            same_plot=True,
            margins=0.2,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_cell_alpha(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[0],
            time_key="latent_time",
            data_key="Ms",
            same_plot=True,
            cell_alpha=0,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_lineage_alpha(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[0],
            time_key="latent_time",
            data_key="Ms",
            same_plot=True,
            lineage_alpha=1,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_time_range(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[:10],
            time_key="latent_time",
            data_key="Ms",
            same_plot=False,
            time_range=(0, 0.5),
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_perc(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[:10],
            time_key="latent_time",
            data_key="Ms",
            same_plot=False,
            perc=(0, 50),
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_perc_per_lineage(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[:3],
            time_key="latent_time",
            figsize=(5, 5),
            data_key="Ms",
            same_plot=False,
            perc=[(0, 50), (5, 95), (50, 100)],
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_time_key(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[:10],
            data_key="Ms",
            same_plot=False,
            time_key="dpt_pseudotime",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_show_lineage_ignores_no_transpose(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[:5],
            time_key="latent_time",
            transpose=False,
            data_key="Ms",
            same_plot=True,
            plot_kwargs={"lineage_probability": True},
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_show_lineage_same_plot(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[:5],
            time_key="latent_time",
            transpose=True,
            data_key="Ms",
            same_plot=True,
            plot_kwargs={"lineage_probability": True},
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_show_lineage_diff_plot(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[0],
            time_key="latent_time",
            data_key="Ms",
            same_plot=False,
            transpose=True,
            plot_kwargs={"lineage_probability": True},
            figsize=(5, 5),
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_show_lineage_ci(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[0],
            time_key="latent_time",
            data_key="Ms",
            same_plot=True,
            transpose=True,
            plot_kwargs={"lineage_probability": True, "lineage_probability_conf_int": True},
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_time_key_del_latent_time(self, adata: AnnData, fpath: str):
        # this ensures that the callback passes the correct values
        del adata.obs["latent_time"]
        assert "latent_time" not in adata.obs

        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[:10],
            data_key="Ms",
            same_plot=False,
            time_key="dpt_pseudotime",
            dpi=DPI,
            save=fpath,
        )

    def test_invalid_time_key(self, adata_cflare: AnnData):
        model = create_model(adata_cflare)
        with pytest.raises(KeyError, match=r"Fatal model"):
            cr.pl.gene_trends(
                adata_cflare,
                model,
                GENES[:10],
                data_key="Ms",
                same_plot=False,
                time_key="foobar",
            )

    def test_all_models_failed(self, adata_cflare: AnnData):
        fm = create_failed_model(adata_cflare)
        with pytest.raises(RuntimeError, match=r"Fatal model"):
            cr.pl.gene_trends(
                adata_cflare,
                fm,
                GENES[:10],
                data_key="Ms",
                mode="lineages",
                time_key="latent_time",
                dpi=DPI,
            )

    def test_return_models_no_failures(self, adata_cflare: AnnData):
        model = create_model(adata_cflare)
        models = cr.pl.gene_trends(
            adata_cflare,
            model,
            GENES[:10],
            data_key="Ms",
            lineages=["0", "1"],
            time_key="latent_time",
            dpi=DPI,
            return_models=True,
        )

        models = pd.DataFrame(models).T
        np.testing.assert_array_equal(models.index, GENES[:10])
        np.testing.assert_array_equal(models.columns, [str(i) for i in range(2)])
        assert np.all(models.astype(bool))

    def test_return_models_with_failures(self, adata_cflare: AnnData):
        fm = create_failed_model(adata_cflare)
        models = cr.pl.gene_trends(
            adata_cflare,
            {GENES[0]: {"0": fm, "*": fm.model}, "*": fm.model},
            GENES[:10],
            lineages=["0", "1"],
            time_key="latent_time",
            dpi=DPI,
            return_models=True,
        )

        models = pd.DataFrame(models).T
        np.testing.assert_array_equal(models.index, GENES[:10])
        np.testing.assert_array_equal(models.columns, [str(i) for i in range(2)])
        assert isinstance(models.loc[GENES[0], "0"], cr.models.FailedModel)

        mask = models.astype(bool)
        assert not mask.loc[GENES[0], "0"]
        mask.loc[GENES[0], "0"] = True

        assert np.all(mask)

    @compare()
    def test_all_models_for_1_gene_failed(self, adata: AnnData, fpath: str):
        fm = create_failed_model(adata)
        cr.pl.gene_trends(
            adata,
            {GENES[0]: fm, "*": fm.model},
            GENES[:3],
            figsize=(5, 5),
            data_key="Ms",
            time_key="latent_time",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_all_models_for_1_lineage_failed(self, adata: AnnData, fpath: str):
        fm = create_failed_model(adata)
        cr.pl.gene_trends(
            adata,
            {g: {"0": fm, "*": fm.model} for g in GENES[:3]},
            GENES[:3],
            figsize=(5, 5),
            data_key="Ms",
            time_key="latent_time",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_all_models_for_1_gene_failed_same_plot(self, adata: AnnData, fpath: str):
        fm = create_failed_model(adata)
        cr.pl.gene_trends(
            adata,
            {GENES[0]: fm, "*": fm.model},
            GENES[:10],
            data_key="Ms",
            time_key="latent_time",
            same_plot=True,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_failed_only_main_diagonal(self, adata: AnnData, fpath: str):
        fm = create_failed_model(adata)
        cr.pl.gene_trends(
            adata,
            {g: {str(ln): fm.model, "*": fm} for ln, g in enumerate(GENES[:3])},
            GENES[:3],
            lineages=["0", "1", "2"],
            data_key="Ms",
            time_key="latent_time",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_failed_only_off_diagonal(self, adata: AnnData, fpath: str):
        fm = create_failed_model(adata)
        cr.pl.gene_trends(
            adata,
            {g: {str(ln): fm.model, "*": fm} for ln, g in zip(range(3)[::-1], GENES[:3])},
            GENES[:3],
            data_key="Ms",
            time_key="latent_time",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_transpose(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[:4],
            transpose=True,
            data_key="Ms",
            time_key="latent_time",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_transpose_same_plot(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            GENES[:3],
            transpose=True,
            same_plot=True,
            data_key="Ms",
            time_key="latent_time",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_transpose_all_models_for_1_gene_failed(self, adata: AnnData, fpath: str):
        fm = create_failed_model(adata)
        cr.pl.gene_trends(
            adata,
            {GENES[0]: fm, "*": fm.model},
            GENES[:10],
            transpose=True,
            time_key="latent_time",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_transpose_all_models_for_1_lineage_failed(self, adata: AnnData, fpath: str):
        fm = create_failed_model(adata)
        cr.pl.gene_trends(
            adata,
            {g: {"0": fm, "*": fm.model} for g in GENES[:10]},
            GENES[:10],
            transpose=True,
            data_key="Ms",
            time_key="latent_time",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_transpose_failed_only_off_diagonal(self, adata: AnnData, fpath: str):
        fm = create_failed_model(adata)
        cr.pl.gene_trends(
            adata,
            {g: {str(ln): fm.model, "*": fm} for ln, g in zip(range(3)[::-1], GENES[:3])},
            GENES[:3],
            transpose=True,
            data_key="Ms",
            time_key="latent_time",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_transpose_all_models_for_1_lineage_failed_same_plot(self, adata: AnnData, fpath: str):
        fm = create_failed_model(adata)
        cr.pl.gene_trends(
            adata,
            {g: {"0": fm, "*": fm.model} for g in GENES[:10]},
            GENES[:10],
            transpose=True,
            same_plot=True,
            data_key="Ms",
            time_key="latent_time",
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_trends_gene_symbols(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        cr.pl.gene_trends(
            adata,
            model,
            [f"{g}:gs" for g in GENES[:3]],
            time_key="latent_time",
            gene_symbols="symbol",
            data_key="Ms",
            dpi=DPI,
            save=fpath,
        )


class TestCFLARE:
    @compare(kind="cflare")
    def test_mc_spectrum(self, mc: CFLARE, fpath: str):
        mc.plot_spectrum(dpi=DPI, save=fpath)

    @compare(kind="cflare")
    def test_mc_complex_spectrum(self, mc: CFLARE, fpath: str):
        mc.plot_spectrum(real_only=False, dpi=DPI, save=fpath)

    @compare(kind="cflare")
    def test_mc_real_spectrum(self, mc: CFLARE, fpath: str):
        mc.plot_spectrum(real_only=True, dpi=DPI, save=fpath)

    @compare(kind="cflare")
    def test_mc_real_spectrum_hide_xticks(self, mc: CFLARE, fpath: str):
        mc.plot_spectrum(real_only=True, show_all_xticks=False, dpi=DPI, save=fpath)

    @compare(kind="cflare")
    def test_mc_real_spectrum_hide_eigengap(self, mc: CFLARE, fpath: str):
        mc.plot_spectrum(real_only=True, show_eigengap=False, dpi=DPI, save=fpath)

    @compare(kind="cflare")
    def test_mc_spectrum_title(self, mc: CFLARE, fpath: str):
        mc.plot_spectrum(title="foobar", real_only=False, dpi=DPI, save=fpath)

    @compare(kind="cflare")
    def test_mc_marker(self, mc: CFLARE, fpath: str):
        mc.plot_spectrum(dpi=DPI, marker="X", save=fpath)

    @compare(kind="cflare")
    def test_mc_kwargs_linewidths(self, mc: CFLARE, fpath: str):
        mc.plot_spectrum(dpi=DPI, linewidths=20, save=fpath)

    @compare(kind="cflare")
    def test_mc_spectrum_evals(self, mc: CFLARE, fpath: str):
        mc.plot_spectrum(2, real_only=True, dpi=DPI, save=fpath)

    @compare(kind="cflare")
    def test_mc_spectrum_evals_complex(self, mc: CFLARE, fpath: str):
        mc.plot_spectrum(2, real_only=False, dpi=DPI, save=fpath)

    @compare(kind="cflare")
    def test_scvelo_final_states(self, mc: CFLARE, fpath: str):
        mc.plot_macrostates(which="terminal", dpi=DPI, save=fpath)

    @compare(kind="cflare")
    def test_scvelo_final_states_clusters(self, mc: CFLARE, fpath: str):
        mc.plot_macrostates(which="terminal", color="clusters", dpi=DPI, save=fpath)

    @compare(kind="cflare")
    def test_scvelo_lin_probs(self, mc: CFLARE, fpath: str):
        mc.plot_fate_probabilities(dpi=DPI, save=fpath)

    @compare(kind="cflare")
    def test_scvelo_lin_probs_clusters(self, mc: CFLARE, fpath: str):
        mc.plot_fate_probabilities(color="clusters", dpi=DPI, save=fpath)

    @compare(kind="cflare")
    def test_scvelo_lin_probs_cmap(self, mc: CFLARE, fpath: str):
        mc.plot_fate_probabilities(cmap=cm.inferno, dpi=DPI, save=fpath)

    @compare(kind="cflare")
    def test_scvelo_lin_probs_lineages(self, mc: CFLARE, fpath: str):
        mc.plot_fate_probabilities(states=["0"], dpi=DPI, save=fpath)

    @compare(kind="cflare")
    def test_scvelo_lin_probs_time(self, mc: CFLARE, fpath: str):
        mc.plot_fate_probabilities(mode="time", time_key="latent_time", dpi=DPI, save=fpath)


class TestGPCCA:
    @compare(kind="gpcca")
    def test_gpcca_complex_spectrum(self, mc: GPCCA, fpath: str):
        mc.plot_spectrum(real_only=False, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_gpcca_real_spectrum(self, mc: GPCCA, fpath: str):
        mc.plot_spectrum(real_only=True, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_gpcca_real_spectrum_hide_eigengap(self, mc: GPCCA, fpath: str):
        mc.plot_spectrum(real_only=True, show_eigengap=False, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_gpcca_spectrum_title(self, mc: GPCCA, fpath: str):
        mc.plot_spectrum(title="foobar", real_only=True, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_gpcca_spectrum_evals(self, mc: CFLARE, fpath: str):
        mc.plot_spectrum(2, real_only=True, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_gpcca_spectrum_evals_complex(self, mc: CFLARE, fpath: str):
        mc.plot_spectrum(2, real_only=False, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_gpcca_schur_matrix(self, mc: GPCCA, fpath: str):
        mc.plot_schur_matrix(dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_gpcca_schur_matrix_title(self, mc: GPCCA, fpath: str):
        mc.plot_schur_matrix(title="foobar", dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_gpcca_schur_matrix_cmap(self, mc: GPCCA, fpath: str):
        mc.plot_schur_matrix(cmap=cm.inferno, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_gpcca_coarse_T(self, mc: GPCCA, fpath: str):
        mc.plot_coarse_T(show_initial_dist=False, show_stationary_dist=False, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_gpcca_coarse_T_stat_dist(self, mc: GPCCA, fpath: str):
        mc.plot_coarse_T(show_initial_dist=False, show_stationary_dist=True, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_gpcca_coarse_T_init_dist(self, mc: GPCCA, fpath: str):
        mc.plot_coarse_T(show_initial_dist=True, show_stationary_dist=False, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_gpcca_coarse_T_stat_init_dist(self, mc: GPCCA, fpath: str):
        mc.plot_coarse_T(show_initial_dist=True, show_stationary_dist=True, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_gpcca_coarse_T_no_cbar(self, mc: GPCCA, fpath: str):
        mc.plot_coarse_T(show_cbar=False, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_gpcca_coarse_T_no_annot(self, mc: GPCCA, fpath: str):
        mc.plot_coarse_T(annotate=False, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_gpcca_coarse_T_cmap(self, mc: GPCCA, fpath: str):
        mc.plot_coarse_T(cmap=cm.inferno, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_gpcca_coarse_T_xtick_rot(self, mc: GPCCA, fpath: str):
        mc.plot_coarse_T(xtick_rotation=0, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_gpcca_coarse_T_no_order(self, mc: GPCCA, fpath: str):
        mc.plot_coarse_T(order=None, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_scvelo_gpcca_meta_states(self, mc: GPCCA, fpath: str):
        mc.plot_macrostates(which="all", dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_scvelo_gpcca_meta_states_lineages(self, mc: GPCCA, fpath: str):
        mc.plot_macrostates(which="all", states=["0"], dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_scvelo_gpcca_meta_states_discrete(self, mc: GPCCA, fpath: str):
        mc.plot_macrostates(which="all", discrete=True, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_scvelo_gpcca_meta_states_cluster_key(self, mc: GPCCA, fpath: str):
        mc.plot_macrostates(which="all", color="clusters", dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_scvelo_gpcca_meta_states_no_same_plot(self, mc: GPCCA, fpath: str):
        mc.plot_macrostates(which="all", same_plot=False, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_scvelo_gpcca_meta_states_cmap(self, mc: GPCCA, fpath: str):
        mc.plot_macrostates(which="all", cmap=cm.inferno, same_plot=False, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_scvelo_gpcca_meta_states_title(self, mc: GPCCA, fpath: str):
        mc.plot_macrostates(which="all", title="foobar", dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_scvelo_gpcca_meta_states_time(self, mc: GPCCA, fpath: str):
        mc.plot_macrostates(which="all", mode="time", dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_scvelo_gpcca_final_states(self, mc: GPCCA, fpath: str):
        mc.plot_macrostates(which="terminal", dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_scvelo_gpcca_final_states_lineages(self, mc: GPCCA, fpath: str):
        mc.plot_macrostates(which="terminal", states=["0"], dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_scvelo_gpcca_final_states_discrete(self, mc: GPCCA, fpath: str):
        mc.plot_macrostates(which="terminal", discrete=True, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_scvelo_gpcca_final_states_cluster_key(self, mc: GPCCA, fpath: str):
        mc.plot_macrostates(which="terminal", color="clusters", dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_scvelo_gpcca_final_states_no_same_plot(self, mc: GPCCA, fpath: str):
        mc.plot_macrostates(which="terminal", same_plot=False, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_scvelo_gpcca_final_states_cmap(self, mc: GPCCA, fpath: str):
        mc.plot_macrostates(which="terminal", cmap=cm.inferno, same_plot=False, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_scvelo_gpcca_final_states_title(self, mc: GPCCA, fpath: str):
        mc.plot_macrostates(which="terminal", title="foobar", dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_scvelo_gpcca_final_states_time(self, mc: GPCCA, fpath: str):
        mc.plot_macrostates(which="terminal", mode="time", dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_scvelo_gpcca_fate_probs_cont_same_no_clusters(self, mc: GPCCA, fpath: str):
        mc.plot_fate_probabilities(same_plot=True, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_scvelo_gpcca_fate_probs_cont_same_clusters(self, mc: GPCCA, fpath: str):
        mc.plot_fate_probabilities(color="clusters", same_plot=True, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_scvelo_gpcca_fate_probs_cont_not_same(self, mc: GPCCA, fpath: str):
        mc.plot_fate_probabilities(color="clusters", same_plot=False, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_scvelo_transition_matrix_projection(self, mc: GPCCA, fpath: str):
        mc.kernel.plot_projection(
            basis="umap",
            stream=False,
            arrow_length=6,
            arrow_size=6,
            dpi=DPI,
            save=fpath,
        )

    @compare(kind="gpcca")
    def test_plot_tsi(self, mc: GPCCA, fpath: str):
        terminal_states = ["Neuroblast", "Astrocyte", "Granule mature"]
        cluster_key = "clusters"
        _ = mc.tsi(n_macrostates=3, terminal_states=terminal_states, cluster_key=cluster_key, n_cells=10)
        mc.plot_tsi(dpi=DPI, save=fpath)


class TestLineage:
    @compare(kind="lineage")
    def test_pie(self, lineage: cr.Lineage, fpath: str):
        lineage.plot_pie(np.mean, dpi=DPI, save=fpath)

    @compare(kind="lineage")
    def test_pie_reduction(self, lineage: cr.Lineage, fpath: str):
        lineage.plot_pie(np.var, dpi=DPI, save=fpath)

    @compare(kind="lineage")
    def test_pie_title(self, lineage: cr.Lineage, fpath: str):
        lineage.plot_pie(np.mean, title="FOOBAR", dpi=DPI, save=fpath)

    @compare(kind="lineage")
    def test_pie_t(self, lineage: cr.Lineage, fpath: str):
        lineage.T.plot_pie(np.mean, dpi=DPI, save=fpath)

    @compare(kind="lineage")
    def test_pie_autopct_none(self, lineage: cr.Lineage, fpath: str):
        lineage.T.plot_pie(np.mean, dpi=DPI, save=fpath, autopct=None)

    @compare(kind="lineage")
    def test_pie_legend_loc(self, lineage: cr.Lineage, fpath: str):
        lineage.plot_pie(np.mean, dpi=DPI, save=fpath, legend_loc="best")

    @compare(kind="lineage")
    def test_pie_legend_loc_one(self, lineage: cr.Lineage, fpath: str):
        lineage.plot_pie(np.mean, dpi=DPI, save=fpath, legend_loc=None)

    @compare(kind="lineage")
    def test_pie_legend_kwargs(self, lineage: cr.Lineage, fpath: str):
        lineage.plot_pie(
            np.mean,
            dpi=DPI,
            save=fpath,
            legend_loc="best",
            legend_kwargs={"fontsize": 20},
        )


class TestLineageDrivers:
    @compare(kind="gpcca")
    def test_drivers_n_genes(self, mc: GPCCA, fpath: str):
        mc.plot_lineage_drivers("0", n_genes=5, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_drivers_ascending(self, mc: GPCCA, fpath: str):
        mc.plot_lineage_drivers("0", ascending=True, dpi=DPI, save=fpath)

    @compare(kind="gpcca_bwd")
    def test_drivers_backward(self, mc: GPCCA, fpath: str):
        mc.plot_lineage_drivers("0", ncols=2, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_drivers_cmap(self, mc: GPCCA, fpath: str):
        mc.plot_lineage_drivers("0", cmap="inferno", dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_drivers_title_fmt(self, mc: GPCCA, fpath: str):
        mc.plot_lineage_drivers(
            "0",
            cmap="inferno",
            title_fmt="{gene} qval={qval} corr={corr}",
            dpi=DPI,
            save=fpath,
        )


class TestModel:
    @compare()
    def test_model_default(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        model.prepare(adata.var_names[0], "1", "latent_time")
        model.fit().predict()
        model.confidence_interval()
        model.plot(save=fpath, dpi=DPI)

    @compare(kind="bwd")
    def test_model_default_bwd(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        model.prepare(adata.var_names[0], "0", "latent_time", backward=True)
        model.fit().predict()
        model.confidence_interval()
        model.plot(save=fpath, dpi=DPI)

    @compare()
    def test_model_obs_data_key(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        gene = adata.X[:, 0]
        adata.obs["foo"] = gene.toarray() if sp.issparse(gene) else gene

        model.prepare("foo", "1", "latent_time", data_key="obs")
        model.fit().predict()
        model.confidence_interval()
        model.plot(save=fpath, dpi=DPI)

    @compare()
    def test_model_no_lineage(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        model.prepare(adata.var_names[0], None, "latent_time")
        model.fit().predict()
        model.confidence_interval()
        model.plot(save=fpath, dpi=DPI)

    @compare()
    def test_model_no_lineage_show_lin_probs(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        model.prepare(adata.var_names[0], None, "latent_time")
        model.fit().predict()
        model.plot(save=fpath, dpi=DPI, lineage_probability=True)

    @compare()
    def test_model_no_legend(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        model.prepare(adata.var_names[0], "1", "latent_time")
        model.fit().predict()
        model.confidence_interval()
        model.plot(save=fpath, dpi=DPI, loc=None)

    # TODO: parametrize (hide cells, ci)
    @compare()
    def test_model_show_lin_prob_cells_ci(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        model.prepare(adata.var_names[0], "1", "latent_time")
        model.fit().predict()
        model.confidence_interval()
        model.plot(
            save=fpath,
            dpi=DPI,
            hide_cells=False,
            conf_int=True,
            lineage_probability=True,
        )

    @compare()
    def test_model_show_lin_prob_cells_lineage_ci(self, adata: AnnData, fpath: str):
        model = create_model(adata)
        model.prepare(adata.var_names[0], "1", "latent_time")
        model.fit().predict()
        model.confidence_interval()
        model.plot(
            save=fpath,
            dpi=DPI,
            hide_cells=True,
            conf_int=True,
            lineage_probability=True,
            lineage_probability_conf_int=True,
        )

    @compare()
    def test_model_1_lineage(self, adata: AnnData, fpath: str):
        adata.obsm[Key.obsm.fate_probs(False)] = Lineage(np.ones((adata.n_obs, 1)), names=["foo"])
        model = create_model(adata)
        model = model.prepare(adata.var_names[0], "foo", "latent_time", n_test_points=100).fit()
        model.fit().predict()
        model.confidence_interval()
        model.plot(save=fpath, dpi=DPI, conf_int=True)


@gamr_skip
class TestGAMR:
    @compare(kind="gamr")
    def test_gamr_default(self, model: GAMR, fpath: str):
        model.prepare(model.adata.var_names[0], "1", "latent_time")
        model.fit().predict()
        model.plot(
            save=fpath,
            dpi=DPI,
        )

    @compare(kind="gamr")
    def test_gamr_ci_50(self, model: GAMR, fpath: str):
        model.prepare(model.adata.var_names[0], "1", "latent_time")
        model.fit().predict(level=0.5)
        model.plot(
            conf_int=True,
            save=fpath,
            dpi=DPI,
        )

    @compare(kind="gamr")
    def test_gamr_no_ci(self, model: GAMR, fpath: str):
        model.prepare(model.adata.var_names[0], "1", "latent_time")
        model.fit().predict(level=None)
        model.plot(
            conf_int=False,
            save=fpath,
            dpi=DPI,
        )

    @compare(kind="gamr")
    def test_gamr_no_cbar(self, model: GAMR, fpath: str):
        model.prepare(model.adata.var_names[0], "1", "latent_time")
        model.fit().predict(level=0.95)
        model.plot(
            cbar=False,
            save=fpath,
            dpi=DPI,
        )

    @compare(kind="gamr")
    def test_gamr_lineage_prob(self, model: GAMR, fpath: str):
        model.prepare(model.adata.var_names[0], "1", "latent_time")
        model.fit().predict(level=0.95)
        model.plot(
            lineage_probability=True,
            lineage_probability_conf_int=True,
            save=fpath,
            dpi=DPI,
        )

    @compare(kind="gamr")
    def test_trends_gam_ci_100(self, model: GAMR, fpath: str):
        cr.pl.gene_trends(
            model.adata,
            model,
            GENES[:3],
            time_key="latent_time",
            conf_int=1,
            backward=False,
            data_key="Ms",
            dpi=DPI,
            save=fpath,
        )

    @compare(kind="gamr")
    def test_trends_gam_ci_20(self, model: GAMR, fpath: str):
        cr.pl.gene_trends(
            model.adata,
            model,
            GENES[:3],
            time_key="latent_time",
            conf_int=0.2,
            backward=False,
            data_key="Ms",
            dpi=DPI,
            save=fpath,
        )


class TestComposition:
    @compare()
    def test_composition(self, adata: AnnData, fpath: str):
        cr.pl._utils.composition(adata, "clusters", dpi=DPI, save=fpath)

    @compare()
    def test_composition_kwargs_autopct(self, adata: AnnData, fpath: str):
        cr.pl._utils.composition(adata, "clusters", dpi=DPI, save=fpath, autopct="%1.0f%%")


class TestFittedModel:
    @compare()
    def test_fitted_empty_model(self, adata: AnnData, fpath: str):
        rng = np.random.default_rng(42)
        fm = cr.models.FittedModel(np.arange(100), rng.normal(size=100))
        fm.plot(dpi=DPI, save=fpath)

    @compare()
    def test_fitted_model_conf_int(self, adata: AnnData, fpath: str):
        rng = np.random.default_rng(43)
        y_test = rng.normal(size=100)

        fm = cr.models.FittedModel(np.arange(100), y_test, conf_int=np.c_[y_test - 1, y_test + 1])
        fm.plot(conf_int=True, dpi=DPI, save=fpath)

    @compare()
    def test_fitted_model_conf_int_no_conf_int_computed(self, adata: AnnData, fpath: str):
        rng = np.random.default_rng(44)

        fm = cr.models.FittedModel(
            np.arange(100),
            rng.normal(size=100),
        )
        fm.plot(conf_int=True, dpi=DPI, save=fpath)

    @compare()
    def test_fitted_model_cells_with_weights(self, adata: AnnData, fpath: str):
        rng = np.random.default_rng(45)

        fm = cr.models.FittedModel(
            np.arange(100),
            rng.normal(size=100),
            x_all=rng.normal(size=200),
            y_all=rng.normal(size=200),
        )

        fm.plot(hide_cells=False, dpi=DPI, save=fpath)

    @compare()
    def test_fitted_model_weights(self, adata: AnnData, fpath: str):
        rng = np.random.default_rng(46)

        fm = cr.models.FittedModel(
            np.arange(100),
            rng.normal(size=100),
            x_all=rng.normal(size=200),
            y_all=rng.normal(size=200),
            w_all=rng.normal(size=200),
        )

        fm.plot(hide_cells=False, dpi=DPI, save=fpath)

    @compare()
    def test_fitted_ignore_plot_smoothed_lineage(self, adata: AnnData, fpath: str):
        rng = np.random.default_rng(47)

        fm = cr.models.FittedModel(
            np.arange(100),
            rng.normal(size=100),
            x_all=rng.normal(size=200),
            y_all=rng.normal(size=200),
            w_all=rng.normal(size=200),
        )

        fm.plot(
            lineage_probability=True,
            lineage_probability_conf_int=True,
            dpi=DPI,
            save=fpath,
        )

    @compare()
    def test_fitted_gene_trends(self, adata: AnnData, fpath: str):
        rng = np.random.default_rng(48)

        fm1 = cr.models.FittedModel(
            np.arange(100),
            rng.normal(size=100),
            x_all=rng.normal(size=200),
            y_all=rng.normal(size=200),
            w_all=rng.normal(size=200),
        )
        fm2 = cr.models.FittedModel(
            np.arange(100),
            rng.normal(size=100),
            x_all=rng.normal(size=200),
            y_all=rng.normal(size=200),
            w_all=rng.normal(size=200),
        )
        cr.pl.gene_trends(
            adata,
            {GENES[0]: fm1, GENES[1]: fm2},
            GENES[:2],
            time_key="latent_time",
            data_key="Ms",
            dpi=DPI,
            save=fpath,
        )

    @compare(tol=250)
    def test_fitted_cluster_fates(self, adata: AnnData, fpath: str):
        rng = np.random.default_rng(49)

        model = cr.models.FittedModel(
            np.arange(100),
            rng.normal(size=100),
        )
        cr.pl.cluster_trends(
            adata,
            model,
            GENES[:10],
            "1",
            "latent_time",
            n_points=100,
            random_state=49,
            dpi=DPI,
            save=fpath,
        )

    @compare(dirname="fitted_heatmap")
    def test_fitted_heatmap(self, adata: AnnData, fpath: str):
        rng = np.random.default_rng(49)

        fm = cr.models.FittedModel(
            np.arange(100),
            rng.normal(size=100),
        )
        cr.pl.heatmap(
            adata,
            fm,
            GENES[:10],
            "latent_time",
            mode="lineages",
            dpi=DPI,
            save=fpath,
        )


class TestCircularProjection:
    def test_proj_too_few_lineages(self, adata_gpcca_fwd):
        adata, _ = adata_gpcca_fwd
        lineages = adata.obsm[Key.obsm.fate_probs(False)].names[:2]

        with pytest.raises(ValueError, match=r"Expected at least `3` lineages"):
            cr.pl.circular_projection(adata, keys=["clusters", "clusters"], lineages=lineages)

    @compare()
    def test_proj_duplicate_keys(self, adata: AnnData, fpath: str):
        cr.pl.circular_projection(adata, keys=["clusters", "clusters"], dpi=DPI, save=fpath)

        key = "X_fate_simplex_fwd"
        assert key in adata.obsm
        assert isinstance(adata.obsm[key], np.ndarray)
        assert adata.obsm[key].shape[1] == 2

    @compare()
    def test_proj_key_added(self, adata: AnnData, fpath: str):
        key = "foo"
        cr.pl.circular_projection(adata, keys=adata.var_names[0], key_added=key, dpi=DPI, save=fpath)

        assert key in adata.obsm
        assert isinstance(adata.obsm[key], np.ndarray)
        assert adata.obsm[key].shape[1] == 2

    @compare()
    def test_proj_hide_edges(self, adata: AnnData, fpath: str):
        cr.pl.circular_projection(adata, keys="dpt_pseudotime", show_edges=False, dpi=DPI, save=fpath)

    @compare()
    def test_proj_dont_normalize_by_mean(self, adata: AnnData, fpath: str):
        cr.pl.circular_projection(adata, keys="clusters", normalize_by_mean=False, dpi=DPI, save=fpath)

    @compare()
    def test_proj_use_raw(self, adata: AnnData, fpath: str):
        cr.pl.circular_projection(adata, keys=adata.raw.var_names[0], use_raw=True, dpi=DPI, save=fpath)

    @compare()
    def test_proj_ncols(self, adata: AnnData, fpath: str):
        cr.pl.circular_projection(adata, keys=adata.var_names[:2], ncols=1, dpi=DPI, save=fpath)

    @compare()
    def test_proj_labelrot(self, adata: AnnData, fpath: str):
        cr.pl.circular_projection(adata, keys="clusters", label_rot="default", dpi=DPI, save=fpath)

    @compare()
    def test_proj_labeldistance(self, adata: AnnData, fpath: str):
        cr.pl.circular_projection(adata, keys="clusters", label_distance=1.5, dpi=DPI, save=fpath)

    @compare()
    def test_proj_text_kwargs(self, adata: AnnData, fpath: str):
        cr.pl.circular_projection(adata, keys="clusters", text_kwargs={"size": 20}, dpi=DPI, save=fpath)

    @compare()
    def test_proj_default_ordering(self, adata: AnnData, fpath: str):
        cr.pl.circular_projection(adata, keys="clusters", lineage_order="default", dpi=DPI, save=fpath)

    @compare()
    def test_proj_extra_keys(self, adata: AnnData, fpath: str):
        cr.pl.circular_projection(adata, keys=["kl_divergence", "entropy"], dpi=DPI, save=fpath)

        apk = Key.obsm.fate_probs(False)
        assert f"{apk}_kl_divergence" in adata.obs
        assert f"{apk}_entropy" in adata.obs

    @compare()
    def test_proj_scvelo_kwargs(self, adata: AnnData, fpath: str):
        cr.pl.circular_projection(adata, keys="clusters", legend_loc="upper right", dpi=DPI, save=fpath)

    @compare()
    def test_proj_no_cbar(self, adata: AnnData, fpath: str):
        cr.pl.circular_projection(adata, keys=adata.var_names[0], colorbar=False, dpi=DPI, save=fpath)


class TestPlotRandomWalk:
    @compare(kind="gpcca")
    def test_kernel_random_walk_params(self, mc: GPCCA, fpath: str):
        mc.kernel.plot_random_walks(
            n_sims=100,
            max_iter=100,
            seed=42,
            start_ixs={"clusters": "OL"},
            dpi=DPI,
            save=fpath,
        )

    @compare(kind="gpcca")
    def test_kernel_random_walk_start_ixs_range(self, mc: GPCCA, fpath: str):
        mc.kernel.plot_random_walks(
            n_sims=10,
            max_iter=100,
            seed=42,
            start_ixs={"dpt_pseudotime": [0, 0]},
            color="dpt_pseudotime",
            dpi=DPI,
            save=fpath,
        )

    @compare(kind="gpcca")
    def test_kernel_random_walk_basis(self, mc: GPCCA, fpath: str):
        mc.kernel.plot_random_walks(n_sims=10, max_iter=100, seed=42, basis="pca", dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_kernel_random_walk_cmap(self, mc: GPCCA, fpath: str):
        mc.kernel.plot_random_walks(n_sims=10, max_iter=100, seed=42, cmap="viridis", dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_kernel_random_walk_line_width(self, mc: GPCCA, fpath: str):
        mc.kernel.plot_random_walks(n_sims=10, max_iter=100, seed=42, linewidth=2, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_kernel_random_walk_line_alpha(self, mc: GPCCA, fpath: str):
        mc.kernel.plot_random_walks(n_sims=10, max_iter=100, seed=42, linealpha=1, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_kernel_random_walk_kwargs(self, mc: GPCCA, fpath: str):
        mc.kernel.plot_random_walks(n_sims=10, max_iter=100, seed=42, color="none", dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_kernel_random_walk_ixs_legend_loc(self, mc: GPCCA, fpath: str):
        mc.kernel.plot_random_walks(
            n_sims=10,
            max_iter=100,
            seed=42,
            ixs_legend_loc="top right out",
            legend_loc="upper left",
            dpi=DPI,
            save=fpath,
        )


class TestPlotSingleFlow:
    @compare(kind="gpcca")
    def test_flow_source_clusters(self, mc: GPCCA, fpath: str):
        mc.kernel.plot_single_flow(
            "Neuroblast",
            "clusters",
            "age(days)",
            clusters=["OPC", "Endothelial", "OL"],
            dpi=DPI,
            save=fpath,
        )

    @compare(kind="gpcca")
    def test_flow_clusters_subset(self, mc: GPCCA, fpath: str):
        mc.kernel.plot_single_flow(
            "Astrocytes",
            "clusters",
            "age(days)",
            clusters=["OPC", "Endothelial", "OL"],
            dpi=DPI,
            save=fpath,
        )

    @compare(kind="gpcca")
    def test_flow_min_flow_remove_empty_clusters(self, mc: GPCCA, fpath: str):
        mc.kernel.plot_single_flow(
            "Astrocytes",
            "clusters",
            "age(days)",
            min_flow=0.2,
            remove_empty_clusters=True,
            dpi=DPI,
            save=fpath,
        )

    @compare(kind="gpcca")
    def test_flow_min_flow_keep_empty_clusters(self, mc: GPCCA, fpath: str):
        mc.kernel.plot_single_flow(
            "Astrocytes",
            "clusters",
            "age(days)",
            min_flow=0.2,
            remove_empty_clusters=False,
            dpi=DPI,
            save=fpath,
        )

    @compare(kind="gpcca")
    def test_flow_cluster_ascending(self, mc: GPCCA, fpath: str):
        mc.kernel.plot_single_flow("Astrocytes", "clusters", "age(days)", ascending=True, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_flow_cluster_descending(self, mc: GPCCA, fpath: str):
        mc.kernel.plot_single_flow("Astrocytes", "clusters", "age(days)", ascending=False, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_flow_explicit_cluster_order(self, mc: GPCCA, fpath: str):
        mc.kernel.plot_single_flow(
            "Astrocytes",
            "clusters",
            "age(days)",
            ascending=None,
            clusters=["OPC", "OL"],
            dpi=DPI,
            save=fpath,
        )

    @compare(kind="gpcca")
    def test_flow_legend_loc(self, mc: GPCCA, fpath: str):
        mc.kernel.plot_single_flow(
            "Astrocytes",
            "clusters",
            "age(days)",
            legend_loc="upper left out",
            dpi=DPI,
            save=fpath,
        )

    @compare(kind="gpcca")
    def test_flow_alpha(self, mc: GPCCA, fpath: str):
        mc.kernel.plot_single_flow("Astrocytes", "clusters", "age(days)", alpha=0.3, dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_flow_no_xticks(self, mc: GPCCA, fpath: str):
        mc.kernel.plot_single_flow(
            "Astrocytes",
            "clusters",
            "age(days)",
            xticks_step_size=None,
            dpi=DPI,
            save=fpath,
        )

    @compare(kind="gpcca")
    def test_flow_time_categories_too_close(self, mc: GPCCA, fpath: str):
        mc.adata.obs["day"] = (
            mc.adata.obs["age(days)"]
            .cat.rename_categories(
                {
                    "12": 0.1,
                    "35": 0.291,
                }
            )
            .values
        )
        mc.kernel.plot_single_flow("Astrocytes", "clusters", "day", dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_flow_return_ax(self, mc: GPCCA, fpath: str):
        ax = mc.kernel.plot_single_flow("Astrocytes", "clusters", "age(days)", show=False, dpi=DPI, save=fpath)
        assert isinstance(ax, plt.Axes)


class TestPlotDriverCorrelation:
    @compare(kind="gpcca")
    def test_driver_corr(self, mc: GPCCA, fpath: str):
        mc.plot_lineage_drivers_correlation("1", "2", dpi=DPI, save=fpath, title="bar", size=100)

    @compare(kind="gpcca")
    def test_driver_corr_color(self, mc: GPCCA, fpath: str):
        mc.plot_lineage_drivers_correlation("0", "1", dpi=DPI, save=fpath, color="2_corr")

    @compare(kind="gpcca")
    def test_driver_corr_gene_sets(self, mc: GPCCA, fpath: str):
        mc.plot_lineage_drivers_correlation("0", "1", dpi=DPI, save=fpath, gene_sets={"0": mc.adata.var_names[:3]})

    @compare(kind="gpcca")
    def test_driver_corr_gene_sets_colors(self, mc: GPCCA, fpath: str):
        mc.plot_lineage_drivers_correlation(
            "0",
            "1",
            dpi=DPI,
            save=fpath,
            gene_sets={"0": mc.adata.var_names[:3], "1": [mc.adata.var_names[4]]},
            gene_sets_colors=["red", "black"],
        )

    @compare(kind="gpcca")
    def test_driver_corr_legend_loc(self, mc: GPCCA, fpath: str):
        mc.plot_lineage_drivers_correlation(
            "0",
            "1",
            dpi=DPI,
            save=fpath,
            gene_sets={"0": mc.adata.var_names[:3], "1": [mc.adata.var_names[4]]},
            legend_loc="lower center out",
        )

    @compare(kind="gpcca")
    def test_driver_corr_use_raw(self, mc: GPCCA, fpath: str):
        mc.compute_lineage_drivers(cluster_key="clusters", use_raw=True)
        mc.plot_lineage_drivers_correlation("0", "1", dpi=DPI, save=fpath, use_raw=True, color="1_qval")

    @compare(kind="gpcca")
    def test_driver_corr_cmap(self, mc: GPCCA, fpath: str):
        mc.plot_lineage_drivers_correlation("0", "1", dpi=DPI, save=fpath, color="1_qval", cmap="inferno")

    @compare(kind="gpcca")
    def test_driver_corr_fontsize(self, mc: GPCCA, fpath: str):
        mc.plot_lineage_drivers_correlation(
            "0",
            "1",
            dpi=DPI,
            save=fpath,
            gene_sets={"foo": mc.adata.var_names[4:6]},
            fontsize=20,
        )

    @compare(kind="gpcca")
    def test_driver_corr_adjust_text(self, mc: GPCCA, fpath: str):
        mc.plot_lineage_drivers_correlation(
            "0",
            "1",
            dpi=DPI,
            save=fpath,
            gene_sets={"bar": mc.adata.var_names[:3]},
            adjust_text=True,
        )

    @compare(kind="gpcca")
    def test_driver_corr_return_ax(self, mc: GPCCA, fpath: str):
        ax = mc.plot_lineage_drivers_correlation("2", "0", dpi=DPI, save=fpath, show=False)
        assert isinstance(ax, plt.Axes)


class TestLogOdds:
    @compare(tol=250)
    def test_log_odds(self, adata: AnnData, fpath: str):
        cr.pl.log_odds(
            adata,
            "0",
            "1",
            "age(days)",
            dpi=DPI,
            save=fpath,
            figsize=(4, 3),
            size=10,
            seed=42,
        )

    @compare(kind="bwd", tol=250)
    def test_log_odds_bwd(self, adata: AnnData, fpath: str):
        cr.pl.log_odds(
            adata,
            "0",
            "1",
            "age(days)",
            dpi=DPI,
            save=fpath,
            backward=True,
            figsize=(4, 3),
            size=10,
            seed=42,
        )

    @compare()
    def test_log_odds_rest(self, adata: AnnData, fpath: str):
        cr.pl.log_odds(
            adata,
            "2",
            None,
            "age(days)",
            dpi=DPI,
            save=fpath,
            figsize=(4, 3),
            size=10,
            seed=42,
        )

    @compare()
    def test_log_odds_continuous_keys(self, adata: AnnData, fpath: str):
        cr.pl.log_odds(
            adata,
            "0",
            "1",
            "age(days)",
            dpi=DPI,
            save=fpath,
            keys=adata.var_names[:3],
            figsize=(4, 3),
            size=4,
        )

    @compare()
    def test_log_odds_categorical_keys(self, adata: AnnData, fpath: str):
        cr.pl.log_odds(
            adata,
            "0",
            "1",
            "age(days)",
            dpi=DPI,
            save=fpath,
            keys=["clusters", "clusters_enlarged"],
            figsize=(4, 3),
            size=10,
            seed=42,
        )

    @compare()
    def test_log_odds_threshold(self, adata: AnnData, fpath: str):
        cr.pl.log_odds(
            adata,
            "0",
            "1",
            "age(days)",
            dpi=DPI,
            save=fpath,
            keys=adata.var_names[:3],
            threshold=0.5,
            figsize=(4, 3),
            size=10,
            seed=42,
        )

    @compare()
    def test_log_odds_multiple_threshold(self, adata: AnnData, fpath: str):
        cr.pl.log_odds(
            adata,
            "0",
            "1",
            "age(days)",
            dpi=DPI,
            save=fpath,
            keys=adata.var_names[:3],
            threshold=[0.7, 0.2, 0.3],
            figsize=(4, 3),
            size=10,
            seed=42,
        )

    @compare()
    def test_log_odds_threshold_color(self, adata: AnnData, fpath: str):
        cr.pl.log_odds(
            adata,
            "0",
            "1",
            "age(days)",
            dpi=DPI,
            save=fpath,
            keys=adata.var_names[:3],
            threshold=0.5,
            threshold_color="blue",
            figsize=(4, 3),
            size=10,
            seed=42,
        )

    @compare()
    def test_log_odds_layer(self, adata: AnnData, fpath: str):
        cr.pl.log_odds(
            adata,
            "0",
            "1",
            "age(days)",
            dpi=DPI,
            save=fpath,
            keys=adata.var_names[3:6],
            layer="Ms",
            figsize=(4, 3),
            size=10,
            seed=42,
        )

    @compare()
    def test_log_odds_use_raw(self, adata: AnnData, fpath: str):
        cr.pl.log_odds(
            adata,
            "0",
            "1",
            "age(days)",
            dpi=DPI,
            save=fpath,
            keys=adata.raw.var_names[3:6],
            use_raw=True,
            figsize=(4, 3),
            size=10,
            seed=42,
        )

    @compare()
    def test_log_odds_size(self, adata: AnnData, fpath: str):
        cr.pl.log_odds(
            adata,
            "0",
            "1",
            "age(days)",
            dpi=DPI,
            save=fpath,
            keys="clusters",
            size=20,
            figsize=(4, 3),
        )

    @compare()
    def test_log_odds_cmap(self, adata: AnnData, fpath: str):
        cr.pl.log_odds(
            adata,
            "0",
            "1",
            "age(days)",
            dpi=DPI,
            save=fpath,
            keys=adata.var_names[:2],
            size=10,
            cmap="inferno",
            figsize=(4, 3),
        )

    @compare()
    def test_log_odds_alpha(self, adata: AnnData, fpath: str):
        cr.pl.log_odds(
            adata,
            "0",
            "1",
            "age(days)",
            dpi=DPI,
            save=fpath,
            keys="clusters",
            alpha=0.5,
            figsize=(4, 3),
            size=10,
            seed=42,
        )

    @compare()
    def test_log_odds_ncols(self, adata: AnnData, fpath: str):
        cr.pl.log_odds(
            adata,
            "0",
            "1",
            "age(days)",
            dpi=DPI,
            save=fpath,
            keys=["clusters", adata.var_names[-1]],
            ncols=1,
            figsize=(3, 4),
            size=10,
            seed=42,
        )

    @compare()
    def test_log_odds_fontsize(self, adata: AnnData, fpath: str):
        cr.pl.log_odds(
            adata,
            "0",
            "1",
            "age(days)",
            dpi=DPI,
            save=fpath,
            keys="clusters",
            fontsize=25,
            figsize=(3, 4),
            size=10,
            seed=42,
        )

    @compare()
    def test_log_odds_xticks_steps_size(self, adata: AnnData, fpath: str):
        cr.pl.log_odds(
            adata,
            "0",
            "1",
            "age(days)",
            dpi=DPI,
            save=fpath,
            keys="clusters",
            xticks_step_size=None,
            figsize=(3, 4),
            size=10,
            seed=42,
        )

    @compare()
    def test_log_odds_legend_loc(self, adata: AnnData, fpath: str):
        cr.pl.log_odds(
            adata,
            "0",
            "1",
            "age(days)",
            dpi=DPI,
            save=fpath,
            keys=["clusters", adata.var_names[-1]],
            legend_loc="upper right out",
            figsize=(4, 3),
            size=10,
            seed=42,
        )

    @compare(tol=250)
    def test_log_odds_jitter(self, adata: AnnData, fpath: str):
        cr.pl.log_odds(
            adata,
            "0",
            "1",
            "age(days)",
            dpi=DPI,
            save=fpath,
            figsize=(4, 3),
            size=10,
            seed=42,
            jitter=1,
        )

    @compare()
    def test_log_odds_kwargs_return_ax(self, adata: AnnData, fpath: str):
        ax = cr.pl.log_odds(
            adata,
            "1",
            "2",
            "age(days)",
            keys="clusters",
            dpi=DPI,
            save=fpath,
            show=False,
            edgecolor="red",
            figsize=(4, 3),
            size=4,
        )
        assert isinstance(ax, plt.Axes)

    @compare()
    def test_log_odds_kwargs_return_axes(self, adata: AnnData, fpath: str):
        axes = cr.pl.log_odds(
            adata,
            "1",
            "2",
            "age(days)",
            keys=adata.var_names[:3],
            dpi=DPI,
            save=fpath,
            ncols=2,
            show=False,
            figsize=(4, 3),
            size=4,
        )
        assert isinstance(axes, np.ndarray)
        assert axes.shape == (3,)
        assert np.all([isinstance(ax, plt.Axes) for ax in axes])

    @compare()
    def test_log_odds_kwargs(self, adata: AnnData, fpath: str):
        cr.pl.log_odds(
            adata,
            "1",
            "2",
            "age(days)",
            dpi=DPI,
            save=fpath,
            linewidth=5,
            edgecolor="red",
            figsize=(4, 3),
            size=4,
        )


class TestMacrostateComposition:
    @compare(kind="gpcca")
    def test_msc_default(self, mc: GPCCA, fpath: str):
        mc.plot_macrostate_composition("clusters", dpi=DPI, save=fpath)

    @compare(kind="gpcca")
    def test_msc_width(self, mc: GPCCA, fpath: str):
        mc.plot_macrostate_composition("clusters", dpi=DPI, save=fpath, width=0.2)

    @compare(kind="gpcca")
    def test_msc_title(self, mc: GPCCA, fpath: str):
        mc.plot_macrostate_composition("clusters", dpi=DPI, save=fpath, title="foobar")

    @compare(kind="gpcca")
    def test_msc_labelrot(self, mc: GPCCA, fpath: str):
        mc.plot_macrostate_composition("clusters", dpi=DPI, save=fpath, labelrot=0)

    @compare(kind="gpcca")
    def test_msc_legend_loc(self, mc: GPCCA, fpath: str):
        mc.plot_macrostate_composition("clusters_enlarged", dpi=DPI, save=fpath, legend_loc="upper left out")


class TestProjectionEmbedding:
    @compare()
    def test_scvelo_connectivity_kernel_emb_stream(self, adata: AnnData, fpath: str):
        ck = ConnectivityKernel(adata)
        ck.compute_transition_matrix()
        ck.plot_projection(dpi=DPI, save=fpath)

    @compare()
    def test_scvelo_pseudotime_kernel_hard_threshold_emb_stream(self, adata: AnnData, fpath: str):
        ptk = PseudotimeKernel(adata, time_key="dpt_pseudotime")
        ptk.compute_transition_matrix(threshold_scheme="hard", frac_to_keep=0.3)
        ptk.plot_projection(dpi=DPI, save=fpath)

    @compare()
    def test_scvelo_pseudotime_kernel_soft_threshold_emb_stream(self, adata: AnnData, fpath: str):
        ptk = PseudotimeKernel(adata, time_key="dpt_pseudotime")
        ptk.compute_transition_matrix(threshold_scheme="soft", frac_to_keep=0.3)
        ptk.plot_projection(dpi=DPI, save=fpath)

    @compare()
    def test_scvelo_velocity_kernel_emb_stream(self, adata: AnnData, fpath: str):
        vk = VelocityKernel(adata)
        vk.compute_transition_matrix()
        vk.plot_projection(dpi=DPI, save=fpath)
