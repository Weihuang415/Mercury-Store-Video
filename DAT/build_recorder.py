# Builds /project1/RECORDER. Run once from the textport:
#   exec(open(project.folder + '/DAT/build_recorder.py').read())
#
# null1 -> RECORDER -> switch1 (input 1)

EXEC_FRAME = '''def onFrameStart(frame):
	parent().ext.RecorderExt.Update()
	return
'''

PAREXEC = '''def onPulse(par):
	ext = parent().ext.RecorderExt
	actions = {
		'Record': ext.Record,
		'Play': ext.Play,
		'Stop': ext.Stop,
		'Listclips': ext.PrintClips,
	}
	if par.name in actions:
		actions[par.name]()
	return
'''


def setMenuByLabel(par, label):
	labels = [l.lower() for l in par.menuLabels]
	if label.lower() in labels:
		par.menuIndex = labels.index(label.lower())
	else:
		print(f'[BUILD] {par.owner.name}.{par.name}: no "{label}" in {par.menuLabels}')


def buildRecorder():
	root = op('/project1')
	if root.op('RECORDER'):
		print('[BUILD] /project1/RECORDER already exists, delete it first to rebuild')
		return

	source = root.op('null1')
	comp = root.create(baseCOMP, 'RECORDER')
	comp.nodeX = source.nodeX + 200
	comp.nodeY = source.nodeY - 300

	# Custom parameters
	page = comp.appendCustomPage('Recorder')
	p = page.appendFloat('Recordseconds', label='Record Seconds')[0]
	p.default, p.val, p.normMin, p.normMax = 5, 5, 0.5, 30
	p.min, p.clampMin = 0.1, True
	page.appendPulse('Record')
	page.appendPulse('Play')
	page.appendPulse('Stop')
	page.appendToggle('Loop')
	p = page.appendMenu('Mode')[0]
	p.menuNames = ['latest', 'random', 'index']
	p.menuLabels = ['Latest', 'Random', 'Index']
	p.default, p.val = 'latest', 'latest'
	p = page.appendInt('Clipindex', label='Clip Index')[0]
	p.default, p.val, p.min, p.clampMin = 1, 1, 1, True
	p = page.appendFloat('Fadeseconds', label='Fade Seconds')[0]
	p.default, p.val, p.normMax = 0.5, 0.5, 3
	p.min, p.clampMin = 0, True
	p = page.appendFloat('Opacity')[0]
	p.default, p.val = 1, 1
	p.min, p.max, p.clampMin, p.clampMax = 0, 1, True, True
	p = page.appendFloat('Speed')[0]
	p.default, p.val, p.normMin, p.normMax = 1, 1, 0.1, 4
	p.min, p.clampMin = 0.1, True
	page.appendPulse('Listclips', label='List Clips')
	page.appendStr('Status')

	# Network inside
	live = comp.create(inTOP, 'in1')
	live.nodeX, live.nodeY = 0, 0
	nullLive = comp.create(nullTOP, 'null_live')
	nullLive.nodeX, nullLive.nodeY = 200, 0
	nullLive.inputConnectors[0].connect(live)

	movieOut = comp.create(moviefileoutTOP, 'moviefileout_rec')
	movieOut.nodeX, movieOut.nodeY = 400, 200
	movieOut.inputConnectors[0].connect(nullLive)

	movieIn = comp.create(moviefileinTOP, 'moviefilein_play')
	movieIn.nodeX, movieIn.nodeY = 200, -200
	setMenuByLabel(movieIn.par.playmode, 'Sequential')
	movieIn.par.play = False

	cross = comp.create(switchTOP, 'cross_mix')
	cross.nodeX, cross.nodeY = 400, 0
	cross.inputConnectors[0].connect(nullLive)
	cross.inputConnectors[1].connect(movieIn)
	cross.par.blend = True
	cross.par.index = 0

	out = comp.create(outTOP, 'out1')
	out.nodeX, out.nodeY = 600, 0
	out.inputConnectors[0].connect(cross)

	extDat = comp.create(textDAT, 'RecorderExt')
	extDat.nodeX, extDat.nodeY = 0, 400
	extDat.par.file = 'DAT/RecorderExt.py'
	extDat.par.syncfile = True
	extDat.text = open(project.folder + '/DAT/RecorderExt.py').read()

	execFrame = comp.create(executeDAT, 'exec_frame')
	execFrame.nodeX, execFrame.nodeY = 200, 400
	execFrame.text = EXEC_FRAME
	execFrame.par.framestart = True

	parexec = comp.create(parameterexecuteDAT, 'parexec')
	parexec.nodeX, parexec.nodeY = 400, 400
	parexec.text = PAREXEC
	parexec.par.op = comp
	parexec.par.pars = '*'
	parexec.par.custom = True
	parexec.par.builtin = False
	parexec.par.valuechange = False
	parexec.par.onpulse = True

	# Extension
	comp.par.ext0object = "op('./RecorderExt').module.RecorderExt(me)"
	comp.par.ext0promote = True
	comp.par.reinitextensions.pulse()

	# Wire into the main chain
	comp.inputConnectors[0].connect(source)
	switch = root.op('switch1')
	comp.outputConnectors[0].connect(switch)
	switch.par.index = len(switch.inputs) - 1

	print(f'[BUILD] /project1/RECORDER ready: null1 -> RECORDER -> switch1 (index {switch.par.index.eval()})')


buildRecorder()
