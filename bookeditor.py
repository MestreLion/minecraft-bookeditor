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

"""Import and Export Minecraft 'Book and Quill' contents"""

import sys
import os.path as osp
import logging
import contextlib

import pymctoolslib as mc


log = logging.getLogger(__name__)


@contextlib.contextmanager
def openstd(filename=None, mode="r"):
    if filename and filename != '-':
        fh = open(filename, mode)
        name = "'%s'" % filename
    else:
        if mode.startswith("r"):
            log.info("Reading from standard input, press CTRL+D when done...")
            fh = sys.stdin
            name = "<stdin>"
        else:
            fh = sys.stdout
            name = "<stdout>"
    try:
        yield fh, name
    finally:
        if fh is not sys.stdout:
            fh.close()


def parseargs(args=None):
    parser = mc.basic_parser(__doc__)

    parser.add_argument('--separator', '-s',
                        default="---",
                        help="Page separator."
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
    logging.basicConfig(level=args.loglevel, format='%(levelname)s: %(message)s')
    log.debug(args)

    if args.command == "export":
        exportbook(args.world, args.player, args.file, args.separator)

    elif args.command == "import":
        importbook(args.world, args.player, args.file, args.separator, args.append, save=args.save)


def get_bookpages(inventory):
    for item in inventory:
        if item["id"].value in (386, 'minecraft:writable_book'):  # Book and Quill
            book = item
            break
    else:
        raise LookupError("No book found in inventory")

    # Books that were never written on have no "tag" key,
    # so create it the same as in-game does:
    # with a "pages" key containing an empty string as 1st page
    book.setdefault("tag", new_booktag())
    return book, book["tag"]["pages"]


def new_booktag():
    from pymctoolslib.pymclevel import nbt
    tag = nbt.TAG_Compound()
    tag["pages"] = nbt.TAG_List([nbt.TAG_String()])
    return tag


def new_book(world, inventory=None, slot=None):
    # TAG_Compound({
    #   "id": TAG_Short(386),
    #   "id": TAG_String(u'minecraft:writable_book'),
    #   "Damage": TAG_Short(0),
    #   "Count": TAG_Byte(1),
    #   "tag": TAG_Compound({
    #     "pages": TAG_List([
    #       TAG_String(u''),
    #     ]),
    #   }),
    #   "Slot": TAG_Byte(0),
    # })
    from pymctoolslib.pymclevel import nbt

    if slot is None:
        if inventory is None:
            slot = 0
        else:
            slots = free_slots(inventory)
            if not slots:
                raise LookupError("No empty slot in inventory to create a new book!")
            slot = slots[0]

    # Decide if ID should be numeric or string, 1.8 onwards (14w03a)
    # Check for known world's tags: 'Version' (1.9, 15w32a) or
    # 'logAdminCommands' (14w03a)
    root = world.root_tag['Data']
    if 'Version' in root or 'logAdminCommands' in root['GameRules']:
        ItemID = nbt.TAG_String('minecraft:writable_book')
    else:
        ItemID = nbt.TAG_Short(386)

    book = nbt.TAG_Compound()
    book["id"]     = ItemID
    book["Damage"] = nbt.TAG_Short(0)
    book["Count"]  = nbt.TAG_Byte(1)
    book["Slot"]   = nbt.TAG_Byte(slot)
    book["tag"]    = new_booktag()

    if inventory is not None:
        inventory.append(book)

    return book, book["tag"]["pages"]


def free_slots(inventory):
    if len(inventory) == 40:  # shortcut for full inventory
        return []

    slots = range(36)
    for item in inventory:
        slot = item["Slot"].value
        if slot in slots:
            slots.remove(slot)
    return slots


def exportbook(levelname, playername=None, filename=None, separator="---"):
    try:
        world = mc.World(levelname)
        player = world.get_player(playername)

        log.info("Exporting book from '%s' in '%s' (%s)",
                 player.name, world.name, world.filename)

        book, bookpages = get_bookpages(player.inventory.get_nbt())

        log.debug("Found book in inventory slot %d", book["Slot"].value)

        pages = [page.value for page in bookpages]
        with openstd(filename, 'w') as (fd, name):
            log.debug("Exporting %d pages to %s", len(pages), name)
            fd.write(("\n%s\n" % separator).join(pages) + "\n")

    except (mc.MCError, LookupError, IOError) as e:
        log.error(e)
        return


def importbook(levelname, playername=None, filename=None, separator="---", append=True, create=True, save=False):
    try:
        sep = "\n%s\n" % separator
        with openstd(filename, 'r') as (fd, name):
            pages = fd.read()[:-1].rstrip(sep).split(sep)
            log.debug("Importing %d pages from %s", len(pages), name)

        world = mc.World(levelname)
        player = world.get_player(playername)

    except (mc.MCError, IOError) as e:
        log.error(e)
        return

    log.info("Importing book to '%s' in '%s' ('%s')",
             player.name, world.name, world.filename)

    try:
        book, bookpages = get_bookpages(player.inventory.get_nbt())
        log.debug("Found book in inventory slot %d", book["Slot"].value)

    except LookupError as e:
        if not create:
            log.error("%s, and create is not enabled.", e)
            return

        log.info("%s, so creating a new one.", e)
        try:
            book, bookpages = new_book(world.level, player.inventory.get_nbt())
            log.debug("Created book in inventory slot %d\n%s", book["Slot"].value, book)
        except LookupError as e:
            log.error(e)
            return

    from pymctoolslib.pymclevel import nbt

    if not append:
        del(bookpages[:])

    for page in pages:
        bookpages.append(nbt.TAG_String(page))

    if save:
        log.info("Applying changes and saving world...")
        world.level.saveInPlace()
    else:
        log.warn("Not saving world, use --save to apply changes")




if __name__ == '__main__':
    log = logging.getLogger(osp.basename(osp.splitext(__file__)[0]))
    try:
        sys.exit(main())
    except Exception as e:
        log.critical(e, exc_info=True)
        sys.exit(1)
    except KeyboardInterrupt:
        pass
