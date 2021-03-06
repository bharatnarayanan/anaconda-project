#!/bin/bash

set -e

# be sure we are in the right place
test -e setup.py || exit 1
test -d anaconda_project || exit 1

(test -d build/packages && /bin/rm -r build/packages) || true
python setup.py test
python setup.py conda_package

anaconda upload -u anaconda-platform --label dev build/packages/**/**/*.tar.bz2
