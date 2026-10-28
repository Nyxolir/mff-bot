"""Small input surface for recognized board and ticket-sweep controls."""
from lib.resource_check import click_game_point


def scroll_board(parent,direction="down",clicks=3):
    click_game_point(parent,1000,500,scroll=(direction,clicks))


def execute_sweep_control(parent,evidence,control,guard=None):
    expected="sweep_result" if control=="close_result" else "sweep"
    if evidence.screen!=expected or evidence.errors:raise ValueError("Sweep screen is not verified")
    if control not in ("close_result","close_sweep","select_max","clear_batch","increment","decrement"):
        raise ValueError("Unknown sweep control")
    values=evidence.values
    if control=="clear_batch" and not values.get("sweep_verified"):
        raise ValueError("Ticket clear control not verified")
    if control=="clear_batch" and guard is None:raise ValueError("Fresh running/reset authorization is required")
    if control=="close_result" and not values.get("result_verified"):
        raise ValueError("Clear result not verified")
    point=values.get("controls",{}).get(control)
    if not point or len(point)!=2:raise ValueError("Sweep control position unreadable")
    # Reader emits only configured current-game controls. No fallback to the
    # archived coordinate driver is allowed.
    from lib.sweep_reader import CONTROL_POINTS
    if tuple(point) not in CONTROL_POINTS.get(control,set()):
        raise ValueError("Sweep control position has not been validated")
    click_game_point(parent,int(point[0]),int(point[1]),guard=guard)
