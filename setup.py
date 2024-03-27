#!/usr/bin/env python
from setuptools import setup, find_packages

setup(
    name='PyNFe',
    version='0.4.97',
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
        "six",
        "python-dateutil >=2.2",
    ],
    zip_safe=False,
)
