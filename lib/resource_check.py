"""Navigation-only resource inspection. No mission-start action is defined."""
from dataclasses import dataclass
from datetime import timedelta


class InputNotSent(RuntimeError):
    """The input was rejected before sending any click."""


@dataclass(frozen=True)
class Navigation:
    name: str
    x: int
    y: int
    expected: tuple


def next_navigation(evidence, have_soul=False):
    if evidence.errors and not (evidence.screen=="gbr_main" and "soul" in evidence.values):return None
    screen=evidence.screen
    if screen=="navigation_menu":return Navigation("Select Mission",491,642,("select_mission","select_mission_coop"))
    if screen=="select_mission":return Navigation("Co-op tab",1080,135,("select_mission_coop",))
    if screen=="select_mission_coop":return Navigation("Giant Boss Raid",174,376,("gbr_main","gbr_selection"))
    if screen=="gbr_selection":return Navigation("Select Onslaught",1060,490,("gbr_main",))
    if screen=="gbr_main" and evidence.values.get("reward_strip_verified"):
        return Navigation("Scroll rewards right" if have_soul else "Scroll rewards left",500 if have_soul else 80,658,("gbr_main",))
    if screen=="gbr_main":return Navigation("Rewards Available",164,589,("gbr_rewards",))
    if screen=="gbr_rewards" and not have_soul:return Navigation("Close rewards to read Soul",640,648,("gbr_main",))
    if screen in ('world_event','timeline','otherworld','game_home'):
        return Navigation('Open Menu',1249,36,('navigation_menu',))
    if screen!="gbr_rewards" and evidence.values.get("menu_available"):
        return Navigation("Open Menu",1249,36,("navigation_menu",))
    return None


def perform_navigation(parent, navigation):
    """App-owned navigation only; no legacy game/battle controller is loaded."""
    allowed={("Select Mission",491,642),("Co-op tab",1080,135),
        ("Giant Boss Raid",174,376),("Select Onslaught",1060,490),
        ("Rewards Available",164,589),("Close rewards to read Soul",640,648),
        ("Open Menu",1249,36),("Status Board",630,642)}
    if navigation.name in ("Scroll rewards right","Scroll rewards left"):
        expected=(500,658) if navigation.name=="Scroll rewards right" else (80,658)
        if (navigation.x,navigation.y)!=expected:raise ValueError("Invalid reward strip swipe")
        click_game_point(parent,*expected,drag_to=(80,658) if expected[0]==500 else (500,658))
        return
    if (navigation.name,navigation.x,navigation.y) not in allowed:
        raise ValueError("Action is not part of the resource-inspection route")
    click_game_point(parent,navigation.x,navigation.y)


def click_game_point(parent,game_x,game_y,scroll=None,guard=None,drag_to=None,key=None):
    """Validated controller callers only; coordinates use the 1280x720 viewport."""
    if not (type(game_x) is int and type(game_y) is int and 0<=game_x<1280 and 0<=game_y<720):
        raise ValueError("Invalid game point")
    if guard is not None and not guard():raise InputNotSent("Queue stopped or authorization expired before input")
    from lib.background_input import configured_backend
    background=configured_backend()
    if background is not None:
        background.send(game_x,game_y,scroll=scroll,drag_to=drag_to,key=key,guard=guard)
        return
    import win32gui
    import win32con
    import win32process
    import win32api
    import autoit
    children=[]
    observed=[]
    def visit(handle,unused):
        title=win32gui.GetWindowText(handle)
        klass=win32gui.GetClassName(handle)
        rect=win32gui.GetClientRect(handle)
        observed.append((title,klass,rect[2:]))
        if "plrNativeInputWindow" in title or "plrNativeInputWindow" in klass or klass=="BlueStacksApp":
            # Current 5.22 render surface has a 1-pixel frame; the screenshot
            # viewport stays 1280x720. Accept only the two observed layouts.
            if rect[2:] in ((1280,720),(1278,719)):children.append((handle,rect[2:]))
    win32gui.EnumChildWindows(parent,visit,None)
    if len(children)!=1:raise RuntimeError("Cannot identify BlueStacks input surface: "+repr(observed))
    child,(width,height)=children[0]
    x=round(game_x*width/1280)
    y=round(game_y*height/720)
    # Current BlueStacks ignores posted/background mouse messages. Activate
    # its window and verify ownership of the physical click point first.
    previous=win32gui.GetForegroundWindow()
    autoit.win_activate_by_handle(parent)
    if win32gui.GetForegroundWindow()!=parent:
        current_thread=win32api.GetCurrentThreadId()
        foreground_thread=win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())[0]
        attached=False
        try:
            if current_thread!=foreground_thread:
                win32process.AttachThreadInput(current_thread,foreground_thread,True)
                attached=True
            win32gui.SetForegroundWindow(parent)
        finally:
            if attached:win32process.AttachThreadInput(current_thread,foreground_thread,False)
    autoit.win_wait_active_by_handle(parent,timeout=2)
    point=win32gui.ClientToScreen(child,(x,y))
    owner=win32gui.WindowFromPoint(point)
    if win32gui.GetAncestor(owner,win32con.GA_ROOT)!=parent:
        raise RuntimeError(f"BlueStacks is not under navigation point {point}; blocked by {win32gui.GetWindowText(win32gui.GetAncestor(owner,win32con.GA_ROOT))!r}; stopped without clicking")
    try:
        if guard is not None and not guard():raise InputNotSent("Reset or Stop occurred while activating the game; no input sent")
        if key is not None:
            if key!="back":raise ValueError("Unsupported navigation key")
            autoit.send("{ESC}")
        elif drag_to is not None:
            if (game_x,game_y,drag_to) not in ((500,658,(80,658)),(80,658,(500,658)),(1030,318,(220,318)),(220,318,(1030,318))):
                raise ValueError("Unsupported reward strip swipe")
            import time
            end=win32gui.ClientToScreen(child,(round(drag_to[0]*width/1280),round(drag_to[1]*height/720)))
            autoit.mouse_move(*point,speed=0)
            time.sleep(.12)
            autoit.mouse_down("left")
            try:
                time.sleep(.15)
                for step in range(1,31):
                    autoit.mouse_move(round(point[0]+(end[0]-point[0])*step/30),point[1],speed=0)
                    time.sleep(.015)
                time.sleep(.12)
            finally:autoit.mouse_up("left")
        elif scroll:
            direction,clicks=scroll
            if direction not in ("up","down") or type(clicks) is not int or not 1<=clicks<=8:
                raise ValueError("Unsupported board scroll")
            autoit.mouse_move(point[0],point[1],speed=0)
            autoit.mouse_wheel(direction,clicks=clicks)
            import time
            time.sleep(.3)
        else:
            autoit.mouse_click("left",x=point[0],y=point[1],clicks=1,speed=0)
            # Give the emulator time to consume input before restoring the GUI.
            import time
            time.sleep(.3)
    finally:
        if previous and win32gui.IsWindow(previous):
            try:win32gui.SetForegroundWindow(previous)
            except Exception:pass


def resource_status(counters, balances, now, gate=None):
    from lib.daily_queue import reset_period
    cleared=bool(gate and gate.cleared(now))
    valid={key:value[0] for key,value in counters.items()
           if reset_period(value[1])==reset_period(now) and
           timedelta(0)<=now-value[1]<=timedelta(minutes=10)}
    if cleared:valid={key:value[0] for key,value in gate.counters.items() if reset_period(value[1])==reset_period(now)}
    missing=[key for key in ("soul","seed") if key not in valid]
    if missing:return "blocked: missing fresh GBR " + ", ".join(missing)
    soul,seed=valid["soul"],valid["seed"]
    if soul[1]!=165 or seed[1]!=300:return "blocked: unexpected GBR daily limits"
    if soul[0]!=0 or seed[0]!=0:
        return f"blocked: GBR incomplete — Soul {soul[0]}/165, Seed {seed[0]}/300"
    if not balances or not timedelta(0)<=now-balances[1]<=timedelta(minutes=10):
        return "GBR complete — boost points need a fresh mission check"
    values=balances[0]
    if "boost" not in values:return "GBR complete — boost unreadable; refresh at mission preparation"
    return f"GBR complete — boost {values['boost']}; mission boost cost check still needed"
