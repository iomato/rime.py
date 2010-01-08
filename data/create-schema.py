#! /usr/bin/env python

try:
    import psyco
    psyco.full()
    print 'psyco activated.'
except:
    pass

import os
import sys
import optparse
import sqlite3
import re

def debug(*what):
    print >> sys.stderr, u'[DEBUG]: ', u' '.join(map(unicode, what))


INIT_PLUME_DB_SQLS = """
CREATE TABLE IF NOT EXISTS setting_paths (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS setting_values (
    path_id INTEGER,
    value TEXT
);
CREATE TABLE IF NOT EXISTS phrases (
    id INTEGER PRIMARY KEY,
    phrase TEXT UNIQUE
);
"""

CREATE_DICT_SQLS = """
CREATE TABLE IF NOT EXISTS %(prefix)s_stats (
    sfreq INTEGER,
    ufreq INTEGER
);
CREATE TABLE IF NOT EXISTS %(prefix)s_unigram (
    id INTEGER PRIMARY KEY,
    p_id INTEGER,
    okey TEXT,
    sfreq INTEGER,
    ufreq INTEGER
);
CREATE TABLE IF NOT EXISTS %(prefix)s_bigram (
    e1 INTEGER,
    e2 INTEGER,
    bfreq INTEGER,
    PRIMARY KEY (e1, e2)
);
INSERT INTO %(prefix)s_stats VALUES (0, 0);
CREATE UNIQUE INDEX IF NOT EXISTS %(prefix)s_entry_idx ON %(prefix)s_unigram (p_id, okey);
CREATE TABLE IF NOT EXISTS %(prefix)s_keywords (
    keyword TEXT
);
CREATE TABLE IF NOT EXISTS %(prefix)s_keys (
    id INTEGER PRIMARY KEY,
    ikey TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS %(prefix)s_ku (
    k_id INTEGER,
    u_id INTEGER,
    PRIMARY KEY (k_id, u_id)
);
CREATE TABLE IF NOT EXISTS %(prefix)s_kb (
    k_id INTEGER,
    b_id INTEGER,
    PRIMARY KEY (k_id, b_id)
);
"""

DROP_DICT_SQLS = """
DROP INDEX IF EXISTS %(prefix)s_entry_idx;
DROP TABLE IF EXISTS %(prefix)s_unigram;
DROP TABLE IF EXISTS %(prefix)s_bigram;
DROP TABLE IF EXISTS %(prefix)s_stats;
DROP TABLE IF EXISTS %(prefix)s_keywords;
DROP TABLE IF EXISTS %(prefix)s_keys;
DROP TABLE IF EXISTS %(prefix)s_ku;
DROP TABLE IF EXISTS %(prefix)s_kb;
"""

CLEAN_UP_SQLS = """
DROP INDEX IF EXISTS %(prefix)s_entry_idx;
"""

CLEAR_SETTING_VALUE_SQL = """
DELETE FROM setting_values WHERE path_id IN (SELECT id FROM setting_paths WHERE path LIKE :path);
"""
CLEAR_SETTING_PATH_SQL = """
DELETE FROM setting_paths WHERE path LIKE :path;
"""

QUERY_SETTING_PATH_SQL = """
SELECT id FROM setting_paths WHERE path = :path;
"""

ADD_SETTING_PATH_SQL = """
INSERT INTO setting_paths VALUES (NULL, :path);
"""

ADD_SETTING_VALUE_SQL = """
INSERT INTO setting_values VALUES (:path_id, :value);
"""

QUERY_PHRASE_SQL = """
SELECT id FROM phrases WHERE phrase = :phrase;
"""

ADD_PHRASE_SQL = """
INSERT INTO phrases VALUES (NULL, :phrase);
"""

usage = 'usage: %prog [options] schema-file [keyword-file [phrase-file]]'
parser = optparse.OptionParser(usage)

parser.add_option('-s', '--schema', dest='schema', help='shortcut to specifying a standard set of input file names')

parser.add_option('-d', '--db-file', dest='db_file', help='specify destination sqlite db', metavar='FILE')

parser.add_option('-k', '--keep', action='store_true', dest='keep', default=False, help='keep existing dict')

parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False, help='make lots of noice')

parser.add_option('-c', '--compact', action='store_true', dest='compact', default=False, help='compact db file')

options, args = parser.parse_args()

if options.schema:
    schema_file = '%s-schema.txt' % options.schema
    keyword_file = '%s-keywords.txt' % options.schema
    phrase_file = '%s-phrases.txt' % options.schema
else:
    if len(args) not in range(1, 4):
        parser.error('incorrect number of arguments')
    schema_file = args[0] if len(args) > 0 else None
    keyword_file = args[1] if len(args) > 1 else None
    phrase_file = args[2] if len(args) > 2 else None

if not options.db_file:
    home_path = os.getenv('HOME')
    db_path = os.path.join(home_path, '.ibus', 'zime')
    if not os.path.isdir(db_path):
        os.makedirs(db_path)
    db_file = os.path.join(db_path, 'zime.db')
else:
    db_file = options.db_file

conn = sqlite3.connect(db_file)
cur = conn.cursor()
cur.executescript(INIT_PLUME_DB_SQLS)

schema = None
prefix = None
#delim = None

max_key_length = 2

def get_or_insert_setting_path(path):
    args = {'path' : path}
    r = cur.execute(QUERY_SETTING_PATH_SQL, args).fetchone()
    if r:
        return r[0]
    else:
        cur.execute(ADD_SETTING_PATH_SQL, args)
        return cur.lastrowid

def clear_schema_setting(path):
    cur.execute(CLEAR_SETTING_VALUE_SQL, {'path' : path})
    cur.execute(CLEAR_SETTING_PATH_SQL, {'path' : path})

spelling_rules = []
fuzzy_rules = []

if schema_file:
    equal_sign = re.compile(ur'\s*=\s*')
    compile_repl_pattern = lambda x: (re.compile(x[0]), x[1])
    f = open(schema_file, 'r')
    for line in f:
        x = line.strip().decode('utf-8')
        if not x or x.startswith(u'#'):
            continue
        try:
            (path, value) = equal_sign.split(x, 1)
        except:
            print >> sys.stderr, 'error parsing (%s) %s' % (schema_file, x)
            exit()
        if not schema:
            m = re.match(ur'Schema/(\w+)', path)
            if m:
                schema = m.group(1)
                print >> sys.stderr, 'processing schema: %s' % schema
                clear_schema_setting(path)
                clear_schema_setting(u'Config/%s/%%' % schema)
        else:
            if not prefix and path == u'Config/%s/Prefix' % schema:
                prefix = value
                print >> sys.stderr, 'dict prefix: %s' % prefix
            #if not delim and path == u'Config/%s/Delimiter' % schema:
            #    if value[0] == u'[' and value[-1] == u']':
            #        delim = value[1]
            #    else:
            #        delim = value[0]
            if path == u'Config/%s/MaxKeyLength' % schema:
                max_key_length = max (2, int(value))
            elif path == u'Config/%s/SpellingRule' % schema:
                spelling_rules.append(compile_repl_pattern(value.split()))
            elif path == u'Config/%s/FuzzyRule' % schema:
                fuzzy_rules.append(compile_repl_pattern(value.split()))
        path_id = get_or_insert_setting_path(path)
        cur.execute(ADD_SETTING_VALUE_SQL, {'path_id' : path_id, 'value' : value})
    f.close()

if options.keep:
    conn.commit()
    conn.close()
    print >> sys.stderr, 'done.'
    exit()

if not prefix:
    print >> sys.stderr, 'error: no prefix specified in schema file.'
    exit()
prefix_args = {'prefix' : prefix}

cur.executescript(DROP_DICT_SQLS % prefix_args)
cur.executescript(CREATE_DICT_SQLS % prefix_args)

ADD_KEYWORD_SQL = """
INSERT INTO %(prefix)s_keywords VALUES (:keyword);
""" % prefix_args

QUERY_KEY_SQL = """
SELECT id FROM %(prefix)s_keys WHERE ikey = :ikey;
""" % prefix_args

ADD_KEY_SQL = """
INSERT INTO %(prefix)s_keys VALUES (NULL, :ikey);
""" % prefix_args

INC_SFREQ_SQL = """
UPDATE %(prefix)s_stats SET sfreq = sfreq + :freq;
""" % prefix_args

ADD_UNIGRAM_SQL = """
INSERT INTO %(prefix)s_unigram VALUES (NULL, :p_id, :okey, :freq, 0);
""" % prefix_args

QUERY_UNIGRAM_SQL = """
SELECT id FROM %(prefix)s_unigram WHERE p_id = :p_id AND okey = :okey;
""" % prefix_args

INC_EFREQ_SQL = """
UPDATE %(prefix)s_unigram SET sfreq = sfreq + :freq WHERE p_id = :p_id AND okey = :okey;
""" % prefix_args

QUERY_KU_SQL = """
SELECT rowid FROM %(prefix)s_ku WHERE k_id = :k_id AND u_id = :u_id;
""" % prefix_args

ADD_KU_SQL = """
INSERT INTO %(prefix)s_ku VALUES (:k_id, :u_id);
""" % prefix_args

def add_keyword(keyword):
    args = {'keyword': keyword}
    cur.execute(ADD_KEYWORD_SQL, args)

def get_or_insert_key(key):
    args = {'ikey' : u' '.join(key)}
    r = None
    while not r:
        r = cur.execute(QUERY_KEY_SQL, args).fetchone()
        if not r:
            cur.execute(ADD_KEY_SQL, args)
    return r[0]

def get_or_insert_phrase(phrase):
    args = {'phrase' : phrase}
    r = None
    while not r:
        r = cur.execute(QUERY_PHRASE_SQL, args).fetchone()
        if not r:
            cur.execute(ADD_PHRASE_SQL, args)
    return r[0]

def inc_sfreq(freq):
    args = {'freq' : freq}
    cur.execute(INC_SFREQ_SQL, args)

def inc_efreq_and_get_u_id(phrase, okey, freq):
    p_id = get_or_insert_phrase(phrase)
    args = {'p_id' : p_id, 'okey' : okey, 'freq' : freq}
    r = cur.execute(QUERY_UNIGRAM_SQL, args).fetchone()
    if not r:
        cur.execute(ADD_UNIGRAM_SQL, args)
        r = cur.execute(QUERY_UNIGRAM_SQL, args).fetchone()
    elif freq > 0:
        cur.execute(INC_EFREQ_SQL, args)
    return r[0]

def add_ku(k_id, u_id):
    args = {'k_id' : k_id, 'u_id' : u_id}
    if not cur.execute(QUERY_KU_SQL, args).fetchone():
        cur.execute(ADD_KU_SQL, args)

keywords = dict()
if keyword_file:
    f = open(keyword_file, 'r')
    for line in f:
        x = line.strip().decode('utf-8')
        if not x or x.startswith(u'#'):
            continue
        try:
            ll = x.split(u'\t', 1)
            (okey, phrase) = ll
        except:
            print >> sys.stderr, 'error: invalid format (%s) %s' % (phrase_file, x)
            exit()
        if okey not in keywords:
            keywords[okey] = [phrase]
        else:
            keywords[okey].append(phrase)
    f.close()

def apply_spelling_rule(m, r):
    return(r[0].sub(r[1], m[0], 1), m[1])
d = dict()
for k, v in [reduce(apply_spelling_rule, spelling_rules, (k, frozenset([k]))) for k in keywords]:
    if k in d:
        d[k] |= v
    else:
        d[k] = v
akas = dict()
def add_aka(s, x):
    if s in akas:
        a = akas[s]
    else:
        a = akas[s] = []
    if x not in a:
        a.append(x)
def del_aka(s, x):
    if s in akas:
        a = akas[s]
    else:
        a = akas[s] = []
    if x in a:
        a.remove(x)
    if not a:
        del akas[s]
def apply_fuzzy_rule(d, r):
    dd = dict(d)
    for x in d:
        if not r[0].search(x):
            continue
        y = r[0].sub(r[1], x, 1)
        if y == x:
            continue
        if y not in dd:
            dd[y] = d[x]
            add_aka(dd[y], y)
        else:
            del_aka(dd[y], y)
            dd[y] |= d[x]
            add_aka(dd[y], y)
    return dd
for k in d:
    add_aka(d[k], k)
reduce(apply_fuzzy_rule, fuzzy_rules, d)

oi_map = dict()
for s in akas:
    spelling = akas[s][0]
    for k in s:
        if k in oi_map:
            a = oi_map[k]
        else:
            a = oi_map[k] = []
        a.append(spelling)
del akas

def g(ikeys, okey, depth):
    if not okey or depth >= max_key_length:
        return ikeys
    r = []
    for x in ikeys:
        if okey[0] not in oi_map:
            if options.verbose:
                print >> sys.stderr, 'invalid keyword encountered: [%s]' % okey[0]
            return []
        for y in oi_map[okey[0]]:
            r.append(x + [y])
    return g(r, okey[1:], depth + 1)

phrase_counter = 0
last_okey = None
key_ids = None

def process_phrase(okey, phrase, freq):
    global phrase_counter, last_okey, key_ids
    phrase_counter += 1
    u_id = inc_efreq_and_get_u_id(phrase, okey, freq)
    if freq != 0:
        inc_sfreq(freq)
    if okey != last_okey:
        last_okey = okey
        key_ids = [get_or_insert_key(k) for k in g([[]], okey.split(), 0)]
        if not key_ids and options.verbose:
            print >> sys.stderr, 'failed index generation for phrase [%s] %s.' % (okey, phrase)
    for k_id in key_ids:
        add_ku(k_id, u_id)

for k in keywords:
    add_keyword(k)
    for p in keywords[k]:
        process_phrase(k, p, 0)
        if options.verbose and phrase_counter % 1000 == 0:
            print >> sys.stderr, '%dk phrases imported from %s.' % (phrase_counter / 1000, keyword_file)
del keywords

if phrase_file:
    f = open(phrase_file, 'r')
    for line in f:
        x = line.strip().decode('utf-8')
        if not x or x.startswith(u'#'):
            continue
        try:
            ll = x.split(u'\t', 2)
            if len(ll) == 3:
                (phrase, freq_str, okey) = ll
                freq = int(freq_str)
            else:
                (okey, phrase) = ll
                if phrase.startswith(u'*'):
                    phrase = phrase[1:]
                freq = 0
            if u' ' in phrase:
                phrase = phrase.replace(u' ', '')
        except:
            print >> sys.stderr, 'error: invalid format (%s) %s' % (phrase_file, x)
            exit()
        process_phrase(okey, phrase, freq)
        if options.verbose and phrase_counter % 1000 == 0:
            print >> sys.stderr, '%dk phrases imported from %s.' % (phrase_counter / 1000, phrase_file)
    f.close()

print >> sys.stderr, 'cleaning up...'
cur.executescript(CLEAN_UP_SQLS % prefix_args)
if options.compact:
    cur.execute("""VACUUM;""")

conn.commit()
conn.close()
print >> sys.stderr, 'done.'

