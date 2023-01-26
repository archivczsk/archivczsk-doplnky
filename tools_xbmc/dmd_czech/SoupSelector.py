"""
	BeautifulSoup HTML parser extended with CSS selector

	Suppored selectors:
	
		*				any element

		E				an element of type E

		E.warning		an E element whose class is "warning" (the document
						 language specifies how class is determined).

		E#myid			an E element with ID equal to "myid".

		E[foo]			an E element with a "foo" attribute

		E[foo="bar"]	an E element whose "foo" attribute value is exactly
						 equal to "bar"

		E[foo~="bar"]	an E element whose "foo" attribute value is a list
						 of whitespace-separated values, one of which is
						 exactly equal to "bar"

		E[foo^="bar"]	an E element whose "foo" attribute value begins
						 exactly with the string "bar"

		E[foo$="bar"]	an E element whose "foo" attribute value ends exactly
						 with the string "bar"

		E[foo*="bar"]	an E element whose "foo" attribute value contains
						 the substring "bar"

		E[foo|="en"]	an E element whose "foo" attribute has
						 a hyphen-separated list of values beginning
						 (from the left) with "en"

		E F				an F element descendant of an E element

		E > F			an F element child of an E element

		E + F			an F element immediately preceded by an E element

		E ~ F			an F element preceded by an E element

	See also:
		
		http://www.w3.org/TR/css3-selectors/

"""

__author__ = "Tomas Pokorny (tomas.zemres@gmail.com)"
__version__ = "0.1"
__license__ = "GPL"

__all__ = ["select", "select_first"]

import re
import BeautifulSoup

try:
	basestring
except NameError:
	basestring = str


RE_SPACE = re.compile(r'\s+')
RE_SEP	= re.compile(r'\s*([>+~])\s*|\s+')
RE_TAG	= re.compile(r'[\w-]+|[*]', re.I)
RE_EXT	= re.compile(r'([.#])([\w-]+)', re.I)
RE_ATTR = re.compile(r'''
				\[								# left backet
					(?P<attr>[\w-]+)			# attribute name
					(?P<match>					# with/without pattern/value
						(?P<op>[~^$*|]?) =		# operator
						(?P<pattern>			  # pattern with/without quotes
							"[^"]+" | [^"'\]]+
						)
					)?
				\]								# right bracket
			''', re.I | re.X)


class SelectorError(Exception):
	pass

class ResultList(list):
	pass

def filter_to_callable(filter_def):
	""" Convert filter definition to lamba function """
	if callable(filter_def):
		return filter_def

	if filter_def is True:
		return lambda v: v is not None

	if hasattr(filter_def, 'match'):
		# regexp object
		def mkFilterClosure(pattern):
			return lambda v: v is not None and pattern.search(v)
		return mkFilterClosure(filter_def)

	if hasattr(filter_def, '__iter__'):
		def mkFilterClosure(pattern):
			return lambda v: v in pattern
		return mkFilterClosure(filter_def)

	if isinstance(filter_def, basestring):
		def mkFilterClosure(pattern):
			return lambda v: v is not None and v == pattern
		return mkFilterClosure(filter_def)

	raise Exception("Invalid filter_def value: " + repr(filter_def))


def update_filters(target_dict, **kwargs):
	""" Recursive extend filters dictionary given in first argument
		by keyword args
	"""
	for key, value in list(kwargs.items()):
		if key in target_dict:
			if isinstance(target_dict ,dict) and isinstance(value, dict):
				update_filters( target_dict[ key ], **value)
			else:
				# "AND" filters:
				old_filter = filter_to_callable( target_dict[key] )
				new_filter = filter_to_callable( value )
				target_dict[key] = lambda v: old_filter(v) and new_filter(v)
		
		else:
			target_dict[key] = value
	


def compile_selector(selector):
	""" Compile CSS selector string to lits of filter parameters """
	outList = []
	filters = {}
	partno = 0
	m = None
	part = selector
	while part:
		if m:
			part = part[m.end():]
			if not part and partno:
				outList.append( filters )
				return outList	# return valid output

		if partno:
			m = RE_SEP.match(part)
			if m:
				partno = 0
				op = m.group(1)

				outList.append(filters)
				filters = {}
				if op == '>':
					# E > F	   -- an F element child of an E element
					filters['recursive'] = False

				elif op == '+':
					# E + F	   -- an F element immediately preceded by an E element
					def immediateNextSibling(content, **kwargs):
						immediateNext = content.findNextSibling()
						if immediateNext:
							found = content.findNextSibling(**kwargs)
							if found and id(found) == id(immediateNext):
								return [ found ]
						return []
					filters['call'] = immediateNextSibling

				elif op == '~':
					# E ~ F	   -- an F element preceded by an E element
					filters['call'] = 'findNextSiblings'

				elif op:
					break # error
				
				continue # next part

		partno += 1

		if partno == 1:
			m = RE_TAG.match( part )
			if m:
				# Filter tag name or *
				tag = m.group(0)
				if tag != '*':
					update_filters(filters, name=tag)
					
				continue # next part

		m = RE_EXT.match( part )
		if m:
			(symbol, key) = m.groups()
			if symbol == '#':
				# select by attribute class
				update_filters(filters, attrs={'id': key})
			elif symbol == '.':
				# select by attribute id
				update_filters(filters, attrs={
					'class': re.compile("(^|\s)%s($|\s)" % key)
				})
			else:
				break # error

			continue # next part

		m = RE_ATTR.match( part )
		if m:
			attr = m.group('attr')
			if m.group('match'):
				(op, pattern) = (m.group('op'), m.group('pattern'))

				if pattern.startswith('"') and pattern.endswith('"'):
					pattern = pattern[1:-1]

				if not op:
					# E[foo="bar"] 
					update_filters(filters, attrs={ attr : pattern })

				elif op == '~':
					# E[foo~="bar"]
					def mkFilterClosure(pattern):
						return lambda v: v and pattern in RE_SPACE.split(v)
					update_filters(filters, attrs={
						attr : mkFilterClosure(pattern)
					})

				elif op == '^':
					# E[foo^="bar"]
					def mkFilterClosure(pattern):
						return lambda v: v and v.startswith(pattern)
					update_filters(filters, attrs={
						attr : mkFilterClosure(pattern)
					})

				elif op == '$':
					# E[foo$="bar"]
					def mkFilterClosure(pattern):
						return lambda v: v and v.endswith(pattern)
					update_filters(filters, attrs={
						attr : mkFilterClosure(pattern)
					})

				elif op == '*':
					# E[foo*="bar"]
					def mkFilterClosure(pattern):
						return lambda v: v and (pattern in v)
					update_filters(filters, attrs={
						attr : mkFilterClosure(pattern)
					})

				elif op == '|':
					# E[foo|="en"]
					def mkFilterClosure(pattern):
						return lambda v: v and ( v == pattern \
												or v.startswith(pattern + '-') )
					update_filters(filters, attrs={
						attr : mkFilterClosure(pattern)
					})

				else:
					break # error

			else:
				update_filters(filters, attrs={ attr : True })
				# E[foo] - an E element with a "foo" attribute

			continue # next part

		break # error - any regexp does not match

	# Raise invalid selector error:
	raise SelectorError("Invalid Selector: " + repr(selector))



def search_call(content, call='findAll', **filters):
	if callable(call):
		return call(content, **filters)
	return getattr(content, call)(**filters)


def select(content, selector, limit=None):
	""" Find all elements by CSS selector

		Paramters:
			content	 - BeatifulSoup document
			selector - CSS selector string
			limit	 - maximum number of returned items
	"""
	compiledList = compile_selector(selector)
	#print( "Compiled %r ==> %r" % (selector, compiledList) )

	if not isinstance(content, list):
		content = [ content ]

	while compiledList:
		filters = compiledList.pop(0)
		foundList = ResultList()
		added = {}
		for searchItem in content:
			for foundItem in search_call(searchItem, **filters):
				# eliminate duplices in result
				if id(foundItem) not in added:
					added[ id(foundItem) ] = 1
					foundList.append( foundItem )
					if not compiledList and limit == len(foundList):
						return foundList
		content = foundList

	return content


def select_first(content, selector):
	""" Find single element by given CSS selector """
	foundList = select(content, selector, limit=1)
	if foundList:
		return foundList[0]
		
	return None # not found


# Extend BeautifulSoup classes and ResultList:
for cls in ( BeautifulSoup.PageElement, BeautifulSoup.ResultSet, ResultList):
	cls.select = select
	cls.select_first = select_first

