from nesta.packages.magrxiv.collect_magrxiv import get_magrxiv_articles
from nesta.packages.magrxiv.collect_magrxiv import ARXIV_MAG
from nesta.core.orms.arxiv_orm import Article
from unittest import mock
import pytest

@pytest.fixture
def dummy_article():
    return {key: f'blah blah{key}' for key in set(ARXIV_MAG.values())}

def test_all_fields_in_orm():
    orm = dir(Article)
    assert all(field in orm for field in ARXIV_MAG.keys())

@mock.patch('nesta.packages.magrxiv.collect_magrxiv.get_journal_articles')
@mock.patch('nesta.packages.magrxiv.collect_magrxiv.uninvert_abstract')
def test_get_magrxiv_articles(_, mocked, dummy_article):
    n_articles = 3
    mocked.return_value = iter([dummy_article]*n_articles)
    for i, article in enumerate(get_magrxiv_articles(xiv='dummyrxiv',
                                                     api_key='dummy_api_key', 
                                                     start_date='dummy_date')):
        assert type(article) is dict
        assert len(article) == len(ARXIV_MAG)
    assert i + 1 == n_articles

