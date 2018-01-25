#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Adapted from Kenneth Reitz' setup.py for humans (MIT license)
# https://github.com/kennethreitz/setup.py

import os

from setuptools import setup

here = os.path.abspath(os.path.dirname(__file__))

# Load the package's __version__.py module as a dictionary.
about = {}
with open(os.path.join(here, 'bztogl', '__version__.py')) as f:
    exec(f.read(), about)

setup(
    name='bztogl',
    version=about['__version__'],
    description='Bugzilla to GitLab migration tool',
    author='GNOME',
    url='https://gitlab.gnome.org/External/bugzilla-to-gitlab-migrator',

    packages=['bztogl'],
    entry_points={
        'console_scripts': ['bztogl=bztogl.bztogl:main',
                            'phabtogl=bztogl.phabtogl:main'],
    },

    install_requires=['python-bugzilla', 'python-gitlab', 'phabricator'],
    setup_requires=['pytest-runner'],
    tests_require=['pytest'],

    license='GPLv3',
    classifiers=[
        # Trove classifiers
        # Full list: https://pypi.python.org/pypi?%3Aaction=list_classifiers
        'License :: OSI Approved :: GNU General Public License v3 or later '
            '(GPLv3+)',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy'
    ],
)
