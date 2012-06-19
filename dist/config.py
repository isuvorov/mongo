#!/usr/bin/env python

import os, re, sys, textwrap
import api_data
from dist import compare_srcfile

# Temporary file.
tmp_file = '__tmp'

#####################################################################
# Update wiredtiger.in with doxygen comments
#####################################################################
f='../src/include/wiredtiger.in'
tfile = open(tmp_file, 'w')

cbegin_re = re.compile(r'(\s*\*\s*)@config(?:empty|start)\{(.*?),.*\}')

def gettype(c):
	'''Derive the type of a config item'''
	checks = c.flags
	ctype = checks.get('type', None)
	if not ctype and ('min' in checks or 'max' in checks):
		ctype = 'int'
	return ctype or 'string'

def typedesc(c):
	'''Descripe what type of value is expected for the given config item'''
	checks = c.flags
	cmin = str(checks.get('min', ''))
	cmax = str(checks.get('max', ''))
	choices = checks.get('choices', [])
	ctype = gettype(c)
	desc = {
		'boolean' : 'a boolean flag',
		'format'  : 'a format string',
		'int'     : 'an integer',
		'list'    : 'a list',
		'string'  : 'a string'}[ctype]
	if cmin and cmax:
		desc += ' between ' + cmin + ' and ' + cmax
	elif cmin:
		desc += ' greater than or equal to ' + cmin
	elif cmax:
		desc += ' no more than ' + cmax
	if choices:
		if ctype == 'list':
			desc += ', with values chosen from the following options: '
		else:
			desc += ', chosen from the following options: '
		desc += ', '.join('\\c "' + c + '"' for c in choices)
	elif ctype == 'list':
		desc += ' of strings'
	return desc

# Some configuration strings can be modified at run-time: instead of listing
# the strings multiple times in api_data.py, review the open methods and copy
# the information into the handle's configuration method.
for a in sorted(api_data.methods['wiredtiger_open'].config):
	if 'runtime' in a.flags:
		api_data.methods['connection.config'].config.append(a)
for a in sorted(api_data.methods['session.open_cursor'].config):
	if 'runtime' in a.flags:
		api_data.methods['cursor.config'].config.append(a)

skip = False
for line in open(f, 'r'):
	if skip:
		if '@configend' in line:
			skip = False
		continue

	m = cbegin_re.match(line)
	if not m:
		tfile.write(line)
		continue

	prefix, config_name = m.groups()
	if config_name not in api_data.methods:
		print >>sys.stderr, "Missing configuration for " + config_name
		tfile.write(line)
		continue

	skip = ('@configstart' in line)

	if not api_data.methods[config_name].config:
		tfile.write(prefix + '@configempty{' + config_name +
				', see dist/api_data.py}\n')
		continue

	tfile.write(prefix + '@configstart{' + config_name +
			', see dist/api_data.py}\n')

	w = textwrap.TextWrapper(width=80-len(prefix.expandtabs()),
			break_on_hyphens=False)
	lastname = None
	for c in sorted(api_data.methods[config_name].config):
		name = c.name
		if '.' in name:
			print >>sys.stderr, "Bad config key " + name

		# Deal with duplicates: with complex configurations (like
		# WT_SESSION::create), it's simpler to deal with duplicates here than
		# manually in api_data.py.
		if name == lastname:
			continue
		lastname = name
		desc = textwrap.dedent(c.desc) + '.'
		desc = desc.replace(',', '\\,')
		default = '\\c ' + str(c.default) if c.default or gettype(c) == 'int' \
				else 'empty'
		tdesc = typedesc(c) + '; default ' + default + '.'
		tdesc = tdesc.replace(',', '\\,')
		output = '@config{' + ','.join((name, desc, tdesc)) + '}'
		for l in w.wrap(output):
			tfile.write(prefix + l + '\n')

	tfile.write(prefix + '@configend\n')

tfile.close()
compare_srcfile(tmp_file, f)

#####################################################################
# Create config_def.c with defaults for each config string
#####################################################################
f='../src/config/config_def.c'
tfile = open(tmp_file, 'w')

tfile.write('''/* DO NOT EDIT: automatically built by dist/config.py. */

#include "wt_internal.h"
''')

# Make a TextWrapper that can wrap at commas.
w = textwrap.TextWrapper(width=72, break_on_hyphens=False)
w.wordsep_re = w.wordsep_simple_re = re.compile(r'(,)')

def checkstr(c):
	'''Generate the JSON string used by __wt_config_check to validate the
	config string'''
	checks = c.flags
	ctype = gettype(c)
	cmin = str(checks.get('min', ''))
	cmax = str(checks.get('max', ''))
	choices = checks.get('choices', [])
	result = []
	if ctype != 'string':
		result.append('type=' + ctype)
	if cmin:
		result.append('min=' + cmin)
	if cmax:
		result.append('max=' + cmax)
	if choices:
		result.append('choices=' + '[' +
		    ','.join('\\"' + s + '\\"' for s in choices) + ']')
	return ','.join(result)

def get_default(c):
	t = gettype(c)
	if c.default or t == 'int':
		return str(c.default)
	elif t == 'string':
		return '""'
	else:
		return '()'

for name in sorted(api_data.methods.keys()):
	ctype = api_data.methods[name].config
	name = name.replace('.', '_')
	tfile.write('''
const char *
__wt_confdfl_%(name)s =
%(config)s;
''' % {
	'name' : name,
	'config' : '\n'.join('    "%s"' % line
		for line in w.wrap(','.join('%s=%s' % (c.name, get_default(c))
			for c in sorted(ctype))) or [""]),
})
	tfile.write('''
const char *
__wt_confchk_%(name)s =
%(check)s;
''' % {
	'name' : name,
	'check' : '\n'.join('    "%s"' % line
		for line in w.wrap(','.join('%s=(%s)' % (c.name, checkstr(c))
			for c in sorted(ctype))) or [""]),
})

tfile.close()
compare_srcfile(tmp_file, f)
