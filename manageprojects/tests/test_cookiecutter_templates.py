import filecmp
import inspect
import json
from pathlib import Path

import yaml
from bx_py_utils.environ import OverrideEnviron
from bx_py_utils.path import assert_is_dir, assert_is_file
from bx_py_utils.test_utils.datetime import parse_dt

from manageprojects.cookiecutter_templates import start_managed_project, update_managed_project
from manageprojects.data_classes import (
    CookiecutterResult,
    GenerateTemplatePatchResult,
    ManageProjectsMeta,
)
from manageprojects.tests.base import BaseTestCase
from manageprojects.tests.utilities.fixtures import copy_fixtures
from manageprojects.tests.utilities.git_utils import init_git
from manageprojects.utilities.pyproject_toml import PyProjectToml
from manageprojects.utilities.temp_path import TemporaryDirectory


class CookiecutterTemplatesTestCase(BaseTestCase):
    def test_start_managed_project(self):
        repro_name = 'mp_test_template1'
        cookiecutter_template = f'https://github.com/jedie/{repro_name}/'
        directory = 'test_template1'

        with TemporaryDirectory(prefix='manageprojects_') as main_temp_path:
            replay_dir_path = main_temp_path / '.cookiecutter_replay'
            replay_dir_path.mkdir()

            cookiecutters_dir = main_temp_path / '.cookiecutters'
            config = {
                'cookiecutters_dir': str(cookiecutters_dir),
                'replay_dir': str(replay_dir_path),
            }
            config_yaml = yaml.dump(config)
            config_file_path = main_temp_path / 'cookiecutter_config.yaml'
            config_file_path.write_text(config_yaml)

            replay_file_path = replay_dir_path / f'{directory}.json'
            cookiecutter_output_dir = main_temp_path / 'cookiecutter_output_dir'
            assert replay_file_path.exists() is False
            assert cookiecutter_output_dir.exists() is False
            assert cookiecutters_dir.exists() is False

            result: CookiecutterResult = start_managed_project(
                template=cookiecutter_template,
                output_dir=cookiecutter_output_dir,
                no_input=True,
                directory=directory,
                config_file=config_file_path,
                extra_context={
                    'dir_name': 'a_dir_name',
                    'file_name': 'a_file_name',
                },
            )
            self.assertIsInstance(result, CookiecutterResult)
            git_path = cookiecutters_dir / repro_name
            self.assertEqual(result.git_path, git_path)
            assert_is_dir(git_path)  # Checkout was made?
            assert_is_dir(cookiecutter_output_dir)  # Created from cookiecutter ?

            # Cookiecutter creates a replay JSON?
            assert_is_file(replay_file_path)
            replay_json = replay_file_path.read_text()
            replay_data = json.loads(replay_json)
            assert replay_data == {
                'cookiecutter': {
                    'dir_name': 'a_dir_name',
                    'file_name': 'a_file_name',
                    '_template': cookiecutter_template,
                    '_output_dir': str(cookiecutter_output_dir),
                }
            }

            # Our replay config was used?
            assert_is_file(cookiecutter_output_dir / 'a_dir_name' / 'a_file_name.py')

            project_path = cookiecutter_output_dir / 'a_dir_name'

            # pyproject.toml created?
            toml = PyProjectToml(project_path=project_path)
            result: ManageProjectsMeta = toml.get_mp_meta()
            self.assertIsInstance(result, ManageProjectsMeta)
            self.assertEqual(
                result,
                ManageProjectsMeta(
                    initial_revision='42f18f3',
                    initial_date=parse_dt('2022-11-02T19:40:09+01:00'),
                    applied_migrations=[],
                    cookiecutter_template='https://github.com/jedie/mp_test_template1/',
                    cookiecutter_directory='test_template1',
                    cookiecutter_context={
                        'cookiecutter': {
                            'dir_name': 'a_dir_name',
                            'file_name': 'a_file_name',
                            '_template': 'https://github.com/jedie/mp_test_template1/',
                        }
                    },
                ),
            )

    def test_update_project1(self):
        with TemporaryDirectory(prefix='test_start_project_') as main_temp_path:

            cookiecutter_directory = 'cookiecutter_directory'
            template_path = main_temp_path / cookiecutter_directory
            template_file_path = (
                template_path / '{{cookiecutter.dir_name}}' / '{{cookiecutter.file_name}}.py'
            )

            new_file_path = template_path / '{{cookiecutter.dir_name}}' / 'new_file.py'

            cookiecutter_destination = main_temp_path / 'cookiecutter_output_dir'
            project_path = cookiecutter_destination / 'default_directory_name'
            destination_file_path = project_path / 'default_file_name.py'
            pyproject_toml_path = project_path / 'pyproject.toml'

            #########################################################################
            # copy existing cookiecutter template to /tmp/:

            copy_fixtures(
                fixtures_dir_name='cookiecutter_simple_template_rev1',
                destination=template_path,
            )
            assert_is_file(template_file_path)

            #########################################################################
            # Make git repro and commit the current state:

            template_git, git_hash1 = init_git(template_path)
            self.assertEqual(len(git_hash1), 7)

            file_paths = template_git.ls_files(verbose=False)
            expected_paths = [
                Path(template_path / 'cookiecutter.json'),
                template_file_path,
            ]
            self.assertEqual(file_paths, expected_paths)

            #########################################################################
            # start project in /tmp/:

            replay_dir_path = main_temp_path / '.cookiecutter_replay'
            replay_dir_path.mkdir()

            cookiecutters_dir = main_temp_path / '.cookiecutters'
            config = {
                'cookiecutters_dir': str(cookiecutters_dir),
                'replay_dir': str(replay_dir_path),
            }
            config_yaml = yaml.dump(config)
            config_file_path = main_temp_path / 'cookiecutter_config.yaml'
            config_file_path.write_text(config_yaml)

            replay_file_path = replay_dir_path / f'{cookiecutter_directory}.json'

            self.assertFalse(cookiecutter_destination.exists())
            self.assertFalse(cookiecutters_dir.exists())
            self.assertFalse(replay_file_path.exists())
            self.assertFalse(project_path.exists())

            from manageprojects.cli import start_project  # import loops

            result: CookiecutterResult = start_project(
                template=str(template_path),
                output_dir=cookiecutter_destination,
                no_input=True,
                # directory=cookiecutter_directory,
                config_file=config_file_path,
            )

            assert_is_dir(project_path)
            self.assertFalse(cookiecutters_dir.exists())  # no git clone, because local repo?
            assert_is_file(replay_file_path)

            self.assertIsInstance(result, CookiecutterResult)
            self.assertEqual(result.git_path, template_path)

            # Cookiecutter creates a replay JSON?
            assert_is_file(replay_file_path)
            replay_json = replay_file_path.read_text()
            replay_data = json.loads(replay_json)
            self.assertDictEqual(
                replay_data,
                {
                    'cookiecutter': {  # All template defaults:
                        'dir_name': 'default_directory_name',
                        'file_name': 'default_file_name',
                        'value': 'default_value',
                        '_template': str(template_path),
                        '_output_dir': str(cookiecutter_destination),
                    }
                },
            )

            # Check created file:
            assert_is_file(destination_file_path)
            filecmp.cmp(destination_file_path, template_file_path)

            # Check created toml file:
            toml = PyProjectToml(project_path=project_path)
            meta = toml.get_mp_meta()
            self.assertIsInstance(meta, ManageProjectsMeta)
            self.assertEqual(meta.initial_revision, git_hash1)
            self.assertEqual(meta.applied_migrations, [])
            self.assertEqual(meta.cookiecutter_template, str(template_path))
            self.assertEqual(meta.cookiecutter_directory, None)
            self.assert_datetime_now_range(meta.initial_date, max_diff_sec=5)

            # Create a git, with this state
            init_git(cookiecutter_destination, comment='Project start')

            #########################################################################
            # Change the source template and update the existing project

            # Add a new template file:
            new_file_path.write_text('print("This is a new added file in template rev2')
            template_git.add('.', verbose=False)
            template_git.commit('Add a new file', verbose=False)
            git_hash2 = template_git.get_current_hash(verbose=False)

            # Change a existing file:
            with template_file_path.open('a') as f:
                f.write('\n# This comment was added in rev2 ;)\n')
            template_git.add('.', verbose=False)
            template_git.commit('Update existing file', verbose=False)
            git_hash3 = template_git.get_current_hash(verbose=False)

            log_lines = template_git.log(format='%h - %s', verbose=False)
            self.assertEqual(
                log_lines,
                [
                    f'{git_hash3} - Update existing file',
                    f'{git_hash2} - Add a new file',
                    f'{git_hash1} - The initial commit ;)',
                ],
            )

            #########################################################################
            # update the existing project

            self.assert_file_content(destination_file_path, "print('Hello World: default_value')")
            self.assert_toml(
                pyproject_toml_path,
                expected={
                    'manageprojects': {
                        'initial_revision': meta.initial_revision,
                        'initial_date': meta.initial_date,
                        'cookiecutter_template': str(template_path),
                        'cookiecutter_context': {
                            'cookiecutter': {
                                'dir_name': 'default_directory_name',
                                'file_name': 'default_file_name',
                                'value': 'default_value',
                                '_template': str(template_path),
                            }
                        },
                    }
                },
            )

            with OverrideEnviron(XDG_CONFIG_HOME=str(main_temp_path)):
                update_result = update_managed_project(
                    project_path=project_path,
                    config_file=config_file_path,
                    cleanup=False,  # Keep temp files if this test fails, for better debugging
                    no_input=True,  # No user input in tests ;)
                )
            self.assertIsInstance(update_result, GenerateTemplatePatchResult)

            self.assert_file_content(
                destination_file_path,
                inspect.cleandoc(
                    '''
                    print('Hello World: default_value')

                    # This comment was added in rev2 ;)
                    '''
                ),
            )

            self.assert_toml(
                pyproject_toml_path,
                expected={
                    'manageprojects': {
                        'initial_revision': meta.initial_revision,
                        'initial_date': meta.initial_date,
                        'cookiecutter_template': str(template_path),
                        'applied_migrations': [git_hash3],
                        'cookiecutter_context': {
                            'cookiecutter': {
                                'dir_name': 'default_directory_name',
                                'file_name': 'default_file_name',
                                'value': 'default_value',
                                '_template': str(template_path),
                            }
                        },
                    }
                },
            )

    def test_update_project2(self):
        cookiecutter_context = {
            'dir_name': 'a_directory',
            'file_name': 'a_file_name',
            'value': 'FooBar',
        }
        context = {'cookiecutter': cookiecutter_context}

        with TemporaryDirectory(prefix='test_generate_template_patch_') as main_temp_path:
            project_path = main_temp_path / 'main_temp_path'
            dst_file_path = project_path / 'a_directory' / 'a_file_name.py'

            template_path = main_temp_path / 'template'
            template_dir_name = 'template_dir'
            template_dir_path = template_path / template_dir_name
            config_file_path = template_dir_path / 'cookiecutter.json'

            test_file_path = (
                template_dir_path / '{{cookiecutter.dir_name}}' / '{{cookiecutter.file_name}}.py'
            )

            dst_file_path.parent.mkdir(parents=True)
            dst_file_path.write_text('# This is a test line, not changed')

            config_file_path.parent.mkdir(parents=True)
            config_file_path.write_text(json.dumps(cookiecutter_context))

            project_git, project_from_rev = init_git(project_path, comment='Git init project.')
            dst_file_path.write_text(
                inspect.cleandoc(
                    '''
                    # This is a test line, not changed
                    #
                    # Revision 1
                    #
                    # The same cookiecutter value:
                    print('Test: FooBar')
                    '''
                )
            )
            project_git.add('.')
            project_git.commit('Store revision 1')

            test_file_path.parent.mkdir(parents=True)
            test_file_path.write_text(
                inspect.cleandoc(
                    '''
                    # This is a test line, not changed
                    #
                    # Revision 1
                    #
                    # The same cookiecutter value:
                    print('Test: {{ cookiecutter.value }}')
                    '''
                )
            )

            git, from_rev = init_git(template_path, comment='Git init template.')
            from_date = git.get_commit_date(verbose=False)

            toml = PyProjectToml(project_path=project_path)
            toml.init(
                revision=from_rev,
                dt=from_date,
                template=str(template_path),
                directory=template_dir_name,
            )
            toml.create_or_update_cookiecutter_context(context=context)
            toml.save()
            toml_content = toml.path.read_text()
            self.assertIn('# Created by manageprojects', toml_content)
            self.assertIn(
                '[manageprojects] # https://github.com/jedie/manageprojects', toml_content
            )
            self.assertIn(f'initial_revision = "{from_rev}"', toml_content)
            self.assertIn(f'cookiecutter_template = "{template_path}"', toml_content)

            test_file_path.write_text(
                inspect.cleandoc(
                    '''
                    # This is a test line, not changed
                    #
                    # Revision 2
                    #
                    # The same cookiecutter value:
                    print('Test: {{ cookiecutter.value }}')
                    '''
                )
            )
            git.add('.', verbose=False)
            git.commit('Template rev 2', verbose=False)
            to_rev = git.get_current_hash(verbose=False)
            to_date = git.get_commit_date(verbose=False)
            assert to_date

            patch_file_path = Path(
                main_temp_path,
                'repo_path',
                '.manageprojects',
                'patches',
                f'{from_rev}_{to_rev}.patch',
            )
            self.assertFalse(patch_file_path.exists())

            result = update_managed_project(
                project_path=project_path,
                password=None,
                config_file=config_file_path,
                cleanup=False,  # Keep temp files if this test fails, for better debugging
                no_input=True,  # No user input in tests ;)
            )

            self.assert_file_content(
                dst_file_path,
                inspect.cleandoc(
                    '''
                    # This is a test line, not changed
                    #
                    # Revision 2
                    #
                    # The same cookiecutter value:
                    print('Test: FooBar')
                    '''
                ),
            )

            self.assertIsInstance(result, GenerateTemplatePatchResult)
            patch_file_path = Path(
                project_path,
                '.manageprojects',
                'patches',
                f'{result.from_rev}_{result.to_rev}.patch',
            )
            assert_is_file(patch_file_path)
            patch_temp_path = result.compiled_to_path.parent
            self.assertEqual(
                result,
                GenerateTemplatePatchResult(
                    repo_path=template_dir_path,
                    patch_file_path=patch_file_path,
                    from_rev=from_rev,
                    compiled_from_path=patch_temp_path / f'{result.from_rev}_compiled',
                    to_rev=to_rev,
                    to_commit_date=to_date,
                    compiled_to_path=patch_temp_path / 'to_rev_compiled',
                ),
            )
