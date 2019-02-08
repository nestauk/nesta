import pytest
from unittest import mock

from nesta.packages.worldbank.collect_worldbank import DEAD_RESPONSE

from nesta.packages.worldbank.collect_worldbank import worldbank_request
from nesta.packages.worldbank.collect_worldbank import _worldbank_request
from nesta.packages.worldbank.collect_worldbank import data_from_response
from nesta.packages.worldbank.collect_worldbank import worldbank_data
from nesta.packages.worldbank.collect_worldbank import get_worldbank_resource
from nesta.packages.worldbank.collect_worldbank import get_variables_by_code
from nesta.packages.worldbank.collect_worldbank import unpack_quantity
from nesta.packages.worldbank.collect_worldbank import unpack_data
from nesta.packages.worldbank.collect_worldbank import get_country_data
from nesta.packages.worldbank.collect_worldbank import flatten_country_data

PKG = "nesta.packages.worldbank.collect_worldbank.{}"


@pytest.fixture
def request_kwargs():
    return dict(suffix="source", page=1, per_page=1)


def test_worldbank_api(request_kwargs):
    """Check the API is still up"""
    _worldbank_request(**request_kwargs)


@mock.patch(PKG.format('requests.get'))
def test_hidden_worldbank_request_with_400(mocked_requests, request_kwargs):
    type(mocked_requests).status_code = 400  #mock.PropertyMock(return_value=400)
    return_value = _worldbank_request(**request_kwargs)
    assert return_value == DEAD_RESPONSE


@mock.patch(PKG.format('requests.get'))
def test_hidden_worldbank_request_with_bad_json(mocked_requests, request_kwargs):
    mocked_requests.json.return_value = "<<DEFINITELY NOT JSON>>"
    return_value = _worldbank_request(**request_kwargs)
    assert return_value == DEAD_RESPONSE


def test_data_from_response_with_dead_response():
    assert data_from_response(DEAD_RESPONSE) == DEAD_RESPONSE


def test_data_from_response_no_key_path():
    response = [1, 2]
    assert data_from_response(response) == response


def test_data_from_response_dict_response_with_key_path():
    response = {"path": {"to": "value"}}
    assert data_from_response(response, ["path", "to"]) == "value"


def test_data_from_response_mixed_response_with_key_path():
    response = {"path": [{"to": "value"}]}
    assert data_from_response(response, ["path", "to"]) == "value"


@mock.patch(PKG.format('_worldbank_request'), return_value=DEAD_RESPONSE)
@mock.patch(PKG.format('data_from_response'), return_value=DEAD_RESPONSE)
def test_worldbank_request_with_dead_response(mocked_worldbank_request,
                                              mocked_data_from_response):
    assert worldbank_request(**request_kwargs) == DEAD_RESPONSE
    

# def test_worldbank_data_yielder():
    


# @pytest.fixture
# def crunchbase_tarfile():
#     tar = NamedTemporaryFile(suffix='.tar.gz')
#     print(tar.name)
#     temp_tar = tarfile.open(tar.name, mode='w:gz')
#     with TemporaryDirectory() as temp_dir:
#         # add 3 test csv files
#         for i in range(3):
#             with open(f'{temp_dir}/test_{i}.csv', mode='w') as f:
#                 f.write("id,data\n111,aaa\n222,bbb")
#             temp_tar.add(f.name, f'test_{i}.csv')  # rename to remove temp folder structure from filename
#     temp_tar.close()
#     yield tar
#     tar.close()


# @mock.patch('nesta.packages.crunchbase.crunchbase_collect.NamedTemporaryFile')
# @mock.patch('nesta.packages.crunchbase.crunchbase_collect.requests.get')
# def test_crunchbase_tar(mocked_requests, mocked_temp_file, crunchbase_tarfile):
#     mocked_temp_file().__enter__.return_value = crunchbase_tarfile
#     mocked_temp_file().__exit__.side_effect = lambda *args: crunchbase_tarfile.close()
#     crunchbase_tarfile.write = lambda x: None  # patch write method to do nothing

#     with crunchbase_tar() as test_tar:
#         assert type(test_tar) == tarfile.TarFile
#         assert test_tar.getnames() == ['test_0.csv', 'test_1.csv', 'test_2.csv']


# @mock.patch('nesta.packages.crunchbase.crunchbase_collect.crunchbase_tar')
# def test_get_csv_list(mocked_crunchbase_tar, crunchbase_tarfile):
#     mocked_crunchbase_tar.return_value = tarfile.open(crunchbase_tarfile.name)

#     expected_result = ['test_0', 'test_1', 'test_2']
#     assert get_csv_list() == expected_result


# @mock.patch('nesta.packages.crunchbase.crunchbase_collect.crunchbase_tar')
# def test_get_files_from_tar(mocked_crunchbase_tar, crunchbase_tarfile):
#     mocked_crunchbase_tar.return_value = tarfile.open(crunchbase_tarfile.name)

#     expected_result = pd.DataFrame({'id': [111, 222], 'data': ['aaa', 'bbb']})
#     dfs = get_files_from_tar(['test_0'])
#     assert type(dfs) == list
#     assert_frame_equal(dfs[0], expected_result, check_like=True)


# @mock.patch('nesta.packages.crunchbase.crunchbase_collect.crunchbase_tar')
# def test_get_files_from_tar_limits_rows(mocked_crunchbase_tar, crunchbase_tarfile):
#     mocked_crunchbase_tar.return_value = tarfile.open(crunchbase_tarfile.name)

#     expected_result = pd.DataFrame({'id': [111], 'data': ['aaa']})
#     dfs = get_files_from_tar(['test_0'], nrows=1)  # only return 1 row
#     assert_frame_equal(dfs[0], expected_result, check_like=True)


# def test_rename_uuid_columns():
#     test_df = pd.DataFrame({'uuid': [1, 2, 3],
#                             'org_uuid': [11, 22, 33],
#                             'other_id': [111, 222, 333]
#                             })

#     expected_result = pd.DataFrame({'id': [1, 2, 3],
#                                     'other_id': [111, 222, 333],
#                                     'org_id': [11, 22, 33]
#                                     })

#     assert_frame_equal(rename_uuid_columns(test_df), expected_result, check_like=True)


# def test_bool_convert():
#     assert bool_convert('t') is True
#     assert bool_convert('f') is False
#     assert bool_convert('aaa') is None
#     assert bool_convert(None) is None


# @pytest.fixture
# def generate_test_data():
#     def _generate_test_data(n):
#         return [{'data': 'foo', 'other': 'bar'} for i in range(n)]
#     return _generate_test_data


# def test_split_batches_when_data_is_smaller_than_batch_size(generate_test_data):
#     yielded_batches = []
#     for batch in split_batches(generate_test_data(200), batch_size=1000):
#         yielded_batches.append(batch)

#     assert len(yielded_batches) == 1


# def test_split_batches_yields_multiple_batches_with_exact_fit(generate_test_data):
#     yielded_batches = []
#     for batch in split_batches(generate_test_data(2000), batch_size=1000):
#         yielded_batches.append(batch)

#     assert len(yielded_batches) == 2


# def test_split_batches_yields_multiple_batches_with_remainder(generate_test_data):
#     yielded_batches = []
#     for batch in split_batches(generate_test_data(2400), batch_size=1000):
#         yielded_batches.append(batch)

#     assert len(yielded_batches) == 3


# def test_total_records_returns_correct_totals(generate_test_data):
#     returned_data = {'inserted': generate_test_data(100),
#                      'existing': generate_test_data(0),
#                      'failed': generate_test_data(230)
#                      }
#     expected_result = {'inserted': 100,
#                        'existing': 0,
#                        'failed': 230,
#                        'total': 330,
#                        'batch_total': 330
#                        }
#     assert total_records(returned_data) == expected_result


# def test_total_records_returns_correct_totals_with_batches(generate_test_data):
#     returned_data = {'inserted': generate_test_data(0),
#                      'existing': generate_test_data(40),
#                      'failed': generate_test_data(920)
#                      }
#     previous_totals = {'inserted': 100,
#                        'existing': 0,
#                        'failed': 230,
#                        'total': 330,
#                        'batch_total': 100
#                        }
#     expected_result = {'inserted': 100,
#                        'existing': 40,
#                        'failed': 1150,
#                        'total': 1290,
#                        'batch_total': 960
#                        }
#     assert total_records(returned_data, previous_totals) == expected_result


# class TestProcessOrgs():
#     @staticmethod
#     @pytest.fixture
#     def valid_org_data():
#         return pd.DataFrame({'uuid': ['1-1', '2-2', '3-3'],
#                              'country_code': ['FRA', 'DEU', 'GBR'],
#                              'category_list': ['Data,Digital,Cats', 'Science,Cats', 'Data'],
#                              'category_group_list': ['Groups', 'More groups', 'extra group'],
#                              'city': ['Paris', 'Berlin', 'London']
#                              })

#     @staticmethod
#     @pytest.fixture
#     def invalid_org_data():
#         return pd.DataFrame({'uuid': ['1-1', '2-2', '3-3'],
#                              'country_code': ['FRI', 'DEU', 'GBR'],
#                              'category_list': ['Data,Digital,Dogs', 'Science,Cats,Goats', pd.np.nan],
#                              'category_group_list': ['Groups', 'More groups', 'extra group'],
#                              'city': [None, 'Berlin', 'London']
#                              })

#     @staticmethod
#     @pytest.fixture
#     def existing_orgs():
#         return {'2-2', '3-3'}

#     @staticmethod
#     @pytest.fixture
#     def no_existing_orgs():
#         return set()

#     @staticmethod
#     @pytest.fixture
#     def valid_cat_groups():
#         return pd.DataFrame({'id': ['A', 'B', 'C', 'D'],
#                              'category_name': ['data', 'digital', 'cats', 'science'],
#                              'category_group_list': ['Group', 'Groups', 'Grep', 'Grow']
#                              })

#     @staticmethod
#     @pytest.fixture
#     def valid_org_descs():
#         return pd.DataFrame({'uuid': ['3-3', '2-2', '1-1'],
#                              'description': ['org three', 'org two', 'org one']
#                              })

#     @staticmethod
#     @pytest.fixture
#     def invalid_org_descs():
#         return pd.DataFrame({'uuid': ['3-3', '2-2'],
#                              'description': ['org three', 'org two']
#                              })

#     def test_process_orgs_renames_uuid_column(self, valid_org_data, no_existing_orgs,
#                                               valid_cat_groups, valid_org_descs):
#         processed_orgs, _, _ = process_orgs(valid_org_data, no_existing_orgs, valid_cat_groups, valid_org_descs)
#         processed_orgs = pd.DataFrame(processed_orgs)

#         assert 'id' in processed_orgs
#         assert 'uuid' not in processed_orgs

#     def test_process_orgs_correctly_applies_country_name(self, valid_org_data, no_existing_orgs,
#                                                          valid_cat_groups, valid_org_descs):
#         processed_orgs, _, _ = process_orgs(valid_org_data, no_existing_orgs,
#                                             valid_cat_groups, valid_org_descs)
#         processed_orgs = pd.DataFrame(processed_orgs)
#         expected_result = pd.Series(['France', 'Germany', 'United Kingdom'])

#         assert_series_equal(processed_orgs['country'], expected_result, check_names=False)

#     def test_process_orgs_removes_country_code_column(self, valid_org_data, no_existing_orgs,
#                                                       valid_cat_groups, valid_org_descs):
#         processed_orgs, _, _ = process_orgs(valid_org_data, no_existing_orgs,
#                                             valid_cat_groups, valid_org_descs)
#         processed_orgs = pd.DataFrame(processed_orgs)

#         assert 'country_code' not in processed_orgs

#     def test_process_orgs_generates_location_id_composite_keys(self, valid_org_data, no_existing_orgs,
#                                                                valid_cat_groups, valid_org_descs):
#         processed_orgs, _, _ = process_orgs(valid_org_data, no_existing_orgs,
#                                             valid_cat_groups, valid_org_descs)
#         processed_orgs = pd.DataFrame(processed_orgs)
#         expected_result = pd.Series(['paris_france', 'berlin_germany', 'london_united-kingdom'])

#         assert_series_equal(processed_orgs.location_id, expected_result, check_names=False)

#     def test_process_orgs_inserts_none_if_composite_key_fails(self, invalid_org_data, no_existing_orgs,
#                                                               valid_cat_groups, valid_org_descs):
#         processed_orgs, _, _ = process_orgs(invalid_org_data, no_existing_orgs,
#                                             valid_cat_groups, valid_org_descs)
#         processed_orgs = pd.DataFrame(processed_orgs)
#         expected_result = pd.Series([None, 'berlin_germany', 'london_united-kingdom'])

#         assert_series_equal(processed_orgs.location_id, expected_result, check_names=False)

#     def test_process_orgs_generates_org_cats_link_table(self, valid_org_data, no_existing_orgs,
#                                                         valid_cat_groups, valid_org_descs):
#         _, org_cats, _ = process_orgs(valid_org_data, no_existing_orgs,
#                                       valid_cat_groups, valid_org_descs)
#         expected_result = [{'organization_id': '1-1', 'category_name': 'data'},
#                            {'organization_id': '1-1', 'category_name': 'digital'},
#                            {'organization_id': '1-1', 'category_name': 'cats'},
#                            {'organization_id': '2-2', 'category_name': 'science'},
#                            {'organization_id': '2-2', 'category_name': 'cats'},
#                            {'organization_id': '3-3', 'category_name': 'data'}
#                            ]

#         assert org_cats == expected_result

#     def test_process_orgs_returns_missing_cat_groups(self, invalid_org_data, no_existing_orgs,
#                                                      valid_cat_groups, valid_org_descs):
#         _, org_cats, missing_cat_groups = process_orgs(invalid_org_data, no_existing_orgs,
#                                                        valid_cat_groups, valid_org_descs)
#         expected_org_cats = [{'organization_id': '1-1', 'category_name': 'data'},
#                              {'organization_id': '1-1', 'category_name': 'digital'},
#                              {'organization_id': '1-1', 'category_name': 'dogs'},
#                              {'organization_id': '2-2', 'category_name': 'science'},
#                              {'organization_id': '2-2', 'category_name': 'cats'},
#                              {'organization_id': '2-2', 'category_name': 'goats'}
#                              ]
#         missing_cats = {c['category_name'] for c in missing_cat_groups}
#         expected_missing_cat_groups = {'dogs', 'goats'}

#         assert org_cats == expected_org_cats
#         assert missing_cats == expected_missing_cat_groups

#     def test_process_orgs_appends_long_descriptions(self, valid_org_data, no_existing_orgs,
#                                                     valid_cat_groups, valid_org_descs):
#         processed_orgs, _, _ = process_orgs(valid_org_data, no_existing_orgs,
#                                             valid_cat_groups, valid_org_descs)
#         processed_orgs = pd.DataFrame(processed_orgs)
#         expected_result = pd.DataFrame({'id': ['1-1', '2-2', '3-3'],
#                                         'long_description': ['org one', 'org two', 'org three']})

#         assert_frame_equal(processed_orgs[['id', 'long_description']], expected_result, check_like=True)

#     def test_process_orgs_inserts_none_for_unfound_long_descriptions(self, valid_org_data, no_existing_orgs,
#                                                                      valid_cat_groups, invalid_org_descs):
#         processed_orgs, _, _ = process_orgs(valid_org_data, no_existing_orgs,
#                                             valid_cat_groups, invalid_org_descs)
#         processed_orgs = pd.DataFrame(processed_orgs)
#         expected_result = pd.DataFrame({'id': ['1-1', '2-2', '3-3'],
#                                         'long_description': [None, 'org two', 'org three']})

#         assert_frame_equal(processed_orgs[['id', 'long_description']], expected_result, check_like=True)

#     def test_process_orgs_removes_redundant_category_columns(self, valid_org_data, no_existing_orgs,
#                                                              valid_cat_groups, valid_org_descs):
#         processed_orgs, _, _ = process_orgs(valid_org_data, no_existing_orgs,
#                                             valid_cat_groups, valid_org_descs)
#         processed_orgs = pd.DataFrame(processed_orgs)

#         assert 'category_list' not in processed_orgs
#         assert 'category_group_list' not in processed_orgs

#     def test_process_orgs_removes_existing_orgs(self, valid_org_data, existing_orgs,
#                                                 valid_cat_groups, valid_org_descs):
#         processed_orgs, _, _ = process_orgs(valid_org_data, existing_orgs,
#                                             valid_cat_groups, valid_org_descs)
#         processed_orgs = pd.DataFrame(processed_orgs)

#         expected_result = pd.Series(['1-1'])
#         assert_series_equal(processed_orgs['id'], expected_result, check_names=False)


# class TestProcessNonOrgs():
#     @staticmethod
#     @pytest.fixture
#     def valid_table():
#         return pd.DataFrame({'id': ['111', '222', '333'],
#                              'other': ['cat', 'dog', 'frog']})

#     @staticmethod
#     @pytest.fixture
#     def location_table():
#         return pd.DataFrame({'uuid': ['111', '222', '333'],
#                              'city': ['London', 'Paris', 'New York'],
#                              'country_code': ['GBR', 'FRA', 'USA']})

#     def test_process_non_orgs_renames_uuid_columns(self, valid_table):
#         expected_result = [{'id': '111', 'other': 'cat'},
#                            {'id': '222', 'other': 'dog'},
#                            {'id': '333', 'other': 'frog'}]

#         assert process_non_orgs(valid_table, set(), ['id']) == expected_result

#     def test_process_non_orgs_drops_existing_rows_with_one_primary_key(self, valid_table):
#         existing = {('111',), ('222',)}
#         pks = ['id']
#         expected_result = [{'id': '333', 'other': 'frog'}]

#         assert process_non_orgs(valid_table, existing, pks) == expected_result

#     def test_process_non_orgs_drops_existing_rows_with_multiple_primary_keys(self, valid_table):
#         existing = {('111', 'cat'), ('222', 'dog')}
#         pks = ['id', 'other']
#         expected_result = [{'id': '333', 'other': 'frog'}]

#         assert process_non_orgs(valid_table, existing, pks) == expected_result

#     def test_process_non_orgs_changes_nans_to_none(self):
#         df = pd.DataFrame({'uuid': ['111', '222', '333'],
#                            'other': [pd.np.nan, 'dog', None]})

#         expected_result = [{'id': '111', 'other': None},
#                            {'id': '222', 'other': 'dog'},
#                            {'id': '333', 'other': None}]

#         assert process_non_orgs(df, set(), ['id']) == expected_result

#     @mock.patch('nesta.packages.crunchbase.crunchbase_collect.generate_composite_key')
#     @mock.patch('nesta.packages.crunchbase.crunchbase_collect.country_iso_code_to_name')
#     def test_process_non_orgs_changes_country_code_column_name(self, mocked_iso_code,
#                                                                mocked_comp_key, location_table):
#         mocked_iso_code.side_effect = ['One', 'Two', 'Three']
#         mocked_comp_key.side_effect = ValueError

#         keys = {k for k, _ in process_non_orgs(location_table, set(), ['id'])[0].items()}

#         assert 'country_code' not in keys
#         assert 'country' in keys

#     @mock.patch('nesta.packages.crunchbase.crunchbase_collect.generate_composite_key')
#     @mock.patch('nesta.packages.crunchbase.crunchbase_collect.country_iso_code_to_name')
#     def test_process_non_orgs_calls_generate_composite_key_correctly(self, mocked_iso_code,
#                                                                      mocked_comp_key, location_table):
#         mocked_iso_code.side_effect = ['One', 'Two', 'Three']
#         mocked_comp_key.side_effect = ['london_one', 'paris_two', 'new-york_three']

#         expected_calls = [mock.call(city='London', country='One'),
#                           mock.call(city='Paris', country='Two'),
#                           mock.call(city='New York', country='Three')]

#         process_non_orgs(location_table, set(), ['id'])
#         assert mocked_comp_key.mock_calls == expected_calls

#     @mock.patch('nesta.packages.crunchbase.crunchbase_collect.generate_composite_key')
#     @mock.patch('nesta.packages.crunchbase.crunchbase_collect.country_iso_code_to_name')
#     def test_process_non_orgs_inserts_none_when_location_id_fails(self, mocked_iso_code,
#                                                                   mocked_comp_key, location_table):
#         mocked_iso_code.side_effect = ['One', 'Two', 'Three']
#         mocked_comp_key.side_effect = ValueError

#         expected_result = [{'id': '111', 'city': 'London', 'country': 'One', 'location_id': None},
#                            {'id': '222', 'city': 'Paris', 'country': 'Two', 'location_id': None},
#                            {'id': '333', 'city': 'New York', 'country': 'Three', 'location_id': None}]

#         assert process_non_orgs(location_table, set(), ['id']) == expected_result

#     @mock.patch('nesta.packages.crunchbase.crunchbase_collect.generate_composite_key')
#     @mock.patch('nesta.packages.crunchbase.crunchbase_collect.country_iso_code_to_name')
#     def test_process_non_orgs_inserts_location_comp_key(self, mocked_iso_code,
#                                                         mocked_comp_key, location_table):
#         mocked_iso_code.side_effect = ['One', 'Two', 'Three']
#         mocked_comp_key.side_effect = ['london_one', 'paris_two', 'new-york_three']

#         expected_result = [{'id': '111', 'city': 'London', 'country': 'One', 'location_id': 'london_one'},
#                            {'id': '222', 'city': 'Paris', 'country': 'Two', 'location_id': 'paris_two'},
#                            {'id': '333', 'city': 'New York', 'country': 'Three', 'location_id': 'new-york_three'}]

#         assert process_non_orgs(location_table, set(), ['id']) == expected_result

#     @mock.patch('nesta.packages.crunchbase.crunchbase_collect.bool_convert')
#     def test_process_non_orgs_converts_boolean_columns(self, mocked_bool_convert):
#         df = pd.DataFrame({'uuid': ['111', '222', '333'],
#                            'is_cool': ['t', 'f', 'bar']})

#         mocked_bool_convert.side_effect = [True, False, None]

#         expected_result = [{'id': '111', 'is_cool': True},
#                            {'id': '222', 'is_cool': False},
#                            {'id': '333', 'is_cool': None}]

#         assert process_non_orgs(df, set(), ['id']) == expected_result
