# Builds /project1/UI and /project1/UI_window (replaces existing ones).
# Run from the textport:
#   exec(open(project.folder + '/DAT/build_ui.py', encoding='utf-8').read())
#
# UI (Container COMP, 1600x900)
#   webrender      Web Render TOP showing UI/index.html  -> UI background
#   webserver      localhost API the page talks to        -> UIExt.HandleHTTP
#   program, cams  native previews on top of the page      -> no lag
#   mouse          UI mouse forwarded to the page every frame
#
# New scene: tag it 'scene' -> scene_table -> the page shows the button on its next poll.

W, H = 1600, 900
PROGRAM = (328, 112, 800, 450)   # x, top, w, h  (same as UIExt and index.html)
CAMS = (328, 634, 800, 144)

CALLBACKS = '''def onHTTPRequest(webServerDAT, request, response):
	return parent.UI.HandleHTTP(request, response)

def onServerStart(webServerDAT):
	print('[UI] page server on ' + parent.UI.Url())
	return
'''

EXEC_FRAME = '''def onFrameStart(frame):
	parent.UI.ForwardMouse()
	return
'''

WATCH = '''# cam_table changed -> rebuild camera previews

def onTableChange(dat):
	run('op({!r}).Rebuild()'.format(parent.UI.path), delayFrames=1)
	return
'''

PAREXEC = '''def onPulse(par):
	ui = parent.UI
	if par.name == 'Rebuild':
		ui.Rebuild()
	elif par.name == 'Reloadpage':
		ui.ReloadPage()
	elif par.name == 'Openwindow':
		op(ui.par.Window).par.winopen.pulse()
	return
'''


def buildUI():
	root = op('/project1')
	pos = (0, 0)
	for name in ('UI', 'UI_window'):
		old = root.op(name)
		if old:
			if name == 'UI':
				pos = (old.nodeX, old.nodeY)
			old.destroy()
	selector = root.op('scene_selector')
	if pos == (0, 0) and selector:
		pos = (selector.nodeX + 300, selector.nodeY)

	ui = root.create(containerCOMP, 'UI')
	ui.nodeX, ui.nodeY = pos
	ui.color = (0.15, 0.35, 0.55)
	ui.par.parentshortcut = 'UI'
	ui.par.w, ui.par.h = W, H

	page = ui.appendCustomPage('UI')
	for name, label, path in [
		('Selector', 'Scene Selector', '/project1/scene_selector'),
		('Scenetable', 'Scene Table', '/project1/scene_table'),
		('Camtable', 'Camera Table', '/project1/cam_table'),
		('Recorder', 'Recorder', '/project1/00_RECORDER'),
		('Window', 'Window COMP', '/project1/UI_window'),
	]:
		page.appendOP(name, label=label)[0].val = path
	p = page.appendFile('Htmlfile', label='HTML File')[0]
	p.default, p.val = 'UI/index.html', 'UI/index.html'
	p = page.appendInt('Port')[0]
	p.default, p.val = 9980, 9980
	page.appendToggle('Flipv', label='Flip Mouse V')
	page.appendPulse('Openwindow', label='Open Window')
	page.appendPulse('Reloadpage', label='Reload Page')
	page.appendPulse('Rebuild')

	# Extension: text first, then link the file, so the DAT never writes an old copy back
	extDat = ui.create(textDAT, 'UIExt')
	extDat.nodeX, extDat.nodeY = -400, 400
	extDat.text = open(project.folder + '/DAT/UIExt.py', encoding='utf-8').read()
	extDat.par.file = 'DAT/UIExt.py'
	extDat.par.syncfile = True
	ui.par.ext0object = "op('./UIExt').module.UIExt(me)"
	ui.par.ext0promote = True
	ui.par.reinitextensions.pulse()
	ext = extDat.module.UIExt(ui)  # own instance for building
	set_ = ext.setPars

	# Page server (localhost)
	callbacks = ui.create(textDAT, 'webserver_callbacks')
	callbacks.nodeX, callbacks.nodeY = -200, 400
	callbacks.text = CALLBACKS
	server = ui.create(webserverDAT, 'webserver')
	server.nodeX, server.nodeY = -200, 250
	set_(server, callbacks=callbacks, port='=parent.UI.par.Port', active=True)

	# Page renderer = UI background
	web = ui.create(webrenderTOP, 'webrender')
	web.nodeX, web.nodeY = 0, 250
	set_(web, outputresolution='custom', resolutionw=W, resolutionh=H,
		url="='http://localhost:' + str(parent.UI.par.Port.eval()) + '/'")
	set_(ui, top=web)

	# Mouse forwarding + table watch + pulses
	execFrame = ui.create(executeDAT, 'exec_mouse')
	execFrame.nodeX, execFrame.nodeY = 0, 400
	execFrame.text = EXEC_FRAME
	set_(execFrame, framestart=True)

	watch = ui.create(datexecuteDAT, 'watch_tables')
	watch.nodeX, watch.nodeY = 200, 400
	watch.text = WATCH
	set_(watch, dat='=parent.UI.par.Camtable.eval()', tablechange=True)

	parexec = ui.create(parameterexecuteDAT, 'parexec')
	parexec.nodeX, parexec.nodeY = 400, 400
	parexec.text = PAREXEC
	set_(parexec, op=ui, pars='Rebuild Reloadpage Openwindow', custom=True, builtin=False,
		valuechange=False, onpulse=True)

	# Native program preview (sits in the hole the page leaves for it)
	x, top, w, h = PROGRAM
	program = ui.create(containerCOMP, 'program')
	program.nodeX, program.nodeY = 200, 0
	ext.place(program, x, top, w, h)
	set_(program, top='=parent.UI.OutTop(parent.UI.par.Selector.eval())',
		bgcolorr=0, bgcolorg=0, bgcolorb=0, bgalpha=1)

	# Native camera previews (UIExt.RebuildCams)
	x, top, w, h = CAMS
	cams = ui.create(containerCOMP, 'cams')
	cams.nodeX, cams.nodeY = 400, 0
	ext.place(cams, x, top, w, h)
	set_(cams, bgalpha=0)
	ext.Rebuild()

	win = root.create(windowCOMP, 'UI_window')
	win.nodeX, win.nodeY = ui.nodeX, ui.nodeY - 150
	set_(win, winop=ui, winw=W, winh=H, borders=True)

	print('[BUILD] /project1/UI ready. UI > Open Window')


buildUI()
