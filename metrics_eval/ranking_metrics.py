import numpy as np
import numba as nb
from numba import njit, prange
from numba.typed import List


# LOW LEVEL FUNCTIONS ==========================================================
@njit(cache=True)
def _average_scores(scores):
    average_scores = np.zeros((scores.shape[1]))

    for i in prange(average_scores.shape[0]):
        average_scores[nb.int64(i)] = np.mean(scores[:, nb.int64(i)])

    return average_scores


@njit(cache=True)
def _isin(x, v):
    for i in prange(v.shape[0]):
        if v[nb.int64(i)] == x:
            return True
    return False


@njit(cache=True)
def _hit_list(y_true, y_pred):
    hit_list = np.zeros((y_pred.shape[0]))

    for i in prange(y_pred.shape[0]):
        hit_list[nb.int64(i)] = _isin(y_pred[nb.int64(i)], y_true)

    return hit_list


@njit(cache=True)
def _hit_list_at_k(y_true, y_pred, k):
    hit_list = _hit_list(y_true, y_pred[:k])

    if k > hit_list.shape[0]:
        hit_list = np.append(
            hit_list, np.zeros((k - hit_list.shape[0]), dtype=hit_list.dtype)
        )

    return hit_list


@njit(cache=True)
def _hits_at_k(y_true, y_pred, k):
    hits = np.sum(_hit_list_at_k(y_true, y_pred, k))

    return hits


@njit(cache=True, parallel=True)
def _hits_at_k_parallel(y_true, y_pred, k):
    score = 0

    for i in prange(len(y_true)):
        score += _hits_at_k(y_true[nb.int64(i)], y_pred[nb.int64(i)], k)

    return score / len(y_true)


@njit(cache=True)
def _precision_at_k(y_true, y_pred, k):
    return _hits_at_k(y_true, y_pred, k) / k


@njit(cache=True, parallel=True)
def _precision_at_k_parallel(y_true, y_pred, k):
    score = 0

    for i in prange(len(y_true)):
        score += _precision_at_k(y_true[nb.int64(i)], y_pred[nb.int64(i)], k)

    return score / len(y_true)


@njit(cache=True)
def _recall_at_k(y_true, y_pred, k):
    return _hits_at_k(y_true, y_pred, k) / y_true.shape[0]


@njit(cache=True, parallel=True)
def _recall_at_k_parallel(y_true, y_pred, k):
    score = 0

    for i in prange(len(y_true)):
        score += _recall_at_k(y_true[nb.int64(i)], y_pred[nb.int64(i)], k)

    return score / len(y_true)


@njit(cache=True)
def _r_precision(y_true, y_pred):
    return _precision_at_k(y_true, y_pred, y_true.shape[0])


@njit(cache=True, parallel=True)
def _r_precision_parallel(y_true, y_pred):
    score = 0

    for i in prange(len(y_true)):
        score += _r_precision(y_true[nb.int64(i)], y_pred[nb.int64(i)])

    return score / len(y_true)


@njit(cache=True)
def _intersection(u, v):
    intersection = np.zeros((u.shape[0]))
    i = 0
    k = 0

    while i < v.shape[0]:
        if _isin(v[nb.int64(i)], u):
            intersection[k] = v[nb.int64(i)]
            k += 1
        i += 1

    return intersection[:k]


@njit(cache=True)
def _reciprocal_rank(y_true, y_pred):
    intersection = _intersection(y_true, y_pred)

    if intersection.shape[0] == 0:
        return 0

    for i in prange(y_pred.shape[0]):
        if y_pred[nb.int64(i)] in set(intersection):
            return 1 / (i + 1)


@njit(cache=True, parallel=True)
def _mrr(y_true, y_pred):
    score = 0

    for i in prange(len(y_true)):
        score += _reciprocal_rank(y_true[nb.int64(i)], y_pred[nb.int64(i)])

    return score / len(y_true)


@njit(cache=True)
def _average_precision(y_true, y_pred, k):
    if k > 0:
        y_pred = y_pred[:k]

    hit_list = _hit_list_at_k(y_true, y_pred, y_pred.shape[0])
    precision_scores = np.zeros((y_pred.shape[0]), dtype=nb.float64)

    for r in prange(y_pred.shape[0]):
        if hit_list[r]:
            # Compute precision at k without computing hit list at k again
            # same as _precision_at_k(y_true, y_pred, r + 1)
            precision_scores[r] = np.sum(hit_list[: r + 1]) / (r + 1)

    return np.sum(precision_scores) / y_true.shape[0]


@njit(cache=True, parallel=True)
def _map(y_true, y_pred, k):
    score = 0

    for i in prange(len(y_true)):
        score += _average_precision(y_true[nb.int64(i)], y_pred[nb.int64(i)], k)

    return score / len(y_true)


@njit()
def _binary_metrics(y_true, y_pred, k):
    metric_scores = np.zeros((6))
    metric_scores[0] = _hits_at_k(y_true, y_pred, k)
    metric_scores[1] = metric_scores[0] / k  # precision at k
    metric_scores[2] = _average_precision(y_true, y_pred)
    metric_scores[3] = _reciprocal_rank(y_true, y_pred)
    metric_scores[4] = _r_precision(y_true, y_pred)
    metric_scores[5] = metric_scores[0] / y_true.shape[0]  # recall at k

    return metric_scores


@njit(cache=True)
def _binary_metrics_parallel(y_true, y_pred, k):
    metric_scores = np.zeros((6))
    metric_scores[0] = _hits_at_k_parallel(y_true, y_pred, k)
    metric_scores[1] = metric_scores[0] / k  # precision at k
    metric_scores[2] = _map(y_true, y_pred)
    metric_scores[3] = _mrr(y_true, y_pred)
    metric_scores[4] = _r_precision_parallel(y_true, y_pred)
    metric_scores[5] = _recall_at_k_parallel(y_true, y_pred, k)

    return metric_scores


@njit(cache=True)
def _isin_weighted(x, v):
    for i in prange(v.shape[0]):
        if v[i, 0] == x:
            return v[i, 1]
    return 0


@njit(cache=True)
def _weighted_hit_list(y_true, y_pred):
    weighted_hit_list = np.zeros((y_pred.shape[0]))

    for i in prange(y_pred.shape[0]):
        weighted_hit_list[nb.int64(i)] = _isin_weighted(
            y_pred[nb.int64(i)], y_true
        )

    return weighted_hit_list


@njit(cache=True)
def _dcg(y_true, y_pred, k):
    k = k if k <= y_pred.shape[0] else y_pred.shape[0]

    weighted_hit_list = _weighted_hit_list(y_true, y_pred[:k])

    # Standard formulation
    return np.sum(
        (2 ** weighted_hit_list - 1) / np.log2(np.arange(1, k + 1) + 1)
    )


@njit(cache=True, parallel=True)
def _dcg_parallel(y_true, y_pred, k):
    scores = np.zeros((len(y_true)))

    for i in prange(len(y_true)):
        scores[nb.int64(i)] = _dcg(y_true[nb.int64(i)], y_pred[nb.int64(i)], k)

    # return np.sum(scores) / len(y_true)
    return scores


@njit(cache=True)
def _idcg(y_true, k, binary):
    if not binary:
        # Sort by descending order of second column
        y_pred = y_true[np.argsort(y_true[:, 1])[::-1]][:, 0]
    else:
        y_pred = y_true[:, 0]
    return _dcg(y_true, y_pred, k)


@njit(cache=True, parallel=True)
def _idcg_parallel(y_true, k, binary):
    scores = np.zeros((len(y_true)))

    for i in prange(len(y_true)):
        scores[nb.int64(i)] = _idcg(y_true[nb.int64(i)], k, binary)

    return scores


@njit(cache=True)
def _ndcg(y_true, y_pred, k, binary):
    dcg_score = _dcg(y_true, y_pred, k)
    idcg_score = _idcg(y_true, k, binary)
    return dcg_score / idcg_score


@njit(cache=True, parallel=True)
def _ndcg_parallel(y_true, y_pred, k, binary):
    score = 0

    for i in prange(len(y_true)):
        score += _ndcg(y_true[nb.int64(i)], y_pred[nb.int64(i)], k, binary)

    return score / len(y_true)


# HIGH LEVEL FUNCTIONS =========================================================
def _choose_optimal_function(
    y_true, y_pred, f_single, f_parallel, f_additional_args={}
):
    # Parallel (all) or single (dcg/idcg/ndcg)
    if (
        type(y_true) == nb.typed.typedlist.List
        and type(y_true[0]) == np.ndarray
        and (
            y_true[0].ndim == 1
            or (
                (f_single == _dcg or f_single == _idcg or f_single == _ndcg)
                and y_true[0].ndim == 2
            )
        )
    ) or (
        type(y_true) == np.ndarray
        and (
            y_true.ndim == 2
            or (
                (f_single == _dcg or f_single == _idcg or f_single == _ndcg)
                and y_true.ndim == 3
            )
        )
    ):
        if type(y_pred) == np.ndarray and y_pred.ndim == 2:
            return f_parallel(y_true, y_pred, **f_additional_args)
        elif (
            (f_single == _dcg or f_single == _idcg or f_single == _ndcg)
            and type(y_pred) == np.ndarray
            and y_pred.ndim == 1
        ):
            print(f_single)
            return f_single(y_true, y_pred, **f_additional_args)
        else:
            raise TypeError("y_pred type not supported.")
    # Multi
    elif (
        type(y_true) == list
        and type(y_true[0]) == np.ndarray
        and (
            y_true[0].ndim == 1
            or (
                (f_single == _dcg or f_single == _idcg or f_single == _ndcg)
                and y_true[0].ndim == 2
            )
        )
    ):
        if (type(y_pred) == np.ndarray or type(y_pred) == list) and all(
            [
                True if type(y) == np.ndarray and y.ndim == 1 else False
                for y in y_pred
            ]
        ):
            return np.sum(
                [
                    f_single(y_t, y_p, **f_additional_args)
                    for y_t, y_p in zip(y_true, y_pred)
                ]
            ) / len(y_true)
        else:
            raise TypeError("y_pred type not supported.")
    # Single
    elif type(y_true) == np.ndarray and y_true.ndim == 1:
        if type(y_pred) == np.ndarray and y_pred.ndim == 1:
            return f_single(y_true, y_pred, **f_additional_args)
        else:
            print(f_single)
            raise TypeError("y_pred type not supported.")
    else:
        raise TypeError("y_true type not supported.")


# BINARY METRICS ---------------------------------------------------------------
def hit_list_at_k(y_true, y_pred, k):
    """Compute hit list at k.

    Hit list at k is a list of k elements where each element is 1 if the corresponding element in y_pred is relevant, 0 otherwise.

    Example:
    >>> y_true = np.array([1, 4, 5, 6])
    >>> y_pred = np.array([1, 2, 3, 4, 5, 7])
    >>> k = 5
    >>> hit_list_at_k(y_true, y_pred, k)
    [1, 0, 0, 1, 1]

    Parameters
    ----------
    y_true : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs of _relevant_ documents.

    y_pred : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs of _retrieved_ documents.

    k : Int
        Number of results to consider.

    Returns
    -------
    Numpy Array or List of Numpy Arrays:
        Hit list at k.

    """
    if (
        (type(y_true) == list or type(y_true) == nb.typed.typedlist.List)
        and type(y_true[0]) == np.ndarray
        and y_true[0].ndim == 1
    ) or (type(y_true) == np.ndarray and y_true.ndim == 2):
        return [_hit_list_at_k(y_t, y_p, k) for y_t, y_p in zip(y_true, y_pred)]

    elif type(y_true) == np.ndarray and y_true.ndim == 1:
        return _hit_list_at_k(y_true, y_pred, k)
    else:
        raise TypeError("Input not supported.")


def hits_at_k(y_true, y_pred, k):
    """Compute hits at k.

    Hits at k is the number of relevant documents in the first k positions of the retrieved documents list.

    If y_true and y_pred are bi-dimensional, it computes the arithmetic mean of the hits at k scores.

    Parameters
    ----------
    y_true : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs of _relevant_ documents.

    y_pred : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs of _retrieved_ documents.

    k : Int
        Number of results to consider.

    Returns
    -------
    Float:
        Hits at k score.

    """

    return _choose_optimal_function(
        y_true, y_pred, _hits_at_k, _hits_at_k_parallel, {"k": k}
    )


def precision_at_k(y_true, y_pred, k):
    r"""Compute precision at k.

    Precision at k (P@k) is the proportion of the top-k documents that are relevant. The top-k documents are the first k documents of a ranked list.

    .. math:: P@k={{r}\over{k}}

    where,

    - :math:`r` is the number of relevant documents.

    If y_true and y_pred are bi-dimensional, it computes the arithmetic mean of the precision at k scores.

    .. math:: mP@k = {1\over n}\sum\limits_n {P@k_n }

    where,

    - :math:`n` is the number of tasks;
    - :math:`P@k_n` is the :math:`Precision\,at\,k` of :math:`n`-th task.


    .. highlight:: bibtex
    .. code-block:: bibtex

        @Inbook{Craswell2009,
            author="Craswell, Nick",
            editor="LIU, LING
            and {\"O}ZSU, M. TAMER",
            title="Precision at n",
            bookTitle="Encyclopedia of Database Systems",
            year="2009",
            publisher="Springer US",
            address="Boston, MA",
            pages="2127--2128",
            isbn="978-0-387-39940-9",
            doi="10.1007/978-0-387-39940-9_484",
            url="https://doi.org/10.1007/978-0-387-39940-9_484"
        }



    Parameters
    ----------
    y_true : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs of _relevant_ documents.

    y_pred : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs of _retrieved_ documents sorted by descending rank order.

    k : Int
        Number of results to consider.

    Returns
    -------
    Float:
        Precision at k score.

    """

    return _choose_optimal_function(
        y_true, y_pred, _precision_at_k, _precision_at_k_parallel, {"k": k}
    )


def recall_at_k(y_true, y_pred, k):
    r"""Compute recall at k.

    Recall at k (P@k) is the ratio between the top-k documents that are relevant and the total number of relevant documents. The top-k documents are the first k in a ranking.

    .. math:: R@k={{r}\over{R}}

    where,

    - :math:`r` is the number of retrieved relevant documents at k.
    - :math:`R` is the total number of relevant documents.

    If y_true and y_pred are bi-dimensional, it computes the arithmetic mean of the recall at k scores.

    .. math:: mR@k = {1\over n}\sum\limits_n {R@k_n }

    where,

    - :math:`n` is the number of tasks;
    - :math:`R@k_n` is the :math:`Recall\,at\,k` of :math:`n`-th task.

    Parameters
    ----------
    y_true : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs of _relevant_ documents.

    y_pred : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs of _retrieved_ documents sorted by descending rank order.

    k : Int
        Number of results to consider.

    Returns
    -------
    Float:
        Recall at k score.

    """

    return _choose_optimal_function(
        y_true, y_pred, _recall_at_k, _recall_at_k_parallel, {"k": k}
    )


def r_precision(y_true, y_pred):
    r"""Compute R-precision.

    For a given query topic :math:`Q`, R-precision is the precision at :math:`R`, where :math:`R` is the number of relevant documents for :math:`Q`. In other words, if there are :math:`r` relevant documents among the top-:math:`R` retrieved documents, then R-precision is

    .. math:: \frac{r}{R}

    If y_true and y_pred are bi-dimensional, it computes the arithmetic mean of the R-precision scores.

    Parameters
    ----------
    y_true : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs of _relevant_ documents.

    y_pred : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs of _retrieved_ documents sorted by descending rank order.

    Returns
    -------
    FLoat
        R-precision score.

    """

    return _choose_optimal_function(
        y_true, y_pred, _r_precision, _r_precision_parallel
    )


def mrr(y_true, y_pred):
    r"""Compute Mean Reciprocal Rank.

    The mean reciprocal rank is a statistic measure for evaluating any process that produces a list of possible responses to a sample of queries, ordered by probability of correctness. The reciprocal rank of a query response is the multiplicative inverse of the rank of the first correct answer: 1 for first place, ​1/2 for second place, 1/3 for third place and so on. The mean reciprocal rank is the average of the reciprocal ranks of results for a sample of queries.

    Usefull when only one document is the correct answer.

    .. math:: MRR = \frac{1}{N}\sum_{i=1}^{N}\frac{1}{rank_i}

    where,

    - :math:`N` is the number of tasks (ranked lists);
    - :math:`rank_i` is the position of the correct document for the task :math:`i`.

    Parameters
    ----------
    y_true : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs of _relevant_ documents.

    y_pred : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs of _retrieved_ documents sorted by descending rank order.

    Returns
    -------
    Float
        Mean Reciprocal Rank score.

    """

    return _choose_optimal_function(y_true, y_pred, _reciprocal_rank, _mrr)


def average_precision(y_true, y_pred, k=0):
    """Compute average precision.

    Average precision is a measure that combines recall and precision for ranked retrieval results. For one information need, the average precision is the mean of the precision scores after each relevant document is retrieved.

    .. math:: AP = {1\over R}{{\sum\limits _{r}P @ r}}

    where,

    - :math:`R` is the number of relevant documents;
    - :math:`r` values are the positions of relevant documents;
    - :math:`P @ r` is the :math:`Precision\,at\,r`.

    .. highlight:: bibtex
    .. code-block:: bibtex

        @Inbook{Zhang2009,
            author="Zhang, Ethan and Zhang, Yi",
            editor="LIU, LING and {\"O}ZSU, M. TAMER",
            title="Average Precision",
            bookTitle="Encyclopedia of Database Systems",
            year="2009",
            publisher="Springer US",
            address="Boston, MA",
            pages="192--193",
            isbn="978-0-387-39940-9",
            doi="10.1007/978-0-387-39940-9_482",
            url="https://doi.org/10.1007/978-0-387-39940-9_482"
        }


    Parameters
    ----------
    y_true : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs of _relevant_ documents.

    y_pred : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs of _retrieved_ documents sorted by descending rank order.

    Returns
    -------
    Float
        Average Precision score.

    """
    if type(y_true) == np.ndarray and y_true.ndim == 1:
        if type(y_pred) == np.ndarray and y_true.ndim == 1:
            return _average_precision(y_true, y_pred, k)
        else:
            raise TypeError("y_pred type not supported.")
    else:
        raise TypeError("y_true type not supported.")


def map(y_true, y_pred, k=0):
    r"""Compute mean average precision.

    The Mean Average Precision (MAP) is the arithmetic mean of the average precision values for a set of ranked lists.

    .. math:: MAP = {1\over n}\sum\limits_n {AP_n }

    where,

    - :math:`n` is the number of tasks (ranked lists);
    - :math:`AP_n` is the :math:`Average\,Precision` of :math:`n`-th task.

    .. highlight:: bibtex
    .. code-block:: bibtex

        @Inbook{Zhang2009,
            author="Zhang, Ethan and Zhang, Yi",
            editor="LIU, LING and {\"O}ZSU, M. TAMER",
            title="Average Precision",
            bookTitle="Encyclopedia of Database Systems",
            year="2009",
            publisher="Springer US",
            address="Boston, MA",
            pages="192--193",
            isbn="978-0-387-39940-9",
            doi="10.1007/978-0-387-39940-9_482",
            url="https://doi.org/10.1007/978-0-387-39940-9_482"
        }

    Parameters
    ----------
    y_true : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs of _relevant_ documents.

    y_pred : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs of _retrieved_ documents sorted by descending rank order.

    k : Int
        Number of results to consider.

    Returns
    -------
    Float
        Mean Average Precision score.

    """

    return _choose_optimal_function(
        y_true, y_pred, _average_precision, _map, {"k": k}
    )


def binary_metrics(y_true, y_pred, k):
    r"""Compute Hits at k, Precision at k, Recall at k, R-precision, Mean Reciprocal Rank, Mean Average Precision.

    Parameters
    ----------
    y_true : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs of _relevant_ documents.

    y_pred : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs of _retrieved_ documents sorted by descending rank order.

    k : Int
        Number of results to consider.

    Returns
    -------
    Float
        Mean Reciprocal Rank score.

    """

    return _choose_optimal_function(
        y_true, y_pred, _binary_metrics, _binary_metrics_parallel, {"k": k}
    )


# NON-BINARY METRICS -----------------------------------------------------------
def dcg(y_true, y_pred, k):
    r"""Compute Discounted Cumulative Gain (DCG) at k.

    Discounted Cumulative Gain measures the usefulness, or _gain_, of a document based on its position in the result list. The gain is accumulated from the top of the result list to the bottom, with the gain of each result discounted at lower ranks.

    Standard formulation:

    .. math:: DCG(k) = \sum_{n=1}^{k}\frac{2^{r_n}-1}{\log_2(n+1)}

    where,

    - :math:`k` is the number of results to consider;
    - :math:`r_n` is the relevance of the item in position :math:`n` of the result list;
    - :math:`\log_2(n)` is the _discount_ factor.

    .. highlight:: bibtex
    .. code-block:: bibtex

        @article{jarvelin2002cumulated,
            title="Cumulated gain-based evaluation of IR techniques",
            author="J{\"a}rvelin, Kalervo and Kek{\"a}l{\"a}inen, Jaana",
            journal="ACM Transactions on Information Systems (TOIS)",
            volume="20",
            number="4",
            pages="422--446",
            year="2002",
            publisher="ACM",
            doi="10.1145/582415.582418",
        }

    If y_true and y_pred are multi-dimensional, it computes the arithmetic mean of the Discounted Cumulative Gain scores.

    Example:
    >>> y_true = np.array([[[12, 0.5], [25, 0.3]], [[11, 0.4], [2, 0.6]]])
    >>> y_pred = np.array([[12, 234, 25, 36, 32, 35], [12, 11, 25, 36, 2, 35]])
    >>> k = 5
    >>> dcg(y_true, y_pred, k)
    array([0.52978577, 0.40109345])

    Parameters
    ----------
    y_true : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs and true relevance scores of _relevant_ documents.

    y_pred : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs of _retrieved_ documents.

    k : Int
        Number of results to consider.

    Returns
    -------
    Float
        Discounted Cumulative Gain at k score.

    """

    return _choose_optimal_function(
        y_true, y_pred, _dcg, _dcg_parallel, {"k": k}
    )


def idcg(y_true, k, binary=False):
    r"""Compute Ideal Discounted Cumulative Gain (IDCG) at k.

    Parameters
    ----------
    y_true : Numpy Array or List
        (List of) Numpy Array of IDs of _relevant_ documents.

    k : Int
        Number of results to consider.

    binary : Boolean
        If `True` it will not reorder y_true by relevance score.

    Returns
    -------
    Float
        Discounted Cumulative Gain at k score.

    """
    if type(y_true) == nb.typed.typedlist.List:
        return _idcg_parallel(y_true, k, binary)
    elif type(y_true) == list and y_true[0] == np.ndarray:
        return np.sum([_idcg(y_t, k, binary) for y_t, in y_true]) / len(y_true)
    elif type(y_true) == np.ndarray:
        return _idcg(y_true, k, binary)
    else:
        raise TypeError("Input not supported.")


def ndcg(y_true, y_pred, k, binary=False):
    r"""Compute Normalized Discounted Cumulative Gain (NDCG) at k.

    .. math:: nDCG(k) = \frac{DCG(k)}{IDCG(k)}

    where,

    - :math:`DCG(k)` is Discounted Cumulative Gain at k;
    - :math:`IDCG(k)` is Ideal Discounted Cumulative Gain at k (max possibile DCG at k).

    .. highlight:: bibtex
    .. code-block:: bibtex

        @article{jarvelin2002cumulated,
            title="Cumulated gain-based evaluation of IR techniques",
            author="J{\"a}rvelin, Kalervo and Kek{\"a}l{\"a}inen, Jaana",
            journal="ACM Transactions on Information Systems (TOIS)",
            volume="20",
            number="4",
            pages="422--446",
            year="2002",
            publisher="ACM",
            doi="10.1145/582415.582418",
        }

    If y_true and y_pred are multi-dimensional, it computes the arithmetic mean of the Normalized Discounted Cumulative Gain scores.

    Example:
    >>> y_true = np.array([[[12, 0.5], [25, 0.3]], [[11, 0.4], [2, 0.6]]])
    >>> y_pred = np.array([[12, 234, 25, 36, 32, 35], [12, 11, 25, 36, 2, 35]])
    >>> k = 5
    >>> ndcg(y_true, y_pred, k)
    0.7525653965843032

    Parameters
    ----------
    y_true : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs and true relevance scores of _relevant_ documents.

    y_pred : Numpy Array or List of Numpy Arrays or Numba Typed List
        IDs of _retrieved_ documents.

    k : Int
        Number of results to consider.

    binary : Boolean
        If `True` it will not reorder y_true by relevance score during iDCG computation.

    Returns
    -------
    Float
        Normalized Discounted Cumulative Gain at k score.

    """

    return _choose_optimal_function(
        y_true, y_pred, _ndcg, _ndcg_parallel, {"k": k, "binary": binary}
    )
