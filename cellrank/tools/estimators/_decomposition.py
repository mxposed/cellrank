# -*- coding: utf-8 -*-
"""Matrix decomposition module."""
from abc import ABC, abstractmethod
from typing import Any, Tuple, Union, Mapping, Optional
from pathlib import Path

import numpy as np
from scipy.sparse.linalg import eigs

import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable

from cellrank import logging as logg
from cellrank.utils._docs import inject_docs
from cellrank.tools._utils import save_fig, _eigengap
from cellrank.tools.estimators._utils import Metadata, _delegate
from cellrank.tools.estimators._property import Property, KernelHolder, VectorPlottable
from cellrank.tools.estimators._constants import A, F, P
from cellrank._vendor.msmtools.analysis.dense.gpcca import GPCCA as _GPCCA

EPS = np.finfo(np.float64).eps


class Decomposable(KernelHolder, Property):
    """Abstract base class handling decomposition of transition matrix."""

    @abstractmethod
    def _compute(self, *args, **kwargs):
        pass


class EigWritable(Decomposable, ABC):
    """Helper class exposes writing the eigendecomposition to :class:`anndata.AnnData` object."""

    def _write_eig_to_adata(self, eig: Mapping[str, Any]):
        setattr(self, A.EIG.s, eig)
        self.adata.uns[f"eig_{self._direction}"] = eig

        logg.debug(f"Adding `.{P.EIG}`" f"       `adata.uns['eig_{self._direction}']`")


class Eigen(VectorPlottable, EigWritable):
    """Class computing the eigendecomposition."""

    __prop_metadata__ = [Metadata(attr=A.EIG, prop=P.EIG, dtype=Mapping[str, Any])]

    @inject_docs(prop=P.EIG)  # TODO: docrep
    def _compute(
        self,
        k: int = 20,
        which: str = "LR",
        alpha: float = 1,
        only_evals: bool = False,
        ncv: Optional[int] = None,
    ) -> None:
        """
        Compute eigendecomposition of transition matrix.

        Uses a sparse implementation, if possible, and only computes the top :math:`k` eigenvectors
        to speed up the computation. Computes both left and right eigenvectors.

        Params
        ------
        k
            Number of eigenvalues/vectors to compute.
        which
            Eigenvalues are in general complex. `'LR'` - largest real part, `'LM'` - largest magnitude.
        alpha
            Used to compute the `eigengap`. :paramref:`alpha` is the weight given
            to the deviation of an eigenvalue from one.
        only_evals
            Return only eigenvalues.
        ncv
            Number of Lanczos vectors generated.

        Returns
        -------
        None
            Nothing, but updates the following field:

                - :paramref:`{prop}`
        """

        def get_top_k_evals():
            return D[np.flip(np.argsort(D.real))][:k]

        logg.info("Computing eigendecomposition of the transition matrix")

        if self.issparse:
            logg.debug(f"Computing top `{k}` eigenvalues for sparse matrix")
            D, V_l = eigs(self.transition_matrix.T, k=k, which=which, ncv=ncv)
            if only_evals:
                self._write_eig_to_adata(
                    {
                        "D": get_top_k_evals(),
                        "eigengap": _eigengap(get_top_k_evals().real, alpha),
                        "params": {"which": which, "k": k, "alpha": alpha},
                    }
                )
                return
            _, V_r = eigs(self.transition_matrix, k=k, which=which, ncv=ncv)
        else:
            logg.warning(
                "This transition matrix is not sparse, computing full eigendecomposition"
            )
            D, V_l = np.linalg.eig(self.transition_matrix.T)
            if only_evals:
                self._write_eig_to_adata(
                    {
                        "D": get_top_k_evals(),
                        "eigengap": _eigengap(D.real, alpha),
                        "params": {"which": which, "k": k, "alpha": alpha},
                    }
                )
                return
            _, V_r = np.linalg.eig(self.transition_matrix)

        # Sort the eigenvalues and eigenvectors and take the real part
        logg.debug("Sorting eigenvalues by their real part")
        p = np.flip(np.argsort(D.real))
        D, V_l, V_r = D[p], V_l[:, p], V_r[:, p]
        e_gap = _eigengap(D.real, alpha)

        pi = np.abs(V_l[:, 0].real)
        pi /= np.sum(pi)

        self._write_eig_to_adata(
            {
                "D": D,
                "stationary_dist": pi,
                "V_l": V_l,
                "V_r": V_r,
                "eigengap": e_gap,
                "params": {"which": which, "k": k, "alpha": alpha},
            }
        )

    # TODO: use docrep
    def plot_eigendecomposition(
        self, left: bool = False, use: Optional[int] = None, *args, **kwargs
    ):
        """
        Plot the eigenvectors in an embedding.

        Parameters
        ----------
        left
        use

        Returns
        -------
        None
            Nothing, just plots the eigenvectors.
        """
        eig = getattr(self, P.EIG.s)

        if eig is None:
            self._plot_vectors(None, P.EIG.s)

        side = "left" if left else "right"
        D, V = (
            eig["D"],
            eig.get(f"V_{side[0]}", None),
        )
        if V is None:
            raise RuntimeError(
                f"Compute eigendecomposition first as "
                f"`.{F.COMPUTE.fmt(P.EIG)}(..., only_evals=False)`."
            )

        # if irreducible, first rigth e-vec should be const.
        if side == "right":
            # quick check for irreducibility:
            if np.sum(np.isclose(D, 1, rtol=1e2 * EPS, atol=1e2 * EPS)) == 1:
                V[:, 0] = 1.0

        if use is None:
            use = eig["eigengap"] + 1  # add one because first e-vec has index 0

        self._plot_vectors(
            V, P.EIG.s, *args, use=use, D=D, **kwargs,
        )

    def plot_spectrum(
        self,
        real_only: bool = False,
        dpi: int = 100,
        figsize: Optional[Tuple[float, float]] = (5, 5),
        legend_loc: Optional[str] = None,
        title: Optional[str] = None,
        save: Optional[Union[str, Path]] = None,
    ) -> None:
        """
        Plot the top eigenvalues in real or complex plane.

        .. image:: https://raw.githubusercontent.com/theislab/cellrank/master/resources/images/real_spectrum.png
           :alt: image of real spectrum
           :width: 400px
           :align: center

        Params
        ------
        real_only
            Whether to plot only the real part of the spectrum.
        dpi
            Dots per inch.
        figsize
            Size of the figure.
        legend_loc
            Location parameter for the legend.
        title
            Title of the figure.
        save
            Filename where to save the plots. If `None`, just shows the plot.

        Returns
        -------
        None
            Nothing, just plots the spectrum in real or complex plane.
        """

        eig = getattr(self, P.EIG.s)
        if eig is None:
            raise RuntimeError(
                f"Compute `.{P.EIG}` first as `.{F.COMPUTE.fmt(P.EIG)}()`."
            )

        if real_only:
            fig = self._plot_real_spectrum(
                dpi=dpi, figsize=figsize, legend_loc=legend_loc, title=title
            )
        else:
            fig = self._plot_complex_spectrum(
                dpi=dpi, figsize=figsize, legend_loc=legend_loc, title=title
            )

        if save:
            save_fig(fig, save)

        fig.show()

    def _plot_complex_spectrum(
        self,
        dpi: int = 100,
        figsize: Optional[Tuple[float, float]] = (None, None),
        legend_loc: Optional[str] = None,
        title: Optional[str] = None,
    ):
        # define a function to make the data limits rectangular
        def adapt_range(min_, max_, range_):
            return (
                min_ + (max_ - min_) / 2 - range_ / 2,
                min_ + (max_ - min_) / 2 + range_ / 2,
            )

        eig = getattr(self, P.EIG.s)
        D, params = eig["D"], eig["params"]

        # create fiture and axes
        fig, ax = plt.subplots(nrows=1, ncols=1, dpi=dpi, figsize=figsize)

        # get the original data ranges
        lam_x, lam_y = D.real, D.imag
        x_min, x_max = np.min(lam_x), np.max(lam_x)
        y_min, y_max = np.min(lam_y), np.max(lam_y)
        x_range, y_range = x_max - x_min, y_max - y_min
        final_range = np.max([x_range, y_range]) + 0.05

        x_min_, x_max_ = adapt_range(x_min, x_max, final_range)
        y_min_, y_max_ = adapt_range(y_min, y_max, final_range)

        # plot the data and the unit circle
        ax.scatter(D.real, D.imag, marker=".", label="eigenvalue")
        t = np.linspace(0, 2 * np.pi, 500)
        x_circle, y_circle = np.sin(t), np.cos(t)
        ax.plot(x_circle, y_circle, "k-", label="unit circle")

        # set labels, ranges and legend
        ax.set_xlabel(r"Re($\lambda$)")
        ax.set_xlim(x_min_, x_max_)

        ax.set_ylabel(r"Im($\lambda$)")
        ax.set_ylim(y_min_, y_max_)

        key = "real part" if params["which"] == "LR" else "magnitude"
        if title is None:
            title = f"top {params['k']} eigenvalues according to their {key}"
        ax.set_title(title)

        ax.legend(loc=legend_loc)

        return fig

    def _plot_real_spectrum(
        self,
        dpi: int = 100,
        figsize: Optional[Tuple[float, float]] = None,
        legend_loc: Optional[str] = None,
        title: Optional[str] = None,
    ):
        eig = getattr(self, P.EIG.s)
        D, params = eig["D"], eig["params"]

        D_real, D_imag = D.real, D.imag
        ixs = np.arange(len(D))
        mask = D_imag == 0  # TODO: @Marius: isclose?

        # plot the top eigenvalues
        fig, ax = plt.subplots(nrows=1, ncols=1, dpi=dpi, figsize=figsize)
        ax.scatter(ixs[mask], D_real[mask], marker="o", label="real eigenvalue")
        ax.scatter(ixs[~mask], D_real[~mask], marker="o", label="complex eigenvalue")

        # add dashed line for the eigengap, ticks, labels, title and legend
        ax.axvline(eig["eigengap"], label="eigengap", ls="--")

        ax.set_xlabel("index")
        ax.set_xticks(range(len(D)))

        ax.set_ylabel(r"Re($\lambda_i$)")

        key = "real part" if params["which"] == "LR" else "magnitude"
        if title is None:
            title = (
                f"real part of top {params['k']} eigenvalues according to their {key}"
            )
        ax.set_title(title)

        ax.legend(loc=legend_loc)

        return fig


class Schur(VectorPlottable, EigWritable):
    """Class computing the Schur decomposition."""

    __prop_metadata__ = [
        Metadata(attr=A.SCHUR, prop=P.SCHUR, dtype=np.ndarray),
        Metadata(attr=A.SCHUR_MAT, prop=P.SCHUR_MAT, dtype=np.ndarray),
        Metadata(attr=A.EIG, prop=P.EIG, dtype=Mapping[str, Any]),
        Metadata(attr="_gpcca", prop=P.NO_PROPERTY),
    ]

    # TODO: docrep
    @inject_docs(schur_vectors=P.SCHUR, schur_matrix=P.SCHUR_MAT, eigendec=P.EIG)
    def _compute(
        self,
        n_components: int = 10,
        initial_distribution: Optional[np.ndarray] = None,
        method: str = "krylov",
        which: str = "LM",
        alpha: float = 1,
    ):
        """
        Compute the Schur decomposition.

        Params
        ------
        n_components
            Number of vectors to compute.
        initial_distribution
            Input probability distribution over all cells. If `None`, uniform is chosen.
        method
            Method for calculating the Schur vectors. Valid options are: `'krylov'` or `'brandts'`.

            For benefits of each method, see :class:`msmtools.analysis.dense.gpcca.GPCCA`. The former is
            an iterative procedure that computes a partial, sorted Schur decomposition for large, sparse
            matrices whereas the latter computes a full sorted Schur decomposition of a dense matrix.
        which
            Eigenvalues are in general complex. `'LR'` - largest real part, `'LM'` - largest magnitude.
        alpha
            Used to compute the `eigengap`. :paramref:`alpha` is the weight given
            to the deviation of an eigenvalue from one.

        Returns
        -------
        None
            Nothing, but updates the following fields:

                - :paramref:`{schur_vectors}`
                - :paramref:`{schur_matrix}`
                - :paramref:`{eigendec}`
        """

        if n_components < 2:
            raise ValueError(
                f"Number of components must be `>=2`, found `{n_components}`."
            )

        self._gpcca = _GPCCA(
            self.transition_matrix, eta=initial_distribution, z=which, method=method
        )

        try:
            self._gpcca._do_schur_helper(n_components)
        except ValueError:
            logg.warning(
                f"Using `{n_components}` components would split a block of complex conjugates. "
                f"Increasing `n_components` to `{n_components + 1}`"
            )
            self._gpcca._do_schur_helper(n_components + 1)

        # make it available for plotting
        setattr(self, A.SCHUR.s, self._gpcca.X)
        setattr(self, A.SCHUR_MAT.s, self._gpcca.R)

        self._write_eig_to_adata(
            {
                "D": self._gpcca.eigenvalues,
                "eigengap": _eigengap(self._gpcca.eigenvalues, alpha),
                "params": {
                    "which": which,
                    "k": len(self._gpcca.eigenvalues),
                    "alpha": alpha,
                },
            }
        )

    plot_schur = _delegate(prop_name=P.SCHUR.s)(VectorPlottable._plot_vectors)

    def plot_schur_matrix(
        self,
        title: Optional[str] = "schur matrix",
        cmap: str = "viridis",
        figsize: Optional[Tuple[float, float]] = None,
        dpi: Optional[float] = 80,
        save: Optional[Union[str, Path]] = None,
        **kwargs,
    ):
        """
        Plot the Schur matrix.

        .. image:: https://raw.githubusercontent.com/theislab/cellrank/master/resources/images/schur_matrix.png
           :alt: image of schur matrix
           :width: 400px
           :align: center

        Params
        ------
        title
            Title of the figure.
        cmap
            Colormap to use.
        figsize
            Size of the figure.
        dpi
            Dots per inch.
        save
            Filename where to save the plots. If `None`, just shows the plot.

        Returns
        -------
        None
            Nothing, just plots the Schur matrix.
        """

        from seaborn import heatmap

        schur_matrix = getattr(self, P.SCHUR_MAT.s)

        if schur_matrix is None:
            raise RuntimeError(
                f"Compute Schur matrix first as `.{F.COMPUTE.fmt(P.SCHUR)}()`."
            )

        fig, ax = plt.subplots(
            figsize=schur_matrix.shape if figsize is None else figsize, dpi=dpi
        )

        divider = make_axes_locatable(ax)  # square=True make the colorbar a bit bigger
        cbar_ax = divider.append_axes("right", size="2.5%", pad=0.05)

        mask = np.zeros_like(schur_matrix, dtype=np.bool)
        mask[np.tril_indices_from(mask, k=-1)] = True
        mask[~np.isclose(schur_matrix, 0.0)] = False

        vmin, vmax = (
            np.min(schur_matrix[~mask]),
            np.max(schur_matrix[~mask]),
        )

        kwargs["fmt"] = kwargs.get("fmt", "0.2f")
        heatmap(
            schur_matrix,
            cmap=cmap,
            square=True,
            annot=True,
            vmin=vmin,
            vmax=vmax,
            cbar_ax=cbar_ax,
            mask=mask,
            xticklabels=[],
            yticklabels=[],
            ax=ax,
            **kwargs,
        )

        ax.set_title(title)

        if save is not None:
            save_fig(fig, path=save)
