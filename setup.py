#!/usr/bin/env python
from setuptools import setup, find_packages
try:  # for pip >= 10
    from pip._internal.req import parse_requirements as parse
except:  # for pip <= 9.0.3
    from pip.req import parse_requirements as parse

def requirements(f):
    try:
        return [str(i.req) for i in parse(f, session=False)]
    except:
        return [str(i.requirement) for i in parse(f, session=False)]

setup(
    name='PyNFe',
    version='0.4.20',
    packages=find_packages(),
    package_data={
        'pynfe': ['data/**/*.txt','data/**/*.xsd'],
    },
    install_requires=requirements('requirements.txt'),
    zip_safe=False,
)
