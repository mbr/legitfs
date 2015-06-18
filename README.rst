legitfs
=======

legit is a `FUSE <http://fuse.sourceforge.net/>`_-filesystem that mounts git
repositories read only, allowing direct access to commits, tags and branches
through the filesystem. This allows you to browse old versions from inside your
favorite editor, provided it doesn't produce a mess by trying to read the whole
tree...

legitfs is read-only and won't eat your data.


Installation
------------

legitfs is available from PyPi::

  $ pip install legitfs

It uses fusepy_ which in turn means you need to have fuse development libraries
and a C compiler installed. All other dependencies can work Python-only.


Example usage
-------------

Try this in an empty directory after installing legitfs:

::

  $ git clone git://github.com/mbr/simplekv.git
  $ git clone git://github.com/mitsuhiko/flask.git

Create a mountpoint and mount the current directory:

::

  $ mkdir _history
  $ legitfs _history

legitfs will run in the foreground (you can unmount with ``C-c``), so we can
continue in another terminal::

  $ cd _history/
  $ ls
  flask  simplekv
  $ ls flask/.git/
  $ ls flask/.git/refs/heads/master
  $ ls flask/.git/refs/heads/master/tree
  artwork  CONTRIBUTING.rst  flask     MANIFEST.in  setup.cfg  tox.ini
  AUTHORS  docs              LICENSE   README       setup.py
  CHANGES  examples          Makefile  scripts      tests

``legitfs`` tries to recreate the directory-structure and also handles nested
repositories or those that are in subdirectories. Of course, you can also mount
just one repository at the root.

Objects are exposed in the ``objects/`` subdirectory, almost everything else is
a symbolic link::

  $ cd flask/.git
  $ ls refs/tags
  0.1  0.10  0.10.1  0.2  0.3  0.3.1  0.4  0.5  0.6  0.6.1  0.7  0.7.1  0.7.2
  0.8  0.8.1  0.9
  $ ls refs/tags/0.7/tree
  ...
  $ head refs/tags/0.7/tree/README  -n 5

                        // Flask //

            web development, one drop at a time
