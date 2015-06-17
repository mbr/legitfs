from errno import ENOENT
import os

from fuse import FuseOSError, Operations, LoggingMixIn
from logbook import Logger

from .util import split_git


log = Logger('fs')


class LegitFS(LoggingMixIn, Operations):
    def __init__(self, root, mountpoint):
        self.root = os.path.abspath(root)
        self.mountpoint = os.path.abspath(mountpoint)

    def _get_path(self, path):
        orig_path = path
        if path.startswith('/'):
            path = path[1:]

        rv = split_git(os.path.join(self.root, path))

        # for debugging
        print '{} => {}'.format(orig_path, rv)
        return rv

    def readdir(self, path, fh):
        lead, sub = self._get_path(path)
        entries = ['.', '..']

        if sub is None:
            for e in os.listdir(lead):
                full = os.path.join(lead, e)

                # only list dirs
                if not os.path.isdir(full):
                    continue

                # hide our own mountpoint
                if os.path.abspath(full) == os.path.abspath(self.mountpoint):
                    continue

                entries.append(e)
            return entries

        print 'git repo, not implemented'

        return entries

    def getattr(self, path, fh=None):
        lead, sub = self._get_path(path)

        if sub is None:
            if not os.path.isdir(lead):
                raise FuseOSError(ENOENT)

            st = os.lstat(lead)

            return dict(
                (key, getattr(st, key)) for key in
                ('st_atime', 'st_ctime', 'st_gid', 'st_mode', 'st_mtime',
                 'st_nlink', 'st_size', 'st_uid')
            )

        raise FuseOSError(ENOENT)
