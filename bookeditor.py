#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#    Copyright (C) 2014 Rodrigo Silva (MestreLion) <linux@rodrigosilva.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program. See <http://www.gnu.org/licenses/gpl.html>

# Installing requirements in Debian/Ubuntu:
# ln -s /PATH/TO/pymclevel /PATH/TO/THIS/SCRIPT

"""Import and Export Minecraft 'Book and Quill' contents"""

import sys
import os
import subprocess
import os.path as osp
import argparse
import logging
import contextlib
from xdg.BaseDirectory import xdg_cache_home


if __name__ == '__main__':
    myname = osp.basename(osp.splitext(__file__)[0])
else:
    myname = __name__

log = logging.getLogger(myname)


def launchfile(filename):
    if sys.platform.startswith('darwin'):
        subprocess.call(('open', filename))
    elif os.name == 'nt':  # works for sys.platform 'win32' and 'cygwin'
        os.system("start %s" % filename)  # could be os.startfile() too
    else:  # Assume POSIX (Linux, BSD, etc)
        subprocess.call(('xdg-open', filename))


@contextlib.contextmanager
def openstd(filename=None, mode="r"):
    if filename and filename != '-':
        fh = open(filename, mode)
    else:
        if mode.startswith("r"):
            fh = sys.stdin
        else:
            fh = sys.stdout
    try:
        yield fh
    finally:
        if fh is not sys.stdout:
            fh.close()


def setuplogging(level):
    # Console output
    for logger, lvl in [(log, level),
                        # pymclevel is too verbose
                        (logging.getLogger("pymclevel"), logging.WARNING)]:
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        sh.setLevel(lvl)
        logger.addHandler(sh)

    # File output
    logger = logging.getLogger()  # root logger, so it also applies to pymclevel
    logger.setLevel(logging.DEBUG)  # set to minimum so it doesn't discard file output
    try:
        logdir = osp.join(xdg_cache_home, 'minecraft')
        if not osp.exists(logdir):
            os.makedirs(logdir)
        fh = logging.FileHandler(osp.join(logdir, "%s.log" % myname))
        fh.setFormatter(logging.Formatter('%(asctime)s\t%(levelname)s\t%(name)s\t%(message)s'))
        fh.setLevel(logging.DEBUG)
        logger.addHandler(fh)
    except IOError as e:  # Probably access denied
        logger.warn("%s\nLogging will not work.", e)


def parseargs(args=None):
    parser = argparse.ArgumentParser(
        description="Import and Export Minecraft 'Book and Quill' contents",)

    parser.add_argument('--quiet', '-q', dest='loglevel',
                        const=logging.WARNING, default=logging.INFO,
                        action="store_const",
                        help="Suppress informative messages.")

    parser.add_argument('--verbose', '-v', dest='loglevel',
                        const=logging.DEBUG,
                        action="store_const",
                        help="Verbose mode, output extra info.")

    parser.add_argument('--separator', '-s',
                        default="---",
                        help="Page separator."
                            " [Default: %(default)s]")

    parser.add_argument('--world', '-w', default="brave",
                        help="Minecraft world, either its 'level.dat' file"
                            " or a name under '~/.minecraft/saves' folder."
                            " [Default: %(default)s]")

    parser.add_argument('--player', '-p', default="Player",
                        help="Player name."
                            " [Default: %(default)s]")

    parser.add_argument('--export', '-e', dest='command',
                        const="export", action="store_const", default="export",
                        help="Export book contents."
                            " [Default]")

    parser.add_argument('--import', '-i', dest='command',
                        const="import", action="store_const",
                        help="Import book contents.")

    parser.add_argument('--append', '-a',
                        default=False, action="store_true",
                        help="On import, append instead of replacing book contents.")

    parser.add_argument(dest='file',
                        nargs="?",
                        help="File to export to or import from."
                            " [Default: stdout / stdin]")

    return parser.parse_args(args)


def main(argv=None):

    args = parseargs(argv)

    setuplogging(args.loglevel)
    log.debug(args)

    if args.command == "export":
        exportbook(args.world, args.player, args.file, args.separator)

    elif args.command == "import":
        importbook(args.world, args.player, args.file, args.separator, args.append)


class PyMCLevelError(Exception):
    pass


def load_world(name):
    import pymclevel  # takes a long time, so only imported after argparse
    if isinstance(name, pymclevel.MCLevel):
        return name

    try:
        if osp.isfile(name):
            return pymclevel.fromFile(name)
        else:
            return pymclevel.loadWorld(name)
    except IOError as e:
        raise PyMCLevelError(e)
    except pymclevel.mclevel.LoadingError:
        raise PyMCLevelError("Not a valid Minecraft world: '%s'" % name)


def get_inventory(world, player=None):
    import pymclevel
    if player is None:
        player = "Player"
    try:
        return world.getPlayerTag(player)["Inventory"]
    except pymclevel.PlayerNotFound:
        raise PyMCLevelError("Player not found in world '%s': %s" % (world.LevelName, player))


def exportbook(world, player=None, filename=None, separator="---"):
    try:
        world = load_world(world)
    except PyMCLevelError as e:
        log.error(e)
        return

    try:
        inventory = get_inventory(world, player)
    except PyMCLevelError as e:
        log.error(e)
        return

    log.info("Exporting book from '%s' in '%s' ('%s')",
             player, world.LevelName, world.filename)

    for item in inventory:
        if item["id"].value == 386:  # Book and Quill
            pages = [page.value for page in item["tag"]["pages"]]
            with openstd(filename, 'w') as fd:
                fd.write(("\n%s\n" % separator).join(pages) + "\n")
            break
    else:
        log.error("No book found in inventory!")


def importbook(world, player=None, filename=None, separator="---", append=True):
    try:
        world = load_world(world)
    except PyMCLevelError as e:
        log.error(e)
        return

    try:
        inventory = get_inventory(world, player)
    except PyMCLevelError as e:
        log.error(e)
        return

    log.info("Importing book to '%s' in '%s' ('%s')",
             player, world.LevelName, world.filename)

    for item in inventory:
        if item["id"].value == 386:  # Book and Quill
            book = item
            break
    else:
        log.error("No book found in inventory!")
        return

    log.info(book)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        log.critical(e, exc_info=True)
        sys.exit(1)
    except KeyboardInterrupt:
        pass
