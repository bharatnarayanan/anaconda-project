from __future__ import absolute_import, print_function

import os
import platform
import pytest

import project.internal.conda_api as conda_api

from project.internal.test.tmpfile_utils import with_directory_contents

if platform.system() == 'Windows':
    PYTHON_BINARY = "python.exe"
    IPYTHON_BINARY = "Scripts\ipython.exe"
else:
    PYTHON_BINARY = "bin/python"
    IPYTHON_BINARY = "bin/ipython"


def test_conda_info():
    json = conda_api.info()

    print(repr(json))  # pytest shows this on failure
    assert isinstance(json, dict)

    # check that some stuff is in here.
    # conda apparently doesn't guarantee that any of this is here,
    # but if it changes I guess we'd like to know via test failure.
    assert 'channels' in json
    assert 'root_prefix' in json
    assert 'platform' in json
    assert 'envs' in json


def test_conda_create_and_install():
    def do_test(dirname):
        envdir = os.path.join(dirname, "myenv")
        # don't specify a python version so we use the one we already have
        # in the root env, otherwise this might take forever.
        conda_api.create(prefix=envdir, pkgs=['python'])

        assert os.path.isdir(envdir)
        assert os.path.isdir(os.path.join(envdir, "conda-meta"))
        assert os.path.exists(os.path.join(envdir, PYTHON_BINARY))

        # test that if it exists we can't create it again
        with pytest.raises(conda_api.CondaEnvExistsError) as excinfo:
            conda_api.create(prefix=envdir, pkgs=['python'])
        assert 'already exists' in repr(excinfo.value)

        # test that we can install a package
        assert not os.path.exists(os.path.join(envdir, IPYTHON_BINARY))
        conda_api.install(prefix=envdir, pkgs=['ipython'])
        assert os.path.exists(os.path.join(envdir, IPYTHON_BINARY))

    with_directory_contents(dict(), do_test)


def test_conda_create_no_packages():
    def do_test(dirname):
        envdir = os.path.join(dirname, "myenv")

        with pytest.raises(TypeError) as excinfo:
            conda_api.create(prefix=envdir, pkgs=[])
        assert 'must specify a list' in repr(excinfo.value)

    with_directory_contents(dict(), do_test)


def test_conda_create_bad_package():
    def do_test(dirname):
        envdir = os.path.join(dirname, "myenv")

        with pytest.raises(conda_api.CondaError) as excinfo:
            conda_api.create(prefix=envdir, pkgs=['this_is_not_a_real_package'])
        # print this because pytest truncates it
        print("bad package excinfo.value: " + repr(excinfo.value))
        # at some point conda changed this error message
        assert ('No packages found' in repr(excinfo.value) or 'Package missing in current' in repr(excinfo.value))
        assert 'this_is_not_a_real_package' in repr(excinfo.value)

    with_directory_contents(dict(), do_test)


def test_conda_install_no_packages():
    def do_test(dirname):
        envdir = os.path.join(dirname, "myenv")

        conda_api.create(prefix=envdir, pkgs=['python'])

        with pytest.raises(TypeError) as excinfo:
            conda_api.install(prefix=envdir, pkgs=[])
        assert 'must specify a list' in repr(excinfo.value)

    with_directory_contents(dict(), do_test)


def test_conda_invoke_fails(monkeypatch):
    def mock_popen(args, stdout=None, stderr=None):
        raise OSError("failed to exec")

    def do_test(dirname):
        monkeypatch.setattr('subprocess.Popen', mock_popen)
        with pytest.raises(conda_api.CondaError) as excinfo:
            conda_api.info()
        assert 'failed to exec' in repr(excinfo.value)
        assert 'conda info' in repr(excinfo.value)

    with_directory_contents(dict(), do_test)


def test_conda_invoke_nonzero_returncode(monkeypatch):
    def get_failed_command(extra_args):
        return ["bash", "-c", "echo TEST_ERROR 1>&2 && false"]

    def do_test(dirname):
        monkeypatch.setattr('project.internal.conda_api._get_conda_command', get_failed_command)
        with pytest.raises(conda_api.CondaError) as excinfo:
            conda_api.info()
        assert 'TEST_ERROR' in repr(excinfo.value)

    with_directory_contents(dict(), do_test)


def test_conda_invoke_zero_returncode_with_stuff_on_stderr(monkeypatch, capsys):
    def get_command(extra_args):
        return ["bash", "-c", "echo TEST_ERROR 1>&2 && echo '{}' || true"]

    def do_test(dirname):
        monkeypatch.setattr('project.internal.conda_api._get_conda_command', get_command)
        conda_api.info()
        (out, err) = capsys.readouterr()
        assert 'Conda: TEST_ERROR\n' == err

    with_directory_contents(dict(), do_test)


def test_conda_invoke_zero_returncode_with_invalid_json(monkeypatch, capsys):
    def get_command(extra_args):
        return ["echo", "NOT_JSON"]

    def do_test(dirname):
        monkeypatch.setattr('project.internal.conda_api._get_conda_command', get_command)
        with pytest.raises(conda_api.CondaError) as excinfo:
            conda_api.info()
        assert 'Invalid JSON from conda' in repr(excinfo.value)

    with_directory_contents(dict(), do_test)


def test_conda_create_gets_channels(monkeypatch):
    def mock_call_conda(extra_args):
        assert ['create', '--yes', '--quiet', '--prefix', '/prefix', '--channel', 'foo', 'python'] == extra_args

    monkeypatch.setattr('project.internal.conda_api._call_conda', mock_call_conda)
    conda_api.create(prefix='/prefix', pkgs=['python'], channels=['foo'])


def test_conda_install_gets_channels(monkeypatch):
    def mock_call_conda(extra_args):
        assert ['install', '--yes', '--quiet', '--prefix', '/prefix', '--channel', 'foo', 'python'] == extra_args

    monkeypatch.setattr('project.internal.conda_api._call_conda', mock_call_conda)
    conda_api.install(prefix='/prefix', pkgs=['python'], channels=['foo'])


def test_resolve_root_prefix():
    prefix = conda_api.resolve_env_to_prefix('root')
    assert prefix is not None
    assert os.path.isdir(prefix)


def test_resolve_named_env(monkeypatch):
    def mock_info():
        return {'root_prefix': '/foo', 'envs': ['/foo/envs/bar']}

    monkeypatch.setattr('project.internal.conda_api.info', mock_info)
    prefix = conda_api.resolve_env_to_prefix('bar')
    assert "/foo/envs/bar" == prefix


def test_resolve_bogus_env(monkeypatch):
    def mock_info():
        return {'root_prefix': '/foo', 'envs': ['/foo/envs/bar']}

    monkeypatch.setattr('project.internal.conda_api.info', mock_info)
    prefix = conda_api.resolve_env_to_prefix('nope')
    assert prefix is None


def test_resolve_env_prefix_from_dirname():
    prefix = conda_api.resolve_env_to_prefix('/foo/bar')
    assert "/foo/bar" == prefix


def test_installed():
    def check_installed(dirname):
        expected = {
            'numexpr': ('numexpr', '2.4.4', 'np110py27_0'),
            'portaudio': ('portaudio', '19', '0'),
            'unittest2': ('unittest2', '0.5.1', 'py27_1'),
            'websocket': ('websocket', '0.2.1', 'py27_0'),
            'ipython-notebook': ('ipython-notebook', '4.0.4', 'py27_0')
        }

        installed = conda_api.installed(dirname)
        assert expected == installed

    files = {
        'conda-meta/websocket-0.2.1-py27_0.json': "",
        'conda-meta/unittest2-0.5.1-py27_1.json': "",
        'conda-meta/portaudio-19-0.json': "",
        'conda-meta/numexpr-2.4.4-np110py27_0.json': "",
        # note that this has a hyphen in package name
        'conda-meta/ipython-notebook-4.0.4-py27_0.json': "",
        'conda-meta/not-a-json-file.txt': "",
        'conda-meta/json_file_without_proper_name_structure.json': ""
    }

    with_directory_contents(files, check_installed)


def test_installed_on_nonexistent_prefix():
    installed = conda_api.installed("/this/does/not/exist")
    assert dict() == installed


def test_installed_no_conda_meta():
    def check_installed(dirname):
        installed = conda_api.installed(dirname)
        assert dict() == installed

    with_directory_contents(dict(), check_installed)


def test_installed_cannot_list_dir(monkeypatch):
    def mock_listdir(dirname):
        raise OSError("cannot list this")

    monkeypatch.setattr("os.listdir", mock_listdir)
    with pytest.raises(conda_api.CondaError) as excinfo:
        conda_api.installed("/this/does/not/exist")
    assert 'cannot list this' in repr(excinfo.value)


def test_set_conda_env_in_path_unix(monkeypatch):
    import platform
    if platform.system() == 'Windows':

        def mock_system():
            return 'Linux'

        monkeypatch.setattr('platform.system', mock_system)

        monkeypatch.setattr('os.pathsep', ':')

    def check_conda_env_in_path_unix(dirname):
        env1 = os.path.join(dirname, "env1")
        os.makedirs(os.path.join(env1, "conda-meta"))
        env1bin = os.path.join(env1, "bin")
        os.makedirs(env1bin)
        env2 = os.path.join(dirname, "env2")
        os.makedirs(os.path.join(env2, "conda-meta"))
        env2bin = os.path.join(env2, "bin")
        os.makedirs(env2bin)
        notenv = os.path.join(dirname, "notenv")
        notenvbin = os.path.join(notenv, "bin")
        os.makedirs(notenvbin)

        # add env to empty path
        path = conda_api.set_conda_env_in_path("", env1)
        assert env1bin == path
        # add env that's already there
        path = conda_api.set_conda_env_in_path(env1bin, env1)
        assert env1bin == path
        # we can set a non-env because we don't waste time checking it
        path = conda_api.set_conda_env_in_path("", notenv)
        assert notenvbin == path
        # add an env to a non-env
        path = conda_api.set_conda_env_in_path(notenvbin, env1)
        assert (env1bin + os.pathsep + notenvbin) == path
        # add an env to another env
        path = conda_api.set_conda_env_in_path(env1bin, env2)
        assert env2bin == path
        # replace an env that wasn't at the front
        path = conda_api.set_conda_env_in_path(notenvbin + os.pathsep + env2bin, env1)
        assert (env1bin + os.pathsep + notenvbin) == path
        # keep a bunch of random stuff
        random_stuff = "foo:bar/:/baz/boo/"
        path = conda_api.set_conda_env_in_path(random_stuff, env1)
        assert (env1bin + os.pathsep + random_stuff) == path

    with_directory_contents(dict(), check_conda_env_in_path_unix)


def _windows_monkeypatch(monkeypatch):
    import platform
    if platform.system() != 'Windows':

        def mock_system():
            return 'Windows'

        monkeypatch.setattr('platform.system', mock_system)

        monkeypatch.setattr('os.pathsep', ';')

        from os.path import dirname as real_dirname

        def mock_dirname(path):
            replaced = path.replace("\\", "/")
            return real_dirname(replaced)

        monkeypatch.setattr('os.path.dirname', mock_dirname)

        def mock_join(path, *more):
            for m in more:
                if not (path.endswith("\\") or path.endswith("/")):
                    path = path + "\\"
                if m.startswith("\\") or m.startswith("/"):
                    m = m[1:]
                path = path + m
            return path.replace("\\", "/")

        monkeypatch.setattr('os.path.join', mock_join)

        from os import makedirs as real_makedirs

        def mock_makedirs(path, mode=int('0777', 8), exist_ok=True):
            return real_makedirs(path.replace("\\", "/"), mode, exist_ok)

        monkeypatch.setattr('os.makedirs', mock_makedirs)

        from os.path import isdir as real_isdir

        def mock_isdir(path):
            return real_isdir(path.replace("\\", "/"))

        monkeypatch.setattr('os.path.isdir', mock_isdir)


def test_set_conda_env_in_path_windows(monkeypatch):
    def check_conda_env_in_path_windows(dirname):
        _windows_monkeypatch(monkeypatch)

        scripts = "Scripts"
        library = "Library\\bin"

        env1 = os.path.join(dirname, "env1")
        os.makedirs(os.path.join(env1, "conda-meta"))
        env1scripts = os.path.join(env1, scripts)
        os.makedirs(env1scripts)
        env1lib = os.path.join(env1, library)
        os.makedirs(env1lib)

        env1path = "%s;%s;%s" % (env1, env1scripts, env1lib)

        env2 = os.path.join(dirname, "env2")
        os.makedirs(os.path.join(env2, "conda-meta"))
        env2scripts = os.path.join(env2, scripts)
        os.makedirs(env2scripts)
        env2lib = os.path.join(env2, library)
        os.makedirs(env2lib)

        env2path = "%s;%s;%s" % (env2, env2scripts, env2lib)

        notenv = os.path.join(dirname, "notenv")
        notenvscripts = os.path.join(notenv, scripts)
        os.makedirs(notenvscripts)
        notenvlib = os.path.join(notenv, library)
        os.makedirs(notenvlib)

        notenvpath = "%s;%s;%s" % (notenv, notenvscripts, notenvlib)

        # add env to empty path
        path = conda_api.set_conda_env_in_path("", env1)
        assert env1path == path
        # add env that's already there
        path = conda_api.set_conda_env_in_path(env1path, env1)
        assert env1path == path
        # we can set a non-env because we don't waste time checking it
        path = conda_api.set_conda_env_in_path("", notenv)
        assert notenvpath == path
        # add an env to a non-env
        path = conda_api.set_conda_env_in_path(notenvpath, env1)
        assert (env1path + os.pathsep + notenvpath) == path
        # add an env to another env
        path = conda_api.set_conda_env_in_path(env1path, env2)
        assert env2path == path
        # replace an env that wasn't at the front
        path = conda_api.set_conda_env_in_path(notenvpath + os.pathsep + env2path, env1)
        assert (env1path + os.pathsep + notenvpath) == path
        # keep a bunch of random stuff
        random_stuff = "foo;bar;/baz/boo"
        path = conda_api.set_conda_env_in_path(random_stuff, env1)
        assert (env1path + os.pathsep + random_stuff) == path

    with_directory_contents(dict(), check_conda_env_in_path_windows)


def test_set_conda_env_in_path_windows_trailing_slashes(monkeypatch):
    def check_conda_env_in_path_windows_trailing_slashes(dirname):
        _windows_monkeypatch(monkeypatch)

        scripts = "Scripts"
        library = "Library\\bin"

        env1 = os.path.join(dirname, "env1")
        os.makedirs(os.path.join(env1, "conda-meta"))
        env1scripts = os.path.join(env1, scripts)
        os.makedirs(env1scripts)
        env1lib = os.path.join(env1, library)
        os.makedirs(env1lib)

        env1path = "%s\\;%s\\;%s\\" % (env1, env1scripts, env1lib)
        env1path_no_slashes = "%s;%s;%s" % (env1, env1scripts, env1lib)

        env2 = os.path.join(dirname, "env2")
        os.makedirs(os.path.join(env2, "conda-meta"))
        env2scripts = os.path.join(env2, scripts)
        os.makedirs(env2scripts)
        env2lib = os.path.join(env2, library)
        os.makedirs(env2lib)

        env2path = "%s\\;%s\\;%s\\" % (env2, env2scripts, env2lib)
        env2path_no_slashes = "%s;%s;%s" % (env2, env2scripts, env2lib)

        notenv = os.path.join(dirname, "notenv\\")
        notenvscripts = os.path.join(notenv, scripts)
        os.makedirs(notenvscripts)
        notenvlib = os.path.join(notenv, library)
        os.makedirs(notenvlib)

        notenvpath = "%s\\;%s\\;%s\\" % (notenv, notenvscripts, notenvlib)
        notenvpath_no_slashes = "%s;%s;%s" % (notenv, notenvscripts, notenvlib)

        # add env to empty path
        path = conda_api.set_conda_env_in_path("", env1)
        assert env1path_no_slashes == path
        # add env that's already there
        path = conda_api.set_conda_env_in_path(env1path, env1)
        assert env1path_no_slashes == path
        # we can set a non-env because we don't waste time checking it
        path = conda_api.set_conda_env_in_path("", notenv)
        assert notenvpath_no_slashes == path
        # add an env to a non-env
        path = conda_api.set_conda_env_in_path(notenvpath, env1)
        assert (env1path_no_slashes + os.pathsep + notenvpath) == path
        # add an env to another env
        path = conda_api.set_conda_env_in_path(env1path, env2)
        assert env2path_no_slashes == path
        # replace an env that wasn't at the front
        path = conda_api.set_conda_env_in_path(notenvpath + os.pathsep + env2path, env1)
        assert (env1path_no_slashes + os.pathsep + notenvpath) == path
        # keep a bunch of random stuff
        random_stuff = "foo;bar;/baz/boo"
        path = conda_api.set_conda_env_in_path(random_stuff, env1)
        assert (env1path_no_slashes + os.pathsep + random_stuff) == path

    with_directory_contents(dict(), check_conda_env_in_path_windows_trailing_slashes)
