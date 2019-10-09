import mock
import pytest
from collections import namedtuple

from nesta.packages.mag.fos_lookup import split_ids
from nesta.packages.mag.fos_lookup import build_fos_lookup
from nesta.packages.mag.fos_lookup import unique_index
from nesta.packages.mag.fos_lookup import find_index
from nesta.packages.mag.fos_lookup import UniqueList
from nesta.packages.mag.fos_lookup import make_fos_map
from nesta.packages.mag.fos_lookup import make_fos_nodes

PATH = 'nesta.packages.mag.fos_lookup.{}'

@pytest.fixture
def fos_map_large():
    return {0: [['Physics']], 
            1: [['Particle physics', 'Physics'], 
                ['Quantum electrodynamics', 'Physics']], 
            2: [['Elementary particle', 'Quantum electrodynamics'], 
                ['Supersymmetry', 'Quantum electrodynamics'], 
                ['Higgs boson', 'Quantum electrodynamics'], 
                ['Elementary particle', 'Particle physics'], 
                ['Supersymmetry', 'Particle physics'], 
                ['Higgs boson', 'Particle physics']], 
            3: [['Superpartner', 'Elementary particle'], 
                ['Superpartner', 'Supersymmetry'], 
                ['Neutralino', 'Supersymmetry'], 
                ['Superpartner', 'Higgs boson'], 
                ['Neutralino', 'Higgs boson']]}

@pytest.fixture
def fos_map():
    return {0: [['Physics']],
            1: [['Particle physics', 'Physics'],
                ['Quantum electrodynamics', 'Physics']],
            2: [['Elementary particle', 'Particle physics'],
                ['Elementary particle', 'Quantum electrodynamics'],
                ['Higgs boson', 'Quantum electrodynamics']]}

@pytest.fixture
def fos_nodes():
    return {'nodes': {'0': {'0': 'Physics'},
                      '1': {'0': 'Particle physics',
                            '1': 'Quantum electrodynamics'},
                      '2': {'0': 'Elementary particle',
                            '1': 'Higgs boson'}},
            'links': [[[0,0], [1,0]],
                      [[0,0], [1,1]],
                      [[1,0], [2,0]],
                      [[1,1], [2,0]],
                      [[1,1], [2,1]]]}

    # {'nodes': {'0': {'0': 'Physics'}, 
    #            '1': {'0': 'Particle physics', 
    #                  '1': 'Quantum electrodynamics'}, 
    #            '2': {'0': 'Elementary particle', 
    #                  '1': 'Elementary particle', 
    #                  '2': 'Higgs boson'}}, 
    #  'links': [[[1, 1], [2, 2]], 
    #            [[1, 1], [2, 1]], 
    #            [[1, 0], [2, 0]], 
    #            [[0, 0], [1, 1]], 
    #            [[0, 0], [1, 0]]]}



class Tmp:
    def __init__(self, id, child_ids):
        self.id = id
        self.child_ids = child_ids
        self.name = f'name-of-{id}'

def test_split_ids():
    assert split_ids(None) == set()
    assert split_ids('1,1,3,4') == set([1,1,3,4])

@mock.patch('nesta.packages.mag.fos_lookup.db_session')
def test_build_fos_lookup(mocked_session):
    fields_of_study = [Tmp(i, ','.join(str(x) 
                                       for x in range(i+1,i+3)))
                       for i in range(0,5)]

    mocked_session().__enter__().query().filter().all.return_value = fields_of_study

    fos_lookup = build_fos_lookup(None)
    for (pid, cid), (pname, cname) in fos_lookup.items():
        assert pname == f'name-of-{pid}'
        assert cname == f'name-of-{cid}'
        assert pid != cid        

def test_UniqueList():
    unique_list = UniqueList()
    normal_list = list()
    for i in list(range(0, 3)) + list(range(1, 5)):
        unique_list.append(i)
        normal_list.append(i)
    assert set(unique_list) == set(normal_list)
    assert len(unique_list) < len(normal_list)

#@mock.patch(PATH.format('UniqueList', return_value=[])
def test_unique_index():
    data = [['a','b'],['a','c'],['b','d'],
            ['b','a'],['c','d'],['a','d']]
    assert unique_index('a', data) == 0
    assert unique_index('b', data) == 1
    assert unique_index('c', data) == 2
    with pytest.raises(ValueError):
        assert unique_index('d', data)
    with pytest.raises(ValueError):
        assert unique_index('blah', data)

                           
def test_find_index(fos_map_large):
    assert find_index('Physics', fos_map_large) == (0, 0)
    assert find_index('Particle physics', fos_map_large) == (1, 0)
    assert find_index('Quantum electrodynamics', fos_map_large) == (1, 1)
    assert find_index('Elementary particle', fos_map_large) == (2, 0)
    assert find_index('Supersymmetry', fos_map_large) == (2, 1)
    assert find_index('Higgs boson', fos_map_large) == (2, 2)
    assert find_index('Superpartner', fos_map_large) == (3, 0)
    assert find_index('Neutralino', fos_map_large) == (3, 1)


def test_make_fos_map(fos_map):
    fos_rows = [{'id': 1, 'child_ids': '2,3', 'level': 0, 'parent_ids':None},
                {'id': 2, 'child_ids': '4', 'level': 1, 'parent_ids':'1'},
                {'id': 3, 'child_ids': '4,5', 'level': 1, 'parent_ids':'1'},
                {'id': 4, 'child_ids': None, 'level': 2, 'parent_ids':'2,3'},
                {'id': 5, 'child_ids': None, 'level': 2, 'parent_ids':'3'}]
    
    fos_lookup = {(1, 2): ('Physics','Particle physics'),
                  (1, 3): ('Physics','Quantum electrodynamics'),
                  (2, 4): ('Particle physics','Elementary particle'),
                  (3, 4): ('Quantum electrodynamics',
                               'Elementary particle'),
                  (3, 5): ('Quantum electrodynamics','Higgs boson')}

    print(make_fos_map(fos_rows, fos_lookup))
    print(fos_map)

    assert make_fos_map(fos_rows, fos_lookup) == fos_map


def test_make_fos_nodes(fos_map, fos_nodes):    
    print(make_fos_nodes(fos_map))
    assert make_fos_nodes(fos_map) == fos_nodes
