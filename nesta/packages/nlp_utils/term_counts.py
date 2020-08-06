from collections import Counter
from scipy.sparse import csr_matrix

def make_term_counts(dct, row, binary=False):
    """Convert a single single document to term counts via
    a gensim dictionary.

    Args:
        dct (Dictionary): Gensim dictionary.
        row (str): A document.
        binary (bool): Binary rather than total count?
    Returns:
        dict of term id (from the Dictionary) to term count.
    """
    return {dct[idx]: (count if not binary else 1)
            for idx, count in Counter(dct.doc2idx(row)).items() 
            if idx != -1}


def term_counts_to_sparse(term_counts):
    # Pack the data into a sparse matrix
    indptr = [0]  # Number of non-null entries per row
    indices = []  # Positions of non-null entries per row
    counts = []  # Term counts/weights per position
    vocab = {}  # {Term: position} lookup
    for row in term_counts:
        for term, count in row.items():
            idx = vocab.setdefault(term, len(vocab))
            indices.append(idx)
            counts.append(count)
        indptr.append(len(indices))
    X = csr_matrix((counts, indices, indptr), dtype=int)

    # {Position: term} lookup
    _vocab = {v:k for k, v in vocab.items()}
    return X, _vocab

