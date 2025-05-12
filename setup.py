#!/usr/bin/env python
from setuptools import setup, find_packages
from pynfe import get_version

setup(
    name='PyNFe',
    version=get_version(),
    packages=find_packages(),
    package_data={
        'pynfe': ['data/**/*.txt','data/**/*.xsd'],
    },
    install_requires=[
        "pyopenssl",
        "requests == 2.27.1",
        "lxml",
        "signxml",
        "pyxb",
        "six == 1.16.0",
        "python-dateutil >=2.2",
    ],
    zip_safe=False,
)
