from collections import Counter
from itertools import count
from errno import ENOENT, EROFS
import os
from stat import S_IFLNK, S_IFDIR, S_IFREG
from threading import RLock

from fuse import FuseOSError, Operations, LoggingMixIn
from dulwich.repo import Repo, NotGitRepository
from logbook import Logger

from .util import split_git


log = Logger('fs')


def _stat_to_dict(st):
    return dict((key, getattr(st, key)) for key in
                ('st_atime', 'st_ctime', 'st_gid', 'st_mode', 'st_mtime',
                 'st_nlink', 'st_size', 'st_uid'))


class DesciptorManager(object):
    def __init__(self):
        self.refcount = Counter()
        self.data_hash = {}
        self.lock = RLock()
        self.fd = count()

    def get_free_fd(self, h):
        fd = self.fd.next()
        self.data_hash[fd] = h
        return fd

    def get_hash(self, fd):
        return self.data_hash[fd]

    def release(self, fd):
        with self.lock:
            newval = max(self.refcount[fd] - 1, 0)
            self.refcount[fd] = newval
            if newval == 0:
                del self.data_hash[fd]

            return newval != 0


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

        if sub == 'objects' or sub.startswith('objects'):
            objects_node = ObjectsNode(fs, lead, sub)

            if sub == 'objects':
                return objects_node

            return objects_node.get_obj_node()

        if sub.startswith('refs/') or sub == 'refs':
            refs_node = RefsNode(fs, lead, sub)
            if refs_node.is_endpoint:
                return RefNode(fs, lead, sub)
            return refs_node

        raise FuseOSError(ENOENT)


class ObjectsNode(RepoMixin, VDirMixin, VNode):
    def readdir(self):
        entries = ['.', '..']

        entries.extend(iter(self.repo.object_store))

        return entries

    def get_obj_node(self):
        parts = self.sub.split('/')
        h = bytes(parts[1])
        obj = self.repo[h]

        # determine type
        if obj.type_name == 'commit':
            return CommitNode(self.repo, obj, self.fs, self.lead, self.sub)
        elif obj.type_name == 'tree':
            # we got the root tree, now fetch subtree:

            fn = '/'.join(parts[2:])

            if fn:
                try:
                    dest_md, dest_sha = obj.lookup_path(
                        self.repo.__getitem__, fn
                    )
                    dest_obj = self.repo[dest_sha]
                except KeyError:
                    raise FuseOSError(ENOENT)

                if dest_obj.type_name == 'tree':
                    obj = dest_obj
                else:
                    return BlobNode(self.repo, dest_obj, self.fs, self.lead,
                                    self.sub)

            return TreeNode(self.repo, obj, self.fs, self.lead, self.sub)
        elif obj.type_name == 'blob':
            return BlobNode(self.repo, obj, self.fs, self.lead, self.sub)

        raise FuseOSError(ENOENT)


class ObjectNode(RepoMixin, VNode):
    def __init__(self, repo, obj, fs, lead, sub):
        # not calling parent constructor, already have repo
        VNode.__init__(self, fs, lead, sub)
        self.repo = repo
        self.obj = obj


class CommitNode(VDirMixin, ObjectNode):
    def get_csub(self):
        parts = self.sub.split('/')
        root = '../' * (len(parts)-1)

        return root, '/'.join(parts[2:])

    def readdir(self):
        _, csub = self.get_csub()

        entries = ['.', '..']

        if not csub:
            entries.append('tree')

            if self.obj.parents:
                entries.append('parents')
                entries.append('parent')

        elif csub == 'parents':
            for i in range(len(self.obj.parents)):
                entries.append('{:02d}'.format(i))
        else:
            raise FuseOSError(ENOENT)

        return entries

    def getattr(self):
        _, csub = self.get_csub()
        if not csub:
            return super(CommitNode, self).getattr()

        st = self.fs.empty_stat.copy()

        if csub == 'tree':
            st['st_mode'] |= S_IFLNK
        elif csub == 'parent':
            st['st_mode'] |= S_IFLNK
        elif csub == 'parents':
            st['st_mode'] |= S_IFDIR
        elif csub.startswith('parents/'):
            st['st_mode'] |= S_IFLNK
        else:
            raise FuseOSError(ENOENT)

        return st

    def readlink(self):
        root, csub = self.get_csub()

        if csub == 'tree':
            return root + 'objects/' + self.obj.tree
        elif csub == 'parent':
            return 'parents/00'
        elif csub.startswith('parents/'):
            idx = int(csub.split('/', 1)[1])
            return root + '/objects/' + self.obj.parents[idx]

        raise FuseOSError(ENOENT)


class TreeNode(VDirMixin, ObjectNode):
    def readdir(self):
        entries = ['.', '..']

        for e in self.obj.iteritems():
            entries.append(e.path)

        return entries


class BlobNode(VDirMixin, ObjectNode):
    def getattr(self):
        st = self.fs.empty_stat.copy()
        st['st_mode'] = S_IFREG
        st['st_size'] = self.obj.raw_length()
        return st

    def open(self, flags):
        with self.fs.data_lock:
            fd = self.fs.fd_man.get_free_fd(self.obj.id)

            # load data into data_cache
            if not self.obj.id in self.fs.data_cache:
                self.fs.data_cache[self.obj.id] = self.obj.as_raw_string()

            return fd

    def read(self, size, offset, fh):
        # lookup hash associated with filehandle
        h = self.fs.fd_man.get_hash(fh)

        # retrieve cached data for filehandle
        data = self.fs.data_cache[h]

        return data[offset:offset+size]

    def release(self, fh):
        with self.fs.data_lock:
            h = self.fs.fd_man.get_hash(fh)

            del self.fs.data_cache[h]

        return 0


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
        root = '../' * refname.count('/')

        target = self.repo.refs.read_ref(refname)

        if target is None:
            raise FuseOSError(ENOENT)

        if target.startswith(self.REFLINK_PREFIX):
            # symbolic ref
            return root + target[len(self.REFLINK_PREFIX):]

        return root + 'objects/' + target


class FileNode(VNode):
    def getattr(self):
        return _stat_to_dict(os.lstat(self.path))

    # file i/o. rather slow, because we reopen the file each time
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

        self.data_cache = {}
        self.data_lock = RLock()
        self.fd_man = DesciptorManager()

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

    def open(self, path, flags):
        if flags & (os.O_WRONLY | os.O_RDWR):
            raise FuseOSError(EROFS)

        node = self._get_node(path)
        return node.open(flags)

    def read(self, path, size, offset, fh):
        node = self._get_node(path)
        return node.read(size, offset, fh)

    def release(self, path, fh):
        # note: for some reason, this isn't called?
        # flush is though...
        node = self._get_node(path)
        return node.release(fh)

    def readlink(self, path):
        node = self._get_node(path)
        return node.readlink()
