import pytest
from unittest import mock
from nesta.core.batchables.general.nih.sql2es import run

def test_datetime_to_date_complete():
    row = run.datetime_to_date({'project_start': '2020-01-01T00:00:00',
                                'project_end': '2021-02-03T00:00:00'})
    assert row == {'project_start': '2020-01-01',
                   'project_end': '2021-02-03'}


def test_datetime_to_date_incomplete():
    # Null dates allowed, also keys != project_start, project_end ignored
    row = run.datetime_to_date({'project_start': '2020-01-01T00:00:00',
                                'project_end': None,
                                'other': '2020-01-01T00:00:00'})
    assert row == {'project_start': '2020-01-01',
                   'project_end': None,
                   'other': '2020-01-01T00:00:00'}


def test_datetime_to_date_bad_date():
    with pytest.raises(ValueError):
        # Value of 12:00:00 doesn't match the expected 00:00:00
        row = run.datetime_to_date({'project_start': '2020-01-01T12:00:00',
                                    'project_end': None})


@mock.patch('nesta.core.batchables.general.nih.sql2es.run.datetime_to_date')
def test_reformat_row(mocked_dt2date):
    mocked_dt2date.side_effect = lambda x: x
    run.reformat_row({
        'project_start': '2020-01-01T00:00:00',
        'other': '2021-02-03T00:00:00',
        'yearly_funds':
        [
            {'project_start': '2020-01-01T00:00:00',
             'project_end': '2021-02-03T00:00:00'},
            {'project_start': '2020-01-01T00:00:00',
             'project_end': '2021-02-03T00:00:00'}
        ]
    })
    assert mocked_dt2date.call_count == 3
