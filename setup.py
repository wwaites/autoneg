from setuptools import setup, find_packages
import sys, os

version = '0.1.2'

def readme():
    dirname = os.path.dirname(os.path.abspath(__file__))
    filename = os.path.join(dirname, "README.txt")
    return open(filename).read()

setup(name='autoneg',
    version=version,
    description="Simple HTTP content auto-negotiation CGI",
    long_description=readme(),
    classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
    keywords='',
    author='William Waites',
    author_email='ww@styx.org',
    url='http://packages.python.org/autoneg',
    license='BSD',
    packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "flup",
    ],
    entry_points="""
        [console_scripts]
        autoneg_cgi=autoneg.command:autoneg_cgi
        autoneg_fcgi=autoneg.command:autoneg_fcgi
    """,
    )
