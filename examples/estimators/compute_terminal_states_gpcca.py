# -*- coding: utf-8 -*-
"""
Compute terminal states using GPCCA
-----------------------------------

This example shows how to compute and plot the terminal states using the :class:`cellrank.tl.estimators.GPCCA`.

This estimator makes use of Generalized Perron Cluster Cluster Analysis [GPCCA18]_ [Reuter19]_.
"""

import cellrank as cr

adata = cr.datasets.pancreas_preprocessed("../example.h5ad")
adata

# %%
# First, we prepare the kernel using the high-level pipeline and the :class:`cellrank.tl.estimators.GPCCA` estimator.
k = cr.tl.transition_matrix(
    adata, weight_connectivities=0.2, softmax_scale=4, show_progress_bar=False
)
g = cr.tl.estimators.GPCCA(k)

# %%
# Next, we need to compute the Schur vectors and the metastable states. We refer the reader to
# :ref:`sphx_glr_auto_examples_estimators_compute_metastable_states.py` where the method is explained more in detail.
g.compute_schur(n_components=4)
g.compute_metastable_states(cluster_key="clusters")

# %%
# We used the term final states to refer to the terminal states if we're considering the forward process, such as this
# case. For the backward process, this term refers to the initial states of the process.
#
# For :class:`cellrank.tl.estimators.GPCCA`, there are 3 methods for choosing the final states:
#
#     1. :meth:`cellrank.tl.estimators.GPCCA.set_final_states`
#     2. :meth:`cellrank.tl.estimators.GPCCA.set_final_states_from_metastable_states`
#     3. :meth:`cellrank.tl.estimators.GPCCA.compute_final_states`
#
# We will cover each of these methods below. In the last 2 cases, parameter ``n_cells`` controls how many cells to take
# from each final state we take as a categorical annotation.

# %%G
# Set final states
# ^^^^^^^^^^^^^^^^
# :meth:`cellrank.tl.estimators.GPCCA.set_final_states` simply sets the final states manually - this
# can be useful when the final states are known beforehand. In this case, we don't need to compute the metastable
# states.
#
# The states can be specified either as a categorical :class:`pandas.Series` where `NaN` values mark cells
# not belonging to any final state or a :class:`dict`, where keys correspond to the names of the final states,
# and the values to the sequence of cell names or their indices.
#
# Below we set the final state called `"Alpha"` as all the cells from the `"Alpha"`
# cluster under ``adata.obs["clusters"]``.
g.set_final_states({"Alpha": adata[adata.obs["clusters"] == "Alpha"].obs_names})

# %%
# Set final states from metastable states
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
# :meth:`cellrank.tl.estimators.GPCCA.set_final_states_from_metastable_states` sets the final states by subsetting
# the metastable states. Note that multiple states can also be combined into new, joint states, as shown below,
# where we combine `"Alpha"` and `"Beta"` states into a new one.
g.set_final_states_from_metastable_states(["Alpha, Beta", "Epsilon"])

# %%
# Compute final states
# ^^^^^^^^^^^^^^^^^^^^
# Lastly, :meth:`cellrank.tl.estimators.GPCCA.compute_final_states` which also makes use of the coarse-grained
# transition matrix :paramref:`cellrank.tl.estimators.GPCCA.coarse_T` of the metastable states or the `eigengap`
# statistic.
#
# In the example below, we use ``method='eigenap'`` which selects the number of states based on the `eigengap`.
# The final states are defined as the top most likely states from the diagonal of the coarse-grained transition matrix.
# To find out more, see :ref:`sphx_glr_auto_examples_estimators_compute_coarse_T.py`.
g.compute_final_states(method="eigengap")

# %%
# Now that the final states have been either set or computed, we can visualize them in an embedding.
# All of the options seen in :ref:`sphx_glr_auto_examples_estimators_compute_metastable_states.py` also apply here,
# like plotting in the same plot (parameter ``same_plot``) or plotting the discrete values (parameter
# ``discrete``).
g.plot_final_states(same_plot=False)

# %%
# We note that membership degree of metastable/terminal states should not be confused with the probability of
# traveling/developing towards these states. For that, we compute the absorption probabilities, see
# :ref:`sphx_glr_auto_examples_estimators_compute_abs_probs.py`. The assignment of cells to metastable states is
# a soft assignment that specifies the degree of membership of any particular cell to a given state.
