# -*- coding: utf-8 -*-
"""Base properties used within the estimators."""
import sys
from abc import ABC, ABCMeta, abstractmethod
from typing import Any, Dict, List, Tuple, Union, Iterable, Optional
from inspect import isabstract
from functools import singledispatchmethod

import numpy as np
import pandas as pd
from scipy.sparse import issparse, spmatrix
from pandas.api.types import is_categorical_dtype

import matplotlib as mpl
from matplotlib import cm

import scvelo as scv
from anndata import AnnData

import cellrank.logging as logg
from cellrank.tools import Lineage
from cellrank.tools._utils import _make_cat, partition, _complex_warning
from cellrank.tools._constants import Prefix, Direction, DirectionPlot
from cellrank.tools.kernels._kernel import KernelExpression, PrecomputedKernel
from cellrank.tools.estimators._utils import (
    Metadata,
    RandomKeys,
    _create_property,
    _delegate_method_dispatch,
)
from cellrank.tools.estimators._constants import META_KEY, A, F, P


# has to be in the same module
def is_abstract(classname: str) -> bool:  # TODO: determine the necessity of this
    """
    Check whether class with a given name inside this module is abstract.

    Params
    ------
    classname
        Name of the class.

    Returns
    -------
    bool
        `True` if the class is abstract, otherwise `False`.

    """

    cls = getattr(sys.modules[__name__], classname, None)
    return cls is not None and isabstract(cls)


class PropertyMeta(ABCMeta, type):
    """Metaclass for all the properties."""

    @staticmethod
    def update_attributes(md: Metadata, attributedict: Dict[str, Any]) -> Optional[str]:
        """
        Update :paramref:`attributedict` with new attribute and property.

        Params
        ------
        md
            Metadata object, containing attribute name, property names, etc.
        attributedict
            Dictionary with attributes.

        Returns
        -------
        Old property name, if found, otherwise a newly constructed one, or `None` if no property is desired.
        """

        # TODO: determine whether supporting strings is a good idea
        if not isinstance(md, Metadata):
            raise TypeError(f"Expected `Metadata` object, found `{type(md).__name__}`.")

        if not isinstance(md.attr, (str, A)):
            raise TypeError(
                f"Attribute `{md.attr}` must be of type `A` or `str`, found `{type(md.attr).__name__!r}`."
            )
        if not str(md.attr).startswith("_"):
            raise ValueError(f"Attribute `{md.attr!r}` must start with `'_'`.")

        attributedict[str(md.attr)] = md.default

        if md.prop == P.NO_PROPERTY:
            return

        if not isinstance(md.prop, (str, P)):
            raise TypeError(
                f"Property must be of type `P` or `str`, found `{type(md.attr).__name__!r}`."
            )

        prop_name = str(md.attr).lstrip("_") if md.prop == P.EMPTY else str(md.prop)

        if not len(prop_name):
            raise ValueError(f"Property name for attribute `{md.attr}` is empty.")
        if prop_name.startswith("_"):
            raise ValueError(
                f"Property musn't start with an underscore: `{prop_name!r}`."
            )

        attributedict[prop_name] = _create_property(
            str(md.attr), doc=md.doc, return_type=md.dtype
        )

        return prop_name

    def __new__(cls, clsname, superclasses, attributedict):
        """
        Create a new instance.

        Params
        ------
        clsname
            Name of class to be constructed.
        superclasses
            List of superclasses.
        attributedict
            Dictionary of attributes.
        """

        compute_md, metadata = attributedict.pop(META_KEY, None), []

        if compute_md is None:
            return super().__new__(cls, clsname, superclasses, attributedict)

        if isinstance(compute_md, str):
            compute_md = Metadata(attr=compute_md)
        elif not isinstance(compute_md, (tuple, list)):
            raise TypeError(
                f"Expected property metadata to be `list` or `tuple`,"
                f"found `{type(compute_md).__name__!r}`."
            )
        elif len(compute_md) == 0:
            raise ValueError("No metadata found.")
        else:
            compute_md, *metadata = [
                Metadata(attr=md) if isinstance(md, str) else md for md in compute_md
            ]

        prop_name = PropertyMeta.update_attributes(compute_md, attributedict)
        ignore_first = compute_md.compute_fmt == F.NO_FUNC
        plot_name = str(compute_md.plot_fmt).format(prop_name)

        if not ignore_first:
            if "_compute" in attributedict:
                attributedict[
                    str(compute_md.compute_fmt).format(prop_name)
                ] = attributedict["_compute"]

            if (
                VectorPlottable in superclasses
                and plot_name not in attributedict
                and not is_abstract(clsname)
            ):
                raise TypeError(
                    f"Method `{plot_name}` is not implemented for class `{clsname}`."
                )

        for md in metadata:
            PropertyMeta.update_attributes(md, attributedict)

        res = super().__new__(cls, clsname, superclasses, attributedict)

        if not ignore_first and Plottable in res.mro():
            # _this works for singledispatchmethod
            # unfortunately, `_plot` is not always in attributedict, so we can't just check for it
            # and res._plot is just a regular function
            # if this gets buggy in the future, consider switching from singlemethoddispatch
            setattr(
                res, plot_name, _delegate_method_dispatch(res._plot, "_plot", prop_name)
            )

        return res


class Property(ABC, metaclass=PropertyMeta):
    """Base class for all the properties."""

    pass


class KernelHolder(ABC):
    """Base class which holds a :class:`cellrank.tool.kernels._kernel.KernelExpression`."""

    def __init__(
        self,
        obj: Union[AnnData, np.ndarray, spmatrix, KernelExpression],
        key_added: Optional[str] = None,
        obsp_key: Optional[str] = None,
    ):
        if isinstance(obj, KernelExpression):
            self._kernel = obj
        elif isinstance(obj, (np.ndarray, spmatrix)):
            self._kernel = PrecomputedKernel(obj)
        elif isinstance(obj, AnnData):
            if obsp_key is None:
                raise ValueError()
            elif obsp_key not in obj.obsp.keys():
                raise KeyError()
            self._kernel = PrecomputedKernel(obj.obsp[obsp_key])
        else:
            raise TypeError()

        if self.kernel.transition_matrix is None:
            logg.debug("Computing transition matrix using default parameters")
            self.kernel.compute_transition_matrix()

        self.kernel.write_to_adata(key_added=key_added)

    def _direction(self):
        return Direction.BACKWARD if self.kernel.backward else Direction.FORWARD

    @property
    def transition_matrix(self) -> Union[np.ndarray, spmatrix]:
        """Transition matrix."""
        return self.kernel.transition_matrix

    @property
    def issparse(self) -> bool:
        """Whether the transition matrix is sparse or not."""
        return issparse(self.transition_matrix)

    @property
    def kernel(self) -> KernelExpression:
        """Underlying kernel."""
        return self._kernel

    @property
    def adata(self) -> AnnData:
        """Annotated data object."""
        return self.kernel.adata

    def __len__(self):
        return self.kernel.transition_matrix.shape[0]

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}[n={len(self)}, kernel={repr(self.kernel)}]"

    def __str__(self) -> str:
        return f"{self.__class__.__name__}[n={len(self)}, kernel={str(self.kernel)}]"


class VectorPlottable(KernelHolder, Property):
    """
    Injector class which plots vectors.

    To be used in conjunction with:

        - :class:`cellrank.tool.estimators._decomposition.Eig`.
        - :class:`cellrank.tool.estimators._decomposition.Schur`.
    """

    def _plot_vectors(
        self,
        vectors: Optional[np.ndarray],
        prop: str,
        use: Optional[Union[int, Tuple[int], List[int]]] = None,
        abs_value: bool = False,
        cluster_key: Optional[str] = None,
        **kwargs,
    ):
        # TODO: SSoT
        if prop not in (P.EIG.v, P.SCHUR.v):
            raise ValueError(
                f"Invalid kind `{prop!r}`. Valid options are `{P.EIG!r}`, `{P.SCHUR!r}``."
            )
        if vectors is None:
            raise RuntimeError(f"Compute `.{prop}` first as `{F.COMPUTE.fmt(prop)}`.")

        if prop == P.SCHUR.s:
            is_schur = True
            vec = "Schur "
        else:
            is_schur = False
            vec = "eigen"

        # check whether dimensions are consistent
        if self.adata.n_obs != vectors.shape[0]:
            raise ValueError(
                f"Number of cells ({self.adata.n_obs}) is inconsistent with the 1."
                f"dimensions of vectors ({vectors.shape[0]})."
            )

        if use is None:
            use = list(range(is_schur, vectors.shape[1] + is_schur - 1))
        elif isinstance(use, int):
            use = list(range(is_schur, use + is_schur))
        elif not isinstance(use, (tuple, list, range)):
            raise TypeError(
                f"Argument `use` must be either `int`, `tuple`, `list` or `range`,"
                f"found `{type(use).__name__}`."
            )
        else:
            if not all(map(lambda u: isinstance(u, int), use)):
                raise TypeError("Not all values in `use` argument are integers.")
        use = list(use)
        if not use:
            raise ValueError("Nothing to plot.")

        muse = max(use)
        if muse >= vectors.shape[1]:
            raise ValueError(
                f"Maximum specified {vec}vector ({muse}) is larger "
                f"than the number of computed {vec}vectors ({vectors.shape[1]})."
            )
        print(use)
        V_ = vectors[:, use]

        if is_schur:
            title = [f"{vec}vector {i}" for i in use]
        else:
            D = kwargs.pop("D")
            V_ = _complex_warning(V_, use, use_imag=kwargs.pop("use_imag", False))
            title = [fr"$\lambda_{i}$={d:.02f}" for i, d in zip(use, D[use])]

        if abs_value:
            V_ = np.abs(V_)

        color = list(V_.T)
        if cluster_key is not None:
            color = [cluster_key] + color

        logg.debug(f"Showing `{use}` {vec}vectors")

        scv.pl.scatter(self.adata, color=color, title=title, **kwargs)


class Plottable(KernelHolder, Property):
    """
    Injector class which plots metastable or final states or absorption probabilities.

    To be used in conjunction with:

        - :class:`cellrank.tool.estimators._property.MetaStates`.
        - :class:`cellrank.tool.estimators._property.FinStates`.
        - :class:`cellrank.tool.estimators._property.AbsProbs`.
    """

    def _plot_discrete(
        self,
        data: pd.Series,
        prop: str,
        same_plot: bool = True,
        title: Optional[Union[str, List[str]]] = None,
        **kwargs,
    ):
        """
        Plot the states for each uncovered lineage.

        Params
        ------
        same_plot
            Whether to plot the lineages on the same plot or separately.
        title
            The title of the plot.
        kwargs
            Keyword arguments for :func:`scvelo.pl.scatter`.

        Returns
        -------
        None
            Nothing, just plots the categorical states.
        """

        if data is None:
            raise RuntimeError(
                f"Compute `.{prop}` first as `.{F.COMPUTE.fmt(prop)}()`."
            )
        if not is_categorical_dtype(data):
            raise TypeError(
                f"Expected property `.{prop}` to be categorical, found `{type(data).__name__!r}`."
            )
        if prop in (P.ABS_RPOBS.s, P.FIN.s):
            colors = getattr(self, A.FIN_COLORS.v, None)
        elif prop == P.META.v:
            colors = getattr(self, A.META_COLORS.v, None)
        else:
            raise NotImplementedError(
                f"Unable to determine plotting conditions for property `.{prop}`."
            )

        with RandomKeys(
            self.adata, None if same_plot else len(data.cat.categories), where="obs"
        ) as keys:
            if same_plot:
                key = keys[0]
                self.adata.obs[key] = data
                self.adata.uns[f"{key}_colors"] = colors

                if title is None:
                    title = (
                        f"{prop.replace('_', ' ')} "
                        f"({Direction.BACKWARD if self.kernel.backward else Direction.FORWARD})"
                    )
                scv.pl.scatter(self.adata, title=title, color=key, **kwargs)
            else:
                for i, (key, cat) in enumerate(zip(keys, data.cat.categories)):
                    d = data.copy()
                    d[data != cat] = None
                    d.cat.set_categories([cat], inplace=True)

                    self.adata.obs[key] = d
                    self.adata.uns[f"{key}_colors"] = colors[i]

                scv.pl.scatter(
                    self.adata,
                    color=keys,
                    title=list(data.cat.categories) if title is None else title,
                    **kwargs,
                )

    def _plot_continuous(
        self,
        probs: Optional[Lineage],
        prop: str,
        diff_potential: Optional[pd.Series] = None,
        lineages: Optional[Union[str, Iterable[str]]] = None,
        cluster_key: Optional[str] = None,
        mode: str = "embedding",
        time_key: str = "latent_time",
        show_dp: bool = True,
        title: Optional[str] = None,
        same_plot: bool = False,
        color_map: Union[str, mpl.colors.ListedColormap] = cm.viridis,
        **kwargs,
    ) -> None:
        if probs is None:
            raise RuntimeError(
                f"Compute `.{prop}` first as `.{F.COMPUTE.fmt(prop)}()`."
            )

        if isinstance(lineages, str):
            lineages = [lineages]

        if lineages is None:
            lineages = probs.names
            A = probs
        else:
            A = probs[lineages]

        prefix = Prefix.BACKWARD if self.kernel.backward else Prefix.FORWARD
        diff_potential = (
            [diff_potential]
            if show_dp
            and not same_plot
            and diff_potential is not None
            and probs.shape[1] > 1
            else []
        )

        A = A.copy()  # the below code modifies stuff inplace
        X = A.X  # list(A.T) behaves differently, because it's Lineage

        for col in X.T:
            mask = col != 1
            # change the maximum value - the 1 is artificial and obscures the color scaling
            if np.sum(mask) > 0:
                max_not_one = np.max(col[mask])
                col[~mask] = max_not_one

        if mode == "time":
            if time_key not in self.adata.obs.keys():
                raise KeyError(f"Time key `{time_key!r}` not found in `adata.obs`.")
            time = self.adata.obs[time_key]
            cluster_key = None

        color = list(X.T) + diff_potential
        if title is None:
            if same_plot:
                title = (
                    f"{prop.replace('_', ' ')} "
                    f"({DirectionPlot.BACKARD if self.kernel.backward else Direction.FORWARD})"
                )
            else:
                title = [f"{prefix} {lin}" for lin in lineages] + (
                    ["differentiation potential"] if diff_potential else []
                )
        elif isinstance(title, str):
            title = [title]

        if cluster_key is not None:
            color = [cluster_key] + color
            title = [cluster_key] + title

        if mode == "embedding":
            if same_plot:
                scv.pl.scatter(
                    self.adata,
                    title=title,
                    color_gradients=A,
                    color_map=color_map,
                    **kwargs,
                )
            else:
                scv.pl.scatter(
                    self.adata, color=color, title=title, color_map=color_map, **kwargs
                )
        elif mode == "time":
            scv.pl.scatter(
                self.adata,
                x=time,
                color_map=color_map,
                y=color,
                title=title,
                xlabel=[time_key] * len(title),
                ylabel=["probability" * len(title)],
                **kwargs,
            )
        else:
            raise ValueError(
                f"Invalid mode `{mode!r}`. Valid options are: `'embedding'` and `'time'`."
            )

    # TODO: docrep - this is where the wrapper gets its doc, but document `plot_discrete` and `plot_continous` instead
    @singledispatchmethod
    def _plot(self, data, prop: str, discrete: bool = False, *args, **kwargs):
        raise RuntimeError(f"Compute `.{prop}` first as `.{F.COMPUTE.fmt(prop)}()`.")

    @_plot.register(pd.Series)
    def _(self, data: pd.Series, prop: str, discrete: bool = False, *args, **kwargs):
        if discrete:
            self._plot_discrete(data, prop, *args, **kwargs)
        elif prop == P.META.v:  # GPCCA
            prop = P.META_PROBS.v
            self._plot_continuous(
                getattr(self, prop, None), prop, None, *args, **kwargs
            )
        elif prop == P.FIN.v:
            probs = getattr(self, A.FIN_ABS_PROBS.s, None)
            if isinstance(probs, Lineage):
                # TODO: logg
                self._plot_continuous(probs, prop, *args, **kwargs)
            else:
                logg.warning(
                    f"Unable to plot continuous observations for `{prop!r}`, plotting in discrete mode"
                )
                self._plot_discrete(data, prop, *args, **kwargs)
        else:
            raise NotImplementedError(
                f"Unable to plot property `.{prop}` in discrete mode."
            )

    @_plot.register(Lineage)
    def _(self, data: Lineage, prop: str, discrete: bool = False, *args, **kwargs):
        if not discrete:
            diff_potential = getattr(self, P.DIFF_POT.v)
            self._plot_continuous(data, prop, diff_potential, *args, **kwargs)
        elif prop == P.ABS_RPOBS.v:
            prop = P.FIN.v
            self._plot_discrete(getattr(self, prop, None), prop, *args, **kwargs)
        else:
            raise NotImplementedError(
                f"Unable to plot property `.{prop}` in continuous mode."
            )


class MetaStates(Plottable):
    """Class dealing with metastable states."""

    __prop_metadata__ = [
        Metadata(attr=A.META, prop=P.META, dtype=pd.Series),
        Metadata(attr=A.META_PROBS, prop=P.META_PROBS, dtype=Lineage,),
        Metadata(attr=A.META_COLORS, prop=P.NO_PROPERTY, dtype=np.ndarray),
    ]

    @abstractmethod
    def compute_metastable_states(self, *args, **kwargs) -> None:  # noqa
        pass


class FinalStates(Plottable):
    """Class dealing with final states."""

    __prop_metadata__ = [
        Metadata(attr=A.FIN, prop=P.FIN, dtype=pd.Series),
        Metadata(attr=A.FIN_PROBS, prop=P.FIN_PROBS, dtype=pd.Series,),
        Metadata(attr=A.FIN_COLORS, prop=P.NO_PROPERTY, dtype=np.ndarray),
    ]

    @abstractmethod
    def set_final_states(self, *args, **kwargs) -> None:  # noqa
        pass

    @abstractmethod
    def compute_final_states(self, *args, **kwargs) -> None:  # noqa
        pass

    @abstractmethod
    def _write_final_states(self, *args, **kwargs) -> None:
        pass


class AbsProbs(Plottable):
    """Class dealing with absorption probabilities."""

    __prop_metadata__ = [
        Metadata(attr=A.ABS_RPOBS, prop=P.ABS_RPOBS, dtype=Lineage),
        Metadata(attr=A.DIFF_POT, prop=P.DIFF_POT, dtype=pd.Series),
    ]

    @abstractmethod
    def compute_absorption_probabilities(self, *args, **kwargs) -> None:  # noqa
        pass

    @abstractmethod
    def _write_absorption_probabilities(self, *args, **kwargs) -> None:
        pass


class Partitioner(KernelHolder, ABC):
    """Abstract base class for partitioning transition matrix into sets of recurrent and transient states."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._is_irreducible = None  # no need to refactor these
        self._rec_classes = None
        self._trans_classes = None

    def compute_partition(self) -> None:
        """
        Compute communication classes for the Markov chain.

        Returns
        -------
        None
            Nothing, but updates the following fields:

                - :paramref:`recurrent_classes`
                - :paramref:`transient_classes`
                - :paramref:`irreducible`
        """

        start = logg.info("Computing communication classes")
        n_states = len(self)

        rec_classes, trans_classes = partition(self.transition_matrix)

        self._is_irreducible = len(rec_classes) == 1 and len(trans_classes) == 0

        if not self._is_irreducible:
            self._trans_classes = _make_cat(
                trans_classes, n_states, self.adata.obs_names
            )
            self._rec_classes = _make_cat(rec_classes, n_states, self.adata.obs_names)
            logg.info(
                f"Found `{(len(rec_classes))}` recurrent and `{len(trans_classes)}` transient classes\n"
                f"Adding `.recurrent_classes`\n"
                f"       `.transient_classes`\n"
                f"       `.irreducible`\n"
                f"    Finish",
                time=start,
            )
        else:
            logg.warning(
                "The transition matrix is irreducible - cannot further partition it\n    Finish",
                time=start,
            )

    @property
    def is_irreducible(self):
        """Whether the Markov chain is irreducible or not."""
        return self._is_irreducible

    @property
    def recurrent_classes(self):
        """Recurrent classes of the Markov chain."""  # noqa
        return self._rec_classes

    @property
    def transient_classes(self):
        """Transient classes of the Markov chain."""  # noqa
        return self._trans_classes


class LineageEstimatorMixin(FinalStates, AbsProbs, ABC):
    """Mixin containing final states and absorption probabilities."""

    pass
