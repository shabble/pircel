#!/usr/bin/env python
# -*- coding: utf8 -*-
import os.path

from setuptools import setup

import pircel

install_requires = [
    'chardet',
    'peewee',
]

classifiers = [
    'Development Status :: 2 - Pre-Alpha',
    'Topic :: Communications :: Chat :: Internet Relay Chat',
    'License :: OSI Approved :: BSD License',
    'Programming Language :: Python :: 3 :: Only',
]

with open(os.path.join(os.path.dirname(__file__), 'README.md')) as readme_file:
    long_description = readme_file.read()

setup(
    # Metadata
    name='pircel',
    version=pircel.__version__,
    packages=['pircel'],
    author='Kit Barnes',
    author_email='kit@ninjalith.com',
    description='Simple IRC client library',
    long_description=long_description,
    url='https://bitbucket.org/KitB/pircel/',
    license='BSD',
    keywords='irc quassel possel',
    classifiers=classifiers,

    # Non-metadata (mostly)
    py_modules=[],
    zip_safe=False,
    install_requires=install_requires,
    extras_require={'bot': ['tornado']},
    scripts=['bin/pircel'],
    package_data={},
)
