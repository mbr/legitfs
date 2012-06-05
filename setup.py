#!/usr/bin/env python
# coding=utf8

import os
import sys

from setuptools import setup, find_packages

def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(name='legitfs',
      version='0.2dev',
      description='A read-only FUSE-based filesystem allowing you to browse '\
                  'git repositories',
      long_description=read('README.rst'),
      keywords='git,fuse,filesystem,fs,read-only,readonly,legit,legitfs',
      author='Marc Brinkmann',
      author_email='git@marcbrinkmann.de',
      url='http://github.com/mbr/legitfs',
      license='MIT',
      scripts=['legitfs'],
      packages=find_packages(exclude=['tests']),
      install_requires=['dulwich', 'fuse-python', 'watchdog'],
     )