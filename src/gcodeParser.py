#!/usr/bin/env python

import math
import re
import numpy as np
import re

def preg_match(rex,s,m,opts={}):
   _m = re.search(rex,s)
   m.clear()
   if _m:
      m.append(s)
      m.extend(_m.groups())
      return True
   return False

class GcodeParser:
	
	def __init__(self):
		self.model = GcodeModel(self)
		self.current_type = None
		self.layer_count = None
		self.layer_current = None
		self.current_tool = None
		self.variables = dict()


	def file_to_lines_array(self, file_path):
		"""Reads a file and returns an array of its lines."""
		try:
			with open(file_path, 'r') as file:
				lines = file.readlines()
			return lines
		except FileNotFoundError:
			return f"Error: File not found at {file_path}"
	

	def parseCode(self, code):
		# read the gcode file for initial variable assignments
		var_multiplier = 1
		for line in code:
			if line == "$0":
				var_multiplier = 10000
			match = re.match(r"#(\d+)=(-?\d*\.?\d*)", line)
			if match and match.group(1) and match.group(2):
				self.variables[match.group(1)] = float(match.group(2)) / var_multiplier


		# init line counter
		self.lineNb = 0
		# for all lines
		for line in code:
			# inc line counter
			self.lineNb += 1
			# remove trailing linefeed
			self.line = line.rstrip()
			# parse a line
			self.parseLine()
			
		return self.model
		
	def parseLine(self):
		# strip comments:
		## first handle round brackets
		command = re.sub("\([^)]*\)", "", self.line)
		## then semicolons
		idx = command.find(';')
		if idx >= 0:                            # -- any comment to parse?
			m = []
			if preg_match(r'TYPE:\s*(\w+)',command,m):
				self.current_type = m[1].lower()
			elif preg_match(r'; (skirt|perimeter|infill|support)',command,m):
				self.current_type = m[1]
			elif not self.layer_count and re.search(r'LAYER_COUNT:',command):
				self.layer_count = 1
			elif preg_match(r'LAYER:\s*(\d+)',command,m):   # -- we have actual LAYER: counter! let's use it
				self.layer_count = 1
				self.layer_current = int(m[1])
			#elif preg_match(r'; (\w+):\s*"?(\d+)"?',command,m): 
			#	self.metadata[m[1]] = m[2]
			command = command[0:idx].strip()
		## detect unterminated round bracket comments, just in case
		idx = command.find('(')
		if idx >= 0:
			self.warn("Stripping unterminated round-bracket comment")
			command = command[0:idx].strip()
		
		# TODO strip logical line number & checksum
		
		# If line is a variable calculation, update the variable
		if self.is_variable_calc(command):
			self.update_variable(command)

		if self.is_tool_line(command):
			self.update_current_tool(command)

		# code is first word, then args
		splits = re.split(r"([A-z][^A-Z]+)", command)
		splits = [s.strip() for s in splits if len(s) > 0]
		comm = splits
		
		if len(comm) > 0:
			if comm[0][0] == 'G':
				code = comm[0] if (len(comm)>0) else None
				args = comm[1:] if (len(comm)>1) else None
			elif comm[0][0] == '$' or comm[0][0] == 'T':
				code = None
				args = None
				self.current_type = None
			else:
				code = self.current_type
				args = comm
		
		if code:
			if hasattr(self, "parse_"+code):
				self.current_type = code
				getattr(self, "parse_"+code)(args, tool=self.current_tool)
			else:
				self.warn("Unknown code '%s'"%code)
		
	def parseArgs(self, args):
		dic = {}
		if args:
			for bit in args:
				if "#" in bit:
					bit = self.sub_variable_string(bit)
				letter = bit[0]
				try:
					arg_string = bit[1:]
					if self.is_calc_arg(arg_string):
						coord = self.parse_calc(arg_string)
					else:
						coord = float(arg_string)
				except ValueError:
					coord = 1
				dic[letter] = coord
		return dic

	def is_calc_arg(self, arg_string):
		return re.search(r"-?\d*\.\d*[+-/*]\d*\.\d*", arg_string)
	
	def sub_variable_string(self, var_string):
		var = re.match(r".*#(\d+)", var_string)
		if var:
			replacement = self.variables.get(var.group(1), 0.0)
		else:
			replacement = 0.0
		return re.sub(r"#\d+", str(replacement), var_string)

	def parse_calc(self, calc_string):
		subbed_string = calc_string.replace("[", "(").replace("]", ")")
		return eval(subbed_string)

	def is_variable_calc(self, code_line):
		return re.search(r"#(\d+)=((-\[)|[\[#])", code_line)

	def update_variable(self, code_line):
		match = re.match(r"#(\d+)=(.*)", code_line)
		calc_string = match.group(2)
		if "#" in calc_string:
			calc_string = self.sub_variable_string(calc_string)
		new_value = self.parse_calc(calc_string)
		self.variables[match.group(1)] = new_value

	def is_tool_line(self, command):
		return command[0] == "T"

	def update_current_tool(self, command: str):
		if command == "T0":
			self.current_tool = None
		else:
			tool_number = command[1:]
			if len(tool_number) == 3:
				self.current_tool = "T" + tool_number[0]
			else:
				self.current_tool = "T" + tool_number[:2]



	def parse_G0(self, args, tool=None):
		# G0: Rapid move
		# same as a controlled move for us (& reprap FW)
		self.parse_G1(args, "G0")
		
	def parse_G1(self, args, type="G1", tool=None):
		# G1: Controlled move
		self.model.do_G1(self.parseArgs(args), type, tool=tool)
		
	def parse_G2(self, args, type="G2", tool=None):
		# G2: Arc move
		self.model.do_G2(self.parseArgs(args), type, tool=tool)

	def parse_G3(self, args, type="G3", tool=None):
		# G3: Arc move
		self.model.do_G2(self.parseArgs(args), type, tool=tool)
		
	def parse_G20(self, args):
		# G20: Set Units to Inches
		self.error("Unsupported & incompatible: G20: Set Units to Inches")
		
	def parse_G21(self, args):
		# G21: Set Units to Millimeters
		# Default, nothing to do
		pass
		
	def parse_G28(self, args):
		# G28: Move to Origin
		self.model.do_G28(self.parseArgs(args))
		
	def parse_G90(self, args):
		# G90: Set to Absolute Positioning
		self.model.setRelative(False)
		
	def parse_G91(self, args):
		# G91: Set to Relative Positioning
		self.model.setRelative(True)
		
	def parse_G92(self, args):
		# G92: Set Position
		self.model.do_G92(self.parseArgs(args))
		
	def warn(self, msg):
		print("[WARN] Line %d: %s (Text:'%s')" % (self.lineNb, msg, self.line))
		
	def error(self, msg):
		print("[ERROR] Line %d: %s (Text:'%s')" % (self.lineNb, msg, self.line))
		raise Exception("[ERROR] Line %d: %s (Text:'%s')" % (self.lineNb, msg, self.line))

class BBox(object):
	
	def __init__(self, coords):
		self.xmin = self.xmax = coords["X"]
		self.ymin = self.ymax = coords["Y"]
		self.zmin = self.zmax = coords["Z"]
		
	def dx(self):
		return self.xmax - self.xmin
	
	def dy(self):
		return self.ymax - self.ymin
	
	def dz(self):
		return self.zmax - self.zmin
		
	def cx(self):
		return (self.xmax + self.xmin)/2
	
	def cy(self):
		return (self.ymax + self.ymin)/2
	
	def cz(self):
		return (self.zmax + self.zmin)/2
	
	def extend(self, coords):
		self.xmin = min(self.xmin, coords["X"])
		self.xmax = max(self.xmax, coords["X"])
		self.ymin = min(self.ymin, coords["Y"])
		self.ymax = max(self.ymax, coords["Y"])
		self.zmin = min(self.zmin, coords["Z"])
		self.zmax = max(self.zmax, coords["Z"])
		
class GcodeModel:
	
	def __init__(self, parser):
		# save parser for messages
		self.parser = parser
		# latest coordinates & extrusion relative to offset, feedrate
		self.position = {
			"X":0.0,
			"Y":0.0,
			"Z":0.0,
			"I":0.0,
			"J":0.0,
			"K":0.0
		}
		# offsets for relative coordinates
		self.offset = {
			"X":0.0,
			"Y":0.0,
			"Z":0.0,
			"U":0.0,
			"V":0.0,
			"W":0.0}
		self.relative = {
			'U': 'X',
			'V': 'Y',
			'W': 'Z'
		}
		self.tool_position_points = {
			"gang":{
				"X":2.0,
				"Y":0.0,
				"Z":0.0,
			},
			"sub": {
				"X":0.0,
				"Y":0.0,
				"Z":-.5,	
			},
			"back":{
				"X":0.0,
				"Y":0.0,
				"Z":-.5,
			}
		}
		self.tool_dict = {**{f"T{n}":"gang" for n in range(1,11)},
					**{f"T{n}":"sub" for n in range(21,24)},
					**{"T30":"sub"},
					**{f"T{n}":"back" for n in range(31,35)}}
		# if true, args for move (G1) are given relatively (default: absolute)
		self.isRelative = False
		# the segments
		self.segments = []
		self.layers = None
		self.distance = None
		self.extrudate = None
		self.bbox = None
	
	def do_G1(self, args, type, tool=None):
		# G0/G1: Rapid/Controlled move
		# clone previous coords
		coords = dict(self.position)
		# update changed coords
		for axis in args.keys():
			if axis in coords:
				coords[axis] = args[axis]
			elif axis in self.relative:
				coords[self.relative[axis]] += args[axis]
			else:
				self.warn("Unknown axis '%s'"%axis)
		# build segment
		absolute = {
			"X": self.offset["X"] + coords["X"],
			"Y": self.offset["Y"] + coords["Y"],
			"Z": self.offset["Z"] + coords["Z"],
		}
		seg = Segment(type, absolute, self.parser.lineNb, self.parser.line, tool=tool)
		self.addSegment(seg)
		# update model coords
		self.position = coords

	def do_G2(self, args, type, tool=None):
		# G2 & G3: Arc move
		coords = dict(self.position)           # -- clone previous coords
		for axis in args.keys():               # -- update changed coords
			if axis in coords:
				if self.isRelative:
					coords[axis] += args[axis]
				else:
					coords[axis] = args[axis]
			else:
				self.warn("Unknown axis '%s'"%axis)
		# -- self.relative (current pos), coords (new pos)
		dir = 1                                    # -- ccw is angle positive
		if type.find("G2")==0: 
			dir = -1                                # -- cw is angle negative
		xp = self.position["X"] + coords["I"]      # -- center point of arc (static), current pos
		yp = self.position["Y"] + coords["J"]
		es = self.position["E"]
		ep = coords["E"] - es
		as_ = math.atan2(-coords["J"],-coords["I"])      # -- angle start (current pos)
		ae_ = math.atan2(coords["Y"]-yp,coords["X"]-xp)  # -- angle end (new position)
		da = math.sqrt(coords["I"]**2 + coords["J"]**2)
		if dir > 0:
			if as_ > ae_: as_ -= math.pi*2 
			al = abs(ae_ - as_) * dir
		else:    
			if as_ < ae_: as_ += math.pi*2
			al = abs(ae_ - as_) * dir
		n = int(abs(al)*da/.5)
		#if coords['Z']<0.4 or coords['Z']==2.3: print(type,dir,n,np.degrees(as_),np.degrees(ae_),al,coords['Z'],"\n",self.relative,"\n",args)
		if n > 0:		
			for i in range(1,n+1):
				f = i/n
				#print(i,f,n)
				a = as_ + al*f
				coords["X"] = xp + math.cos(a) * da
				coords["Y"] = yp + math.sin(a) * da
				coords["E"] = es + ep*f
				absolute = {
					"X": self.offset["X"] + coords["X"],
					"Y": self.offset["Y"] + coords["Y"],
					"Z": self.offset["Z"] + coords["Z"],
					"F": coords["F"],	# no feedrate offset
					"E": self.offset["E"] + coords["E"]
				}
				seg = Segment(type, absolute, self.parser.lineNb, self.parser.line, tool=tool)
				self.addSegment(seg)
				# update model coords
				self.position = coords
		
	def do_G28(self, args):
		# G28: Move to Origin
		self.warn("G28 unimplemented")
		
	def do_G92(self, args):
		# G92: Set Position
		# this changes the current coords, without moving, so do not generate a segment
		
		# no axes mentioned == all axes to 0
		if not len(args.keys()):
			args = {"X":0.0, "Y":0.0, "Z":0.0, "E":0.0}
		# update specified axes
		for axis in args.keys():
			if axis in self.offset:
				# transfer value from relative to offset
				self.offset[axis] += self.position[axis] - args[axis]
				self.position[axis] = args[axis]
			else:
				self.warn("Unknown axis '%s'"%axis)

	def setRelative(self, isRelative):
		self.isRelative = isRelative
		
	def addSegment(self, segment):
		if self.parser.layer_count:
			segment.layerIdx = self.parser.layer_current
		self.segments.append(segment)
		#print segment
		
	def warn(self, msg):
		self.parser.warn(msg)
		
	def error(self, msg):
		self.parser.error(msg)
		
		
	def classifySegments(self):
		# apply intelligence, to classify segment layers
			
		# first layer at Z=0
		currentLayerIdx = 0
		currentLayerTool = self.segments[0].tool
		currentInLayerIdx = 0

		for seg in self.segments:
			if seg.tool != currentLayerTool:
				currentLayerTool = seg.tool
				currentLayerIdx += 1
				currentInLayerIdx = 0
			
			if not self.parser.layer_count:
				seg.layerIdx = currentLayerIdx
				seg.inLayerIdx = currentInLayerIdx
				currentInLayerIdx += 1
			
			
	def splitLayers(self):
		# split segments into previously detected layers

		# init layer store
		self.layers = []
		
		currentLayerIdx = -1
		
		# for all segments
		for seg in self.segments:
			# next layer
			if currentLayerIdx != seg.layerIdx:
				coords = self.tool_position_points[self.tool_dict.get(seg.tool,"T1")]
				layer = Layer(seg.tool)
				layer.start = coords
				self.layers.append(layer)
				currentLayerIdx = seg.layerIdx
			
			layer.segments.append(seg)
			
			# execute segment
			coords = seg.coords
		
		self.topLayer = len(self.layers)-1
		
	def calcMetrics(self):
		# init distances
		self.distance = 0
		
		# init model bbox
		self.bbox = None
		
		# extender helper
		def extend(bbox, coords):
			if bbox is None:
				return BBox(coords)
			else:
				bbox.extend(coords)
				return bbox
		
		# for all layers
		for layer in self.layers:
			# start at layer start
			coords = layer.start
			
			# init distances and extrudate
			layer.distance = 0
			#layer.range = { }
			#for k in ['X','Y','Z']: layer.range[k] = { }
			layer.bbox = extend(layer.bbox, coords)

			# include start point
			self.bbox = extend(self.bbox, coords)

			# for all segments
			for seg in layer.segments:
				# calc XYZ distance
				d  = (seg.coords["X"]-coords["X"])**2
				d += (seg.coords["Y"]-coords["Y"])**2
				d += (seg.coords["Z"]-coords["Z"])**2
				seg.distance = math.sqrt(d)

				#for k in ['X','Y','Z']:
				#	if layer.range[k].max < coords[k]: layer.range[k].max = coords[k]
				#	if layer.range[k].min > coords[k]: layer.range[k].min = coords[k]
	
				# accumulate layer metrics
				layer.distance += seg.distance
				
				# execute segment
				coords = seg.coords
				
				# include end point
				extend(self.bbox, coords)

			layer.end = coords			

			# accumulate total metrics
			self.distance += layer.distance
		
	def postProcess(self):
		self.classifySegments()
		self.splitLayers()
		self.calcMetrics()

	def __str__(self):
		return "<GcodeModel: len(segments)=%d, len(layers)=%d, distance=%f, bbox=%s>"%(len(self.segments), len(self.layers), self.distance, self.bbox)
	
class Segment:
	def __init__(self, type, coords, lineNb, line, tool=None):
		self.type = type
		self.coords = coords
		self.lineNb = lineNb
		self.line = line
		self.tool = tool
		self.layerIdx = None
		self.inLayerIdx = None
		self.distance = None
	def __str__(self):
		return "<Segment: type=%s, lineNb=%d, tool=%s, layerIdx=%d, distance=%f>"%(self.type, self.lineNb, self.tool, self.layerIdx, self.distance)
		
class Layer:
	def __init__(self, tool):
		self.tool = tool
		self.segments = []
		self.distance = None
		self.bbox = None

	def __str__(self):
		return "<Layer: Z=%f, len(segments)=%d, distance=%f>"%(self.Z, len(self.segments), self.distance)
		
		
if __name__ == '__main__':
	path = "test.gcode"

	parser = GcodeParser()
	code = parser.file_to_lines_array(path)
	model = parser.parseCode(code)
	model.postProcess()
	print(model)
