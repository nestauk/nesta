import pytest
import unittest
from unittest import mock
import pytest

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.mysql import VARCHAR, TEXT
from sqlalchemy.types import INTEGER
from sqlalchemy import Column
from sqlalchemy.engine.base import Engine
from sqlalchemy.exc import OperationalError

from nesta.production.orms.orm_utils import get_class_by_tablename
from nesta.production.orms.orm_utils import get_mysql_engine
from nesta.production.orms.orm_utils import try_until_allowed
from nesta.production.orms.orm_utils import insert_data

from nesta.production.orms.orm_utils import load_json_from_pathstub
from nesta.production.orms.orm_utils import get_es_mapping
from nesta.production.orms.orm_utils import setup_es
from nesta.production.orms.orm_utils import Elasticsearch
from nesta.production.orms.orm_utils import merge_metadata


@pytest.fixture
def alias_lookup():
    return {
        "alias1": {
            "dataset1": "field1a",
            "dataset2": "field1b"
        },
        "alias2": {
            "dataset1": "field2a",
            "dataset2": "field2b"
        }
    }

@pytest.fixture
def mapping():
    return {
        'mappings': {
            '_doc': {
                'properties': {
                    'field1a': {'type': 'keyword'},
                    'field2a': {'type': 'text'},
                }
            }
        }        
    }
    

Base = declarative_base()


class DummyModel(Base):
    __tablename__ = 'dummy_model'

    _id = Column(INTEGER, primary_key=True)
    _another_id = Column(INTEGER, primary_key=True)
    some_field = Column(INTEGER)


class DummyFunctionWrapper:
    i = 0

    def __init__(self, exc, *args):
        self.exc = exc(*args)

    def f(self):
        if self.i < 1:
            self.i += 1
            raise self.exc


class TestOrmUtils(unittest.TestCase):
    ''''''
    @classmethod    
    def setUpClass(cls):
        engine = get_mysql_engine("MYSQLDBCONF", "mysqldb")
        Base.metadata.drop_all(engine)

    @classmethod    
    def tearDownClass(cls):
        engine = get_mysql_engine("MYSQLDBCONF", "mysqldb")
        Base.metadata.drop_all(engine)

    def tests_insert_and_exists(self):
        data = [{"_id": 10, "_another_id": 2,
                 "some_field": 20},
                {"_id": 10, "_another_id": 2,
                 "some_field": 30},  # <--- Duplicate pkey, so should be ignored
                {"_id": 20, "_another_id": 2,
                 "some_field": 30}]
        objs = insert_data("MYSQLDBCONF", "mysqldb", "production_tests",
                           Base, DummyModel, data)
        self.assertEqual(len(objs), 2)

        objs = insert_data("MYSQLDBCONF", "mysqldb", "production_tests",
                           Base, DummyModel, data)
        self.assertEqual(len(objs), 0)

    def test_get_class_by_tablename(self):
        '''Check that the DummyModel is acquired from it's __tablename__'''
        _class = get_class_by_tablename(Base, 'dummy_model')
        self.assertEqual(_class, DummyModel)

    def test_get_mysql_engine(self):
        '''Test that an sqlalchemy Engine is returned'''
        engine = get_mysql_engine("MYSQLDBCONF", "mysqldb")
        self.assertEqual(type(engine), Engine)

    def test_try_until_allowed(self):
        '''Test that OperationalError leads to retrying'''
        dfw = DummyFunctionWrapper(OperationalError, None, None, None)
        try_until_allowed(dfw.f)

    def test_bad_try_until_allowed(self):
        '''Test that non-OperationalError lead to an exception'''
        dfw = DummyFunctionWrapper(Exception)
        self.assertRaises(Exception, try_until_allowed, dfw.f)


def test_load_json_from_pathstub():
    for ds in ["nih", "crunchbase"]:
        js = load_json_from_pathstub("production/orms/",
                                     f"{ds}_es_config.json")
        assert len(js) > 0

@mock.patch("nesta.production.orms.orm_utils.load_json_from_pathstub")
def test_get_es_mapping(mocked_load_json_from_pathstub, alias_lookup, 
                        mapping):
    mocked_load_json_from_pathstub.side_effect = (mapping, 
                                                  alias_lookup)
    _mapping = get_es_mapping("dataset1", "blah")    
    alias1 = _mapping["mappings"]["_doc"]["properties"].pop("alias1")
    alias2 = _mapping["mappings"]["_doc"]["properties"].pop("alias2")
    assert mapping == _mapping
    assert alias1 == {'type': 'alias', 'path': 'field1a'}
    assert alias2 == {'type': 'alias', 'path': 'field2a'}

@mock.patch("nesta.production.orms.orm_utils.load_json_from_pathstub")
def test_get_es_mapping_bad_alias(mocked_load_json_from_pathstub, 
                                  alias_lookup, mapping):
    mocked_load_json_from_pathstub.side_effect = (mapping, 
                                                  alias_lookup)
    with pytest.raises(ValueError):
        get_es_mapping("dataset2", "blah")

@mock.patch("nesta.production.orms.orm_utils.get_config")
@mock.patch("nesta.production.orms.orm_utils.assert_correct_config")
@mock.patch("nesta.production.orms.orm_utils.Elasticsearch")
@mock.patch("nesta.production.orms.orm_utils.get_es_mapping")
def test_setup_es_bad_es_mode(mock_get_es_mapping, mock_Elasticsearch, 
                              mock_assert_correct_config, mock_get_config):
    with pytest.raises(ValueError):
        setup_es(es_mode="dave", test_mode=False, drop_and_recreate=False, 
                 dataset=None, aliases=None)


@mock.patch("nesta.production.orms.orm_utils.get_config")
@mock.patch("nesta.production.orms.orm_utils.assert_correct_config")
@mock.patch("nesta.production.orms.orm_utils.Elasticsearch")
@mock.patch("nesta.production.orms.orm_utils.get_es_mapping")
def test_setup_es_true_test_delete_called(mock_get_es_mapping, 
                                          mock_Elasticsearch, 
                                          mock_assert_correct_config, 
                                          mock_get_config):
    mock_Elasticsearch.return_value.indices.exists.return_value = True
    setup_es(es_mode="dev", test_mode=True, drop_and_recreate=True, 
             dataset=None, aliases=None)
    assert mock_Elasticsearch.return_value.indices.delete.call_count == 1
    assert mock_Elasticsearch.return_value.indices.create.call_count == 1

@mock.patch("nesta.production.orms.orm_utils.get_config")
@mock.patch("nesta.production.orms.orm_utils.assert_correct_config")
@mock.patch("nesta.production.orms.orm_utils.Elasticsearch")
@mock.patch("nesta.production.orms.orm_utils.get_es_mapping")
def test_setup_es_true_test_delete_not_called_not_exists(mock_get_es_mapping, 
                                                         mock_Elasticsearch, 
                                                         mock_assert_correct_config, 
                                                         mock_get_config):
    mock_Elasticsearch.return_value.indices.exists.return_value = False
    setup_es(es_mode="dev", test_mode=True, drop_and_recreate=True, 
             dataset=None, aliases=None)
    assert mock_Elasticsearch.return_value.indices.delete.call_count == 0
    assert mock_Elasticsearch.return_value.indices.create.call_count == 1

@mock.patch("nesta.production.orms.orm_utils.get_config")
@mock.patch("nesta.production.orms.orm_utils.assert_correct_config")
@mock.patch("nesta.production.orms.orm_utils.Elasticsearch")
@mock.patch("nesta.production.orms.orm_utils.get_es_mapping")
def test_setup_es_false_test_delete_not_called(mock_get_es_mapping, 
                                               mock_Elasticsearch, 
                                               mock_assert_correct_config, 
                                               mock_get_config):
    mock_Elasticsearch.return_value.indices.exists.return_value = False
    setup_es(es_mode="dev", test_mode=False, drop_and_recreate=True, 
             dataset=None, aliases=None)
    assert mock_Elasticsearch.return_value.indices.delete.call_count == 0
    assert mock_Elasticsearch.return_value.indices.create.call_count == 1

@mock.patch("nesta.production.orms.orm_utils.get_config")
@mock.patch("nesta.production.orms.orm_utils.assert_correct_config")
@mock.patch("nesta.production.orms.orm_utils.Elasticsearch")
@mock.patch("nesta.production.orms.orm_utils.get_es_mapping")
def test_setup_es_false_reindex_delete_not_called(mock_get_es_mapping, 
                                                  mock_Elasticsearch, 
                                                  mock_assert_correct_config, 
                                                  mock_get_config):
    mock_Elasticsearch.return_value.indices.exists.return_value = False
    setup_es(es_mode="dev", test_mode=True, drop_and_recreate=False, 
             dataset=None, aliases=None)
    assert mock_Elasticsearch.return_value.indices.delete.call_count == 0
    assert mock_Elasticsearch.return_value.indices.create.call_count == 1

@mock.patch("nesta.production.orms.orm_utils.get_config")
@mock.patch("nesta.production.orms.orm_utils.assert_correct_config")
@mock.patch("nesta.production.orms.orm_utils.Elasticsearch")
@mock.patch("nesta.production.orms.orm_utils.get_es_mapping")
def test_setup_es_no_create_if_exists(mock_get_es_mapping, 
                                      mock_Elasticsearch, 
                                      mock_assert_correct_config, 
                                      mock_get_config):
    mock_Elasticsearch.return_value.indices.exists.return_value = True
    setup_es(es_mode="dev", test_mode=True, drop_and_recreate=False, 
             dataset=None, aliases=None)
    assert mock_Elasticsearch.return_value.indices.delete.call_count == 0
    assert mock_Elasticsearch.return_value.indices.create.call_count == 0


@pytest.fixture
def primary_base():
    PrimaryBase = declarative_base()

    class MainTable(PrimaryBase):
        __tablename__ = 'main_table'
        id = Column(VARCHAR(10), primary_key=True)
        data = Column(INTEGER)

    class OtherMainTable(PrimaryBase):
        __tablename__ = 'other_table'
        id = Column(VARCHAR(20), primary_key=True)
        text = Column(TEXT)

    return PrimaryBase


@pytest.fixture
def secondary_base():
    SecondaryBase = declarative_base()

    class SecondTable(SecondaryBase):
        __tablename__ = 'second_table'
        id = Column(INTEGER, primary_key=True)
        number = Column(INTEGER)

    return SecondaryBase


@pytest.fixture
def tertiary_base():
    TertiaryBase = declarative_base()

    class ThirdTable(TertiaryBase):
        __tablename__ = 'third_table'
        id = Column(VARCHAR(25), primary_key=True)
        other_id = Column(VARCHAR(10), primary_key=True)

    return TertiaryBase


def test_merge_metadata_with_two_bases(primary_base, secondary_base):
    merge_metadata(primary_base, secondary_base)
    assert list(primary_base.metadata.tables.keys()) == ['main_table',
                                                         'other_table',
                                                         'second_table']


def test_merge_metadata_with_three_bases(primary_base, secondary_base, tertiary_base):
    merge_metadata(primary_base, secondary_base, tertiary_base)

    assert list(primary_base.metadata.tables.keys()) == ['main_table',
                                                         'other_table',
                                                         'second_table',
                                                         'third_table']
