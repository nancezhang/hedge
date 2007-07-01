#!/usr/bin/env python
# -*- coding: latin-1 -*-

import glob
import os
import os.path
import sys

try:
    execfile("siteconf.py")
except IOError:
    print "*** Please copy siteconf-template.py to siteconf.py,"
    print "*** then edit siteconf.py to match your environment."
    sys.exit(1)

from distutils.core import setup,Extension

def non_matching_config():
    print "*** The version of your configuration template does not match"
    print "*** the version of the setup script. Please copy siteconf-template.py"
    print "*** over siteconf.py and re-customize it to your environment."
    sys.exit(1)

try:
    HEDGE_CONF_TEMPLATE_VERSION
except NameError:
    non_matching_config()

if HEDGE_CONF_TEMPLATE_VERSION != 2:
    non_matching_config()

INCLUDE_DIRS = BOOST_INCLUDE_DIRS + BOOST_MATH_TOOLKIT_INCLUDE_DIRS
LIBRARY_DIRS = BOOST_LIBRARY_DIRS
LIBRARIES = BPL_LIBRARIES

OP_EXTRA_DEFINES = {}

setup(name="hedge",
      version="0.90",
      description="The Hybrid-and-Easy Discontinuous Galerkin Environment",
      author=u"Andreas Kloeckner",
      author_email="inform@tiker.net",
      license = "BSD-Style",
      url="http://news.tiker.net/software/hedge",
      packages=["hedge"],
      package_dir={"hedge": "src/python"},
      ext_package="hedge",
      #scripts=["scripts/pylinear"],
      ext_modules=[ 
          Extension("_internal", 
              ["src/cxx/wrap_main.cpp", 
                  "src/cxx/wrap_polynomial.cpp", 
                  "src/cxx/wrap_flux.cpp", 
                  "src/cxx/wrap_op_target.cpp", 
                  "src/cxx/wrap_volume_operators.cpp", 
                  "src/cxx/wrap_face_operators.cpp", 
                  ],
              include_dirs = INCLUDE_DIRS,
              library_dirs = LIBRARY_DIRS,
              libraries = LIBRARIES,
              extra_compile_args = EXTRA_COMPILE_ARGS,
              ),
          ]
     )
