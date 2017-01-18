import click
import fuse

from logbook.handlers import StderrHandler
from logbook.compat import redirect_logging
from logbook import Logger, DEBUG, INFO

from .fs import LegitFS

log = Logger('cli')


@click.command()
@click.argument(
    'mountpoint',
    type=click.Path(file_okay=False,
                    dir_okay=True, exists=True))
@click.option(
    '--root',
    '-r',
    default='.',
    type=click.Path(file_okay=False,
                    dir_okay=True, exists=True), )
@click.option('--debug',
              '-d',
              default=False,
              is_flag=True,
              help='Enable debug output', )
def main(mountpoint, root, debug):
    redirect_logging()

    # setup logging
    StderrHandler(level=DEBUG if debug else INFO).push_application()

    log.info('mounting {} onto {}'.format(root, mountpoint))
    fuse.FUSE(LegitFS(root, mountpoint), mountpoint, foreground=True)
