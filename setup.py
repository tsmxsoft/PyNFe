#!/usr/bin/env python
from setuptools import setup, find_packages

setup(
    name='PyNFe',
    version='0.4.104',
    packages=find_packages(),
    package_data={
        'pynfe': ['data/**/*.txt','data/**/*.xsd'],
    },
    install_requires=[
        "pyopenssl",
        "requests",
        "lxml",
        "signxml",
        "pyxb",
        "six == 1.10.0",
        "python-dateutil >=2.2",
    ],
    zip_safe=False,
)
