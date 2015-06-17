import click
import fuse

from logbook.compat import redirect_logging
from logbook import Logger

from .fs import LegitFS


log = Logger('cli')


@click.command()
@click.argument('mountpoint',
                type=click.Path(file_okay=False, dir_okay=True, exists=True))
@click.option('--root', '-r', default='.',
              type=click.Path(file_okay=False, dir_okay=True, exists=True))
def main(mountpoint, root):
    redirect_logging()
    log.debug('mounting {} onto {}'.format(root, mountpoint))

    fuse.FUSE(LegitFS(root, mountpoint), mountpoint, foreground=True)
