# Copyright (c) 2011, Daniel Crosta
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice,
#   this list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

__all__ = ('FSResultStorage', )

from dabble import ResultStorage
from os.path import exists, join, abspath
from os import SEEK_END
from lockfile import FileLock
import json


def find_lines(filename, **pattern):
    """Find a line (JSON-formatted) in the given file where
    all keys in `pattern` are present as keys in the line's
    JSON, and where their values equal the corresponding
    values in `pattern`. Additional keys in the line are
    ignored. If no matching line is found, or if the
    file does not exist, return None.
    """
    if exists(filename):
        with file(filename, 'r') as fp:
            for line in fp:
                try:
                    data = json.loads(line)
                except:
                    continue
                matches = True
                for key, value in pattern.iteritems():
                    matches = matches and key in data and data[key] == value
                if matches:
                    yield data

def find_line(filename, **pattern):
    """Return the first line that would be found by
    :func:`find_lines`.
    """
    for line in find_lines(filename, **pattern):
        return line
    return None

lock = None
def append_line(filename, **line):
    """Safely (i.e. with locking) append a line to
    the given file, serialized as JSON.
    """
    global lock

    data = json.dumps(line, separators=(',', ':')) + '\n'
    with lock:
        with file(filename, 'a') as fp:
            fp.seek(0, SEEK_END)
            fp.write(data)


class FSResultStorage(ResultStorage):

    def __init__(self, directory):
        """Set up storage in the filesystem for A/B test results.

        :Parameters:
          - `directory`: an existing directory in the filesystem where
            results can be stored. Several files with the ".dabble"
            extension will be created.
          - `namespace`: the name prefix used to name collections
        """
        global lock

        self.directory = abspath(directory)

        if not exists(self.directory):
            raise Exception('directory "%s" does not exist' % self.directory)

        lock = FileLock(join(self.directory, 'lock.dabble'))

        self.tests_path = join(self.directory, 'tests.dabble')
        self.results_path = join(self.directory, 'results.dabble')
        self.alts_path = join(self.directory, 'alts.dabble')

    def save_test(self, test_name, alternatives):
        existing = find_line(self.tests_path, t=test_name)
        if existing and existing['a'] != alternatives:
            raise Exception(
                'test "%s" already exists with different alternatives' % test_name)

        append_line(self.tests_path, t=test_name, a=alternatives)

    def record(self, identity, test_name, alternative, action, completed=False):
        append_line(self.results_path,
                    i=identity, t=test_name, n=alternative, a=action, c=completed)

    def is_completed(self, identity, test_name, alternative):
        completed = find_line(self.results_path, i=identity, t=test_name, n=alternative, c=True)
        return completed is not None

    def set_alternative(self, identity, test_name, alternative):
        existing = find_line(self.alts_path, i=identity, t=test_name)
        if existing and existing['n'] != alternative:
            raise Exception(
                'different alternative already set for identity %s' % identity)

        append_line(self.alts_path, i=identity, t=test_name, n=alternative)

    def get_alternative(self, identity, test_name):
        existing = find_line(self.alts_path, i=identity, t=test_name) or {}
        return existing.get('n')

    def ab_report(self, test_name, a, b):
        test = find_line(self.tests_path, t=test_name)
        if test is None:
            raise Exception('unknown test "%s"' % test_name)

        out = {
            'test_name': test_name,
            'alternatives': test['a'],
            'results': [
                {'attempted': set(), 'completed': set()}
                for alt in test['a']
            ]
        }

        for data in find_lines(self.results_path, t=test_name):
            result = out['results'][data['n']]
            if data['a'] == a:
                result['attempted'].add(data['i'])
            elif data['a'] == b and data['i'] in result['attempted']:
                result['completed'].add(data['i'])

        for result in out['results']:
            result['attempted'] = len(result['attempted'])
            result['completed'] = len(result['completed'])

        return out

