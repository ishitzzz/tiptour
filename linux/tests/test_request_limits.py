from tiptour_linux.request_limits import forbidden_plan as f
make=lambda t,**kw:{'steps':[dict(type=t,**kw)]}
assert f('Do not edit the document',make('type',value='x'))
assert f('Do not delete anything',make('pressKey',label='Delete'))
assert f('Put a title in the document, but do not save or send it.',make('keyboardShortcut',label='Ctrl+S'))
assert f('Put a title in the document, but do not save or send it.',make('pressKey',label='Enter'))
assert not f('Put a title in the document, but do not save or send it.',make('type',value='TITLE'))
assert not f('Do not save the document; point to the title',make('observe',label='Title'))
print('PASS standalone no-edit/no-delete and restricted save/send; allowed independent type/observe preserved')

assert f('Put a title here without saving or sending it',make('keyboardShortcut',label='Ctrl+S'))
assert f('Do not edit the document',make('click',label='Clear all'))
assert f('Do not edit the document',make('click',label='Reset'))
print('PASS ordinary gerund save/send restriction and supported clear/reset target labels')
