leGit-fs
========

legit is a `FUSE <http://fuse.sourceforge.net/>`_-filesystem that mounts any
number of git repositories read only, allowing direct access to all commits and
their files through a directory structure.

legit is read-only, unless there are catastrophic bugs in the software, it
should not touch your data in any way.


Installation (from PyPI)
------------------------

Assuming your have `virtualenvwrapper
<http://www.doughellmann.com/projects/virtualenvwrapper/>`_ installed:

::

  $ mkvirtualenv legitfs
  $ pip install legitfs


Installation (without PyPI)
---------------------------

legit requires the `FUSE python bindings
<http://sourceforge.net/apps/mediawiki/fuse/index.php?title=FusePython>`_,
usually these are available (and most often already installed) through your
distro. The correct package on PyPI is named `fuse-python
<http://pypi.python.org/pypi/fuse-python/>`_.

In addition, a somewhat recent version of `dulwich
<http://www.samba.org/~jelmer/dulwich/>`_ is required. Install it through your
distro or via `PyPI <http://pypi.python.org/pypi/dulwich/>`_.

The program itself is just a single file. Download it to anywhere in your path
and run it.

If you have the `watchdog <http://pypi.python.org/pypi/watchdog>`_ package
installed, legit will automatically refresh the filesystem-contents when you
add, update or remove repositories.


Usage example
-------------

Let's try it! In an empty directory, type:

::

  $ git clone git://github.com/mbr/simplekv.git
  $ git clone git://github.com/mitsuhiko/flask.git

That will clone two git repositories for us to play around with. Now create a
mountpoint somewhere

::

  $ mkdir /tmp/legitfs-test

Finally, we mount the current directory (and therefore its git repositories):

::

  $ legitfs -o root=./ /tmp/legitfs-test

Done! Now let's see what we've got:

::

  $ ls /tmp/legitfs-test/
  flask  simplekv

``legitfs`` tries to recreate the directory-structure and also handles nested
repositories or those that are in subdirectories. Of course, you can also mount
just one repository at the root.

Some more interesting stuff:

::

  $ ls /tmp/legitfs-test/flask/
  commits  HEAD  refs
  $ ls /tmp/legitfs-test/flask/refs/tags -l
  total 48
  lrwxrwxrwx. 1 root root 4096  1. Jan 1970  0.1 -> ../../commits/8605cc310d260c3b08160881b09da26c2cc95f8d
  lrwxrwxrwx. 1 root root 4096  1. Jan 1970  0.2 -> ../../commits/e0fa5aec3a13d9c3e8e27b53526fcee56ac0298d
  lrwxrwxrwx. 1 root root 4096  1. Jan 1970  0.3 -> ../../commits/ce6e4cbd73d57cb8c1bba85c46490f71061f865f
  lrwxrwxrwx. 1 root root 4096  1. Jan 1970  0.3.1 -> ../../commits/6b3e616cf905fd19c37fca93d1198cad1490567b
  lrwxrwxrwx. 1 root root 4096  1. Jan 1970  0.4 -> ../../commits/1592c53a664c82d9badac81fa0104af226cce5a7
  lrwxrwxrwx. 1 root root 4096  1. Jan 1970  0.5 -> ../../commits/4c937be2524de0fddc2d2f7f39b09677497260aa
  lrwxrwxrwx. 1 root root 4096  1. Jan 1970  0.6 -> ../../commits/5cadd9d34da46b909f91a5379d41b90f258d5998
  lrwxrwxrwx. 1 root root 4096  1. Jan 1970  0.6.1 -> ../../commits/774b7f768214f5b0c125a1b80daa97247a0ac1a6
  lrwxrwxrwx. 1 root root 4096  1. Jan 1970  0.7 -> ../../commits/fb1482d3bb1b95803d25247479eb8ca8317a3219
  lrwxrwxrwx. 1 root root 4096  1. Jan 1970  0.7.1 -> ../../commits/9682d6b371d8c1ce1fd0e58424e836d27d2317b3
  lrwxrwxrwx. 1 root root 4096  1. Jan 1970  0.7.2 -> ../../commits/3f5db33ece48bd22b77fcc62553998ea9a6cfdfc
  lrwxrwxrwx. 1 root root 4096  1. Jan 1970  0.8 -> ../../commits/d5e10e4685f54dde5ffc27c4f55a19fb23f7a536

Each repository contains at least three files: ``commits`` contains
directories, one for each commit, allowing you to access commits. ``HEAD`` is
the current ``HEAD``-ref and is, like all refs, a symlink. ``refs`` also works
as you would expect and is full of symlinks.

Another feature are relative refs:

::

  $ head -n5 /tmp/legitfs-test/flask/refs/tags/0.7~15/README

                            // Flask //

                web development, one drop at a time

Notice the '0.7~15', which is git-speak for "tag 0.7, then go 15 revisions
back". While these virtual "files" aren't shown when you ``ls`` the
``refs/tags`` directory, you can append any number of ``~n`` or ``^`` to any
ref to go back commits.


What's missing
--------------

* Optimizations for when the tree needs to be rebuilt.

* Submodules. I currently don't use any and haven't tried them at all.

* Currently, each file is read into memory completely (since I haven't been
  able to find a streaming-api for blobs in dulwich yet), so working on large
  files might not be feasible at the moment. Unless you have a lot of RAM.


Is it legit?
------------

Completely.
