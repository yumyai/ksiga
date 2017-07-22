# -*- coding: utf-8 -*-

""" Store and calculate various statistic of kmer (1).
    (1) Viral Phylogenomics using an alignment-free method: A three step approach to determine optimal length of k-mer
"""

import math

from scipy.interpolate import interp1d
import h5py
import numpy as np

import ksiga.ksignature as ksignature
from ksiga.ksignature import KmerSignature
import ksiga.sparse_util as su
from ksiga import kmerutil
from ksiga import logutil

# So that old codes won't break
rebuild_sparse_matrix = ksignature.rebuild_sparse_matrix


def calculate_relative_entropy(indexFilename, ksize):
    """ Calculate the relative entropy (obs vs expected)
        The equation is (Something in latex here)
        Expected (ABCD) =  (obs(ABC) * obs(BCD)) / obs(BC)
    """
    # Check if exists
    store = KmerSignature(indexFilename)
    # Sparse array of ONE row, so it has shape = (1, col)
    array0 = store.get_kmer(ksize)
    array1 = store.get_kmer(ksize-1)
    array2 = store.get_kmer(ksize-2)

    relativeEntropy = _calculate_re_vectorize(array0, array1, array2)
    #relativeEntropy = _calculate_re(array0, array1, array2)

    return relativeEntropy


def _calculate_re(array0, array1, array2):
    """ Calculate relative entropy

    Args:
        array1 (TODO): Main array
        array2 (TODO): -1 order array
        array3 (TODO): -2 order array

    Returns: TODO

    """

    ksize = int(math.log(array1.shape[1], 4)) + 1

    genLoc1 = kmerutil.create_kmer_loc_fn(ksize-1)
    genLoc2 = kmerutil.create_kmer_loc_fn(ksize-2)

    ARes = []
    FRes = []
    BRes = []
    MRes = []
    # Calculate final normalization factor. Delegate the normalization to the last step (Arithmatric).
    # 3. the way, we might speed it up by reduce a redundant, xTTTTTTx required to look for TTTTTT at least 16 times.
    #    3.1 So, store kmer as a "TREE"????
    for (idxA, locL) in enumerate(array0.indices):
        mer = kmerutil.decode(locL, ksize)
        merFront = mer[0:-1]
        merBack = mer[1:]
        merMiddle = mer[1:-1]
        # Find location of left mer, right mer, and middle mer
        locF = genLoc1(merFront)
        locB = genLoc1(merBack)
        locM = genLoc2(merMiddle)
        # TODO: There should be an easy and very efficient way to map ATTT -> ATT, TTT
  
        # This is quicker than a naive lookup.
        idxF = su.has_indices(array1, locF)
        idxB = su.has_indices(array1, locB)
        idxM = su.has_indices(array2, locM)
        # # For debugging. This shouldn't be happened since occurence of ATTT imply the existenced of ATT, TT, and TTT
        # if __debug__:
            # if idxF == array1.indices.shape[0]:
                # raise IndexError("Left not found")
            # if idxB == array1.indices.shape[0]:
                # raise IndexError("Right not found")
            # if idxM == array2.indices.shape[0]:
                # raise IndexError("Middle not found")
        # # All, Front, Back, Middle

        countA = array0.data[idxA]
        countF = array1.data[idxF]
        countB = array1.data[idxB]
        countM = array2.data[idxM]

        ARes.append(countA)
        FRes.append(countF)
        BRes.append(countB)
        MRes.append(countM)

    ARes = np.array(ARes)  # Obs
    FRes = np.array(FRes)  # Front
    BRes = np.array(BRes)  # Back
    MRes = np.array(MRes)  # Middle
    # Calculate by using a factorized version of formula.
    norm0 = array0.data.sum()
    norm1 = array1.data.sum()
    norm2 = array2.data.sum()
    expectation = (FRes * BRes) / MRes
    observation = ARes
    normFactor = (norm1 ** 2) / (norm2 * norm0)
    rhs = np.log2(observation / expectation) + np.log2(normFactor)
    lhs = ARes / norm0
    relativeEntropy = (lhs * rhs).sum()

    ## Version which follow a formula as written in paper. Performance is still the same though.
    ## Roughly the same speed with the reduce version above.
    # norm0 = array0.data.sum()
    # norm1 = array1.data.sum()
    # norm2 = array2.data.sum()
    # expectation = (FRes/norm1) * (BRes/norm1) / (MRes/norm2)
    # observation = ARes / norm0
    # relativeEntropy = (observation * np.log2(observation/expectation)).sum()

    return relativeEntropy


def _calculate_re_vectorize(array0, array1, array2):
    """ Calculate relative entropy

    Args:
        array1 (TODO): Main array
        array2 (TODO): -1 order array
        array3 (TODO): -2 order array

    Returns: TODO

    """

    # def _convert_to_front(kmerHash, ksize):
    #     pass

    # def _convert_to_back(kmerHash, ksize):
    #     pass

    # def _convert_to_middle(kmerHash, ksize):
    #     pass

    def _calculate_limit(ksize):
        # And then we can use bin to calculate how much to delete from hash
        A_lim = kmerutil.encode("A" + ("T" * (ksize-1)))[0]
        C_lim = int((A_lim * 2) + 1)
        G_lim = int((A_lim * 3) + 2)
        return np.array([A_lim + 1, C_lim + 1, G_lim + 1])



    ksize = int(math.log(array1.shape[1], 4)) + 1  # Calculate kmer from size of array to hold all kmer

    # Calculate all index for each level.
    ARes = array0.data  # Obs
    # All merFront
    # convertFrontVec = np.vectorize(lambda khash:_convert_to_front(khash, ksize))
    # fHash = convertFrontVec(array0.indices)
    bins = _calculate_limit(ksize)
    frontCharHash = np.digitize(array0.indices, bins)
    fHash = array0.indices - (frontCharHash * (4 ** (ksize - 1)))
    idx = np.argsort(fHash)
    inv_idx = np.argsort(idx)
    fIdx_sorted = su.searchsorted(array1.indices, fHash[idx])
    fIdx = fIdx_sorted[inv_idx]
    FRes = array1.data[fIdx]
    # All merBack
    m = np.mod(array0.indices, 4)
    bHash = (array0.indices - m) / 4  # No need to sort since the order will be preserved.
    bIdx = su.searchsorted(array1.indices, bHash)
    BRes = array1.data[bIdx]

    # All Mer middle
    # Use fhash and calculate back hash
    # convertMidVec = np.vectorize(lambda khash:_convert_to_middle(khash, ksize))
    # mHash = convertMidVec(array0.indices)
    m = np.mod(fHash, 4)
    mHash = (fHash - m) / 4
    idx = np.argsort(mHash)
    inv_idx = np.argsort(idx)
    mIdx_sorted = su.searchsorted(array2.indices, mHash[idx])
    mIdx = mIdx_sorted[inv_idx]
    MRes = array2.data[mIdx]

    # Check
    assert len(ARes) == len(FRes)
    assert len(FRes) == len(BRes)
    assert len(BRes) == len(MRes)

    # Calculate by using a factorized version of formula.
    norm0 = array0.data.sum()
    norm1 = array1.data.sum()
    norm2 = array2.data.sum()
    expectation = (FRes * BRes) / MRes
    observation = ARes
    normFactor = (norm1 ** 2) / (norm2 * norm0)
    rhs = np.log2(observation / expectation) + np.log2(normFactor)
    lhs = ARes / norm0
    relativeEntropy = (lhs * rhs).sum()

    ## Version which follow a formula as written in paper. Performance is still the same though.
    ## Roughly the same speed with the reduce version above.
    # norm0 = array0.data.sum()
    # norm1 = array1.data.sum()
    # norm2 = array2.data.sum()
    # expectation = (FRes/norm1) * (BRes/norm1) / (MRes/norm2)
    # observation = ARes / norm0
    # relativeEntropy = (observation * np.log2(observation/expectation)).sum()

    return relativeEntropy


def calculate_average_common_feature(stores, ksize):
    """ Calculate an average common features from sparse matrix.

    Args:
        stores (TODO): TODO
        ksize (TODO): TODO

    Returns: TODO

    """

    csr_matrix = rebuild_sparse_matrix(stores, ksize)
    rowNum = csr_matrix.shape[0]

    vals = []
    norm = csr_matrix.shape[0] - 1

    # Read these later
    # 1. http://stackoverflow.com/questions/24566633/which-is-the-best-way-to-multiply-a-large-and-sparse-matrix-with-its-transpose
    # 2. C.dot(C.transpose)
    csr_matrix.data = np.ones(csr_matrix.data.shape[0], np.int64)  # Convert all number to 1

    for i in range(rowNum):
        initVal = csr_matrix.dot(csr_matrix[i].transpose())  #  Need to delete one that compare to itself
        initVal[i] = 0
        val = initVal.sum()
        vals.append(val)

    result = np.array(vals) / norm

    return result


def calculate_obsff(stores, ksize):
    """ Calculate an observe and expect.

    Args:
        stores (TODO): TODO
        ksize (TODO): TODO

    Returns: TODO

    """
    csr_matrix = rebuild_sparse_matrix(stores, ksize)
    # Probalbility that kmers exist.
    norm = csr_matrix.sum()
    prob = np.asarray(csr_matrix.sum(axis=0)).squeeze() / norm
    # Remove zero
    prob = prob[np.nonzero(prob)]
    # How many genome they occur
    csr_matrix.data = np.ones_like(csr_matrix.data)
    occurence = np.asarray(csr_matrix.sum(axis=0)).squeeze()
    occurence = occurence[np.nonzero(occurence)]  #  Remove zero
    sites = np.unique(csr_matrix.indices)  # Kmer string
    fn = np.vectorize(kmerutil.decode)
    kmerStr = fn(sites, ksize)

    return (prob, occurence, kmerStr)


def calculate_cre_kmer(indexFilename, start_k, stop_k):
    """ Calculate CRE and kmer.

    Args:
        stores (TODO): TODO
        ksize (TODO): TODO

    Returns: TODO

    """

    #  Check that all k-mer is already indexed.
    store = KmerSignature(indexFilename)
    for k in range(start_k - 2, stop_k + 1):
        pass

    relEntropies = []
    for k in range(start_k+1, stop_k+1):  # You don't need to calculate the first one (because it is equal to sum).
        relEntropies.append(calculate_relative_entropy(indexFilename, k))

    relEntropies = np.array(relEntropies)
    #  This shouldn't have much impact, but just in case where number goes below 0.
    relEntropies = np.clip(relEntropies, 0, np.inf)
    maximumVal = relEntropies.sum()
    cre = maximumVal - relEntropies.cumsum()
    cre = np.insert(cre, 0, maximumVal)
    kmerRange = np.arange(start_k, stop_k+1)
    suggestKmer = _find_yintercept(kmerRange, cre, 10)

    return (cre, suggestKmer)


def calculate_acf_kmer(stores, start_k, stop_k):
    """
    """

    acfs = []
    for ksize in range(start_k, stop_k + 1):
        val = calculate_average_common_feature(stores, ksize)
        val = val[:, np.newaxis]
        acfs.append(val)

    acfs = np.hstack(acfs)
    # For each row, calculate the k-mer
    kmers = []
    for acf in acfs:
        kmer = _find_yintercept(np.arange(start_k, stop_k+1), acf, 10)
        kmers.append(kmer)

    return (acfs, kmers)


def calculate_ofc_kmer(stores, start_k, stop_k):
    """ Calculate OFC.

    Args:
        arg1 (TODO): TODO

    Returns: TODO

    """

    allPossibleKmer = []
    ocf = []

    for ksize in range(start_k, stop_k + 1):
        csr_matrix = rebuild_sparse_matrix(stores, ksize)
        a, o = _calculate_ocf(csr_matrix)
        allPossibleKmer.append(a)
        ocf.append(o)

    ocf = np.array(ocf)
    allPossibleKmer = np.array(allPossibleKmer)
    cutoff = 80
    percentage = (1 - (ocf / allPossibleKmer)) * 100

    # TODO: Maybe interpolate to find a more optimal point?
    kmer = np.argwhere(np.diff(np.sign(percentage - cutoff)) < 0)[:,-1][-1] + start_k

    return (percentage, kmer)


def calculate_ofc(stores, ksize):
    """ Calculate an observe and expect.

    Args:
        stores (TODO): TODO
        ksize (TODO): TODO

    Returns: TODO

    """
    csr_matrix = rebuild_sparse_matrix(stores, ksize)
    unique, count = np.unique(csr_matrix.indices, return_counts=True)

    allPossible = unique.shape[0]
    numberOfUnique = np.where(count == 1)[0].shape[0]

    return (allPossible, numberOfUnique)

#
#  Working horse functions.
#

def _find_yintercept(x, y, percent):
    """ Find an intercept of CRE graph. ( Log/Ln graph)?
    """

    cutoff = y.max() / percent
    #  Check if it is still fall in range.
    if y.min() > cutoff:
        raise NotImplementedError("Calculate the k-mer beyond index is not implemented yet.")
    #  Interpolate to get more resolution on k-mer.
    fi = interp1d(x, y, kind="cubic")
    xn = np.linspace(x[0], x[-1], 500)
    yn = fi(xn)
    #  Check for an intercept
    idx = np.argwhere(np.diff(np.sign(yn - cutoff)) != 0).reshape(-1)
    xIntercept = xn[idx[0]]
    kmer = xIntercept #  Kmer
    return kmer



def _calculate_acf(spmatrix):
    """TODO: Docstring for function.

    Args:
        spmatrix (csr_matrix): TODO

    Returns: TODO

    """
    pass


def _calculate_ocf(spmatrix):
    """TODO: Docstring for function.

    Args:
        spmatrix (csr_matrix): TODO

    Returns: TODO

    """
    unique, count = np.unique(spmatrix.indices, return_counts=True)
    allPossible = unique.shape[0]
    numberOfUnique = np.where(count == 1)[0].shape[0]

    return (allPossible, numberOfUnique)


def build_signature(fasta, ksize, store, force):
    """ Build signature file from fasta.

    Args:
        fasta (fh): filehandle for fasta file
        ksize (int): kmer size
        store (str): filename
        force (bool): filename

    Returns: Write a signature into file

    """

    if force:
        store = h5py.File(store, "w")
    else:
        store = h5py.File(store, "a")
    store.attrs["index"] = "index"
    sigName = "/kmer/{size}".format(size=ksize)
    if sigName in store:
        raise KeyError("Kmer is already create")

    group = store.create_group(sigName)
    indice, data = kmerutil.build_csr_matrix_from_fasta(fasta, ksize)
    colSize = 4 ** (ksize)
    group.create_dataset("indices", compression="gzip", compression_opts=5, data=indice)
    group.create_dataset("data", compression="gzip", compression_opts=5, data=data)
    group.create_dataset("shape", data=(1, colSize))
