import pytest
from unittest import mock

from nesta.core.luigihacks.luigi_test_runner import luigi_test_runner
from nesta.core.luigihacks.luigi_test_runner import find_root_tasks
from nesta.core.luigihacks.luigi_test_runner import find_python_files
from nesta.core.luigihacks.luigi_test_runner import build_docker_image
from nesta.core.luigihacks.luigi_test_runner import containerised_database

from nesta.core.luigihacks.luigi_test_runner import docker
from nesta.core.luigihacks.luigi_test_runner import misctools
from nesta.core.luigihacks.luigi_test_runner import os


@mock.patch('nesta.core.luigihacks.luigi_test_runner.run_luigi_pipeline', autospec=True)
@mock.patch('nesta.core.luigihacks.luigi_test_runner.containerised_database')
@mock.patch('nesta.core.luigihacks.luigi_test_runner.build_docker_image', autospec=True)
@mock.patch('nesta.core.luigihacks.luigi_test_runner.find_root_tasks', autospec=True)
class TestTestRunner:
    @pytest.fixture
    def modules_to_find(self):
        return ['routines.mag.mag_root_task',
                'routines.crunchbase.crunchbase_root_task',
                'routines.nih.nih_root_task']

    def test_find_root_tasks_is_called_correctly(self,
                                                 mocked_find_root_tasks,
                                                 mocked_build_image,
                                                 mocked_database,
                                                 mocked_run_pipeline):
        luigi_test_runner(start_directory='routines')

        mocked_find_root_tasks.assert_called_once_with(start_directory='routines')

    def test_build_docker_image_is_called_with_branch_in_buildargs(self,
                                                                   mocked_find_root_tasks,
                                                                   mocked_build_image,
                                                                   mocked_database,
                                                                   mocked_run_pipeline):
        luigi_test_runner(start_directory='routines', branch='new_feature')

        buildargs = mocked_build_image.call_args[1]['buildargs']
        assert buildargs == {'GIT_TAG': 'new_feature'}

    def test_all_pipelines_are_run(self,
                                   mocked_find_root_tasks,
                                   mocked_build_image,
                                   mocked_database,
                                   mocked_run_pipeline,
                                   modules_to_find):
        mocked_find_root_tasks.return_value = modules_to_find
        expected_result = [mock.call(module) for module in modules_to_find]

        luigi_test_runner(start_directory='routines')

        assert mocked_run_pipeline.mock_calls == expected_result

    def test_all_pipelines_are_still_run_when_they_error(self,
                                                         mocked_find_root_tasks,
                                                         mocked_build_image,
                                                         mocked_database,
                                                         mocked_run_pipeline,
                                                         modules_to_find):
        mocked_find_root_tasks.return_value = modules_to_find
        mocked_run_pipeline.side_effect = [ValueError, ZeroDivisionError, None]

        luigi_test_runner(start_directory='routines')

        assert mocked_run_pipeline.call_count == 3


@mock.patch('nesta.core.luigihacks.luigi_test_runner.contains_root_task', autospec=True)
@mock.patch('nesta.core.luigihacks.luigi_test_runner.find_python_files', autospec=True)
class TestFindRootTasks:
    @pytest.fixture
    def paths_to_find(self):
        return ['routines/mag/mag_root_task.py',
                'routines/crunchbase/crunchbase_root_task.py',
                'routines/nih/nih_root_task.py']

    def test_all_found_tasks_are_returned_in_module_format(self,
                                                           mocked_find_python,
                                                           mocked_contains_root,
                                                           paths_to_find):
        mocked_find_python.return_value = paths_to_find
        mocked_contains_root.return_value = True
        expected_result = ['routines.mag.mag_root_task',
                           'routines.crunchbase.crunchbase_root_task',
                           'routines.nih.nih_root_task']

        result = find_root_tasks(start_directory='routines')

        assert result == expected_result

    def test_files_not_contining_root_tasks_are_excluded(self,
                                                         mocked_find_python,
                                                         mocked_contains_root,
                                                         paths_to_find):
        mocked_find_python.return_value = paths_to_find
        mocked_contains_root.side_effect = [True, False, True]

        result = find_root_tasks(start_directory='routines')

        assert len(result) == 2
        assert 'routines.crunchbase.crunchbase_root_task' not in result


@mock.patch('nesta.core.luigihacks.luigi_test_runner.glob.glob', autospec=True)
class TestFindPythonFiles:
    def test_glob_is_called_correctly(self, mocked_glob):
        find_python_files('subfolder/routines')

        mocked_glob.assert_called_once_with('subfolder/routines/**/*.py', recursive=True)

    def test_trailing_slash_is_removed_from_start_directory(self, mocked_glob):
        find_python_files('subfolder/routines/')

        assert mocked_glob.call_args[0][0] == 'subfolder/routines/**/*.py'


@mock.patch('nesta.core.luigihacks.luigi_test_runner.docker.from_env', autospec=True)
def test_docker_build_called_with_nocache_and_rm_options_set_to_true(mocked_docker):
    mocked_client = mock.Mock()
    mocked_client.images.build.return_value = None, []
    mocked_docker.return_value = mocked_client

    build_docker_image('test_tag:test')

    assert all(mocked_client.images.build.call_args[1][arg]
               for arg in ['nocache', 'rm'])


@mock.patch.object(os, 'environ', autospec=True)
@mock.patch.object(misctools, 'get_config', autospec=True)
@mock.patch.object(docker, 'from_env', autospec=True)
class TestCreateDatabase:
    def test_run_is_called_with_auto_remove_and_detatch(self,
                                                        mocked_docker,
                                                        mocked_get_config,
                                                        mocked_environ):
        mocked_client = mock.Mock()
        mocked_docker.return_value = mocked_client

        with containerised_database(name='testdb',
                                    db_config='DB_CONFIG',
                                    config_header='config_section'):
            pass

        assert all(mocked_client.containers.run.call_args[1][arg]
                   for arg in ['auto_remove', 'detach'])

    def test_run_is_called_with_correctly_formatted_config_from_file(self,
                                                                     mocked_docker,
                                                                     mocked_get_config,
                                                                     mocked_environ):
        config = dict(user='test_runner',
                      password='my_testing_pw',
                      host='some_ip',
                      port=1234,
                      version=1)
        mocked_get_config.return_value = config
        mocked_client = mock.Mock()
        mocked_docker.return_value = mocked_client
        database_name = 'testdb'

        with containerised_database(name=database_name,
                                    db_config='DB_CONFIG',
                                    config_header='config_section'):
            pass

        run_call_args = mocked_client.containers.run.call_args[0]
        run_call_kwargs = mocked_client.containers.run.call_args[1]

        assert run_call_kwargs['name'] == database_name
        assert run_call_kwargs['ports'] == {3306: 3306}
        assert run_call_kwargs['environment'] == {
            'MYSQL_ROOT_PASSWORD': config['password'],
            'MYSQL_DATABASE': 'dev'}
        assert f"mysql:{config['version']}" in run_call_args
