from setuptools import setup
from setuptools import find_packages

setup(
    name='nestauk',
    version='0.1',
    packages=find_packages(exclude=['docs', 'tests*']),
    license='MIT',
    long_description=open('README.rst').read(),
    url='https://github.com/nestauk/nesta',
    author='Joel Klinger',
    author_email='joel.klinger@nesta.org.uk',
    maintainer='Joel Klinger',
    maintainer_email='joel.klinger@nesta.org.uk',
    classifiers=[
        'Development Status :: 1 - Planning',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.6',
        'Environment :: Web Environment'
        'Topic :: System :: Monitoring',
    ],
    python_requires='>3.6',
)
