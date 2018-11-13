from nesta.packages.nlp_utils.preprocess import tokenize_document
from nesta.packages.nlp_utils.preprocess import build_ngrams
from nesta.packages.nlp_utils.preprocess import filter_by_idf
from nesta.packages.nlp_utils.preprocess import keras_tokenizer
import nltk
from nltk.corpus import gutenberg
import unittest


def get_vocab(docs):
    vocab = set()
    for d in docs:
        for sent in d:
            vocab = vocab.union(set(sent))
    return vocab


class PreprocessTest(unittest.TestCase):

    def setUp(self):
        nltk.download("gutenberg")
        self.docs = []
        for fid in gutenberg.fileids():
            f = gutenberg.open(fid)
            self.docs.append(f.read())
            f.close()

    def test_ngrams(self):
        docs = [tokenize_document(d) for d in self.docs]
        docs = build_ngrams(docs, n=3)
        n = sum("poor_miss_taylor" in sent
                for sent in docs[0])
        self.assertGreater(n, 0)

    def test_tfidf(self):
        docs = [tokenize_document(d) for d in self.docs]
        vocab_before = get_vocab(docs)
        docs = filter_by_idf(docs, 10, 90)
        vocab_after = get_vocab(docs)
        self.assertLess(len(vocab_after), len(vocab_before))
        self.assertGreater(len(vocab_after), 1)

    def test_keras_sequences(self):
        sequences = keras_tokenizer(self.docs, num_words=2000, maxlen=20,
        sequences=True)
        self.assertTrue(sequences.shape[1]==20)

    def test_keras_matrix(self):
        tfidf_matrix = keras_tokenizer(self.docs, num_words=2000, mode='tfidf')
        self.assertTrue(self.docs==tdidf_matrix.shape[1])

if __name__ == "__main__":
    unittest.main()
