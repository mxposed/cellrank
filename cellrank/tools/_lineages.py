# -*- coding: utf-8 -*-
"""Lineages module."""

from typing import TypeVar, Optional

from cellrank import logging as logg
from cellrank.utils._docs import d
from cellrank.tools._utils import _info_if_obs_keys_categorical_present
from cellrank.utils._utils import _read_graph_data
from cellrank.tools.kernels import VelocityKernel
from cellrank.tools._constants import Direction, AbsProbKey, FinalStatesKey, _transition
from cellrank.tools.estimators import GPCCA
from cellrank.tools.estimators._base_estimator import BaseEstimator

AnnData = TypeVar("AnnData")

d.delete_kwargs("gpcca_fit")


@d.dedent
def lineages(
    adata: AnnData,
    estimator: type(BaseEstimator) = GPCCA,
    backward: bool = False,
    cluster_key: Optional[str] = None,
    copy: bool = False,
    return_estimator: bool = False,
    **kwargs,
) -> Optional[AnnData]:
    """
    Compute probabilistic lineage assignment using RNA velocity.

    For each cell `i` in {{1, ..., N}} and %(root_or_final)s state j in {{1, ..., M}}, the probability is computed
    that cell `i` is either going to %(final)s state `j` (`backward=False`) or is coming from %(root)s state `j`
    (`backward=True`). We provide two estimators for computing these probabilities:

    For the estimator :class:`cellrank.tl.GPCCA`, we perform Generalized Perron Cluster Cluster Analysis [GPCCA18]_.
    Cells are mapped to a simplex where each corner represents a %(root_or_final) state, and the position of a cell
    in the simplex determines its probability of going to a %(final)s states or coming from %(root)s states.

    For the estimator :class:`cellrank.tl.CFLARE`, we compute absorption probabilities towards the %(root_or_final)s
    states of the Markov chain.
    For related approaches in the single cell context that utilise absorption probabilities to map cells to lineages,
    see [Setty19]_ or [Weinreb18]_.

    Before running this function, compute %(root_or_final) states using :func:`cellrank.tl.root_states` or
    :func:`cellrank.tl.final_states`, respectively.

    Parameters
    ----------
    %(adata)s
    estimator
        Estimator to use to compute the lineage probabilities.
    %(backward)s
    %(gpcca_fit.parameters)s
    copy
        Whether to update the existing AnnData object or to return a copy.
    return_estimator
        Whether to return the estimator. Only available when :paramref:`copy=False`.
    **kwargs
        Keyword arguments for :meth:`cellrank.tl.estimators.BaseEstimator.fit`.

    Returns
    -------
    :class:`anndata.AnnData`, :class:`cellrank.tools.estimators.BaseEstimator` or :class:`NoneType`
        Depending on :paramref:`copy`, either updates the existing :paramref:`adata` object
        or returns a copy or returns the estimator.
    """

    if not isinstance(estimator, type):
        raise TypeError(
            f"Expected estimator to be a class, found `{type(estimator).__name__!r}`."
        )

    if not issubclass(estimator, BaseEstimator):
        raise TypeError(
            f"Expected estimator to be a subclass of `BaseEstimator`, found `{type(estimator).__name__!r}`."
        )

    # Set the keys and print info
    adata = adata.copy() if copy else adata

    if backward:
        direction = Direction.BACKWARD
        lin_key = AbsProbKey.BACKWARD
        rc_key = FinalStatesKey.BACKWARD
    else:
        direction = Direction.FORWARD
        lin_key = AbsProbKey.FORWARD
        rc_key = FinalStatesKey.FORWARD

    transition_key = _transition(direction)
    vk = VelocityKernel(adata, backward=backward)

    try:
        vk._transition_matrix = _read_graph_data(adata, transition_key)
    except KeyError as e:
        raise KeyError(
            f"Compute the states first as `cellrank.tl.find_{'root' if backward else 'final'}`."
        ) from e

    start = logg.info(f"Computing lineage probabilities towards `{rc_key}`")
    mc = estimator(vk, read_from_adata=False)

    if cluster_key is None:
        _info_if_obs_keys_categorical_present(
            adata,
            keys=["louvain", "clusters"],
            msg_fmt="Found categorical observation in `adata.obs[{!r}]`. "
            "Consider specifying it as `cluster_key=...`.",
        )
    # compute the absorption probabilities
    mc.fit(cluster_key=cluster_key, **kwargs)

    logg.info(f"Adding lineages to `adata.obsm[{lin_key!r}]`\n    Finish", time=start)

    return adata if copy else mc if return_estimator else None
