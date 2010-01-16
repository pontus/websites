#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-
"""
imapfilter.py 
Public domain software by Pontus Sköld <pont_imapfilter@soua.net>


This hack runs as a "daemon" (doesn't detach though) and runs mail
coming to your IMAP box through a filter and replaces the old
message with the filtered.

Example usage: Create a .imaprc containing

---CUT HERE---
[imapfilter]
username = YOURUSERNAME
host = YOURIMAPSERVER
mailbox = INBOX
password = YOURPASSWORD
---CUT HERE---

Optionally you may specify ssl = YES to use a ssl-connection to the
server, note though that there's no verification of the servers
identity - you'll know that your conversation can't be overheard, but
you'll don't know (more than usual) who you talk to.

You may also specify a filter program:

filter = /usr/bin/spamc -f

the arguments are whitespace separated. Normal quoting is *NOT*
handled.

Filtered messages are marked on the imap-server (to not refilter),
the default flag name is 'spamchecked', but this can be changed:

flag = flagname 

This program requires popen5 (see PEP 324 and
<URL:http://www.lysator.liu.se/~astrand/popen5/>).
"""

import os
import imaplib
import popen5
import time
import ConfigParser

PN = "imapfilter"

# Defaults

flagname = "spamchecked"
filter = ('/usr/bin/spamc','-f') # Default to spamc


homed = os.getenv("HOME")

if not homed:   # No such environment variable
    homed = ""
else:
    homed = homed+"/"

p = ConfigParser.ConfigParser()
p.read( homed + ".imapfilterrc" )

for q in ("username", "password", "host", "mailbox"):
    if not p.has_option(PN, q):
        print "Missing %s in options." % q
        raise SystemExit


if p.has_option(PN,"filter"):
    filter =  p.get( PN, "filter").split()

if p.has_option(PN,"flag"):
    flagname =  p.get( PN, "flag")

if p.has_option(PN, "ssl") and p.getboolean(PN, "ssl"):
    c = imaplib.IMAP4_SSL( p.get( PN, "host" ) )
else:
    c = imaplib.IMAP4( p.get( PN, "host" ) )

c.login(  p.get( PN, "username" ),
          p.get( PN, "password" ) )


class filterError( Exception ):
    pass

class filteredAlready( filterError ):
    pass


def fail():
    raise filterError()

def ok():
    pass

respd = { 'OK':ok, 'NO':fail }

while 1:
    time.sleep(15)
    c.select(  p.get( PN, "mailbox" ) ) 
    new = c.uid( 'search', None, 'UNKEYWORD', flagname, 'undeleted')

    try:
        respd[ new[0] ]

        for msgid in new[1][0].split():
            print "Fixing message"
            
            h = c.uid( 'fetch', msgid, 'ALL' )
            respd[ h[0] ]
            mtxt = str(h[1][0]) # Sometimes it's ('foo'), sometimes 'foo'?

            print h
            
            flstart = mtxt.index( '(', mtxt.index('FLAGS'))+1
            flend = mtxt.index(')', flstart ) 
            flags = mtxt[ flstart:flend ]

            if flags.find( flagname ) != -1:
                raise filteredAlready
            
            dtstart = mtxt.index( '"', mtxt.index('INTERNALDATE'))
            dtend = mtxt.index('"', dtstart+1 ) + 1
            date  = mtxt[ dtstart:dtend ]
            
            h = c.uid( 'fetch', msgid, '(BODY[HEADER] BODY[TEXT])' )
            respd[ h[0] ]
            headers = h[1][0][1]
            body = h[1][1][1]

            spamc = popen5.Popen( filter,
                                  stdin=popen5.PIPE,
                                  stdout=popen5.PIPE,
                                  stderr=popen5.PIPE)
            (out,err) = spamc.communicate(headers+body)

            if spamc.returncode == 0: # Everything OK?
                curflags = flags.replace( '\\\\',  '\\' ) # Seems to be neccessarry
                curflags = curflags.replace( '\Recent','')  + " " + flagname

                h = c.append( p.get( PN, "mailbox" ) ,
                              '(' + curflags.strip() + ')' ,
                              date, out )

                respd[ h[0] ] # Message added OK

                h = c.uid( 'store', msgid, '+FLAGS', '(\Deleted)' )
            
    except filterError:
        pass
