#/*
# *		 Copyright (C) 2011 Libor Zoubek
# *
# *
# *	 This Program is free software; you can redistribute it and/or modify
# *	 it under the terms of the GNU General Public License as published by
# *	 the Free Software Foundation; either version 2, or (at your option)
# *	 any later version.
# *
# *	 This Program is distributed in the hope that it will be useful,
# *	 but WITHOUT ANY WARRANTY; without even the implied warranty of
# *	 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# *	 GNU General Public License for more details.
# *
# *	 You should have received a copy of the GNU General Public License
# *	 along with this program; see the file COPYING.	 If not, write to
# *	 the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *	 http://www.gnu.org/copyleft/gpl.html
# *
# */


##########################################################3
# all resolvers modules in this directory must have following methods:

# __name__ - name of the resolver module - can override module filename
# def supports(url) - returns true iff resolver is able to resolve url to stream otherwise false
# def resolve(url) - returns array of all hashmaps that were resolved
#	- if resolving fails, nothing is returned
#	- a hash MUST contain key 'url' - it's value is stream URL
#	- optional keys are 'subs' (link to subtitle), 'quality' (quality string like '240p' or just 'HD'
