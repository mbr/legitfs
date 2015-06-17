from errno import ENOENT
import os

from fuse import FuseOSError, Operations, LoggingMixIn
from dulwich.repo import Repo, NotGitRepository
from logbook import Logger

from .util import split_git


log = Logger('fs')


def _stat_to_dict(st):
    return dict((key, getattr(st, key)) for key in
                ('st_atime', 'st_ctime', 'st_gid', 'st_mode', 'st_mtime',
                 'st_nlink', 'st_size', 'st_uid'))


class VNode(object):
    def __init__(self, fs, lead, sub):
        self.fs = fs
        self.lead = lead
        self.sub = sub

    @property
    def path(self):
        if self.sub:
            return os.path.join(self.lead, self.sub)
        return self.lead

    def getattr(self):
        raise FuseOSError(ENOENT)

    def readdir(self):
        raise FuseOSError(ENOENT)


class DirNode(VNode):
    def readdir(self):
        entries = ['.', '..']

        for e in os.listdir(self.lead):
            full = os.path.join(self.lead, e)

            # only list dirs
            if not os.path.isdir(full):
                continue

            # hide our own mountpoint
            if os.path.abspath(full) == os.path.abspath(self.fs.mountpoint):
                continue

            entries.append(e)

        return entries

    def getattr(self):
        # either the .git folder, or not inside git repo
        if not os.path.isdir(self.lead):
            raise FuseOSError(ENOENT)

        return _stat_to_dict(os.lstat(self.lead))


class RepoNode(VNode):
    PLAIN_FILES = ('config', 'description')

    def __init__(self, fs, lead, sub):
        super(RepoNode, self).__init__(fs, lead, sub)
        try:
            self.repo = Repo(lead)
        except NotGitRepository:
            raise FuseOSError(ENOENT)

        self.refs = self.repo.refs.keys()
        self.ref_dirs = {r.split('/', 2)[1] for r in self.refs
                         if r.startswith('refs/')}

    def getattr(self):
        return _stat_to_dict(os.lstat(self.lead))

    def readdir(self):
        entries = ['.', '..']

        if 'HEAD' in self.refs:
            entries.append('HEAD')

        for fn in ('config', 'description'):
            if os.path.exists(os.path.join(self.lead, fn)):
                entries.append(fn)

        entries.extend(self.ref_dirs)

        return entries

    @classmethod
    def load(cls, fs, lead, sub):
        if not sub:
            return cls(fs, lead, sub)

        if sub in cls.PLAIN_FILES:
            return FileNode(fs, lead, sub)

        raise FuseOSError(ENOENT)


class FileNode(VNode):
    def getattr(self):
        return _stat_to_dict(os.lstat(self.path))

    def read(self, size, offset, fh):
        with open(self.path, 'rb') as f:
            f.seek(offset, 0)
            return f.read(size)


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
        print log.debug('{} => {}'.format(orig_path, rv))
        return rv

    def _get_node(self, path):
        lead, sub = self._get_path(path)

        if sub is None:
            return DirNode(self, lead, sub)

        return RepoNode.load(self, lead, sub)

    def readdir(self, path, fh=None):
        node = self._get_node(path)
        return node.readdir()

    def getattr(self, path, fh=None):
        node = self._get_node(path)
        return node.getattr()

    # file i/o. rather slow, because we reopen the file each time
    def read(self, path, size, offset, fh):
        node = self._get_node(path)
        return node.read(size, offset, fh)
