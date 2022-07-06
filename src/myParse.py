
import sys

import pyverilog
from pyverilog.vparser.parser import parse
from parse_cell_lib import CellInfo

type_map = {
	'and': 'AND',
	'nand': 'NAND',
	'or': 'OR',
	'nor': 'NOR',
	'xor': 'XOR',
	'xnor': 'NXOR',
	'not': 'INV',
	'buf': 'BUF'
}

def myParse( fname ):

	print( f'Parsing {fname}' )

	ast, directives = parse([fname])
	top_module = ast.description.definitions[0]

	nodes: List[Tuple[str, Dict[str, str]]] = [
		("1'b0", {"type": "1'b0"}),
		("1'b1", {"type": "1'b1"}),
	]  # a list of (node, {"type": type})
	edges: List[
		Tuple[str, str, Dict[str, bool]]
	] = []  # a list of (src, dst, {"is_reverted": is_reverted})

	buff_replace = {}

	for item in top_module.items:
		if type(item) != pyverilog.vparser.ast.InstanceList:
			continue
		
		instance = item.instances[0]
		mtype = type_map[instance.module]
		ports = instance.portlist

		fanins = []

		# read port names
		for idx,p in enumerate(ports):
			if ( type(p.argname) == pyverilog.vparser.ast.Pointer ):
				pname = f'{p.argname.var}[{p.argname.ptr}]'
			else:
				pname = p.argname.name

			if idx == 0:
				fanout = pname
			else:
				fanins.append(pname)
		

		# create nodes
		if mtype != 'BUF':
			nodes.append( (fanout, {"type": mtype}) )
		else:
			buff_replace[fanout] = fanins[0]
			continue

		# create edges
		for fi in fanins:
			edges.append(
				(
					fi,
					fanout,
					{"is_reverted": False, "is_sequencial": False },
				)
			)
	
	# recursively update buff_replace
	new_buff_replace = {}
	for key, val in buff_replace.items():
		r = val
		while buff_replace.get( r, None ) != None:
			r = buff_replace[r]
		new_buff_replace[key] = r
	buff_replace = new_buff_replace
		

	# change the edges with src as buffer
	new_edges = []
	for edge in edges:
		if buff_replace.get(edge[0],None) is not None:
			new_edges.append( (buff_replace[edge[0]],edge[1],edge[2]) )
		else:
			new_edges.append(edge)
	edges = new_edges


	# add the node of PIs
	gate_names = set([n[0] for n in nodes])
	node_dict = {}
	for nm in gate_names:
		node_dict[nm] = True
	pis = {}
	for (src, _, _) in edges:
		if node_dict.get(src,None) is None and pis.get(src,None) is None:
			nodes.append((src, {"type": "PI"}))
			pis[src] = True
	
	return nodes, edges


if __name__ == '__main__':
	myParse( sys.argv[1])