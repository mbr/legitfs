from errno import ENOENT
from stat import S_IFLNK, S_IFDIR
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


class RepoMixin(object):
    def __init__(self, fs, lead, sub):
        super(RepoMixin, self).__init__(fs, lead, sub)
        try:
            self.repo = Repo(lead)
        except NotGitRepository:
            raise FuseOSError(ENOENT)


class VDirMixin(object):
    def getattr(self):
        st = self.fs.empty_stat.copy()
        st['st_mode'] |= S_IFDIR
        return st


class RepoNode(RepoMixin, VNode):
    PLAIN_FILES = ('config', 'description')

    def getattr(self):
        return _stat_to_dict(os.lstat(self.lead))

    def readdir(self):
        entries = ['.', '..']

        if 'HEAD' in self.repo.refs:
            entries.append('HEAD')

        for fn in ('config', 'description'):
            if os.path.exists(os.path.join(self.lead, fn)):
                entries.append(fn)

        entries.extend([
            'refs',
            'objects',
        ])

        return entries

    @classmethod
    def load(cls, fs, lead, sub):
        if not sub:
            return cls(fs, lead, sub)

        if sub in cls.PLAIN_FILES:
            return FileNode(fs, lead, sub)

        if sub == 'HEAD':
            return RefNode(fs, lead, sub)

        if sub == 'objects':
            pass

        if sub.startswith('refs/') or sub == 'refs':
            refs_node = RefsNode(fs, lead, sub)
            if refs_node.is_endpoint:
                return RefNode(fs, lead, sub)
            return refs_node

        raise FuseOSError(ENOENT)


class RefsNode(RepoMixin, VDirMixin, VNode):
    def readdir(self):
        entries = ['.', '..']

        prefix = self.sub + '/'
        valid_refs = set()
        for ref in self.repo.refs.keys():
            if not ref.startswith(prefix):
                continue
            valid_refs.add(ref[len(prefix):].split('/', 1)[0])

        entries.extend(valid_refs)
        return entries

    @property
    def is_endpoint(self):
        return self.sub in self.repo.refs.keys()


class RefNode(RepoMixin, VNode):
    REFLINK_PREFIX = 'ref: '

    def getattr(self):
        st = self.fs.empty_stat.copy()
        st['st_mode'] |= S_IFLNK
        return st

    def readlink(self):
        refname = self.sub

        target = self.repo.refs.read_ref(refname)

        if target is None:
            raise FuseOSError(ENOENT)

        if target.startswith(self.REFLINK_PREFIX):
            # symbolic ref
            p = '../' * refname.count('/')

            return p + target[len(self.REFLINK_PREFIX):]

        return 'objects/' + target


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

        root_stat = os.lstat(root)

        self.empty_stat = {
            'st_atime': 0,
            'st_ctime': 0,
            'st_gid': root_stat.st_gid,
            'st_mode': 0644,
            'st_mtime': 0,
            'st_nlink': 1,
            'st_size': 0,
            'st_uid': root_stat.st_uid,
        }

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

    def readlink(self, path):
        node = self._get_node(path)
        return node.readlink()
