#!/usr/bin/env python3

"""
Hive Query Extractor.

Reads Hive log files, and extract all queries ran, with some info (user, duration...)

Assumptions:
- files are rolled per day

"""

import argparse
import collections
import datetime
import glob
import gzip
import logging
import os
import re


class Config():

    loglevel = 'warn'
    logdir = '/var/log/hive'
    logfile_glob = 'hiveserver2.log*'

    since = '15m'
    to = 'now'

    def __init__(self):
        """
        Initialise the parser and do its magic.
        """
        parser = argparse.ArgumentParser(
            description='Displays queries ran on Hive.',
            formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )

        parser.add_argument(
            '--since',
            dest='since',
            action='store',
            default=self.since,
            type=str,
            help='how far to look back.'
        )
        parser.add_argument(
            '--to',
            dest='to',
            action='store',
            default=self.to,
            type=str,
            help='How far to look forward.'
        )

        parser.add_argument(
            '--logdir',
            dest='logdir',
            action='store',
            default=self.logdir,
            type=str,
            help='Directory of hive log files.'
        )

        parser.add_argument(
            '--glob',
            dest='logfile_glob',
            action='store',
            default=self.logfile_glob,
            type=str,
            help='Shell pattern of hive logfiles inside their logdir.'
        )

        parser.add_argument(
            '--loglevel', '-l',
            dest='loglevel',
            choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
            type=str.upper,
            default=self.loglevel,
            help='Log level.'
        )

        parser.parse_args(namespace=self)
        logging.basicConfig(level=self.loglevel)


class Grep():

    def __init__(self, config):
        self.config = config

    def get_queries(self):
        """
        Return all hive queries ran in Hive between since and to.
        """
        since = self.parse_ts(self.config.since, 'since')
        to = self.parse_ts(self.config.to, 'to')

        logging.info("Looking at queries between {since} and {to}.".format(
            since=since.isoformat(' '),
            to=to.isoformat(' ')
        ))

        f = self.find_files_to_parse(since, to)
        logging.info("Looking at files: {}".format(list(map(os.path.basename, f))))
        return self.extract_queries(f, since, to)

    def parse_ts(self, ts, direction='since'):
        """
        Returns datetime from a human readable timestamp
        Accepts:
          - now
          - yyyymmdd (any separators)
          - yyyymmddhhMMss (any separators)
          - \d+[mhd] (eg 15m, 2h...)

        Direction helps to add time to date only. 00:00:00 if since, 23:59:59 for to.
        """
        # Debug log line
        logstr = "Parsing ts {ts} as {dt}."

        if ts == 'now':
            r = datetime.datetime.utcnow()
            logging.debug(logstr.format(ts=ts, dt=r))
            return r

        is_dt = re.search(
            '(?P<y>\d{4})(?P<datesep>\D?)(?P<m>\d{2})(?P=datesep)(?P<d>\d{2})'
            '\D?'
            '(?P<h>\d{2})(?P<timesep>\D?)(?P<M>\d{2})(?P=timesep)(?P<s>\d{2})',
            ts
        )
        if is_dt:
            r = datetime.datetime(int(is_dt.group('y')), int(is_dt.group('m')), int(is_dt.group('d')),
                                  int(is_dt.group('h')), int(is_dt.group('M')), int(is_dt.group('s')))
            logging.debug(logstr.format(ts=ts, dt=r))
            return r

        is_date = re.search('(?P<y>\d{4})(?P<datesep>\D?)(?P<m>\d{2})(?P=datesep)(?P<d>\d{2})', ts)
        if is_date:
            if direction.lower() == 'since':
                r = datetime.datetime(int(is_date.group('y')), int(is_date.group('m')), int(is_date.group('d')), 0, 0, 0)
            else:
                r = datetime.datetime(int(is_date.group('y')), int(is_date.group('m')), int(is_date.group('d')), 23, 59, 59, 9999)
            logging.debug(logstr.format(ts=ts, dt=r))
            return r

        is_timedelta = re.search('(?P<delta>\d+)(?P<inc>[mhd])', ts)
        if is_timedelta:
            if is_timedelta.group('inc') == 'm':
                r = datetime.datetime.utcnow() - datetime.timedelta(minutes=int(is_timedelta.group('delta')))
            elif is_timedelta.group('inc') == 'h':
                r = datetime.datetime.utcnow() - datetime.timedelta(hours=int(is_timedelta.group('delta')))
            elif is_timedelta.group('inc') == 'd':
                r = datetime.datetime.utcnow() - datetime.timedelta(days=int(is_timedelta.group('delta')))
            else:
                raise(Exception('timedelta not understood: "{}"'.format(ts)))
            logging.debug(logstr.format(ts=ts, dt=r))
            return r

        raise(Exception("Timestamp not recognised: '{}'".format(ts)))

    def find_files_to_parse(self, since, to):
        """
        Looks at from and to, and find the relevant files based on their filename, returned in chronological order.
        """
        # All files matching pattern
        allfiles = glob.glob('/'.join([self.config.logdir, self.config.logfile_glob]))
        # All files with right date
        selected = []

        # Current file has no TS, cannot be sorted with the rest
        current_file = []

        for f in allfiles:
            m = re.search('(?P<y>\d{4})(?P<datesep>\D?)(?P<m>\d{2})(?P=datesep)(?P<d>\d{2})', f)
            if m:
                start = datetime.date(int(m.group('y')), int(m.group('m')), int(m.group('d')))
            else:
                start = datetime.datetime.utcnow()

            filestart = datetime.datetime(start.year, start.month, start.day)
            tomorrow = start + datetime.timedelta(days=1)
            fileend = datetime.datetime(tomorrow.year, tomorrow.month, tomorrow.day)

            if ((since >= filestart and since < fileend) or  # since and to fully inside the file
                (to >= filestart and to < fileend) or  # since and to accross file boundary
                    (since <= filestart and to >= fileend)):  # since and to wider than a file
                if m:
                    selected.append(f)
                else:
                    current_file = [f]

        return sorted(set(selected)) + current_file

    def query_from_dict(self, d, tid):
        """
        Transform a hash in a qery object,
        """
        # Will become the returned object
        Query = collections.namedtuple('Query', ['start', 'user', 'host', 'duration', 'querytype', 'query', 'threadid', 'queryid', 'txnid', 'status', 'error'])
        return Query(querytype=d['query'][0].lstrip().partition(' ')[0],
                     query=''.join(d['query']),

                     user=d['user'] if 'user' in d else 'Unknown',
                     host=d['host'] if 'host' in d else 'Unknown',
                     duration='{:3f}'.format(int(d['duration']) / 1000) if 'duration' in d else 'Unknown',
                     start=d['start'] if 'start' in d else 'Unknown',

                     threadid=tid,
                     queryid=d['qid'] if 'qid' in d else 'Unknown',
                     txnid=d['txnid'] if 'txnid' in d else 'Unknown',

                     status=d['status'] if 'status' in d else 'Unknown',

                     error=d['error'] if 'error' in d else None,
                     )

    def extract_queries(self, files, since, to):
        """
        From a list of file path and a since/to pair, extract queries.extract
        """

        # returned list
        queries = []

        # Multiple queries can run in parallel, with log line intertwined, so we keep a hash of queries we know of.
        # One a query is fully parsed, its entry is deleted from the hash, so it should never become too big.
        parsing = {}

        # When getting parsing error, here is no good id to extract from the log. Generate it here.
        handler_id = 0

        # pattern that will be look for.
        re_dt = re.compile('^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3} (?P<log>.*)$')

        # Happy flow
        re_bgpool = re.compile('HiveServer2-Background-Pool: Thread-(?P<tid>\d+)\]: (?P<rest>.*)$')
        re_endofthread = re.compile('</PERFLOG method=Driver.run .* duration=(?P<duration>\d+) from=org.apache.hadoop.hive.ql.Driver>')
        re_cmdstart = re.compile('Starting command\(queryId=(?P<qid>\S*)\): (?P<cmd>.*)$')
        re_meta = re.compile('txnid:(?P<txnid>\S*), user:(?P<user>\S*), hostname:(?P<host>\S*),')

        # Error flow
        re_handler = re.compile('\[HiveServer2-Handler-Pool.*?\]: (?P<rest>.*)')
        re_parsing = re.compile('Parsing command: (?P<cmd>.*)')
        re_handler_error = re.compile('FAILED: (?P<error>.*)')

        # A command is special beast as it is a multi line log message, without the Ts and other metadata.
        # If a command is started, this variable will be set to the thread id.
        in_command = None

        for file in files:
            logging.debug("opening {}".format(file))
            if file.endswith('.gz'):
                f = gzip.open(file)
            else:
                f = open(file)

            for l in f:
                # predefine vars for easy logging
                cmdstart = None
                end = None
                meta = None

                # Step 1: is the line between from and to?
                dt_match = re.search(re_dt, l)
                if dt_match:
                    log = dt_match.group('log')
                    dt = datetime.datetime.strptime(dt_match.group('dt'), '%Y-%m-%d %H:%M:%S')

                    if dt > to or dt < since:
                        continue
                else:
                    # Step 1.5: if there is no TS, we might be reading a multiline command
                    if in_command is not None:
                        if 'lines' in parsing[in_command]:
                            parsing[in_command]['lines'] += [l]
                        parsing[in_command]['query'] += [l]
                        continue
                    else:
                        # probably a multiline exception
                        continue

                # We are definitely not in a command anymore, reset the flag.
                in_command = None

                # Step 2: commands are only run in HiveServer2-Background-Pool
                isbg = re.search(re_bgpool, log)
                if isbg:
                    tid = isbg.group('tid')
                    rest = isbg.group('rest')

                    if tid not in parsing:
                        # First occurence of this thread id
                        parsing[tid] = {
                            'lines': [l],
                            'start': dt
                        }
                    else:
                        # Thread id already exists
                        cmdstart = re.search(re_cmdstart, rest)

                        # Is the current line a commad start?
                        if cmdstart:
                            parsing[tid]['query'] = [cmdstart.group('cmd') + '\n']
                            parsing[tid]['qid'] = cmdstart.group('qid')
                            # Next lines might be the rest of a multi line command.
                            in_command = tid
                        else:
                            # Are there interesting metadata on this line?
                            meta = re.search(re_meta, rest)
                            if meta:
                                parsing[tid]['txnid'] = meta.group('txnid')
                                parsing[tid]['user'] = meta.group('user')
                                parsing[tid]['host'] = meta.group('host')
                            else:
                                # No start, no meta... Is the current line a command end?
                                end = re.search(re_endofthread, rest)
                                if end:
                                    if 'query' in parsing[tid]:
                                        parsing[tid]['duration'] = end.group('duration')
                                        parsing[tid]['status'] = 'Probably success'
                                        queries.append(self.query_from_dict(parsing[tid], tid))
                                    # Once a command is ended, no need to keep it forever.
                                    del(parsing[tid])
                                else:
                                    # no start, no end, no metatada.. Discard
                                    pass
                else:
                    # Parse and semantic errors are given by the Handler pool, but without nice metadata.
                    is_handler = re.search(re_handler, log)
                    if is_handler:

                        is_parsing = re.search(re_parsing, is_handler.group('rest'))
                        if is_parsing:
                            handler_id += 1
                            tid = 'handler-{}'.format(handler_id)
                            in_command = tid
                            parsing[tid] = {
                                'start': dt,
                                'query': [is_parsing.group('cmd') + '\n'],
                                'is_handler': True
                            }
                        else:
                            tid = 'handler-{}'.format(handler_id)
                            is_handler_error = re.search(re_handler_error, is_handler.group('rest'))
                            if is_handler_error:
                                parsing[tid]['error'] = is_handler_error.group('error')
                                parsing[tid]['status'] = 'FAILED'
                                queries.append(self.query_from_dict(parsing[tid], tid))

                                # Once a command is ended, no need to keep it forever.
                                del(parsing[tid])

                logging.debug('line {line}: in_command: {cmd}, isbg: {bg}, isstart: {isstart}, isend: {end}, ismeta: {meta}'.format(
                    line=l,
                    cmd=in_command,
                    bg=isbg is not None,
                    isstart=cmdstart is not None,
                    end=end is not None,
                    meta=meta is not None
                ))
            f.close()

        for tid in parsing:
            # Maybe there are queries not completed
            if 'query' in parsing[tid] and 'is_handler' not in parsing[tid]:
                parsing[tid]['status'] = 'Running'
                queries.append(self.query_from_dict(parsing[tid], tid))

        return queries


config = Config()
grep = Grep(config)
qs = grep.get_queries()
for q in qs:
    print("Started at {start} for {duration}s by {user} on {host} ({status}). (Thread id: {tid}, query id: {qid}, txn id: {txnid}):\n{q}\n{error}".format(
        start=q.start,
        duration=q.duration,
        user=q.user,
        host=q.host,
        tid=q.threadid,
        qid=q.queryid,
        txnid=q.txnid,
        q=q.query.strip(),
        status=q.status,
        error="Error: {}\n".format(q.error) if q.error else ''
    ))
