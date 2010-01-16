#!/usr/bin/env python
#
# (C) 2002 Pontus Sköld. This code is released under GPL.
#

import elf
import sys
import readline


def getstr( prompt ):
    s = ""

    while not s:
        s = raw_input( prompt )

    return s

src = ""
dst = ""

if len( sys.argv ) > 1:
    src = sys.argv[1]  # File given first

if len( sys.argv ) > 2:
    dst = sys.argv[2]  # File given first


if not src:
    src = getstr( "Please give a filename to read: " )
if not dst:
    dst = getstr( "Please give the destination filename: " )

e = elf.ELFhandler( src )


e.write_elf( dst )

