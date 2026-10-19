"""Local output confirmation. The dialog process cannot mutate simulation/output files."""
import json
from pathlib import Path
import subprocess
import sys
import uuid
import tempfile
import shutil
import plistlib


def key_allowed(*, focused, armed, modifiers):
    # A cell-launch modifier (Shift/Ctrl/Alt/Command) is never agreement.
    return focused and armed and not (modifiers & (1 | 4 | 8 | 16 | 128))


class PressReleaseGate:
    """An ignored press stays ignored until release, regardless of elapsed time."""
    def __init__(self, startup=()):
        self.startup=set(startup)
        self.held=set()

    def press(self, name, *, focused, armed, modifiers):
        fresh=name not in self.held
        self.held.add(name)
        return fresh and name not in self.startup and key_allowed(focused=focused,armed=armed,modifiers=modifiers)

    def release(self, name):
        self.held.discard(name)
        self.startup.discard(name)


def _mac_key_state_reader():
    # Read physical state before mapping a window: the launching key may already
    # be down and its first repeat may arrive only after the focus delay.
    import ctypes
    cg=ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
    cg.CGEventSourceKeyState.argtypes=[ctypes.c_int32,ctypes.c_uint16]
    cg.CGEventSourceKeyState.restype=ctypes.c_bool
    def read():
        return {name for name,codes in [('Return',(36,76)),('Escape',(53,))]
                if any(cg.CGEventSourceKeyState(0,code) for code in codes)}
    return read


def _in_kernel():
    try:
        from IPython import get_ipython
        return getattr(get_ipython(), 'kernel', None) is not None
    except ImportError:
        return False


def _dialog_command(payload):
    script=str(Path(__file__).resolve())
    if sys.platform!='darwin':
        return [sys.executable,'-I',script,json.dumps(payload)],None
    # A temporary bundle gives Conda's CLI interpreter a visible, focusable Mac
    # application identity. It contains only this installed interpreter copy.
    temporary=tempfile.TemporaryDirectory(prefix='fimrun-confirm-')
    try:
        contents=Path(temporary.name)/'FiM Confirmation.app'/'Contents'
        executable=contents/'MacOS'/'confirmation';executable.parent.mkdir(parents=True)
        base=Path(getattr(sys,'_base_executable',sys.executable)).resolve()
        shutil.copy2(base,executable)
        (contents/'pyvenv.cfg').write_text('home = '+str(base.parent)+'\ninclude-system-site-packages = true\nversion = '+sys.version.split()[0]+'\n')
        (contents/'Info.plist').write_bytes(plistlib.dumps(dict(CFBundleName='FiM Confirmation',
            CFBundleDisplayName='FiM 确认覆盖',CFBundleExecutable='confirmation',
            CFBundleIdentifier='org.fimrun.confirmation',CFBundlePackageType='APPL',NSHighResolutionCapable=True)))
        return [str(executable),'-I',script,json.dumps(payload)],temporary
    except BaseException:
        temporary.cleanup();raise


def confirm_overwrite(targets):
    """Ask before locks/config/files change; never interpret GUI failure as consent."""
    paths=[str(p) for p in targets]
    if _in_kernel():
        payload=dict(nonce=uuid.uuid4().hex, paths=paths)
        child=None;temporary=None
        try:
            command,temporary=_dialog_command(payload)
            child=subprocess.Popen(command,
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            out,err=child.communicate()
            if child.returncode==0:
                response=json.loads(out)
                if response.get('nonce')!=payload['nonce'] or type(response.get('accepted')) is not bool:
                    raise ValueError('invalid confirmation response')
                return response['accepted']
            print('确认窗口不可用：下面的输入框不支持Esc；直接Enter覆盖，输入cancel后Enter取消，或中断单元。')
        except (OSError,ValueError) as error:
            print('确认窗口未完成，取消本次覆盖：'+str(error))
            return False
        finally:
            if child is not None:
                if child.poll() is None:
                    child.terminate()
                    try:child.wait(timeout=2)
                    except subprocess.TimeoutExpired:child.kill();child.wait()
                if child.stdout:child.stdout.close()
                if child.stderr:child.stderr.close()
            if temporary is not None:temporary.cleanup()
    else:
        print('已有同名结果：'+Path(paths[0]).stem+'（CSV、OVF、state）')
    try:
        answer=input('Enter覆盖；输入cancel后Enter取消（此输入框不支持Esc）：')
    except EOFError:
        return False
    return answer in ('','OVERWRITE')


def _dialog(payload):
    import tkinter as tk
    from tkinter import ttk
    read_keys=_mac_key_state_reader() if sys.platform=='darwin' else None
    gate=PressReleaseGate(read_keys() if read_keys else ())
    root=tk.Tk()
    if sys.platform=='darwin':
        # Conda's command-line Python has no app bundle. Make this dialog-only
        # child a normal foreground app so the window can receive keyboard focus.
        import ctypes
        objc=ctypes.CDLL('/usr/lib/libobjc.A.dylib')
        objc.objc_getClass.argtypes=[ctypes.c_char_p];objc.objc_getClass.restype=ctypes.c_void_p
        objc.sel_registerName.argtypes=[ctypes.c_char_p];objc.sel_registerName.restype=ctypes.c_void_p
        send=objc.objc_msgSend;send.restype=ctypes.c_void_p
        send.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
        app=send(objc.objc_getClass(b'NSApplication'),objc.sel_registerName(b'sharedApplication'))
        send.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_long]
        send(app,objc.sel_registerName(b'setActivationPolicy:'),0)
        send(app,objc.sel_registerName(b'activateIgnoringOtherApps:'),1)
    root.title('确认覆盖 · 微磁模拟');root.resizable(False,False)
    result={'nonce':payload['nonce'],'accepted':False,'reason':'window_close'}
    armed=False
    def focus_valid():
        return root.focus_displayof() is not None
    def arm():
        nonlocal armed
        armed=focus_valid()
    def focus_in(event):
        if read_keys:gate.startup.update(read_keys())
        root.after(350,arm)
    def focus_out(event):
        nonlocal armed
        armed=False
    def finish(accepted,reason):
        result.update(accepted=accepted,reason=reason);root.destroy()
    def key(event,accepted):
        name='Return' if accepted else 'Escape'
        if gate.press(name,focused=focus_valid(),armed=armed,modifiers=event.state):
            finish(accepted,'enter' if accepted else 'escape')
        return 'break'
    def release(event,name):
        # Ignore synthetic repeat release events while the physical key is down.
        if not read_keys or name not in read_keys():gate.release(name)
        return 'break'
    def startup_release():
        # This clears only the initial physical snapshot. A press already seen
        # by Tk remains latched until its KeyRelease handler runs.
        gate.startup.intersection_update(read_keys())
        root.after(25,startup_release)
    body=ttk.Frame(root,padding=18);body.pack(fill='both',expand=True)
    ttk.Label(body,text='已有同名结果，是否覆盖？',font=('',16)).pack(anchor='w')
    ttk.Label(body,text=Path(payload['paths'][0]).stem+'（CSV、OVF、state）').pack(anchor='w',pady=(8,12))
    details=ttk.Frame(body)
    def toggle():
        if details.winfo_ismapped():details.pack_forget();disclosure.configure(text='▸ 文件明细')
        else:details.pack(fill='x',before=actions,pady=8);disclosure.configure(text='▾ 文件明细')
    disclosure=ttk.Button(body,text='▸ 文件明细',command=toggle);disclosure.pack(anchor='w')
    for path in payload['paths']:ttk.Label(details,text=path,wraplength=640).pack(anchor='w',pady=2)
    actions=ttk.Frame(body);actions.pack(fill='x',pady=(16,0))
    ttk.Button(actions,text='覆盖（Enter）',command=lambda:finish(True,'button')).pack(side='left',padx=(0,12))
    cancel=ttk.Button(actions,text='取消（Esc）',command=lambda:finish(False,'button'));cancel.pack(side='left')
    root.protocol('WM_DELETE_WINDOW',lambda:finish(False,'window_close'))
    root.bind('<Return>',lambda e:key(e,True));root.bind('<Escape>',lambda e:key(e,False))
    root.bind('<KP_Enter>',lambda e:key(e,True))
    root.bind('<KeyRelease-Return>',lambda e:release(e,'Return'))
    root.bind('<KeyRelease-KP_Enter>',lambda e:release(e,'Return'))
    root.bind('<KeyRelease-Escape>',lambda e:release(e,'Escape'))
    root.bind('<FocusIn>',focus_in);root.bind('<FocusOut>',focus_out)
    root.update_idletasks();root.lift();cancel.focus_force();root.after(350,arm)
    if read_keys:root.after(25,startup_release)
    root.mainloop()
    return result


if __name__=='__main__':
    try:
        answer=_dialog(json.loads(sys.argv[1]))
        print(json.dumps(answer),flush=True)
    except Exception as error:
        print('Confirmation UI unavailable: '+str(error),file=sys.stderr)
        sys.exit(2)
